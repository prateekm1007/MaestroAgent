"""C1 fix — Postgres compatibility helpers (P22).

C1 from adversarial audit at f16cf66:
> SQLite is not designed for concurrent writes from multiple processes.
> Multi-replica deployment will fail.
> Fix: Migrate to PostgreSQL with proper connection pooling and advisory locks.

The migration infrastructure was ALREADY BUILT (maestro_db/sqlite_compat.py
routes all SQLite calls through SQLAlchemy with Postgres support + connection
pooling). The gap was: stores used SQLite-specific PRAGMA statements and
AUTOINCREMENT syntax that Postgres doesn't support.

This test verifies the C1 fix:
1. is_postgres() / is_sqlite() correctly detect the backend
2. safe_pragma() is a no-op on Postgres, executes on SQLite
3. autoincrement_syntax() returns the right syntax per backend
4. checkpoint_store.py and instrumentation.py use safe_pragma (regression guard)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def test_is_postgres_detects_postgres_urls():
    """C1 fix: is_postgres() returns True for PostgreSQL connection strings."""
    from maestro_db.sqlite_compat import is_postgres, is_sqlite

    # Postgres URLs
    assert is_postgres("postgresql://user:pass@localhost:5432/maestro")
    assert is_postgres("postgresql+psycopg2://user:pass@localhost:5432/maestro")
    assert is_postgres("postgres://user:pass@localhost:5432/maestro")

    # SQLite paths (should be False for is_postgres)
    assert not is_postgres("/path/to/db.sqlite")
    assert not is_postgres("sqlite:///path/to/db.sqlite")
    assert not is_postgres(":memory:")

    # is_sqlite is the inverse
    assert is_sqlite("/path/to/db.sqlite")
    assert is_sqlite(":memory:")
    assert not is_sqlite("postgresql://user:pass@localhost:5432/maestro")


def test_autoincrement_syntax_returns_correct_syntax_per_backend():
    """C1 fix: autoincrement_syntax() returns SERIAL for Postgres, AUTOINCREMENT for SQLite."""
    from maestro_db.sqlite_compat import autoincrement_syntax

    # SQLite
    assert autoincrement_syntax("/path/to/db.sqlite") == "INTEGER PRIMARY KEY AUTOINCREMENT"
    assert autoincrement_syntax(":memory:") == "INTEGER PRIMARY KEY AUTOINCREMENT"
    assert autoincrement_syntax("sqlite:///path/to/db.sqlite") == "INTEGER PRIMARY KEY AUTOINCREMENT"

    # Postgres
    assert autoincrement_syntax("postgresql://user:pass@localhost:5432/maestro") == "SERIAL PRIMARY KEY"
    assert autoincrement_syntax("postgres://user:pass@localhost:5432/maestro") == "SERIAL PRIMARY KEY"


def test_safe_pragma_is_noop_on_postgres():
    """C1 fix: safe_pragma() does NOT execute PRAGMA on Postgres backends.

    This is the key fix: stores that call safe_pragma(conn, db_path,
    "PRAGMA journal_mode=WAL") will have it be a no-op when db_path
    is a Postgres URL. Previously, the raw PRAGMA call would raise
    a syntax error on Postgres.
    """
    from maestro_db.sqlite_compat import safe_pragma, is_sqlite

    # Create a mock connection that records execute calls
    class MockConn:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params=()):
            self.executed.append(sql)
            return self

    # Postgres backend — PRAGMA should NOT be executed
    pg_conn = MockConn()
    safe_pragma(pg_conn, "postgresql://user:pass@localhost:5432/maestro", "PRAGMA journal_mode=WAL")
    safe_pragma(pg_conn, "postgresql://user:pass@localhost:5432/maestro", "PRAGMA foreign_keys=ON")
    assert pg_conn.executed == [], \
        f"PRAGMA must NOT execute on Postgres. Got: {pg_conn.executed}"

    # SQLite backend — PRAGMA SHOULD be executed
    sqlite_conn = MockConn()
    safe_pragma(sqlite_conn, "/path/to/db.sqlite", "PRAGMA journal_mode=WAL")
    safe_pragma(sqlite_conn, "/path/to/db.sqlite", "PRAGMA foreign_keys=ON")
    assert len(sqlite_conn.executed) == 2, \
        f"PRAGMA must execute on SQLite. Got: {sqlite_conn.executed}"
    assert "PRAGMA journal_mode=WAL" in sqlite_conn.executed
    assert "PRAGMA foreign_keys=ON" in sqlite_conn.executed


def test_safe_pragma_swallows_errors_on_sqlite():
    """C1 fix: safe_pragma() swallows errors gracefully (non-fatal).

    PRAGMA can fail on some SQLite configurations (e.g., in-memory DBs
    don't support WAL). The helper should log and continue, not crash.
    """
    from maestro_db.sqlite_compat import safe_pragma

    class FailingConn:
        def execute(self, sql, params=()):
            raise RuntimeError("simulated PRAGMA failure")

    # Should NOT raise — safe_pragma swallows the error
    safe_pragma(FailingConn(), "/path/to/db.sqlite", "PRAGMA journal_mode=WAL")


def test_checkpoint_store_uses_safe_pragma_not_raw_pragma():
    """C1 fix (regression guard): checkpoint_store.py uses safe_pragma, not raw PRAGMA.

    P11: verify the wiring — the module must IMPORT safe_pragma and CALL it,
    not just have it available. This test grep-verifies the source.
    """
    import inspect
    from maestro_oem import checkpoint_store

    source = inspect.getsource(checkpoint_store)

    # Must import safe_pragma
    assert "from maestro_db.sqlite_compat import" in source, \
        "checkpoint_store must import from sqlite_compat"

    # Must call safe_pragma (not raw PRAGMA)
    assert "safe_pragma(" in source, \
        "checkpoint_store must call safe_pragma() for PRAGMA statements"

    # Must NOT have raw PRAGMA execute calls (the old pattern)
    # Allow PRAGMA only inside _auto_migrate_org_id's is_sqlite branch
    # and inside the test file. The production _connect() must use safe_pragma.
    lines = source.split("\n")
    raw_pragma_in_connect = False
    for i, line in enumerate(lines):
        if 'self._conn.execute("PRAGMA' in line:
            raw_pragma_in_connect = True
    assert not raw_pragma_in_connect, \
        "checkpoint_store._connect() must use safe_pragma(), not raw self._conn.execute('PRAGMA ...')"


def test_instrumentation_uses_safe_pragma_not_raw_pragma():
    """C1 fix (regression guard): instrumentation.py uses safe_pragma, not raw PRAGMA."""
    import inspect
    from maestro_oem import instrumentation

    source = inspect.getsource(instrumentation)

    # Must import safe_pragma
    assert "from maestro_db.sqlite_compat import safe_pragma" in source, \
        "instrumentation must import safe_pragma"

    # Must call safe_pragma
    assert "safe_pragma(" in source, \
        "instrumentation must call safe_pragma() for PRAGMA statements"

    # Must NOT have raw PRAGMA execute calls
    lines = source.split("\n")
    raw_pragma = False
    for line in lines:
        if 'self._conn.execute("PRAGMA' in line:
            raw_pragma = True
    assert not raw_pragma, \
        "instrumentation must use safe_pragma(), not raw self._conn.execute('PRAGMA ...')"


def test_checkpoint_store_works_with_sqlite_backend():
    """C1 fix: checkpoint_store still works with SQLite after the safe_pragma change.

    Regression test: the safe_pragma helper must not break existing SQLite
    behavior. This test creates a real CheckpointStore with an in-memory
    SQLite DB and verifies basic CRUD works.
    """
    from maestro_oem.checkpoint_store import CheckpointStore

    store = CheckpointStore(":memory:")
    job_id = store.create_job(providers=["github"], since="1y")
    job = store.get_job(job_id)
    assert job is not None
    assert job["status"] == "pending"
    assert job["providers"] == ["github"]
    store.close()


if __name__ == "__main__":
    test_is_postgres_detects_postgres_urls()
    print("PASS: test_is_postgres_detects_postgres_urls")
    test_autoincrement_syntax_returns_correct_syntax_per_backend()
    print("PASS: test_autoincrement_syntax_returns_correct_syntax_per_backend")
    test_safe_pragma_is_noop_on_postgres()
    print("PASS: test_safe_pragma_is_noop_on_postgres")
    test_safe_pragma_swallows_errors_on_sqlite()
    print("PASS: test_safe_pragma_swallows_errors_on_sqlite")
    test_checkpoint_store_uses_safe_pragma_not_raw_pragma()
    print("PASS: test_checkpoint_store_uses_safe_pragma_not_raw_pragma")
    test_instrumentation_uses_safe_pragma_not_raw_pragma()
    print("PASS: test_instrumentation_uses_safe_pragma_not_raw_pragma")
    test_checkpoint_store_works_with_sqlite_backend()
    print("PASS: test_checkpoint_store_works_with_sqlite_backend")
    print("\nAll C1 compatibility tests passed.")
