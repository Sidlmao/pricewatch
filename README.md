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

### Telegram instead of SMS (free, recommended)

1. In Telegram, message **@BotFather**, send `/newbot`, pick a name, and copy the token it gives you.
2. Run `python check.py --telegram-setup`, paste the token, then send your new bot any
   message. It finds your chat id, writes both to `.env`, and sends you a test message.
3. Run `./deploy.sh` (again, if you already deployed) to push the values to GitHub.

### Other notifiers

The notifier is one small class (`pricewatch/notify/base.py`). Included:

- `NOTIFIER=twilio` (default)
- `NOTIFIER=telegram` with `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` (see above)
- `NOTIFIER=ntfy` with `NTFY_TOPIC=<a long random string>` sends free push notifications
  via https://ntfy.sh. Install the ntfy app and subscribe to the same topic. No account
  needed.
- `NOTIFIER=console` just prints.

To add Discord, Slack or anything else, subclass `Notifier`, implement `send(text)`, and add a
branch in `get_notifier()`.

## Deploy (one command)

```bash
cd pricewatch
./deploy.sh
```

The first time, it installs the GitHub CLI if needed, opens a browser tab for you to log in
to GitHub, creates a private repo called `pricewatch`, pushes the code, copies whatever is in
your `.env` into the repo's secrets, and starts the first check. It prints three links when
it's done:

- **Dashboard**: `https://<you>.github.io/pricewatch/`, a read-only copy of the web page,
  rebuilt after every check.
- **Add / remove items**: the "manage items" workflow. Press *Run workflow*, paste a URL,
  optional size and target, and it's tracked. Works from your phone. Remove or pause an
  item by its `#` number from the dashboard.
- **Runs & logs**: the Actions tab.

If `.env` has no Twilio values yet, it sets up free push notifications through
[ntfy.sh](https://ntfy.sh) instead: install the ntfy app and subscribe to the topic it
prints. Add Twilio values to `.env` later, set `NOTIFIER=twilio`, and run `./deploy.sh`
again to switch to SMS. Re-running the script is always safe; it just pushes and re-syncs.

Checks run every 6 hours. To change that, edit the single `cron:` line in
`.github/workflows/check.yml` (GitHub's minimum is every 5 minutes; scheduled runs can lag
by 10 to 15 minutes at busy times).

### Doing it by hand instead

Push this folder to a GitHub repo, add the secrets `TWILIO_SID`, `TWILIO_TOKEN`,
`TWILIO_FROM`, `MY_PHONE` (or `NTFY_TOPIC` plus a repository *variable* `NOTIFIER=ntfy`)
under Settings > Secrets and variables > Actions, set Settings > Actions > General >
Workflow permissions to *Read and write*, set Settings > Pages > Source to *GitHub Actions*,
and run "price check" once from the Actions tab.

### Why not Vercel / a normal host?

Vercel-style platforms have no persistent disk (the SQLite file would vanish), can't run
Playwright's Chromium (Zara and SSENSE would break), and their free cron runs once a day.
GitHub Actions gives you a real Linux box with a browser for a minute every 6 hours, for
free, and the repo itself is the storage.

### Committed SQLite vs a hosted database

**Committed SQLite (what this uses).** Free, zero accounts, one file you can copy or open
with any SQLite tool. The downsides: every run that records a price makes a commit (about
4 a day, each a few KB, so the repo grows slowly forever), and if you also run the local
web UI, its copy is only as fresh as your last `git pull`. Fine for one person and a few
dozen items.

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
deploy.sh                one-command deploy to GitHub
check.py                 CLI: run checks, --dry-run, --add/--list/--remove/--toggle, --test-sms
scrape.py                debug one URL
app.py + templates/      web UI (Flask, one page, server-rendered SVG chart)
build_site.py            renders the same page statically for GitHub Pages
pricewatch/
  fetch.py               user agents, delays, robots.txt, requests + Playwright
  prices.py              price string / currency parsing
  db.py                  SQLite schema and helpers (items, price_history, alerts)
  checker.py             the check + alert rules
  extractors/            one file per store + generic fallback
  notify/                Notifier interface: twilio, telegram, ntfy, console
data/pricewatch.db       the database (committed)
.github/workflows/       check.yml = the 6-hourly cron + dashboard, manage.yml = add/remove form
```
