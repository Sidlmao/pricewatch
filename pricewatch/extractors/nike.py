"""nike.com: JSON-LD ProductGroup with per-size variants + __NEXT_DATA__ prices/sizes."""
from typing import Optional

from .base import Extractor, ProductInfo, soup_of, json_ld_blocks, product_from_json_ld, script_json, walk


class NikeExtractor(Extractor):
    store = "nike"
    domains = ("nike.com",)

    def extract(self, html: str, url: str) -> Optional[ProductInfo]:
        soup = soup_of(html)
        info = product_from_json_ld(json_ld_blocks(soup), url, self.store) or ProductInfo(url=url, store=self.store)
        data = script_json(soup, "__NEXT_DATA__")
        if data:
            for d in walk(data):
                prices = d.get("prices")
                if isinstance(prices, dict) and "currentPrice" in prices:
                    info.price = float(prices["currentPrice"])
                    init = prices.get("initialPrice")
                    if init and float(init) > info.price:
                        info.original_price = float(init)
                    info.currency = prices.get("currency") or info.currency
                    info.source = "next-data"
                    sizes = d.get("sizes")
                    if isinstance(sizes, list):
                        info.sizes = {s.get("localizedLabel") or s.get("label"): s.get("status") == "ACTIVE"
                                      for s in sizes if isinstance(s, dict) and (s.get("label") or s.get("localizedLabel"))}
                        if info.sizes:
                            info.in_stock = any(info.sizes.values())
                    if not info.name:
                        info.name = d.get("fullTitle") or d.get("title")
                    if not info.image_url:
                        img = d.get("images") or {}
                        info.image_url = img.get("squarishURL") or img.get("portraitURL") if isinstance(img, dict) else None
                    break
        # Nike JSON-LD variants list every size but no availability; keep the price and name from it.
        self._fill_from_meta(info, soup)
        return info
