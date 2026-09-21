"""Telegram link step: deep-link /start links the user and stores the @name; a cold /start gets a help reply once."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); os.environ.pop("DATABASE_URL", None)
import pricewatch
from pricewatch import db, config
from pricewatch.notify import telegram as tg
db.DATABASE_URL = None; config.TELEGRAM_TOKEN = "T"
conn = db.connect(tempfile.mktemp(suffix=".db"))
calls = []
class R:
    def __init__(self, j): self.j = j
    def raise_for_status(self): pass
    def json(self): return self.j
U = "11111111-1111-1111-1111-111111111111"
updates = [
  {"update_id": 1, "message": {"text": f"/start {U}", "chat": {"id": 42, "type": "private", "username": "sid"}}},
  {"update_id": 2, "message": {"text": "/start", "chat": {"id": 43, "type": "private", "first_name": "Bob"}}},
  {"update_id": 3, "message": {"text": "hello?", "chat": {"id": 43, "type": "private", "first_name": "Bob"}}},
  {"update_id": 4, "message": {"text": "/start", "chat": {"id": -9, "type": "group"}}},
]
tg.requests.get = lambda url, **k: R({"result": updates})
tg.requests.post = lambda url, json=None, **k: calls.append(json) or R({})
n = tg.link_users(conn, app_url="https://sidlmao.github.io/pricewatch/")
p = db.get_profile(conn, U)
ok = lambda c, m: print(("ok   " if c else "FAIL ") + m)
ok(n == 1 and p["telegram_chat_id"] == "42" and p["telegram_name"] == "@sid", "links the deep-link user and stores @username")
ok(len(calls) == 2, f"one confirmation + one help reply (got {len(calls)})")
ok(calls[0]["chat_id"] == 42 and "connected" in calls[0]["text"], "confirmation to linked chat")
ok(calls[1]["chat_id"] == 43 and "Connect Telegram" in calls[1]["text"] and "sidlmao.github.io" in calls[1]["text"], "help reply once to a cold chat, with the app link")
ok(db.get_setting(conn, "telegram_offset") == "5", "offset advances past all updates")
