"""Extractor registry + the top-level scrape() function."""
import logging
from typing import Optional

from ..fetch import Fetcher, FetchError, RobotsDisallowed
from .base import Extractor, ProductInfo, stock_for_size, store_from_url
from .nike import NikeExtractor
from .endclothing import EndClothingExtractor
from .zara import ZaraExtractor
from .uniqlo import UniqloExtractor
from .ssense import SsenseExtractor
from .grailed import GrailedExtractor
from .amazon import AmazonExtractor

log = logging.getLogger("pricewatch.scrape")

EXTRACTORS = [NikeExtractor, EndClothingExtractor, ZaraExtractor, UniqloExtractor, SsenseExtractor, GrailedExtractor, AmazonExtractor]


class ScrapeError(Exception):
    pass


def pick_extractor(url: str) -> Extractor:
    for cls in EXTRACTORS:
        if cls.matches(url):
            return cls()
    return Extractor()


def scrape(url: str, fetcher: Optional[Fetcher] = None, use_browser: Optional[bool] = None) -> ProductInfo:
    """Fetch and extract a product. Tries plain HTTP + structured data first, then Playwright."""
    own = fetcher is None
    fetcher = fetcher or Fetcher()
    ex = pick_extractor(url)
    info, errors = None, []
    try:
        if ex.uses_api:
            try:
                info = ex.from_api(url, fetcher)
                if info and info.ok():
                    return info
                errors.append("api: no price")
            except RobotsDisallowed:
                raise
            except FetchError as e:
                errors.append(f"api: {e}")
        if use_browser is not True and not ex.needs_browser:
            try:
                html = fetcher.get(url)
                info = ex.extract(html, url)
                if info and info.ok():
                    return info
                errors.append("no price in plain HTML")
            except RobotsDisallowed:
                raise
            except FetchError as e:
                errors.append(f"http: {e}")
        if use_browser is not False:
            try:
                html = fetcher.get_rendered(url, wait_ms=ex.wait_ms, wait_for=ex.wait_for)
                info2 = ex.extract(html, url) or Extractor().extract(html, url)
                if info2 and info2.ok():
                    info2.source = "browser/" + (info2.source or "?")
                    return info2
                errors.append("no price in rendered HTML")
            except RobotsDisallowed:
                raise
            except FetchError as e:
                errors.append(f"browser: {e}")
    finally:
        if own:
            fetcher.close()
    raise ScrapeError("; ".join(errors) or "unknown")


__all__ = ["scrape", "ScrapeError", "ProductInfo", "pick_extractor", "stock_for_size", "store_from_url",
           "Fetcher", "FetchError", "RobotsDisallowed", "EXTRACTORS"]
