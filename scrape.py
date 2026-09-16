#!/usr/bin/env python3
"""Scrape one product URL and print what we found. Usage: python scrape.py URL [--size M] [--browser|--no-browser]"""
import argparse, json, logging, sys
from pricewatch.extractors import scrape, ScrapeError, stock_for_size, pick_extractor
from pricewatch.prices import fmt

p = argparse.ArgumentParser()
p.add_argument("url"); p.add_argument("--size")
p.add_argument("--browser", action="store_true", help="force Playwright")
p.add_argument("--no-browser", action="store_true", help="never use Playwright")
p.add_argument("--json", action="store_true")
a = p.parse_args()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
try:
    info = scrape(a.url, use_browser=True if a.browser else (False if a.no_browser else None))
except ScrapeError as e:
    print("FAILED:", e); sys.exit(1)
if a.json:
    print(json.dumps(info.__dict__, indent=2)); sys.exit(0)
print(f"extractor : {type(pick_extractor(a.url)).__name__}  (source: {info.source})")
print(f"store     : {info.store}")
print(f"name      : {info.name}")
print(f"price     : {fmt(info.price, info.currency)}" + (f"  (was {fmt(info.original_price, info.currency)})" if info.original_price else ""))
print(f"currency  : {info.currency}")
print(f"in stock  : {info.in_stock}")
print(f"image     : {info.image_url}")
if info.sizes:
    print("sizes     : " + ", ".join(f"{k}{'' if v else ' (sold out)'}" for k, v in info.sizes.items()))
if a.size:
    st, matched = stock_for_size(info, a.size)
    print(f"size {a.size!r:6}: {'in stock' if st else 'NOT in stock'}{'' if matched else ' (size not listed)'}")
