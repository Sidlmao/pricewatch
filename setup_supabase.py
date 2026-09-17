#!/usr/bin/env python3
"""One-time Supabase setup: row-level security so each signed-in user only sees their own items.
Run after setting DATABASE_URL in .env (deploy.sh runs it for you). Safe to re-run."""
import sys
import pricewatch  # noqa: F401
from pricewatch import db

if not db.DATABASE_URL:
    sys.exit("DATABASE_URL is not set")

SQL = """
-- new rows from the web app belong to whoever inserted them
ALTER TABLE items ALTER COLUMN user_id SET DEFAULT auth.uid();
ALTER TABLE profiles ALTER COLUMN user_id SET DEFAULT auth.uid();

ALTER TABLE items         ENABLE ROW LEVEL SECURITY;
ALTER TABLE price_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts        ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles      ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings      ENABLE ROW LEVEL SECURITY;   -- no policies: invisible to the web app

DROP POLICY IF EXISTS items_own ON items;
CREATE POLICY items_own ON items FOR ALL TO authenticated
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS history_own ON price_history;
CREATE POLICY history_own ON price_history FOR SELECT TO authenticated
  USING (EXISTS (SELECT 1 FROM items WHERE items.id = price_history.item_id AND items.user_id = auth.uid()));

DROP POLICY IF EXISTS alerts_own ON alerts;
CREATE POLICY alerts_own ON alerts FOR SELECT TO authenticated
  USING (EXISTS (SELECT 1 FROM items WHERE items.id = alerts.item_id AND items.user_id = auth.uid()));

DROP POLICY IF EXISTS profiles_own ON profiles;
CREATE POLICY profiles_own ON profiles FOR ALL TO authenticated
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON items, profiles TO authenticated;
GRANT SELECT ON price_history, alerts TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;
"""

conn = db.connect()
conn.executescript(SQL)
conn.close()
print("Supabase policies in place: users only see their own items, history and alerts.")
