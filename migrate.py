#!/usr/bin/env python3
"""Copy everything from the SQLite file into the Postgres database in DATABASE_URL (ids preserved).
Safe to re-run: rows that already exist are skipped."""
import os, sqlite3, sys
import pricewatch  # noqa: F401  loads .env
from pricewatch import db

if not db.DATABASE_URL:
    sys.exit("DATABASE_URL is not set in .env")
if not os.path.exists(db.DB_PATH):
    sys.exit(f"no SQLite file at {db.DB_PATH}")
src = sqlite3.connect(db.DB_PATH); src.row_factory = sqlite3.Row
dst = db.connect()
counts = {}
for table in ("items", "price_history", "alerts"):
    rows = src.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
    n = 0
    for r in rows:
        cols = r.keys()
        if dst.execute(f"SELECT 1 FROM {table} WHERE id = ?", (r["id"],)).fetchone():
            continue
        dst.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", tuple(r))
        n += 1
    # keep the identity counter ahead of the copied ids
    dst.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)")
    counts[table] = (n, len(rows))
dst.commit(); dst.close()
for t, (n, total) in counts.items():
    print(f"{t}: copied {n} of {total}")
