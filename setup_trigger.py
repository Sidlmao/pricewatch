#!/usr/bin/env python3
"""Make the price check really run every 5 minutes.

GitHub's `schedule:` trigger is best-effort: on this repo it fired every few hours no matter what the
cron line said. This installs a pg_cron job inside Supabase that calls GitHub's workflow_dispatch API
every 5 minutes (via pg_net), which starts check.yml on time. Needs in .env:

  DATABASE_URL           the Supabase connection string (already used by the checker)
  GITHUB_DISPATCH_TOKEN  a fine-grained personal access token for this repo with
                         "Actions: read and write" (github.com -> Settings -> Developer settings)

The token is kept in Supabase Vault, not in the job text. Safe to re-run; --remove takes it out again.
deploy.sh runs this automatically when GITHUB_DISPATCH_TOKEN is set."""
import os
import re
import subprocess
import sys
import time

import pricewatch  # noqa: F401  loads .env
from pricewatch import db

JOB = "pricewatch-check"
SECRET = "pricewatch_github_token"
EVERY = os.getenv("TRIGGER_CRON", "*/5 * * * *")


def repo_slug() -> str:
    slug = os.getenv("GITHUB_REPO")
    if not slug:
        try:
            url = subprocess.check_output(["git", "remote", "get-url", "origin"], text=True).strip()
        except Exception:
            url = ""
        m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", url)
        if not m:
            sys.exit("Can't tell which GitHub repo this is; set GITHUB_REPO=owner/name in .env")
        slug = m.group(1)
    return slug


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not db.DATABASE_URL:
        sys.exit("DATABASE_URL is not set")
    conn = db.connect()
    if "--remove" in argv:
        conn.execute("SELECT cron.unschedule(jobid) FROM cron.job WHERE jobname = ?", (JOB,))
        conn.execute("DELETE FROM vault.secrets WHERE name = ?", (SECRET,))
        conn.commit(); conn.close()
        print("Removed the Supabase trigger; the workflow is back to GitHub's own schedule."); return 0

    token = os.getenv("GITHUB_DISPATCH_TOKEN")
    if not token:
        sys.exit("GITHUB_DISPATCH_TOKEN is not set (see .env.example)")
    slug = repo_slug()
    url = f"https://api.github.com/repos/{slug}/actions/workflows/check.yml/dispatches"

    for stmt in ("CREATE EXTENSION IF NOT EXISTS pg_cron",
                 "CREATE EXTENSION IF NOT EXISTS pg_net",
                 "GRANT USAGE ON SCHEMA cron TO postgres",
                 "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA cron TO postgres"):
        try:
            conn.execute(stmt); conn.commit()
        except Exception as e:  # already enabled through the dashboard, or not permitted: keep going
            conn.rollback(); print(f"  note: {stmt.split(' ON ')[0]}: {str(e).splitlines()[0]}")

    # token lives in Vault; the job reads it at run time so it never appears in cron.job
    conn.execute("DELETE FROM vault.secrets WHERE name = ?", (SECRET,))
    conn.execute("SELECT vault.create_secret(?, ?, ?)", (token, SECRET, "fine-grained PAT that may start check.yml"))
    call = f"""SELECT net.http_post(
      url := '{url}',
      body := '{{"ref":"main"}}'::jsonb,
      headers := jsonb_build_object(
        'Authorization', 'Bearer ' || (SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name = '{SECRET}'),
        'Accept', 'application/vnd.github+json', 'Content-Type', 'application/json',
        'User-Agent', 'pricewatch', 'X-GitHub-Api-Version', '2022-11-28'))"""
    conn.execute("SELECT cron.unschedule(jobid) FROM cron.job WHERE jobname = ?", (JOB,))
    conn.execute("SELECT cron.schedule(?, ?, ?)", (JOB, EVERY, call))
    conn.commit()

    # fire one dispatch now so a bad token shows up here instead of silently in the cron log
    rid = conn.execute(call).fetchone()
    rid = list(rid.values())[0] if isinstance(rid, dict) else rid[0]
    conn.commit()
    status = None
    for _ in range(15):
        time.sleep(1)
        row = conn.execute("SELECT status_code, content FROM net._http_response WHERE id = ?", (rid,)).fetchone()
        if row:
            status = row["status_code"] if isinstance(row, dict) else row[0]
            body = row["content"] if isinstance(row, dict) else row[1]
            break
    conn.close()
    if status == 204:
        print(f"Supabase now starts {slug} check.yml on '{EVERY}'. Test dispatch accepted (204); "
              f"watch it at https://github.com/{slug}/actions/workflows/check.yml")
        return 0
    print(f"Job installed, but the test dispatch returned {status}: {str(body)[:300] if status else 'no response yet'}")
    print("Check that the token is a fine-grained PAT for this repo with Actions: read and write, then re-run.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
