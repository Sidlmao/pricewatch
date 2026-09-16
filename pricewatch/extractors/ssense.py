"""ssense.com: JSON-LD Product (browser only) + a size <select> whose options say 'XL - Sold Out'."""
import re
from typing import Optional

from .base import Extractor, ProductInfo, soup_of


class SsenseExtractor(Extractor):
    store = "ssense"
    domains = ("ssense.com",)
    needs_browser = True
    wait_ms = 5000

    def extract(self, html: str, url: str) -> Optional[ProductInfo]:
        info = self.generic(html, url)
        if not info:
            return None
        soup = soup_of(html)
        sizes = {}
        # Only the size dropdown: its id/name/class mentions "size" or its placeholder says "select a size".
        selects = [sel for sel in soup.find_all("select")
                   if "size" in " ".join(str(v) for v in sel.attrs.values()).lower()
                   or (sel.option and "size" in sel.option.get_text(" ", strip=True).lower())]
        for opt in (o for sel in selects[:1] for o in sel.find_all("option")):
            text = opt.get_text(" ", strip=True)
            if not text or "select" in text.lower():
                continue
            sold_out = bool(re.search(r"sold\s*out", text, re.I)) or opt.get("disabled") is not None
            text = re.sub(r"\s*-\s*sold\s*out\s*$", "", text, flags=re.I)
            # "XS-S =  XS" -> label "XS"; plain "40" stays "40"
            label = text.split("=")[-1].strip() if "=" in text else text
            if len(label) <= 12 and not any(c in label for c in ",."):
                sizes[label] = not sold_out
        if sizes:
            info.sizes = sizes
            info.in_stock = any(sizes.values())
        if info.image_url and "__IMAGE_PARAMS__" in info.image_url:
            info.image_url = info.image_url.replace("__IMAGE_PARAMS__", "b_white,c_lpad,g_center,h_960,q_80,w_720")
        return info
