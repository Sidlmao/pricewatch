"""SQLite storage. One file, three tables, no ORM."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable, Optional

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "pricewatch.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url           TEXT NOT NULL,
    store         TEXT,
    name          TEXT,
    image_url     TEXT,
    size          TEXT,
    target_price  REAL,
    currency      TEXT,
    active        INTEGER NOT NULL DEFAULT 1,
    notify_restock INTEGER NOT NULL DEFAULT 0,
    fail_count    INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id    INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    price      REAL,
    original_price REAL,
    in_stock   INTEGER,
    checked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_item ON price_history(item_id, checked_at);
CREATE TABLE IF NOT EXISTS alerts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id   INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    type      TEXT NOT NULL,          -- price_drop | target_hit | restock | needs_attention
    old_price REAL,
    new_price REAL,
    sent_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_item ON alerts(item_id, type, sent_at);
"""


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path: Optional[str] = None) -> sqlite3.Connection:
    path = path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def tx(conn: sqlite3.Connection):
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# --- items --------------------------------------------------------------

def add_item(conn, url, size=None, target_price=None, notify_restock=False, store=None, name=None,
             image_url=None, currency=None) -> int:
    with tx(conn):
        cur = conn.execute(
            "INSERT INTO items (url, store, name, image_url, size, target_price, currency, active, notify_restock, created_at)"
            " VALUES (?,?,?,?,?,?,?,1,?,?)",
            (url, store, name, image_url, size or None, target_price, currency, int(bool(notify_restock)), now()))
        return cur.lastrowid


def update_item_meta(conn, item_id, **fields):
    allowed = {"store", "name", "image_url", "currency", "active", "target_price", "size", "notify_restock",
               "fail_count", "last_error"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    with tx(conn):
        conn.execute(f"UPDATE items SET {sets} WHERE id = ?", (*fields.values(), item_id))


def delete_item(conn, item_id):
    with tx(conn):
        conn.execute("DELETE FROM items WHERE id = ?", (item_id,))


def get_item(conn, item_id):
    return conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()


def list_items(conn, active_only=False):
    q = "SELECT * FROM items" + (" WHERE active = 1" if active_only else "") + " ORDER BY created_at DESC"
    return conn.execute(q).fetchall()


# --- price history --------------------------------------------------------

def record_price(conn, item_id, price, in_stock, original_price=None, checked_at=None) -> int:
    with tx(conn):
        cur = conn.execute(
            "INSERT INTO price_history (item_id, price, original_price, in_stock, checked_at) VALUES (?,?,?,?,?)",
            (item_id, price, original_price, None if in_stock is None else int(bool(in_stock)), checked_at or now()))
        return cur.lastrowid


def history(conn, item_id, limit=500):
    return conn.execute(
        "SELECT price, original_price, in_stock, checked_at FROM price_history WHERE item_id = ?"
        " ORDER BY checked_at DESC LIMIT ?", (item_id, limit)).fetchall()[::-1]


def last_checks(conn, item_id, n=2):
    """Most recent n history rows, newest first."""
    return conn.execute(
        "SELECT price, original_price, in_stock, checked_at FROM price_history WHERE item_id = ?"
        " ORDER BY checked_at DESC, id DESC LIMIT ?", (item_id, n)).fetchall()


def latest_for_items(conn):
    """item_id -> latest history row, for the UI list."""
    rows = conn.execute("""
        SELECT h.item_id, h.price, h.original_price, h.in_stock, h.checked_at,
               (SELECT MIN(price) FROM price_history WHERE item_id = h.item_id AND price IS NOT NULL) AS min_price
        FROM price_history h
        JOIN (SELECT item_id, MAX(id) AS max_id FROM price_history GROUP BY item_id) m
          ON m.max_id = h.id
    """).fetchall()
    return {r["item_id"]: r for r in rows}


# --- alerts ---------------------------------------------------------------

def record_alert(conn, item_id, type_, old_price=None, new_price=None) -> int:
    with tx(conn):
        cur = conn.execute(
            "INSERT INTO alerts (item_id, type, old_price, new_price, sent_at) VALUES (?,?,?,?,?)",
            (item_id, type_, old_price, new_price, now()))
        return cur.lastrowid


def last_alert(conn, item_id, type_=None):
    if type_:
        return conn.execute("SELECT * FROM alerts WHERE item_id = ? AND type = ? ORDER BY id DESC LIMIT 1",
                            (item_id, type_)).fetchone()
    return conn.execute("SELECT * FROM alerts WHERE item_id = ? ORDER BY id DESC LIMIT 1", (item_id,)).fetchone()


def alerts_for(conn, item_id, limit=20):
    return conn.execute("SELECT * FROM alerts WHERE item_id = ? ORDER BY id DESC LIMIT ?", (item_id, limit)).fetchall()
