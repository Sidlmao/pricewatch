"""uniqlo.com: the HTML is bot-walled, but the public JSON API behind the product page is open.

URL shapes:  https://www.uniqlo.com/us/en/products/E471808-000/00?colorDisplayCode=03&sizeDisplayCode=004
"""
import re
from typing import Optional
from urllib.parse import urlparse, parse_qs

from .base import Extractor, ProductInfo

_PATH = re.compile(r"^/(?P<country>[a-z]{2})/(?P<lang>[a-z]{2})/products/(?P<pid>E\d+-\d{3})(?:/(?P<pg>\d{2}))?", re.I)


class UniqloExtractor(Extractor):
    store = "uniqlo"
    domains = ("uniqlo.com",)
    uses_api = True
    needs_browser = True   # never bother with plain HTML; browser fallback is a last resort

    def from_api(self, url: str, fetcher) -> Optional[ProductInfo]:
        u = urlparse(url)
        m = _PATH.match(u.path)
        if not m:
            return None
        country, lang, pid, pg = m.group("country"), m.group("lang"), m.group("pid"), m.group("pg") or "00"
        q = parse_qs(u.query)
        color = (q.get("colorDisplayCode") or [None])[0]
        base = f"https://www.uniqlo.com/{country}/api/commerce/v5/{lang}/products/{pid}/price-groups/{pg}"
        detail = fetcher.get_json(f"{base}/details?includeModelSize=false&httpFailure=true", referer=url).get("result", {})
        l2s = fetcher.get_json(f"{base}/l2s?withPrices=true&withStocks=true&httpFailure=true", referer=url).get("result", {})

        info = ProductInfo(url=url, store=self.store, source="uniqlo-api", name=detail.get("name"))
        size_names = {s.get("code"): s.get("name") for s in detail.get("sizes", []) if s.get("code")}
        images = detail.get("images", {}).get("main", {})
        img = images.get(color) if color else None
        if not img and images:
            img = next(iter(images.values()))
        info.image_url = img.get("image") if isinstance(img, dict) else None

        prices, stocks = l2s.get("prices", {}), l2s.get("stocks", {})
        sizes, pay, base_prices = {}, [], []
        for v in l2s.get("l2s", []):
            if color and v.get("color", {}).get("displayCode") != color:
                continue
            l2id = v.get("l2Id")
            p = prices.get(l2id) or {}
            base_p = (p.get("base") or {}).get("value")
            promo = (p.get("promo") or {}).get("value")
            current = promo if promo is not None else base_p
            if current is not None:
                pay.append(float(current)); base_prices.append(float(base_p or current))
                info.currency = info.currency or ((p.get("base") or {}).get("currency") or {}).get("code")
            label = size_names.get(v.get("size", {}).get("code")) or v.get("size", {}).get("displayCode")
            st = (stocks.get(l2id) or {}).get("statusCode", "")
            in_stock = st == "IN_STOCK" or (stocks.get(l2id) or {}).get("quantity", 0) > 0
            if label:
                sizes[label] = sizes.get(label, False) or in_stock
        if pay:
            info.price = min(pay)
            orig = min(base_prices)
            if orig > info.price:
                info.original_price = orig
        info.sizes = sizes
        info.in_stock = any(sizes.values()) if sizes else None
        return info
