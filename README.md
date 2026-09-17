# pricewatch

Track prices on clothes you want. Sign in, paste a product link, and get a Telegram
message when the price drops (or when your size is back in stock).

- **Web app**: sign in with Google or an email link, add items by link, see price history.
  Hosted free on GitHub Pages.
- **Database + login**: Supabase (free tier). Row-level security means each user only
  ever sees their own items.
- **Scraping**: a GitHub Actions cron runs hourly and checks whatever is due (every item
  about every 6 hours, new items within the hour). Playwright handles the JS-heavy sites.
- **Alerts**: each user connects the Telegram bot once; alerts go to their own chat.

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
| anything else | JSON-LD offers, then og:/product: meta tags, then embedded JSON, then Chromium | overall only |

Sale prices are handled: the tracker records what you'd pay now and remembers the
struck-through original separately. Currency symbols and ISO codes are parsed.

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
web/index.html  ── supabase-js ──>  Supabase (auth + Postgres, RLS)  <── psycopg ──  check.py (GitHub Actions, hourly)
      │                                                                                     │
  GitHub Pages                                                                    Telegram bot -> each user's chat
```

- The browser talks to Supabase directly with the public anon key. Policies in
  `setup_supabase.py` restrict every table to `user_id = auth.uid()`.
- The cron connects as the database owner (bypasses RLS), scrapes items that are due,
  appends to `price_history`, and decides alerts.
- "Connect Telegram" opens `t.me/<bot>?start=<user_id>`. The next cron run reads the
  bot's messages, links that chat to the user, and confirms with a message.

### Alert rules

- **Target set**: message when the price is at or below the target. Not again unless it
  falls further, or goes back above target and then drops again.
- **No target**: message on any drop compared with the previous check.
- **Restock** (per item): message when the size was sold out last check and is available now.
- **Needs attention**: 3 failed checks in a row = one message, then silence until it works again.

Every alert is written to the `alerts` table, which is how it never sends the same one twice.

### Being polite to the stores

Rotating desktop user agents, a random 2 to 6 second gap between requests, `robots.txt`
respected, plain HTTP first and Chromium only when a site needs it (images and fonts
blocked). One check per item every 6 hours is far below anything a store notices.

## Local commands

```bash
python scrape.py "https://..." --size M        # scrape one URL, print what it found
python check.py --dry-run                      # check everything, print alerts, commit nothing
python check.py --due                          # what the cron runs
python check.py --due-count
python setup_supabase.py                       # (re)apply RLS policies
python migrate.py                              # copy a personal-mode SQLite file into Supabase
python app.py                                  # personal-mode local UI (SQLite only)
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
check.py                 CLI: --due, --dry-run, --add/--list/--remove/--toggle, --telegram-setup
scrape.py                debug one URL
setup_supabase.py        row-level security policies + grants
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
