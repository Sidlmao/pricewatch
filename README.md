# pricewatch

A personal price tracker for clothing. Paste a product URL, optionally a size and a target
price, and get a text when the price drops (or when your size comes back in stock).

Runs for free on a GitHub Actions cron every 6 hours. Price history lives in a SQLite file
that the workflow commits back to the repo. A tiny local web page lets you add and remove
items and see a price chart.

## Supported stores

| Store   | How it's read                                      | Sizes / stock |
|---------|----------------------------------------------------|---------------|
| Nike    | JSON-LD + embedded page data (plain HTTP)          | per size      |
| END.    | JSON-LD + embedded page data (plain HTTP)          | per size      |
| Amazon  | HTML price block (plain HTTP)                      | per size      |
| Uniqlo  | Uniqlo's product JSON API (site HTML is bot-walled)| per size      |
| Grailed | Grailed's listing JSON API (pages are Cloudflare-walled) | listing size |
| Zara    | Headless Chromium, then JSON-LD variants           | per size      |
| SSENSE  | Headless Chromium, then JSON-LD + size dropdown    | per size      |
| anything else | JSON-LD offers, then og:/product: meta tags, then embedded JSON, then Chromium | overall only |

Sale prices are handled: the tracker records what you'd pay now, and remembers the
struck-through original price separately for display. Currency symbols and ISO codes are
parsed (`$54.99`, `1.299,00 €`, `£45`, `¥12,000`, `US$ 120` ...).

## Setup (local)

```bash
cd pricewatch
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium          # only needed for Zara/SSENSE/unknown stores
cp .env.example .env                 # then fill in the values (see Twilio below)
```

Quick checks that everything works:

```bash
python scrape.py "https://www.nike.com/t/..."  --size M     # scrape one URL, print what it found
python check.py --add "https://www.nike.com/t/..." --size M --target 60 --restock
python check.py --list
python check.py --dry-run            # check every item, print alerts, change nothing
python check.py                      # the real thing: records history and texts you
python check.py --test-sms           # sends one test message through the configured notifier
python app.py                        # web UI at http://127.0.0.1:5055
```

`--dry-run` works on a throwaway copy of the database, so it never records prices or
alerts. That matters: a real drop will still be texted on the next real run.

## Twilio setup (SMS)

1. Create an account at https://www.twilio.com/try-twilio. The free trial is enough for
   a personal tracker.
2. In the Console, **Get a trial phone number**. That number is `TWILIO_FROM`
   (E.164 format, e.g. `+15551234567`).
3. **Verified Caller IDs** (Phone Numbers > Manage > Verified Caller IDs): add and verify
   your own mobile number. Trial accounts can only text verified numbers. That number is
   `MY_PHONE`.
4. From the Console home page copy **Account SID** (`TWILIO_SID`) and **Auth Token**
   (`TWILIO_TOKEN`).
5. Put all four in `.env`, then run `python check.py --test-sms`.

Trial messages carry a "Sent from your Twilio trial account" prefix. If you upgrade to a
paid account and text a US number, Twilio may require A2P 10DLC registration for a local
number; a toll-free number with toll-free verification is the simplest route.

### Using something other than Twilio

The notifier is one small class (`pricewatch/notify/base.py`). Two are included:

- `NOTIFIER=twilio` (default)
- `NOTIFIER=ntfy` with `NTFY_TOPIC=<a long random string>` sends free push notifications
  via https://ntfy.sh. Install the ntfy app and subscribe to the same topic. No account
  needed.
- `NOTIFIER=console` just prints.

To add Telegram or anything else, subclass `Notifier`, implement `send(text)`, and add a
branch in `get_notifier()`.

## Scheduling with GitHub Actions

1. Make this folder its own git repo and push it to GitHub (private is fine):
   ```bash
   git init && git add -A && git commit -m "pricewatch" && gh repo create pricewatch --private --source . --push
   ```
2. In the repo: **Settings > Secrets and variables > Actions**, add secrets
   `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM`, `MY_PHONE`
   (or `NTFY_TOPIC` plus a repository *variable* `NOTIFIER=ntfy`).
3. **Settings > Actions > General > Workflow permissions**: choose *Read and write*, so
   the workflow can commit the database.
4. Open the **Actions** tab and run "price check" once by hand to confirm it works.

From then on it runs every 6 hours. To change the interval, edit the single `cron:` line
in `.github/workflows/check.yml` (GitHub's minimum is every 5 minutes; scheduled runs can
lag by 10 to 15 minutes at busy times).

### Adding items when the tracker runs on GitHub

The database is the file `data/pricewatch.db`. The workflow commits its updates, so:

```bash
git pull                                  # get the latest history
python check.py --add "https://..." --size M --target 60   # or use the web UI
git commit -am "track new item" && git push
```

If you push at the same moment a scheduled run pushes, one side has to re-pull. The
workflow retries with `git pull --rebase` and keeps its own copy of the DB on conflict,
so re-add the item if that ever happens. In practice, runs take about a minute.

### Committed SQLite vs a hosted database

**Committed SQLite (what this uses).** Free, zero accounts, one file you can copy or open
with any SQLite tool. The downsides: every run that records a price makes a commit (about
4 a day, each a few KB, so the repo grows slowly forever), and the copy on your laptop is
only as fresh as your last `git pull`. Fine for one person and a few dozen items.

**Hosted DB (Turso, Supabase, Neon all have free tiers).** One live source of truth for
both the workflow and your laptop, no commits, and the web UI could run anywhere. The
cost is another account, credentials in two places, a driver dependency, and the free
tiers can pause or change terms. Worth it only if you want the UI online or several
people sharing one tracker. Switching later means replacing `pricewatch/db.py`; nothing
else touches SQL.

## How alerts work

Every run checks each active item once and appends a row to `price_history`. Then:

- **Target set**: text when the price is at or below the target. It won't text again
  unless the price falls further, or goes back above the target and then drops again.
- **No target**: text on any drop compared with the previous check.
- **Restock** (per-item checkbox): text when your size was sold out on the previous check
  and is available now. Without a size it uses the item's overall availability.
- **Needs attention**: if a check fails 3 times in a row (site changed, blocked, URL
  dead) you get exactly one text. The count resets when a check succeeds. Change the
  threshold with `FAIL_THRESHOLD` in `.env`.

Each message has the item name, old price, new price, percent off and the link. Every
alert is recorded in the `alerts` table, which is how it avoids texting the same drop twice.

## Being polite to the stores

- Rotates through realistic desktop user agents.
- Waits a random 2 to 6 seconds between requests (`MIN_DELAY` / `MAX_DELAY`).
- Reads each site's `robots.txt` and skips URLs it disallows (`RESPECT_ROBOTS=0` to turn
  off, not recommended).
- Tries cheap plain HTTP first and only launches Chromium when the site needs it, with
  images, fonts and media blocked.

One check every 6 hours per item is far below anything a store would notice. Don't set the
cron to every 5 minutes with 200 items.

## Adding a store

Drop a file in `pricewatch/extractors/` with a subclass of `Extractor`, set `domains`,
and either override `extract(html, url)` (parse HTML) or set `uses_api = True` and
override `from_api(url, fetcher)`. Set `needs_browser = True` if plain HTTP is blocked.
Register it in `EXTRACTORS` in `pricewatch/extractors/__init__.py`. The `nike.py` and
`grailed.py` files are short examples of each style. Test with `python scrape.py URL`.

## Layout

```
check.py                 CLI: run checks, --dry-run, --add/--list/--remove, --test-sms
scrape.py                debug one URL
app.py + templates/      web UI (Flask, one page, server-rendered SVG chart)
pricewatch/
  fetch.py               user agents, delays, robots.txt, requests + Playwright
  prices.py              price string / currency parsing
  db.py                  SQLite schema and helpers (items, price_history, alerts)
  checker.py             the check + alert rules
  extractors/            one file per store + generic fallback
  notify/                Notifier interface: twilio, ntfy, console
data/pricewatch.db       the database (committed)
.github/workflows/       the 6-hourly cron
```
