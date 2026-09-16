"""endclothing.com: JSON-LD offer + __NEXT_DATA__ product with per-size in_stock and reference_price."""
from typing import Optional

from .base import Extractor, ProductInfo, soup_of, json_ld_blocks, product_from_json_ld, script_json, walk
from ..prices import parse_amount


class EndClothingExtractor(Extractor):
    store = "end"
    domains = ("endclothing.com",)

    def extract(self, html: str, url: str) -> Optional[ProductInfo]:
        soup = soup_of(html)
        info = product_from_json_ld(json_ld_blocks(soup), url, self.store) or ProductInfo(url=url, store=self.store)
        data = script_json(soup, "__NEXT_DATA__")
        product = None
        if data:
            for d in walk(data):
                if "sku" in d and "options" in d and "price" in d and "in_stock" in d:
                    product = d
                    break
        if product:
            info.source = "next-data"
            info.name = info.name or product.get("name")
            price = parse_amount(product.get("price"))
            if price is not None:
                info.price = price
            ref = parse_amount(product.get("reference_price"))
            if ref and info.price and ref > info.price:
                info.original_price = ref
            info.in_stock = bool(product.get("in_stock", info.in_stock))
            for opt in product.get("options") or []:
                if str(opt.get("label", "")).lower() == "size":
                    info.sizes = {v["label"]: bool(v.get("in_stock")) and v.get("enabled", True)
                                  for v in opt.get("values", []) if v.get("label")}
            if not info.image_url:
                gallery = product.get("media_gallery_entries") or []
                if gallery and isinstance(gallery[0], dict):
                    info.image_url = gallery[0].get("file")
        self._fill_from_meta(info, soup)
        return info
