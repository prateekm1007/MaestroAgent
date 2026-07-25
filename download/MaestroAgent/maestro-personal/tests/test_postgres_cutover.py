"""K3-DATA-002 / TICKET-13: Postgres cutover verification test.

Verifies that PostgresConnection:
1. Connects to a real Postgres instance
2. CREATE TABLE works (including INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL)
3. INSERT OR REPLACE works (→ ON CONFLICT DO UPDATE)
4. INSERT OR IGNORE works (→ ON CONFLICT DO NOTHING)
5. sqlite3.Row-style access (row["col"]) works via DictCursor
6. ? placeholders are converted to %s
7. PRAGMA statements are no-ops

This test only runs when MAESTRO_DATABASE_URL is set to a postgresql:// URL.
On SQLite (the default), it skips — the SQLite path is covered by the
existing 1500+ tests.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest


# Skip all tests in this module if Postgres isn't configured
pytestmark = pytest.mark.skipif(
    not os.environ.get("MAESTRO_DATABASE_URL", "").startswith("postgres"),
    reason="MAESTRO_DATABASE_URL not set to a postgresql:// URL — Postgres tests skipped",
)


def _get_pg_conn():
    """Get a fresh PostgresConnection for testing."""
    from maestro_personal_shell.db_util import PostgresConnection
    return PostgresConnection(os.environ["MAESTRO_DATABASE_URL"])


def _drop_test_tables(conn):
    """Clean up any leftover test tables."""
    for table in ["k3_test_signals", "k3_test_upsert", "k3_test_autoincrement", "k3_test_ignore"]:
        try:
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        except Exception:
            pass
    conn.commit()


def test_postgres_connection_basic():
    """PostgresConnection connects and can execute a simple query."""
    conn = _get_pg_conn()
    try:
        cur = conn.execute("SELECT 1 AS val")
        row = cur.fetchone()
        assert row is not None
        # DictCursor supports both index and name access
        assert row[0] == 1
        assert row["val"] == 1
    finally:
        conn.close()


def test_postgres_create_table_with_text_primary_key():
    """CREATE TABLE with TEXT PRIMARY KEY works on Postgres."""
    conn = _get_pg_conn()
    try:
        _drop_test_tables(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS k3_test_signals (
                signal_id TEXT PRIMARY KEY,
                entity TEXT NOT NULL,
                text TEXT NOT NULL,
                user_email TEXT NOT NULL
            )
        """)
        conn.commit()
        # Verify the table was created
        cur = conn.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'k3_test_signals'
            ORDER BY ordinal_position
        """)
        cols = [r[0] for r in cur.fetchall()]
        assert cols == ["signal_id", "entity", "text", "user_email"]
    finally:
        _drop_test_tables(conn)
        conn.close()


def test_postgres_create_table_with_autoincrement():
    """CREATE TABLE with INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY."""
    conn = _get_pg_conn()
    try:
        _drop_test_tables(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS k3_test_autoincrement (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
        """)
        conn.commit()
        # Verify the column type is integer (SERIAL creates int4)
        cur = conn.execute("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'k3_test_autoincrement' AND column_name = 'id'
        """)
        row = cur.fetchone()
        assert row is not None
        # SERIAL creates an `integer` column with a sequence
        assert row[0] in ("integer", "smallint", "bigint")
    finally:
        _drop_test_tables(conn)
        conn.close()


def test_postgres_insert_or_replace_upsert():
    """INSERT OR REPLACE → ON CONFLICT DO UPDATE (true upsert)."""
    conn = _get_pg_conn()
    try:
        _drop_test_tables(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS k3_test_upsert (
                signal_id TEXT PRIMARY KEY,
                entity TEXT NOT NULL,
                text TEXT NOT NULL
            )
        """)
        conn.commit()

        # First insert
        conn.execute(
            "INSERT OR REPLACE INTO k3_test_upsert (signal_id, entity, text) VALUES (?, ?, ?)",
            ("sig-1", "Maria", "I will send the proposal"),
        )
        conn.commit()

        # Second insert with same PK — should UPDATE, not fail
        conn.execute(
            "INSERT OR REPLACE INTO k3_test_upsert (signal_id, entity, text) VALUES (?, ?, ?)",
            ("sig-1", "Maria", "I will send the proposal by Friday"),
        )
        conn.commit()

        # Verify only one row exists with the updated text
        cur = conn.execute("SELECT signal_id, entity, text FROM k3_test_upsert WHERE signal_id = ?", ("sig-1",))
        row = cur.fetchone()
        assert row is not None
        assert row["text"] == "I will send the proposal by Friday"
        assert row["entity"] == "Maria"

        # Verify count is 1 (not 2)
        cur = conn.execute("SELECT COUNT(*) FROM k3_test_upsert")
        assert cur.fetchone()[0] == 1
    finally:
        _drop_test_tables(conn)
        conn.close()


def test_postgres_insert_or_ignore():
    """INSERT OR IGNORE → ON CONFLICT DO NOTHING (skip duplicates)."""
    conn = _get_pg_conn()
    try:
        _drop_test_tables(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS k3_test_ignore (
                signal_id TEXT PRIMARY KEY,
                entity TEXT NOT NULL
            )
        """)
        conn.commit()

        # First insert succeeds
        conn.execute(
            "INSERT OR IGNORE INTO k3_test_ignore (signal_id, entity) VALUES (?, ?)",
            ("sig-1", "Maria"),
        )
        conn.commit()

        # Second insert with same PK — should be ignored, not fail
        conn.execute(
            "INSERT OR IGNORE INTO k3_test_ignore (signal_id, entity) VALUES (?, ?)",
            ("sig-1", "Alex"),  # different entity, but same PK — should be ignored
        )
        conn.commit()

        # Verify the original row is preserved (entity = Maria, not Alex)
        cur = conn.execute("SELECT entity FROM k3_test_ignore WHERE signal_id = ?", ("sig-1",))
        row = cur.fetchone()
        assert row is not None
        assert row["entity"] == "Maria"
    finally:
        _drop_test_tables(conn)
        conn.close()


def test_postgres_pragma_noop():
    """PRAGMA statements are no-ops on Postgres (not errors)."""
    conn = _get_pg_conn()
    try:
        # These should all be no-ops, not raise
        result = conn.execute("PRAGMA journal_mode = WAL")
        assert result is conn  # returns self, not a cursor
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA synchronous = NORMAL")
    finally:
        conn.close()


def test_postgres_row_access_by_name():
    """Rows support sqlite3.Row-style access (row["col"]) via DictCursor."""
    conn = _get_pg_conn()
    try:
        _drop_test_tables(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS k3_test_signals (
                signal_id TEXT PRIMARY KEY,
                entity TEXT NOT NULL,
                text TEXT NOT NULL,
                user_email TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO k3_test_signals (signal_id, entity, text, user_email) VALUES (?, ?, ?, ?)",
            ("sig-1", "Maria Garcia", "I will send the proposal", "alice@example.com"),
        )
        conn.commit()

        # Access by column name (the sqlite3.Row pattern used in 14 places)
        cur = conn.execute("SELECT signal_id, entity, text, user_email FROM k3_test_signals WHERE signal_id = ?", ("sig-1",))
        row = cur.fetchone()
        assert row is not None
        assert row["signal_id"] == "sig-1"
        assert row["entity"] == "Maria Garcia"
        assert row["text"] == "I will send the proposal"
        assert row["user_email"] == "alice@example.com"

        # Index access should also work (tuple-style)
        assert row[0] == "sig-1"
        assert row[1] == "Maria Garcia"
    finally:
        _drop_test_tables(conn)
        conn.close()


def test_postgres_question_mark_placeholders():
    """? placeholders are converted to %s for psycopg2."""
    conn = _get_pg_conn()
    try:
        cur = conn.execute("SELECT ? AS a, ? AS b", (42, "hello"))
        row = cur.fetchone()
        assert row is not None
        assert row["a"] == 42
        assert row["b"] == "hello"
    finally:
        conn.close()
