"""Check every active item once, record history, and send alerts (deduplicated via the alerts table)."""
import logging
from typing import List, Optional

from . import config, db
from .extractors import scrape, ScrapeError, FetchError, RobotsDisallowed, stock_for_size, Fetcher
from .notify import get_notifier, Notifier, ConsoleNotifier
from .prices import fmt

log = logging.getLogger("pricewatch.checker")


def pct_off(old: Optional[float], new: Optional[float]) -> str:
    if not old or new is None or old <= 0:
        return ""
    return f"{round((old - new) / old * 100)}% off"


def _label(item) -> str:
    name = item["name"] or item["url"]
    return f"{name} (size {item['size']})" if item["size"] else name


def build_message(kind: str, item, old_price, new_price, currency) -> str:
    cur = currency or item["currency"]
    if kind == "target_hit":
        head = f"🎯 Target hit: {_label(item)}"
        line = f"{fmt(old_price, cur)} -> {fmt(new_price, cur)}" if old_price else f"now {fmt(new_price, cur)}"
        line += f" (target {fmt(item['target_price'], cur)}"
        p = pct_off(old_price, new_price)
        line += f", {p})" if p else ")"
    elif kind == "price_drop":
        head = f"📉 Price drop: {_label(item)}"
        line = f"{fmt(old_price, cur)} -> {fmt(new_price, cur)}"
        p = pct_off(old_price, new_price)
        line += f" ({p})" if p else ""
    elif kind == "restock":
        head = f"📦 Back in stock: {_label(item)}"
        line = f"{fmt(new_price, cur)}"
    else:  # needs_attention
        head = f"⚠️ Needs attention: {_label(item)}"
        line = f"failed {config.FAIL_THRESHOLD} checks in a row: {item['last_error']}"
    return f"{head}\n{line}\n{item['url']}"


class NullNotifier(Notifier):
    """Owner hasn't connected a channel yet: record the alert, send nothing."""
    name = "none"

    def send(self, text: str) -> None:
        log.info("alert not delivered (owner has no Telegram linked):\n%s", text)


def notifier_for(conn, item, default: Notifier) -> Notifier:
    """Items with an owner go to that owner's Telegram; ownerless items (personal mode) use the default."""
    if not item["user_id"]:
        return default
    if isinstance(default, ConsoleNotifier):   # dry run: print, don't send
        return default
    prof = db.get_profile(conn, item["user_id"])
    if prof and prof["telegram_chat_id"]:
        from .notify.telegram import TelegramNotifier
        return TelegramNotifier(chat_id=prof["telegram_chat_id"])
    return NullNotifier()


def check_item(conn, item, fetcher: Fetcher, notifier: Notifier) -> List[str]:
    """Returns list of alert types sent for this item."""
    sent = []
    notifier = notifier_for(conn, item, notifier)
    prev = db.last_checks(conn, item["id"], 1)
    prev = prev[0] if prev else None
    try:
        info = scrape(item["url"], fetcher)
    except (ScrapeError, FetchError, RobotsDisallowed) as e:
        return _handle_failure(conn, item, str(e), notifier)

    in_stock, _ = stock_for_size(info, item["size"])
    db.record_price(conn, item["id"], info.price, in_stock, original_price=info.original_price)
    meta = {"fail_count": 0, "last_error": None}
    for k in ("name", "image_url", "store", "currency"):
        if getattr(info, k) and not item[k]:
            meta[k] = getattr(info, k)
    db.update_item_meta(conn, item["id"], **meta)
    item = db.get_item(conn, item["id"])
    price, cur = info.price, info.currency or item["currency"]
    prev_price = prev["price"] if prev else None
    log.info("%s: %s%s | stock=%s", _label(item), fmt(price, cur),
             f" (prev {fmt(prev_price, cur)})" if prev_price is not None else "", in_stock)

    # --- price alerts ---------------------------------------------------
    target = item["target_price"]
    if target is not None:
        if price is not None and price <= target:
            last = db.last_alert(conn, item["id"], "target_hit")
            # Alert if never alerted, if the price fell further since the last alert,
            # or if the price went back above target in between and has now dropped again.
            fresh = last is None or price < last["new_price"] or (prev_price is not None and prev_price > target)
            if fresh:
                old = prev_price if prev_price is not None else info.original_price
                notifier.send(build_message("target_hit", item, old, price, cur))
                db.record_alert(conn, item["id"], "target_hit", old, price)
                sent.append("target_hit")
    elif prev_price is not None and price is not None and price < prev_price:
        last = db.last_alert(conn, item["id"], "price_drop")
        if not (last and last["new_price"] == price and last["old_price"] == prev_price):
            notifier.send(build_message("price_drop", item, prev_price, price, cur))
            db.record_alert(conn, item["id"], "price_drop", prev_price, price)
            sent.append("price_drop")

    # --- restock alert --------------------------------------------------
    if item["notify_restock"] and in_stock and prev is not None and prev["in_stock"] == 0:
        last = db.last_alert(conn, item["id"], "restock")
        if not (last and last["sent_at"] > prev["checked_at"]):
            notifier.send(build_message("restock", item, None, price, cur))
            db.record_alert(conn, item["id"], "restock", None, price)
            sent.append("restock")
    return sent


def _handle_failure(conn, item, error: str, notifier: Notifier) -> List[str]:
    count = (item["fail_count"] or 0) + 1
    db.update_item_meta(conn, item["id"], fail_count=count, last_error=error[:300])
    db.record_price(conn, item["id"], None, None)
    log.warning("%s: check failed (%d/%d): %s", _label(item), count, config.FAIL_THRESHOLD, error)
    if count == config.FAIL_THRESHOLD:           # exactly once per failure streak
        item = db.get_item(conn, item["id"])
        notifier.send(build_message("needs_attention", item, None, None, None))
        db.record_alert(conn, item["id"], "needs_attention")
        return ["needs_attention"]
    return []


def run_checks(dry_run: bool = False, item_ids: Optional[List[int]] = None, db_path: Optional[str] = None,
               notifier: Optional[Notifier] = None, due_only: bool = False) -> dict:
    """Check all active items. In dry-run mode nothing is committed and alerts are printed instead of sent."""
    # Dry run = one big transaction that is rolled back at the end (works for SQLite and Postgres).
    conn = db.connect(db_path, dry_run=dry_run)
    if notifier is None:
        try:
            notifier = get_notifier(dry_run=dry_run)
        except RuntimeError as e:           # multi-user mode: no global channel is fine
            log.warning("no default notifier (%s); only items with an owner get alerts", e)
            notifier = NullNotifier()
    fetcher = Fetcher()
    summary = {"checked": 0, "failed": 0, "alerts": [], "linked": 0}
    try:
        if not dry_run and config.TELEGRAM_TOKEN:
            try:
                from .notify.telegram import link_users
                summary["linked"] = link_users(conn)
            except Exception as e:
                log.warning("telegram link step failed: %s", e)
        items = db.due_items(conn, config.CHECK_INTERVAL_HOURS) if due_only else db.list_items(conn, active_only=True)
        if item_ids:
            items = [i for i in items if i["id"] in item_ids]
        for item in items:
            try:
                sent = check_item(conn, item, fetcher, notifier)
            except Exception as e:  # never let one item kill the run
                log.exception("unexpected error on item %s", item["id"])
                sent = _handle_failure(conn, item, f"internal: {e}", notifier)
            summary["checked"] += 1
            if db.get_item(conn, item["id"])["fail_count"]:
                summary["failed"] += 1
            summary["alerts"].extend((item["id"], s) for s in sent)
    finally:
        fetcher.close()
        if dry_run:
            conn.rollback()
        conn.close()
    return summary
