"""amazon.com: no structured data; parse the price block, availability and size swatches from HTML."""
import re
from typing import Optional

from .base import Extractor, ProductInfo, soup_of, meta
from ..prices import parse_price

PRICE_SELECTORS = [
    "#corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen",
    "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
    "#corePrice_feature_div .a-price .a-offscreen",
    "#apex_desktop .priceToPay .a-offscreen",
    "#apex_desktop .a-price .a-offscreen",
    "#priceblock_dealprice", "#priceblock_saleprice", "#priceblock_ourprice",
    "#price_inside_buybox", "#newBuyBoxPrice",
]
ORIG_SELECTORS = [".basisPrice .a-offscreen", "span.a-price[data-a-strike='true'] .a-offscreen",
                  "#listPrice", "#priceblock_ourprice_lbl + span .a-text-strike", ".a-text-price .a-offscreen"]


class AmazonExtractor(Extractor):
    store = "amazon"
    domains = ("amazon.com", "amazon.co.uk", "amazon.ca", "amazon.de", "amazon.fr", "amazon.it", "amazon.es",
               "amazon.co.jp", "amazon.com.au")

    def extract(self, html: str, url: str) -> Optional[ProductInfo]:
        soup = soup_of(html)
        if soup.select_one("form[action*='validateCaptcha']"):
            return None  # bot check page; let the browser fallback try
        info = ProductInfo(url=url, store=self.store, source="amazon-html")
        t = soup.select_one("#productTitle")
        info.name = t.get_text(strip=True) if t else meta(soup, "og:title")
        for sel in PRICE_SELECTORS:
            el = soup.select_one(sel)
            txt = el.get_text(" ", strip=True) if el else ""
            if txt:
                info.price, info.currency = parse_price(txt)
                if info.price is not None:
                    break
        for sel in ORIG_SELECTORS:
            el = soup.select_one(sel)
            txt = el.get_text(" ", strip=True) if el else ""
            if txt:
                orig, _ = parse_price(txt, info.currency)
                if orig and info.price and orig > info.price:
                    info.original_price = orig
                    break
        img = soup.select_one("#landingImage") or soup.select_one("#imgTagWrapperId img")
        if img:
            info.image_url = img.get("data-old-hires") or img.get("src")
        avail = soup.select_one("#availability")
        if avail:
            a = avail.get_text(" ", strip=True).lower()
            info.in_stock = not any(k in a for k in ("unavailable", "out of stock", "not available"))
        sizes = {}
        for li in soup.select("#inline-twister-expander-content-size_name li, #variation_size_name li"):
            label = li.get_text(" ", strip=True)
            label = re.sub(r"\s*(unavailable|currently unavailable|out of stock).*$", "", label, flags=re.I).strip()
            if not label or len(label) > 24:
                continue
            classes = " ".join(li.get("class", [])) + " " + " ".join(c for e in li.find_all(True) for c in e.get("class", []))
            unavailable = "navailable" in classes.lower() or bool(re.search(r"unavailable|out of stock", li.get_text(" "), re.I))
            sizes[label] = not unavailable
        for opt in soup.select("#native_dropdown_selected_size_name option"):
            if opt.get("value") in (None, "-1", ""):
                continue
            label = opt.get_text(" ", strip=True)
            unavailable = "navailable" in " ".join(opt.get("class", [])).lower() or "unavailable" in label.lower()
            sizes[re.sub(r"\s*-\s*unavailable.*$", "", label, flags=re.I)] = not unavailable
        info.sizes = sizes
        if sizes and info.in_stock is None:
            info.in_stock = any(sizes.values())
        return info
