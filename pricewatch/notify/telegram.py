"""Telegram bot notifications. Set NOTIFIER=telegram, TELEGRAM_TOKEN (from @BotFather) and TELEGRAM_CHAT_ID."""
import requests

from .base import Notifier, log
from .. import config


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self):
        missing = [k for k in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID") if not getattr(config, k)]
        if missing:
            raise RuntimeError("missing in .env: " + ", ".join(missing) + " (run: python check.py --telegram-setup)")
        self.url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"

    def send(self, text: str) -> None:
        r = requests.post(self.url, json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text,
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
