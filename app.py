#!/usr/bin/env python3
"""Single-page UI: add/remove items, see latest price and a small history chart.  python app.py"""
import logging
from datetime import datetime, timezone

from flask import Flask, render_template, request, redirect, url_for, flash

import pricewatch  # noqa: F401  loads .env
from pricewatch import db
from pricewatch.checker import run_checks
from pricewatch.notify import ConsoleNotifier, get_notifier
from pricewatch.prices import fmt

app = Flask(__name__)
app.secret_key = "pricewatch-local-ui"   # only used for flash messages on localhost
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def sparkline(rows, target=None, w=180, h=44):
    """Inline SVG polyline of price history. Returns dict for the template, or None."""
    pts = [(r["checked_at"], r["price"]) for r in rows if r["price"] is not None]
    if len(pts) < 2:
        return None
    prices = [p for _, p in pts]
    lo, hi = min(prices + ([target] if target else [])), max(prices + ([target] if target else []))
    span = (hi - lo) or 1.0
    pad = 3
    def y(v): return round(pad + (h - 2 * pad) * (1 - (v - lo) / span), 1)
    xs = [round(pad + (w - 2 * pad) * i / (len(pts) - 1), 1) for i in range(len(pts))]
    points = " ".join(f"{x},{y(p)}" for x, p in zip(xs, prices))
    return {"w": w, "h": h, "points": points, "last": (xs[-1], y(prices[-1])),
            "target_y": y(target) if target else None, "lo": lo, "hi": hi}


def ago(iso):
    if not iso:
        return "never"
    dt = datetime.fromisoformat(iso)
    s = int((datetime.now(timezone.utc) - dt).total_seconds())
    for unit, n in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= n:
            return f"{s // n}{unit} ago"
    return "just now"


def _notifier():
    try:
        return get_notifier()
    except Exception as e:          # no Twilio creds yet -> print instead
        logging.warning("notifier unavailable (%s); printing alerts to console", e)
        return ConsoleNotifier()


def render_page(static=False, manage_url=None):
    """Build the page. static=True hides the forms (used for the GitHub Pages copy)."""
    conn = db.connect()
    latest = db.latest_for_items(conn)
    items = []
    for it in db.list_items(conn):
        l = latest.get(it["id"])
        cur = it["currency"]
        items.append({
            "row": it,
            "price": fmt(l["price"], cur) if l and l["price"] is not None else None,
            "original": fmt(l["original_price"], cur) if l and l["original_price"] else None,
            "min": fmt(l["min_price"], cur) if l and l["min_price"] is not None else None,
            "in_stock": None if not l else l["in_stock"],
            "checked": ago(l["checked_at"]) if l else "never",
            "target": fmt(it["target_price"], cur) if it["target_price"] else None,
            "chart": sparkline(db.history(conn, it["id"]), it["target_price"]),
            "alerts": db.alerts_for(conn, it["id"], 3),
        })
    conn.close()
    return render_template("index.html", items=items, fmt=fmt, ago=ago, static=static, manage_url=manage_url,
                           built_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))


@app.route("/")
def index():
    return render_page()


@app.post("/add")
def add():
    url = (request.form.get("url") or "").strip()
    if not url.startswith("http"):
        flash("Paste a full product URL starting with http(s)://")
        return redirect(url_for("index"))
    target = request.form.get("target") or None
    conn = db.connect()
    iid = db.add_item(conn, url, size=(request.form.get("size") or "").strip() or None,
                      target_price=float(target) if target else None,
                      notify_restock=bool(request.form.get("restock")))
    conn.close()
    s = run_checks(item_ids=[iid], notifier=_notifier())   # fetch it now so the row isn't empty
    conn = db.connect(); it = db.get_item(conn, iid); conn.close()
    flash(f"Added: {it['name'] or url}" + (f" (first check failed: {it['last_error']})" if it["fail_count"] else ""))
    return redirect(url_for("index"))


@app.post("/remove/<int:item_id>")
def remove(item_id):
    conn = db.connect(); db.delete_item(conn, item_id); conn.close()
    return redirect(url_for("index"))


@app.post("/toggle/<int:item_id>")
def toggle(item_id):
    conn = db.connect(); it = db.get_item(conn, item_id)
    if it:
        db.update_item_meta(conn, item_id, active=0 if it["active"] else 1)
    conn.close()
    return redirect(url_for("index"))


@app.post("/check/<int:item_id>")
def check(item_id):
    s = run_checks(item_ids=[item_id], notifier=_notifier())
    flash("Checked. " + (f"Sent: {', '.join(t for _, t in s['alerts'])}" if s["alerts"] else "No alerts."))
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5055, debug=False)
