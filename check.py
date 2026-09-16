#!/usr/bin/env python3
"""pricewatch CLI.

  python check.py                 check all active items and send alerts
  python check.py --dry-run       same, but print alerts instead of texting (and change nothing)
  python check.py --add URL [--size M] [--target 60] [--restock]
  python check.py --list
  python check.py --remove ID
  python check.py --toggle ID     pause / resume
  python check.py --test-sms      send one test message through the configured notifier
"""
import argparse
import logging
import sys

import pricewatch  # noqa: F401  loads .env
from pricewatch import db
from pricewatch.checker import run_checks
from pricewatch.prices import fmt


def main(argv=None):
    p = argparse.ArgumentParser(description="Personal clothing price tracker")
    p.add_argument("--dry-run", action="store_true", help="print alerts instead of sending; DB untouched")
    p.add_argument("--item", type=int, action="append", help="only check this item id (repeatable)")
    p.add_argument("--add", metavar="URL"); p.add_argument("--size"); p.add_argument("--target", type=float)
    p.add_argument("--restock", action="store_true", help="also alert when the size comes back in stock")
    p.add_argument("--list", action="store_true"); p.add_argument("--remove", type=int, metavar="ID")
    p.add_argument("--toggle", type=int, metavar="ID", help="pause or resume an item")
    p.add_argument("--test-sms", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    if a.add:
        conn = db.connect()
        iid = db.add_item(conn, a.add, size=a.size, target_price=a.target, notify_restock=a.restock)
        print(f"added item {iid}: {a.add}" + (f" size={a.size}" if a.size else "") + (f" target={a.target}" if a.target else ""))
        print("run `python check.py --dry-run` to fetch it now")
        return 0
    if a.list:
        conn = db.connect()
        latest = db.latest_for_items(conn)
        for it in db.list_items(conn):
            l = latest.get(it["id"])
            price = fmt(l["price"], it["currency"]) if l else "-"
            print(f"[{it['id']:3}] {'on ' if it['active'] else 'off'} {price:>10}  target={fmt(it['target_price'], it['currency']) if it['target_price'] else '-':>8} "
                  f" size={it['size'] or '-':4} restock={'y' if it['notify_restock'] else 'n'}  {it['name'] or it['url']}")
        return 0
    if a.remove:
        conn = db.connect(); db.delete_item(conn, a.remove); print(f"removed item {a.remove}"); return 0
    if a.toggle:
        conn = db.connect(); it = db.get_item(conn, a.toggle)
        if not it:
            print(f"no item {a.toggle}"); return 1
        db.update_item_meta(conn, a.toggle, active=0 if it["active"] else 1)
        print(f"item {a.toggle} {'paused' if it['active'] else 'resumed'}"); return 0
    if a.test_sms:
        from pricewatch.notify import get_notifier
        get_notifier().send("pricewatch test: notifications are working ✅"); print("sent"); return 0

    s = run_checks(dry_run=a.dry_run, item_ids=a.item)
    mode = "DRY RUN" if a.dry_run else "run"
    print(f"\n{mode}: checked {s['checked']} item(s), {s['failed']} failing, {len(s['alerts'])} alert(s)"
          + (": " + ", ".join(f"#{i} {t}" for i, t in s["alerts"]) if s["alerts"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
