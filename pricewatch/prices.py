"""Parse price strings like "$54.99", "1.299,00 €", "US$ 120" into (amount, currency)."""
import re
from typing import Optional, Tuple

# Order matters: multi-character prefixes must come before the bare "$".
SYMBOLS = [
    ("US$", "USD"), ("CA$", "CAD"), ("C$", "CAD"), ("A$", "AUD"), ("AU$", "AUD"),
    ("NZ$", "NZD"), ("HK$", "HKD"), ("S$", "SGD"), ("MX$", "MXN"), ("R$", "BRL"),
    ("$", "USD"), ("€", "EUR"), ("£", "GBP"), ("¥", "JPY"), ("₩", "KRW"),
    ("₹", "INR"), ("zł", "PLN"), ("kr", None), ("CHF", "CHF"),
]
ISO_CODES = {"USD", "EUR", "GBP", "JPY", "CAD", "AUD", "NZD", "CHF", "SEK", "NOK",
             "DKK", "PLN", "CNY", "KRW", "HKD", "SGD", "INR", "MXN", "BRL", "CZK", "HUF"}
ZERO_DECIMAL = {"JPY", "KRW", "HUF"}

_NUM = re.compile(r"\d[\d.,\s ]*\d|\d")


def detect_currency(text: str) -> Optional[str]:
    if not text:
        return None
    upper = text.upper()
    for code in ISO_CODES:
        if re.search(r"(?<![A-Z])" + code + r"(?![A-Z])", upper):
            return code
    for sym, code in SYMBOLS:
        if sym in text:
            return code
    return None


def parse_amount(text: str, currency: Optional[str] = None) -> Optional[float]:
    """Turn '1.299,00' / '1,299.00' / '54,99' / '12,000' into a float."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    m = _NUM.search(str(text))
    if not m:
        return None
    raw = re.sub(r"[\s ]", "", m.group(0))
    if "," in raw and "." in raw:
        # Whichever separator comes last is the decimal point.
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw or "." in raw:
        sep = "," if "," in raw else "."
        head, _, tail = raw.rpartition(sep)
        if raw.count(sep) > 1 or len(tail) == 3 or (currency in ZERO_DECIMAL):
            raw = raw.replace(sep, "")          # thousands separator(s)
        else:
            raw = head + "." + tail             # decimal separator
    try:
        return round(float(raw), 2)
    except ValueError:
        return None


def parse_price(text, currency_hint: Optional[str] = None) -> Tuple[Optional[float], Optional[str]]:
    """Return (amount, ISO currency). Either may be None."""
    if text is None:
        return None, currency_hint
    if isinstance(text, (int, float)):
        return float(text), currency_hint
    text = str(text)
    currency = currency_hint or detect_currency(text)
    return parse_amount(text, currency), currency


def fmt(amount: Optional[float], currency: Optional[str]) -> str:
    if amount is None:
        return "?"
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CAD": "CA$", "AUD": "A$"}.get(currency or "", "")
    if currency in ZERO_DECIMAL:
        return f"{sym}{amount:,.0f}"
    s = f"{sym}{amount:,.2f}"
    return s if sym else f"{s} {currency or ''}".strip()
