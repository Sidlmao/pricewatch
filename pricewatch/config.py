"""Load .env once. Import this before anything that reads os.environ."""
import os
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))

TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_FROM")
MY_PHONE = os.getenv("MY_PHONE")
NOTIFIER = os.getenv("NOTIFIER", "twilio")        # twilio | ntfy | console
NTFY_TOPIC = os.getenv("NTFY_TOPIC")
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
FAIL_THRESHOLD = int(os.getenv("FAIL_THRESHOLD", "3"))
