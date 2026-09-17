#!/usr/bin/env bash
# One-command deploy to GitHub: creates a private repo, pushes, sets secrets from .env,
# enables the cron + dashboard, and kicks off the first check.
#
#   ./deploy.sh              (repo will be called "pricewatch")
#   ./deploy.sh my-tracker   (custom repo name)
#
# Run it again any time you change code or .env; it just pushes and re-syncs secrets.
set -euo pipefail
cd "$(dirname "$0")"
REPO_NAME="${1:-pricewatch}"
LOCAL_ONLY="${LOCAL_ONLY:-0}"

# --- gh CLI ---------------------------------------------------------------
GH="$(command -v gh || true)"
[ -z "$GH" ] && [ -x "$HOME/.local/bin/gh" ] && GH="$HOME/.local/bin/gh"
if [ -z "$GH" ]; then
  echo "Installing GitHub CLI to ~/.local/bin ..."
  ARCH=$([ "$(uname -m)" = "arm64" ] && echo arm64 || echo amd64)
  VER=$(curl -sI https://github.com/cli/cli/releases/latest | grep -i '^location:' | sed -E 's#.*/tag/v([0-9.]+).*#\1#' | tr -d '\r')
  TMP=$(mktemp -d); curl -sL -o "$TMP/gh.zip" "https://github.com/cli/cli/releases/download/v${VER}/gh_${VER}_macOS_${ARCH}.zip"
  (cd "$TMP" && unzip -qo gh.zip); mkdir -p "$HOME/.local/bin"; cp "$TMP"/gh_*/bin/gh "$HOME/.local/bin/gh"; chmod +x "$HOME/.local/bin/gh"
  GH="$HOME/.local/bin/gh"
fi

# --- local git repo -------------------------------------------------------
if [ ! -d .git ]; then
  git init -q -b main 2>/dev/null || git init -q
fi
if [ -z "$(git config user.email || true)" ]; then
  git config user.name "${USER:-pricewatch}"
  git config user.email "${USER:-pricewatch}@users.noreply.github.com"
fi
git add -A
git commit -qm "pricewatch $(date -u +'%Y-%m-%d %H:%M')" 2>/dev/null || echo "nothing new to commit"
if [ "$LOCAL_ONLY" = "1" ]; then echo "local repo ready (LOCAL_ONLY=1, stopping before GitHub)"; exit 0; fi

# --- GitHub login ---------------------------------------------------------
if ! "$GH" auth status >/dev/null 2>&1; then
  echo "Log in to GitHub (a browser window will open) ..."
  "$GH" auth login --web --git-protocol https
fi
"$GH" auth setup-git >/dev/null 2>&1 || true

# --- create or push the repo ---------------------------------------------
if git remote get-url origin >/dev/null 2>&1; then
  git push -u origin HEAD
else
  "$GH" repo create "$REPO_NAME" --private --source . --push
fi
FULL=$("$GH" repo view --json nameWithOwner -q .nameWithOwner)
OWNER=${FULL%%/*}; NAME=${FULL##*/}

# --- secrets from .env ----------------------------------------------------
[ -f .env ] && set -a && . ./.env && set +a
NOTIFIER="${NOTIFIER:-twilio}"
if [ "$NOTIFIER" = "twilio" ] && [ -z "${TWILIO_SID:-}" ] && [ -n "${TELEGRAM_TOKEN:-}" ]; then
  NOTIFIER=telegram
fi
if [ "$NOTIFIER" = "twilio" ] && [ -z "${TWILIO_SID:-}" ]; then
  echo "No Twilio credentials in .env yet -> using free ntfy.sh push notifications for now."
  NOTIFIER=ntfy
fi
if [ "$NOTIFIER" = "ntfy" ]; then
  if [ -z "${NTFY_TOPIC:-}" ]; then
    NTFY_TOPIC="pricewatch-$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 10)"
    printf '\nNOTIFIER=ntfy\nNTFY_TOPIC=%s\n' "$NTFY_TOPIC" >> .env
  fi
  "$GH" secret set NTFY_TOPIC -b "$NTFY_TOPIC" -R "$FULL"
fi
for k in TWILIO_SID TWILIO_TOKEN TWILIO_FROM MY_PHONE TELEGRAM_TOKEN TELEGRAM_CHAT_ID DATABASE_URL; do
  v="${!k:-}"; [ -n "$v" ] && "$GH" secret set "$k" -b "$v" -R "$FULL"
done
"$GH" variable set NOTIFIER -b "$NOTIFIER" -R "$FULL"

# --- permissions, Pages, first run ---------------------------------------
"$GH" api -X PUT "repos/$FULL/actions/permissions/workflow" -f default_workflow_permissions=write -F can_approve_pull_request_reviews=false >/dev/null
"$GH" api -X POST "repos/$FULL/pages" -f build_type=workflow >/dev/null 2>&1 || true
# Workflows register a few seconds after the first push; retry once.
"$GH" workflow run check.yml -R "$FULL" >/dev/null 2>&1 || { sleep 6; "$GH" workflow run check.yml -R "$FULL" >/dev/null 2>&1 || true; }

cat <<MSG

Deployed.

  Dashboard (live after the first run, ~2 min):  https://$OWNER.github.io/$NAME/
  Add / remove items:  https://github.com/$FULL/actions/workflows/manage.yml  -> "Run workflow"
  Runs & logs:         https://github.com/$FULL/actions

MSG
if [ -n "${DATABASE_URL:-}" ]; then
  echo "Storage: Supabase/Postgres (DATABASE_URL). The SQLite file in the repo is no longer used."
else
  echo "Storage: SQLite file committed to the repo. Set DATABASE_URL in .env to use Supabase instead."
fi
if [ "$NOTIFIER" = "telegram" ]; then
  echo "Notifications: Telegram bot (chat id $TELEGRAM_CHAT_ID)."
fi
if [ "$NOTIFIER" = "ntfy" ]; then
cat <<MSG
Notifications: install the ntfy app (iOS/Android), tap +, subscribe to topic:

    $NTFY_TOPIC

That's it. To switch to SMS later, put your Twilio values in .env, set NOTIFIER=twilio, and run ./deploy.sh again.
MSG
fi
