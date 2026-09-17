"""Notifier interface. Implement send(text) and register in get_notifier()."""
import logging
from typing import List

log = logging.getLogger("pricewatch.notify")


class Notifier:
    name = "base"

    def send(self, text: str) -> None:
        raise NotImplementedError


class ConsoleNotifier(Notifier):
    """Prints instead of sending. Used by --dry-run and when NOTIFIER=console."""
    name = "console"

    def __init__(self):
        self.sent: List[str] = []

    def send(self, text: str) -> None:
        self.sent.append(text)
        print("\n--- WOULD SEND ---\n" + text + "\n------------------")


def get_notifier(dry_run: bool = False) -> Notifier:
    from .. import config
    if dry_run or config.NOTIFIER == "console":
        return ConsoleNotifier()
    if config.NOTIFIER == "twilio":
        from .twilio_sms import TwilioNotifier
        return TwilioNotifier()
    if config.NOTIFIER == "telegram":
        from .telegram import TelegramNotifier
        return TelegramNotifier()
    if config.NOTIFIER == "ntfy":
        from .ntfy import NtfyNotifier
        return NtfyNotifier()
    raise ValueError(f"unknown NOTIFIER={config.NOTIFIER!r} (use twilio, telegram, ntfy or console)")
