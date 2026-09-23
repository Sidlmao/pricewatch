"""Checker behaviour on SQLite with a stubbed scraper: priority queue, sizes_json, check_requested, min-drop rule."""
import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("DATABASE_URL", None)
import pricewatch
from pricewatch import db, config, checker
from pricewatch.extractors import ProductInfo
from pricewatch.notify import ConsoleNotifier
import pricewatch.checker as ck
db.DATABASE_URL = None
path = tempfile.mktemp(suffix=".db")
conn = db.connect(path)
fails = []
def check(c, m): print(("ok   " if c else "FAIL ") + m); c or fails.append(m)

# migration on an OLD schema (no new columns) must add them
old = tempfile.mktemp(suffix=".db")
import sqlite3
o = sqlite3.connect(old); o.executescript("""CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL, store TEXT, name TEXT, image_url TEXT, size TEXT,
 target_price REAL, currency TEXT, active INTEGER NOT NULL DEFAULT 1, notify_restock INTEGER NOT NULL DEFAULT 0, fail_count INTEGER NOT NULL DEFAULT 0, last_error TEXT, created_at TEXT NOT NULL);
 CREATE TABLE profiles (user_id TEXT PRIMARY KEY, email TEXT, telegram_chat_id TEXT, created_at TEXT);"""); o.commit(); o.close()
oc = db.connect(old); cols = [r[1] for r in oc.execute("PRAGMA table_info(items)").fetchall()]
check("check_requested" in cols and "sizes_json" in cols and "user_id" in cols, "migration adds new columns to an old db")
check("telegram_name" in [r[1] for r in oc.execute("PRAGMA table_info(profiles)").fetchall()], "migration adds telegram_name")
oc.close()

# due ordering: requested first, then never-checked, then stale
a = db.add_item(conn, "https://x/a", user_id="u1")          # never checked
b = db.add_item(conn, "https://x/b", user_id="u1")          # checked long ago
c = db.add_item(conn, "https://x/c", user_id="u1")          # fresh, but check requested
d = db.add_item(conn, "https://x/d", user_id="u1")          # fresh, not due
db.record_price(conn, b, 10, 1, checked_at="2020-01-01T00:00:00+00:00")
db.record_price(conn, c, 10, 1); db.record_price(conn, d, 10, 1)
db.update_item_meta(conn, c, check_requested=1)
due = [r["id"] for r in db.due_items(conn, 6)]
check(due == [c, a, b], f"due order is requested, never-checked, stale: {due}")

# stub scraper
infos = {}
def fake_scrape(url, fetcher): 
    r = infos[url]
    if isinstance(r, Exception): raise r
    return r
ck.scrape = fake_scrape
class F: 
    def close(self): pass
n = ConsoleNotifier()
sent = []
class Spy(ConsoleNotifier):
    def send(self, t): sent.append(t)
spy = Spy()

infos["https://x/c"] = ProductInfo(url="https://x/c", store="nike", name="Thing", price=10, currency="USD", sizes={"S": True, "M": False})
db.update_item_meta(conn, c, size="m")
ck.check_item(conn, db.get_item(conn, c), F(), spy)
it = db.get_item(conn, c)
check(it["check_requested"] == 0, "check clears check_requested")
check(json.loads(it["sizes_json"]) == {"S": True, "M": False}, "sizes_json saved")
check(db.last_checks(conn, c, 1)[0]["in_stock"] == 0, "size m matched M -> sold out recorded")

# min-drop rule: 10 -> 9.95 (0.5%) no alert; 10 -> 9.8 (2%) alert
infos["https://x/c"] = ProductInfo(url="https://x/c", store="nike", name="Thing", price=9.95, currency="USD")
sent.clear(); ck.check_item(conn, db.get_item(conn, c), F(), spy)
check(not sent, "0.5% drop ignored (MIN_DROP_PCT=1)")
infos["https://x/c"] = ProductInfo(url="https://x/c", store="nike", name="Thing", price=9.8, currency="USD")
sent.clear(); ck.check_item(conn, db.get_item(conn, c), F(), spy)
check(len(sent) == 1 and "Price drop" in sent[0], "1.5% drop alerts")
check(json.loads(db.get_item(conn, c)["sizes_json"]) == {"S": True, "M": False}, "sizes kept when a check returns none")

# failure clears check_requested
db.update_item_meta(conn, a, check_requested=1)
from pricewatch.extractors import ScrapeError
infos["https://x/a"] = ScrapeError("http: HTTP 403")
ck.check_item(conn, db.get_item(conn, a), F(), spy)
ia = db.get_item(conn, a)
check(ia["check_requested"] == 0 and ia["fail_count"] == 1, "failed check clears check_requested and counts")

# needs-attention: once per streak, friendly text, and not again within the cooldown even after a success in between
sent.clear()
for _ in range(3): ck.check_item(conn, db.get_item(conn, a), F(), spy)
check(len(sent) == 1 and "blocking automated checks" in sent[0] and "HTTP 403" not in sent[0].splitlines()[1], "3rd failure sends one plain-language needs-attention message")
infos["https://x/a"] = ProductInfo(url="https://x/a", store="nike", name="A", price=5, currency="USD")
ck.check_item(conn, db.get_item(conn, a), F(), spy)
infos["https://x/a"] = ScrapeError("http: HTTP 403")
for _ in range(3): ck.check_item(conn, db.get_item(conn, a), F(), spy)
check(len(sent) == 1, "a new failure streak within the cooldown stays quiet")
conn.execute("UPDATE alerts SET sent_at = ? WHERE item_id = ? AND type = 'needs_attention'", ("2020-01-01T00:00:00+00:00", a)); conn.commit()
infos["https://x/a"] = ProductInfo(url="https://x/a", store="nike", name="A", price=5, currency="USD")
ck.check_item(conn, db.get_item(conn, a), F(), spy)
infos["https://x/a"] = ScrapeError("http: HTTP 403")
for _ in range(3): ck.check_item(conn, db.get_item(conn, a), F(), spy)
check(len(sent) == 2, "after the cooldown a new streak alerts again")

# telegram link stores a name
db.set_telegram(conn, "11111111-1111-1111-1111-111111111111", 42, "@sid")
p = db.get_profile(conn, "11111111-1111-1111-1111-111111111111")
check(p["telegram_chat_id"] == "42" and p["telegram_name"] == "@sid", "set_telegram stores name")
conn.close()

# --- JSON-LD variant selection (Lululemon-style: every colour x size is a variant with its own URL) ---
from pricewatch.extractors.base import product_from_json_ld, _size_label, select_variants
def mk(color, code, size, price, avail):
    return {"@type": "Product", "color": color, "size": [size, {"@type": "SizeSpecification"}],
            "offers": [{"@type": "Offer", "price": str(price), "priceCurrency": "USD", "url": f"https://s/p/x?color={code}&sz={size}",
                        "availability": "https://schema.org/" + ("InStock" if avail else "OutOfStock")}]}
group = {"@type": "ProductGroup", "name": "Short", "offers": {"@type": "AggregateOffer", "lowPrice": "29", "priceCurrency": "USD"},
         "hasVariant": [mk("Clearance", "1", "S", 29, True), mk("Clearance", "1", "M", 29, False), mk("Walnut", "2", "S", 49, True), mk("Walnut", "2", "M", 49, False)]}
i = product_from_json_ld([group], "https://s/p/x?color=2&sz=S", "s")
check(i.price == 49 and i.sizes == {"S": True, "M": False}, f"variants filtered to the link's colour: {i.price} {i.sizes}")
i = product_from_json_ld([group], "https://s/p/x", "s")
check(i.price == 29, "no colour in the link -> cheapest variant as before")
i = product_from_json_ld([group], "https://s/p/x?color=999", "s")
check(i.price == 29, "unknown colour -> falls back to all variants")
check(_size_label(["S", {"@type": "SizeSpecification"}]) == "S" and _size_label({"name": "M"}) == "M" and _size_label("L") == "L" and _size_label(None) is None, "size labels unwrapped")
check(select_variants([{"url": "https://s/p?Color=2"}, {"url": "https://s/p?color=3"}], "https://s/p?color=2") == [{"url": "https://s/p?Color=2"}], "param match is case-insensitive on the key")
print(f"\n{len(fails)} failure(s) total"); sys.exit(1 if fails else 0)
