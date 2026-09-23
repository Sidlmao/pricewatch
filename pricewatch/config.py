"""Load .env once. Import this before anything that reads os.environ."""
import os
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))

TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_FROM")
MY_PHONE = os.getenv("MY_PHONE")
NOTIFIER = os.getenv("NOTIFIER", "twilio")        # twilio | telegram | ntfy | console
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
NTFY_TOPIC = os.getenv("NTFY_TOPIC")
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
FAIL_THRESHOLD = int(os.getenv("FAIL_THRESHOLD", "3"))
# How often each item is re-checked. CHECK_INTERVAL_MINUTES (default 5) is the normal knob;
# CHECK_INTERVAL_HOURS still works for older .env files and wins when set.
CHECK_INTERVAL_MINUTES = float(os.getenv("CHECK_INTERVAL_MINUTES") or "5")
CHECK_INTERVAL_HOURS = float(os.getenv("CHECK_INTERVAL_HOURS") or CHECK_INTERVAL_MINUTES / 60)
MIN_DROP_PCT = float(os.getenv("MIN_DROP_PCT", "1"))   # no-target items: ignore drops smaller than this (noise)
MAX_ITEMS_PER_USER = int(os.getenv("MAX_ITEMS_PER_USER", "100"))
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
APP_URL = os.getenv("APP_URL")   # public link to the web app, used in bot replies
