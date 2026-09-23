# pricewatch

Track prices on clothes you want. Sign in, paste a product link, and get a Telegram
message when the price drops (or when your size is back in stock).

- **Web app**: sign in with Google or an email link, add items by link, see price history.
  Hosted free on GitHub Pages.
- **Database + login**: Supabase (free tier). Row-level security means each user only
  ever sees their own items.
- **Scraping**: a GitHub Actions workflow runs every 5 minutes and re-checks every item each
  time (`CHECK_INTERVAL_MINUTES`, default 5). Playwright handles the JS-heavy sites. GitHub's
  own cron is unreliable, so a small Supabase job starts the workflow on time (see below).
- **Alerts**: each user connects the Telegram bot once; alerts go to their own chat.

## What a user can do

- Paste a link (tracking junk like `utm_*`/`fbclid` is stripped, Amazon links are canonicalised)
  and see the store and a readable name immediately, then the real name, image and price after
  the first check (about 5 minutes). Pasting the same link twice is caught.
- Add a size and a target price, tick "restock alert", and **edit** any of that later in place.
  The checker records which sizes the page offers, so the app shows size chips and warns when
  the size you typed isn't on the page.
- **Check now** on any item, with a countdown to the next run; the page refreshes itself after
  each run so prices appear without reloading.
- Expand an item for the full price chart, every check (price, sale price, stock) and every alert.
  Search, sort (newest, price, biggest drop, recent alerts), and filter (at target, on sale,
  sold out, needs attention, paused). Sale items show the % off.
- Failed checks explain themselves ("the store is blocking automated checks", "that page is
  gone", "use the product page, not a search page") instead of showing raw errors.
- Telegram: after tapping Connect the app waits and confirms on its own; the account menu shows
  who it's connected as and lets you disconnect. Someone who messages the bot cold gets told
  how to connect.
- **Landing page** for signed-out visitors: hero with a demo card, how it works, features,
  stores, FAQ. Signing in swaps it for the app.
- **Dashboard strip**: tracked / at target / on sale / sold out counts (click one to filter),
  how much cheaper things are than when first seen, and the next check countdown.
- **Activity tab**: every alert across all items in one timeline; click one to jump to the item.
- **Check all** queues a fresh check of every active item. Sort by store as well as name/price/drop.
- **Quick targets** in the edit form: 10% / 20% below the current price, the historic low, half the
  original price. Detail view also shows the average price, % below high and days tracked.
- **Get links in fast**: paste several links at once to track them all; share a page to the
  installed app (`share_target`); or drag the bookmarklet from the account menu to your bookmarks
  bar and click it on any product page. `?add=<url>` prefills the form.
- **Share** an item's link from the row (system share sheet, or copy). Keyboard: `n` new item,
  `/` search, `Esc` close.
- **Getting-started checklist** for new accounts: first item, Telegram, install to home screen
  (with an install button where the browser supports it).
- Account menu: theme (system / light / dark), export items as CSV or everything as JSON, item
  count against the per-user cap (100, enforced in the database), delete all my data, sign out.
  The app installs to the home screen (manifest + icons).

A single-user "personal mode" without Supabase or sign-in still exists: leave
`DATABASE_URL` unset and it keeps everything in a SQLite file and texts one phone/chat.
The rest of this README is about the full app.

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
| Lululemon | Headless Chromium, then JSON-LD variants (generic path) | per size |
| anything else | JSON-LD offers, then og:/product: meta tags, then embedded JSON, then Chromium | per size when the page lists variants |

Sale prices are handled: the tracker records what you'd pay now and remembers the
struck-through original separately. Currency symbols and ISO codes are parsed.

When a page lists every colour and size as its own variant (Lululemon does), the tracker
uses only the variants that match the colour in your link, so a clearance colour can't
masquerade as your price. Copy the link *after* picking your colour on the store page;
a bare product link falls back to the cheapest variant on the page.

## Setup

### 1. Supabase (database + sign-in)

1. Create a project at https://supabase.com. Note the database password.
2. **Project Settings > API**: copy the **Project URL** and the **anon public** key.
3. **Connect** (top bar) > **Session pooler**: copy the URI and put your password in it.
   Use the pooler, not "Direct connection": GitHub's runners are IPv4-only.
4. **Authentication > Providers**: enable **Google** (paste a Google OAuth client id and
   secret from Google Cloud Console; the callback URL to register there is shown on that
   page). Email sign-in links work out of the box with no extra setup.
5. **Authentication > URL Configuration**: after step 3 below you'll know your app URL
   (`https://<you>.github.io/pricewatch/`). Set it as **Site URL** and add it to
   **Redirect URLs**, otherwise sign-in bounces back to localhost.

### 2. Telegram bot (alerts)

Message **@BotFather**, send `/newbot`, copy the token. Users connect themselves from
inside the app (one tap), so you never need their chat ids.

### 3. Deploy

```bash
cd pricewatch
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env     # fill in DATABASE_URL, SUPABASE_URL, SUPABASE_ANON_KEY, TELEGRAM_TOKEN
./deploy.sh
```

The script logs you into GitHub (browser tab), creates a private repo, pushes, copies the
values from `.env` into the repo's secrets and variables, applies the row-level security
policies to Supabase, and starts the first runs. It prints the app link. Re-run it any
time you change `.env` or the code.

## How it works

```
web/index.html  ── supabase-js ──>  Supabase (auth + Postgres, RLS)  <── psycopg ──  check.py (GitHub Actions, every 5 min)
      │                                                                                     │
  GitHub Pages                                                                    Telegram bot -> each user's chat
```

- The browser talks to Supabase directly with the public anon key. Policies in
  `setup_supabase.py` restrict every table to `user_id = auth.uid()`.
- The browser can also set `items.check_requested = 1` (on add, "check now", or a size change);
  the cron picks those up first. Policies cap each user at `MAX_ITEMS_PER_USER` rows via a
  `SECURITY DEFINER` count function, so the cap holds even against a hand-written request.
- The cron connects as the database owner (bypasses RLS), scrapes items that are due,
  appends to `price_history`, stores the sizes it saw in `items.sizes_json`, and decides alerts.
- "Connect Telegram" opens `t.me/<bot>?start=<user_id>`. The next cron run reads the
  bot's messages, links that chat to the user, and confirms with a message. The app polls the
  profile meanwhile and flips to "connected" by itself.
- The app knows the cron minutes (`cronMinutes` in `config.js`, written by `pages.yml`) so it
  can say "next check in ~N min" and quietly reload once after each run. If you change the
  schedule in `check.yml`, change `CRON_MINUTES` in `pages.yml` (and `TRIGGER_CRON` below) too.

### Making it actually run every 5 minutes

`schedule:` in GitHub Actions is best-effort. On this repo it fired every 3 to 6 hours even with a
15-minute cron line, so the schedule alone can't deliver 5-minute checks. The fix is to have
something reliable call the workflow_dispatch API on time. Supabase can do that itself with
`pg_cron` + `pg_net`:

1. Create a fine-grained personal access token at github.com -> Settings -> Developer settings ->
   Fine-grained tokens, limited to this repo, with **Actions: read and write**.
2. Put it in `.env` as `GITHUB_DISPATCH_TOKEN=...` and run `./deploy.sh` (or
   `.venv/bin/python setup_trigger.py` directly). It stores the token in Supabase Vault, schedules
   `pricewatch-check` on `*/5 * * * *`, and fires one test dispatch so a bad token fails loudly.
3. `python setup_trigger.py --remove` takes it out again. `TRIGGER_CRON` in `.env` changes the cadence.

The workflow's `concurrency` group keeps runs from overlapping if one takes longer than 5 minutes.

### Alert rules

- **Target set**: message when the price is at or below the target. Not again unless it
  falls further, or goes back above target and then drops again.
- **No target**: message on any drop compared with the previous check, ignoring drops smaller
  than `MIN_DROP_PCT` (default 1%) so rounding noise doesn't page you.
- **Restock** (per item): message when the size was sold out last check and is available now.
- **Needs attention**: 3 failed checks in a row = one message, then silence until it works again,
  and at most one such message per item per `ATTENTION_COOLDOWN_HOURS` (default 24). Stores that
  block most checks but let one through now and then would otherwise page you several times a day.

Every alert is written to the `alerts` table, which is how it never sends the same one twice.

### Being polite to the stores

Rotating desktop user agents, a random 2 to 6 second gap between requests, `robots.txt`
respected, plain HTTP first and Chromium only when a site needs it (images and fonts
blocked). At the default 5-minute interval each item is fetched about 290 times a day from GitHub's
IP ranges, which stores that already dislike bots (Zara, SSENSE) may notice sooner; raise
`CHECK_INTERVAL_MINUTES` if items start failing with 403s. "Check now" only moves an item to the
front of the next run; it can't hammer a store, and a failing item isn't retried until its normal slot.

## Local commands

```bash
python scrape.py "https://..." --size M        # scrape one URL, print what it found
python check.py --dry-run                      # check everything, print alerts, commit nothing
python check.py --due                          # what the cron runs
python check.py --due-count
python setup_supabase.py                       # (re)apply RLS policies
python migrate.py                              # copy a personal-mode SQLite file into Supabase
python app.py                                  # personal-mode local UI (SQLite only)

python tests/test_backend.py                   # checker rules on SQLite with a stubbed scraper
python tests/test_tg.py                        # Telegram link step with stubbed HTTP
python tests/test_pg.py                        # schema + RLS policies + item cap on a bundled local Postgres (pip install pgserver)
python tests/smoke_web.py                      # drives web/ in headless Chromium against an in-memory fake Supabase
```

To test the web app locally without deploying: `cd web && python3 -m http.server 8765`,
fill `web/config.js` with your Supabase URL/anon key, and add `http://localhost:8765` to
Supabase's Redirect URLs.

## Adding a store

Drop a file in `pricewatch/extractors/` with a subclass of `Extractor`, set `domains`,
and either override `extract(html, url)` or set `uses_api = True` and override
`from_api(url, fetcher)`. Set `needs_browser = True` if plain HTTP is blocked. Register it
in `EXTRACTORS`. `nike.py` and `grailed.py` are short examples of each style.

## Layout

```
web/                     the app (static HTML/JS, deployed to GitHub Pages by pages.yml)
  index.html             everything: sign-in, list, detail, edit, account menu
  config.js              written by pages.yml from repo variables
  manifest.webmanifest, icon.svg, icon-*.png   home-screen install
tests/                   backend, Postgres/RLS, Telegram, and browser smoke tests
check.py                 CLI: --due, --dry-run, --add/--list/--remove/--toggle, --telegram-setup
scrape.py                debug one URL
setup_supabase.py        row-level security policies, per-user item cap, grants
migrate.py               SQLite -> Supabase copy
deploy.sh                one-command deploy
pricewatch/
  fetch.py               user agents, delays, robots.txt, requests + Playwright
  prices.py              price string / currency parsing
  db.py                  storage: Postgres (DATABASE_URL) or SQLite, same API
  checker.py             check + alert rules, per-user routing
  extractors/            one file per store + generic fallback
  notify/                telegram (per user), twilio, ntfy, console
app.py + templates/      personal-mode Flask UI
.github/workflows/       check.yml (hourly cron), pages.yml (deploys web/)
```
