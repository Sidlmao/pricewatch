from .base import Notifier, log
from .. import config


class TwilioNotifier(Notifier):
    name = "twilio"

    def __init__(self):
        missing = [k for k in ("TWILIO_SID", "TWILIO_TOKEN", "TWILIO_FROM", "MY_PHONE") if not getattr(config, k)]
        if missing:
            raise RuntimeError("missing in .env: " + ", ".join(missing))
        from twilio.rest import Client
        self.client = Client(config.TWILIO_SID, config.TWILIO_TOKEN)

    def send(self, text: str) -> None:
        msg = self.client.messages.create(body=text, from_=config.TWILIO_FROM, to=config.MY_PHONE)
        log.info("twilio sent %s", msg.sid)
