"""Telegram bot notifications. Set NOTIFIER=telegram, TELEGRAM_TOKEN (from @BotFather) and TELEGRAM_CHAT_ID."""
import requests

from .base import Notifier, log
from .. import config


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self, chat_id=None):
        self.chat_id = chat_id or config.TELEGRAM_CHAT_ID
        missing = [k for k, v in (("TELEGRAM_TOKEN", config.TELEGRAM_TOKEN), ("TELEGRAM_CHAT_ID", self.chat_id)) if not v]
        if missing:
            raise RuntimeError("missing in .env: " + ", ".join(missing) + " (run: python check.py --telegram-setup)")
        self.url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"

    def send(self, text: str) -> None:
        r = requests.post(self.url, json={"chat_id": self.chat_id, "text": text,
                                          "disable_web_page_preview": False}, timeout=20)
        r.raise_for_status()
        log.info("telegram sent")


def find_chat_id(token: str):
    """Return the chat id of whoever most recently messaged the bot, or None."""
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
    r.raise_for_status()
    for upd in reversed(r.json().get("result", [])):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat")
        if chat and chat.get("id"):
            return chat["id"], chat.get("first_name") or chat.get("title") or chat.get("username")
    return None


UUID_RE = __import__("re").compile(r"^/start\s+([0-9a-fA-F-]{36})\s*$")


def link_users(conn) -> int:
    """Users press 'Connect Telegram' in the web app, which opens t.me/<bot>?start=<user_id>.
    The bot receives '/start <user_id>'; here we map that chat to the user. Returns how many were linked."""
    from .. import db
    if not config.TELEGRAM_TOKEN:
        return 0
    offset = int(db.get_setting(conn, "telegram_offset", 0) or 0)
    r = requests.get(f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getUpdates",
                     params={"offset": offset, "timeout": 0}, timeout=20)
    r.raise_for_status()
    linked, last = 0, None
    for upd in r.json().get("result", []):
        last = upd["update_id"]
        msg = upd.get("message") or {}
        m = UUID_RE.match(msg.get("text") or "")
        chat = msg.get("chat") or {}
        if m and chat.get("id"):
            db.set_telegram(conn, m.group(1), chat["id"])
            linked += 1
            try:
                TelegramNotifier(chat_id=chat["id"]).send("pricewatch connected ✅ You'll get price alerts here.")
            except Exception as e:
                log.warning("could not confirm telegram link: %s", e)
    if last is not None:
        db.set_setting(conn, "telegram_offset", last + 1)
    return linked
