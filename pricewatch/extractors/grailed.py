"""grailed.com: listing pages sit behind a Cloudflare challenge, but /api/listings/<id> is open."""
import re
from typing import Optional

from .base import Extractor, ProductInfo


class GrailedExtractor(Extractor):
    store = "grailed"
    domains = ("grailed.com",)
    uses_api = True
    needs_browser = True

    def from_api(self, url: str, fetcher) -> Optional[ProductInfo]:
        m = re.search(r"/listings/(\d+)", url)
        if not m:
            return None
        d = fetcher.get_json(f"https://www.grailed.com/api/listings/{m.group(1)}", referer=url)
        d = d.get("data", d)
        if not isinstance(d, dict) or "price" not in d:
            return None
        info = ProductInfo(url=url, store=self.store, source="grailed-api")
        designer = d.get("designer_names") or ""
        info.name = f"{designer} {d.get('title', '')}".strip()
        info.price = float(d["price"])
        info.currency = "USD"
        drops = d.get("price_drops") or []
        if drops:
            try:
                first = float(drops[0] if not isinstance(drops[0], dict) else drops[0].get("price"))
                if first > info.price:
                    info.original_price = first
            except (TypeError, ValueError):
                pass
        photos = d.get("photos") or []
        info.image_url = photos[0].get("url") if photos and isinstance(photos[0], dict) else None
        available = not (d.get("sold") or d.get("deleted") or d.get("expired") or d.get("hidden"))
        info.in_stock = available
        # raw size is "m"; pretty_size is "US M / EU 48-50 / 2". Keep both so either matches.
        for size in {str(d.get("size") or "").upper(), str(d.get("pretty_size") or "")} - {""}:
            info.sizes[size] = available
        return info
