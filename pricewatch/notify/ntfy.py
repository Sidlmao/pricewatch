"""ntfy.sh push notifications: free, no account. Set NOTIFIER=ntfy and NTFY_TOPIC=<something-secret>."""
import requests

from .base import Notifier, log
from .. import config


class NtfyNotifier(Notifier):
    name = "ntfy"

    def __init__(self):
        if not config.NTFY_TOPIC:
            raise RuntimeError("missing in .env: NTFY_TOPIC")
        self.url = f"{config.NTFY_SERVER.rstrip('/')}/{config.NTFY_TOPIC}"

    def send(self, text: str) -> None:
        r = requests.post(self.url, data=text.encode("utf-8"), headers={"Title": "pricewatch"}, timeout=20)
        r.raise_for_status()
        log.info("ntfy sent to %s", self.url)
