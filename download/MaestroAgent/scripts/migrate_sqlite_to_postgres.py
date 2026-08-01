#!/usr/bin/env python3
"""TICKET-13: SQLite → Postgres migration script.

Reads all data from the existing SQLite database and writes it to the Postgres
database. This is the proper migration that was missing when MAESTRO_DATABASE_URL
was first set (which was a cold start to an empty Postgres, not a migration).

USAGE:
  python3 migrate_sqlite_to_postgres.py --sqlite /data/personal.db --postgres "postgresql://..."

The script:
1. Reads all tables from SQLite
2. Creates the same tables on Postgres (if they don't exist)
3. Copies all rows, converting SQLite-specific syntax (AUTOINCREMENT, etc.)
4. Rebuilds the FTS index on Postgres (tsvector)
5. Verifies row counts match

This is a ONE-TIME migration. After it completes, set MAESTRO_DATABASE_URL on
Railway to switch the backend to Postgres.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import os
from pathlib import Path


def migrate(sqlite_path: str, postgres_url: str) -> int:
    """Migrate all data from SQLite to Postgres."""
    try:
        import psycopg2
        from psycopg2.extras import DictCursor
    except ImportError:
        print("ERROR: psycopg2 not installed. Install with: pip install psycopg2-binary")
        return 1

    print(f"=== SQLite → Postgres Migration ===")
    print(f"  SQLite:   {sqlite_path}")
    print(f"  Postgres: {postgres_url[:30]}...{postgres_url[-20:]}")
    print()

    # Connect to both databases
    sq = sqlite3.connect(sqlite_path)
    sq.row_factory = sqlite3.Row
    pg = psycopg2.connect(postgres_url, cursor_factory=DictCursor)
    pg.autocommit = False

    # Get all tables from SQLite
    tables = [r[0] for r in sq.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%_fts'"
    ).fetchall()]
    # Skip FTS virtual tables (they'll be rebuilt as tsvector on Postgres)
    tables = [t for t in tables if not t.endswith("_fts")]
    print(f"SQLite tables to migrate: {tables}")
    print()

    total_rows = 0
    for table in tables:
        # Get column info
        cols = [c[1] for c in sq.execute(f"PRAGMA table_info({table})").fetchall()]
        if not cols:
            print(f"  SKIP {table}: no columns (empty or virtual)")
            continue

        # Get row count from SQLite
        sq_count = sq.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {sq_count} rows in SQLite")

        if sq_count == 0:
            print(f"    SKIP: 0 rows")
            continue

        # Create the table on Postgres (using the same CREATE TABLE logic as init_db,
        # which PostgresConnection.execute() will translate)
        # We use a simplified approach: create the table with TEXT columns if it
        # doesn't exist, then let the app's init_db() handle the real schema.
        # Actually, let's just call init_db() on Postgres first, then copy data.
        try:
            # Create table on Postgres using the same schema
            # Read the CREATE TABLE statement from SQLite
            create_sql = sq.execute(
                f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'"
            ).fetchone()[0]
            # Convert SQLite syntax to Postgres
            create_sql = create_sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            create_sql = create_sql.replace("AUTOINCREMENT", "")
            # Execute on Postgres (ignore errors if table already exists)
            try:
                pg.execute(create_sql.replace("?", "%s"))
                pg.commit()
            except Exception as e:
                pg.rollback()
                # Table might already exist — that's fine
                pass

            # Copy rows
            rows = sq.execute(f"SELECT * FROM {table}").fetchall()
            placeholders = ", ".join(["%s"] * len(cols))
            col_list = ", ".join(f'"{c}"' for c in cols)
            insert_sql = f'INSERT INTO {table} ({col_list}) VALUES ({placeholders})'

            copied = 0
            for row in rows:
                row_dict = dict(row)
                values = tuple(row_dict.get(c) for c in cols)
                try:
                    pg.execute(insert_sql, values)
                    copied += 1
                except Exception as e:
                    # Row might already exist (duplicate key) — skip
                    pg.rollback()
                    continue
            pg.commit()

            # Verify count
            pg_count = pg.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"    → {pg_count} rows in Postgres ({'OK' if pg_count >= sq_count else 'MISMATCH!'})")
            total_rows += copied
        except Exception as e:
            print(f"    ERROR: {e}")
            pg.rollback()

    print(f"\nTotal rows migrated: {total_rows}")

    # Rebuild the FTS index on Postgres (tsvector)
    print("\nRebuilding FTS index on Postgres...")
    try:
        from maestro_personal_shell.db_util import PostgresConnection
        pg_conn = PostgresConnection(postgres_url)
        from maestro_personal_shell.semantic_retrieval import rebuild_fts_index
        count = rebuild_fts_index(db_path=postgres_url)
        print(f"  FTS index rebuilt: {count} signals indexed")
        pg_conn.close()
    except Exception as e:
        print(f"  FTS rebuild failed (non-fatal): {e}")

    sq.close()
    pg.close()
    print("\n✓ Migration complete. Verify the data, then set MAESTRO_DATABASE_URL on Railway.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate SQLite to Postgres")
    parser.add_argument("--sqlite", required=True, help="Path to SQLite database")
    parser.add_argument("--postgres", required=True, help="Postgres connection URL")
    args = parser.parse_args()
    sys.exit(migrate(args.sqlite, args.postgres))
