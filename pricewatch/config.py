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
CHECK_INTERVAL_HOURS = float(os.getenv("CHECK_INTERVAL_HOURS", "6"))
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
