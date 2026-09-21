#!/usr/bin/env python3
"""One-time Supabase setup: row-level security so each signed-in user only sees their own items,
plus a per-user item cap. Run after setting DATABASE_URL in .env (deploy.sh runs it for you). Safe to re-run."""
import sys
import pricewatch  # noqa: F401
from pricewatch import db, config

if not db.DATABASE_URL:
    sys.exit("DATABASE_URL is not set")

SQL = f"""
-- new rows from the web app belong to whoever inserted them
ALTER TABLE items ALTER COLUMN user_id SET DEFAULT auth.uid();
ALTER TABLE profiles ALTER COLUMN user_id SET DEFAULT auth.uid();

ALTER TABLE items         ENABLE ROW LEVEL SECURITY;
ALTER TABLE price_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts        ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles      ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings      ENABLE ROW LEVEL SECURITY;   -- no policies: invisible to the web app

-- how many items the caller already has (runs as the table owner so it can count past RLS)
CREATE OR REPLACE FUNCTION public.my_item_count() RETURNS integer
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS
  $$ SELECT count(*)::int FROM items WHERE user_id = auth.uid() $$;
REVOKE ALL ON FUNCTION public.my_item_count() FROM public;
GRANT EXECUTE ON FUNCTION public.my_item_count() TO authenticated;

DROP POLICY IF EXISTS items_own ON items;
DROP POLICY IF EXISTS items_select ON items;
DROP POLICY IF EXISTS items_insert ON items;
DROP POLICY IF EXISTS items_update ON items;
DROP POLICY IF EXISTS items_delete ON items;
CREATE POLICY items_select ON items FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY items_insert ON items FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid() AND public.my_item_count() < {config.MAX_ITEMS_PER_USER});
CREATE POLICY items_update ON items FOR UPDATE TO authenticated
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY items_delete ON items FOR DELETE TO authenticated USING (user_id = auth.uid());

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

if __name__ == "__main__":
    conn = db.connect()
    conn.executescript(SQL)
    conn.close()
    print(f"Supabase policies in place: users only see their own items, history and alerts; "
          f"{config.MAX_ITEMS_PER_USER} items per user max.")
