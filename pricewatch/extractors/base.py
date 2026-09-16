"""Shared extraction helpers and the generic (any-site) extractor."""
import json
import re
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..prices import parse_price, parse_amount, detect_currency


@dataclass
class ProductInfo:
    url: str
    store: str
    name: Optional[str] = None
    image_url: Optional[str] = None
    price: Optional[float] = None            # what you'd pay right now
    original_price: Optional[float] = None   # struck-through price if on sale
    currency: Optional[str] = None
    in_stock: Optional[bool] = None          # overall availability
    sizes: Dict[str, bool] = field(default_factory=dict)  # size label -> in stock
    source: str = ""                         # which strategy produced the data

    def ok(self) -> bool:
        return self.price is not None


SIZE_ALIASES = {
    "xxs": "xxs", "xx-small": "xxs", "extra extra small": "xxs",
    "xs": "xs", "x-small": "xs", "extra small": "xs",
    "s": "s", "small": "s", "sm": "s",
    "m": "m", "medium": "m", "med": "m",
    "l": "l", "large": "l", "lg": "l",
    "xl": "xl", "x-large": "xl", "extra large": "xl",
    "xxl": "xxl", "xx-large": "xxl", "2xl": "xxl", "2x-large": "xxl",
    "xxxl": "xxxl", "3xl": "xxxl", "3x-large": "xxxl",
}


def norm_size(label: str) -> str:
    s = re.sub(r"\s+", " ", str(label).strip().lower())
    s = re.sub(r"^(us|uk|eu|size)\s+", "", s)
    return SIZE_ALIASES.get(s, s)


def stock_for_size(info: ProductInfo, size: Optional[str]):
    """Return (in_stock, matched) for the requested size, falling back to overall stock."""
    if not size or not info.sizes:
        return info.in_stock, False
    want = norm_size(size)
    for label, avail in info.sizes.items():
        if norm_size(label) == want:
            return bool(avail), True
    # size not listed at all -> treat as unavailable (sold-out sizes often vanish from the list)
    return False, False


# --- HTML helpers -----------------------------------------------------------

def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def json_ld_blocks(soup: BeautifulSoup) -> List[dict]:
    out = []
    for tag in soup.find_all("script", type=re.compile(r"application/ld\+json", re.I)):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (ValueError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and "@graph" in item:
                out.extend(x for x in item["@graph"] if isinstance(x, dict))
            elif isinstance(item, dict):
                out.append(item)
    return out


def _is_type(obj: dict, name: str) -> bool:
    t = obj.get("@type")
    return t == name or (isinstance(t, list) and name in t)


def script_json(soup: BeautifulSoup, script_id: str) -> Optional[dict]:
    tag = soup.find("script", id=script_id)
    if not tag:
        return None
    try:
        return json.loads(tag.string or tag.get_text())
    except (ValueError, TypeError):
        return None


def walk(obj) -> Iterator[dict]:
    """Yield every dict nested anywhere inside obj."""
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            yield cur
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)


def meta(soup: BeautifulSoup, *names: str) -> Optional[str]:
    for n in names:
        tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n}) \
            or soup.find("meta", attrs={"itemprop": n})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _availability(value) -> Optional[bool]:
    if value is None:
        return None
    v = str(value).lower()
    if any(k in v for k in ("instock", "in_stock", "limitedavailability", "onlineonly", "preorder", "backorder")):
        return True
    if any(k in v for k in ("outofstock", "out_of_stock", "soldout", "discontinued")):
        return False
    return None


def _offer_price(offer: dict):
    cur = offer.get("priceCurrency")
    spec = offer.get("priceSpecification")
    if isinstance(spec, list):
        spec = spec[0] if spec else None
    if isinstance(spec, dict):
        cur = cur or spec.get("priceCurrency")
        if offer.get("price") is None:
            offer = {**offer, "price": spec.get("price")}
    raw = offer.get("price", offer.get("lowPrice"))
    amount, cur2 = parse_price(raw, cur)
    return amount, cur2


def product_from_json_ld(blocks: List[dict], url: str, store: str) -> Optional[ProductInfo]:
    for obj in blocks:
        if not (_is_type(obj, "Product") or _is_type(obj, "ProductGroup")):
            continue
        info = ProductInfo(url=url, store=store, source="json-ld")
        info.name = obj.get("name")
        img = obj.get("image")
        if isinstance(img, list):
            img = img[0] if img else None
        if isinstance(img, dict):
            img = img.get("url") or img.get("contentUrl")
        info.image_url = img
        offers = obj.get("offers")
        offers = offers if isinstance(offers, list) else ([offers] if offers else [])
        variants = obj.get("hasVariant") or []
        prices, avail = [], []
        for off in offers:
            if not isinstance(off, dict):
                continue
            if _is_type(off, "AggregateOffer"):
                amount, cur = parse_price(off.get("lowPrice") or off.get("price"), off.get("priceCurrency"))
            else:
                amount, cur = _offer_price(off)
            if amount is not None:
                prices.append(amount); info.currency = info.currency or cur
            a = _availability(off.get("availability"))
            if a is not None:
                avail.append(a)
        for v in variants:
            if not isinstance(v, dict):
                continue
            voff = v.get("offers")
            voff = voff[0] if isinstance(voff, list) and voff else voff
            if not isinstance(voff, dict):
                continue
            amount, cur = _offer_price(voff)
            a = _availability(voff.get("availability"))
            if amount is not None:
                prices.append(amount); info.currency = info.currency or cur
            if a is not None:
                avail.append(a)
            size = v.get("size")
            if size and a is not None:
                info.sizes[str(size)] = a
            if not info.image_url and v.get("image"):
                info.image_url = v["image"] if isinstance(v["image"], str) else None
        if prices:
            info.price = min(prices)
        if avail:
            info.in_stock = any(avail)
        if info.ok() or info.name:
            return info
    return None


def product_from_meta(soup: BeautifulSoup, url: str, store: str) -> Optional[ProductInfo]:
    raw = meta(soup, "product:price:amount", "og:price:amount", "product:sale_price:amount", "price")
    if raw is None:
        tag = soup.find(attrs={"itemprop": "price"})
        raw = (tag.get("content") or tag.get_text()) if tag else None
    if raw is None:
        return None
    cur = meta(soup, "product:price:currency", "og:price:currency", "priceCurrency")
    if cur is None:
        tag = soup.find(attrs={"itemprop": "priceCurrency"})
        cur = tag.get("content") if tag else None
    amount, cur = parse_price(raw, cur)
    info = ProductInfo(url=url, store=store, source="og-meta", price=amount, currency=cur)
    info.name = meta(soup, "og:title", "twitter:title") or (soup.title.get_text(strip=True) if soup.title else None)
    info.image_url = meta(soup, "og:image", "twitter:image")
    info.in_stock = _availability(meta(soup, "product:availability", "og:availability"))
    return info if info.ok() else None


PRICE_KEYS = ("currentPrice", "salePrice", "sale_price", "finalPrice", "final_price", "price", "lowPrice")
ORIG_KEYS = ("initialPrice", "fullPrice", "originalPrice", "original_price", "listPrice", "list_price",
             "regularPrice", "regular_price", "wasPrice", "compareAtPrice", "compare_at_price", "reference_price")


def product_from_embedded_json(soup: BeautifulSoup, url: str, store: str) -> Optional[ProductInfo]:
    """Last resort: look inside __NEXT_DATA__ / __NUXT__ / inline JSON for a product-ish dict."""
    candidates = []
    for tag in soup.find_all("script"):
        txt = tag.string or ""
        if not txt or len(txt) < 50:
            continue
        if tag.get("id") in ("__NEXT_DATA__", "__NUXT_DATA__") or tag.get("type") == "application/json":
            try:
                candidates.append(json.loads(txt))
            except ValueError:
                pass
        else:
            for m in re.finditer(r"(?:window\.__[A-Z_]+__|__PRELOADED_STATE__|__INITIAL_STATE__)\s*=\s*(\{.*?\})\s*;?\s*(?:</script>|\n)", txt, re.S):
                try:
                    candidates.append(json.loads(m.group(1)))
                except ValueError:
                    pass
    best = None
    for root in candidates:
        for d in walk(root):
            if not any(k in d for k in PRICE_KEYS):
                continue
            name = d.get("name") or d.get("title") or d.get("productName")
            if not isinstance(name, str):
                continue
            price = None
            for k in PRICE_KEYS:
                if k in d and isinstance(d[k], (int, float, str)):
                    price = parse_amount(d[k]); break
            if price is None:
                continue
            info = ProductInfo(url=url, store=store, source="embedded-json", name=name, price=price)
            for k in ORIG_KEYS:
                if k in d and isinstance(d[k], (int, float, str)):
                    info.original_price = parse_amount(d[k]); break
            cur = d.get("currency") or d.get("currencyCode") or d.get("priceCurrency")
            info.currency = cur if isinstance(cur, str) and len(cur) == 3 else None
            img = d.get("image") or d.get("imageUrl") or d.get("image_url")
            info.image_url = img if isinstance(img, str) else None
            info.in_stock = _availability(d.get("availability") or d.get("stockStatus")) \
                if (d.get("availability") or d.get("stockStatus")) else (bool(d["inStock"]) if "inStock" in d else None)
            best = info
            break
        if best:
            break
    return best


class Extractor:
    store = "generic"
    domains = ()            # e.g. ("nike.com",)
    needs_browser = False   # True -> skip plain HTTP, go straight to Playwright
    wait_for = None         # CSS selector to wait for when using Playwright
    wait_ms = 2500          # settle time after DOM load when using Playwright
    uses_api = False        # True -> call from_api() instead of fetching HTML

    def from_api(self, url: str, fetcher) -> Optional[ProductInfo]:
        raise NotImplementedError

    @classmethod
    def matches(cls, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(host == d or host.endswith("." + d) for d in cls.domains)

    def extract(self, html: str, url: str) -> Optional[ProductInfo]:
        return self.generic(html, url)

    def generic(self, html: str, url: str) -> Optional[ProductInfo]:
        soup = soup_of(html)
        store = self.store if self.store != "generic" else store_from_url(url)
        info = product_from_json_ld(json_ld_blocks(soup), url, store)
        if info and info.ok():
            self._fill_from_meta(info, soup)
            return info
        m = product_from_meta(soup, url, store)
        if m and m.ok():
            return m
        e = product_from_embedded_json(soup, url, store)
        if e and e.ok():
            return e
        return info  # may have a name but no price -> caller decides


    @staticmethod
    def _fill_from_meta(info: ProductInfo, soup: BeautifulSoup):
        if not info.image_url:
            info.image_url = meta(soup, "og:image")
        if not info.name:
            info.name = meta(soup, "og:title")
        if not info.currency:
            info.currency = meta(soup, "product:price:currency", "og:price:currency")


def store_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    host = re.sub(r"^(www|shop|store|m)\.", "", host)
    return host.split(".")[0]
