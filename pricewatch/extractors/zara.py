"""zara.com: Akamai blocks plain HTTP, but full Chromium gets a JSON-LD ProductGroup with per-size offers."""
from .base import Extractor


class ZaraExtractor(Extractor):
    store = "zara"
    domains = ("zara.com",)
    needs_browser = True
    wait_ms = 5000
