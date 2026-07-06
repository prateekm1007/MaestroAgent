"""Smoke tests for maestro_db — the SQLite/PostgreSQL compatibility shim.

Principle 2: this was the last backend module with zero test coverage.
The shim is critical because every store (long_term, checkpoints, cost_ledger,
import_state) routes through it. If the shim silently breaks parameter binding
or row access, every store breaks.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from maestro_db.db_helper import DBCursor, DBRow, _get_engine, db_execute, db_execute_write
from maestro_db import sqlite_compat as sqlite3
from maestro_db.sqlite_compat import _HAS_SQLALCHEMY


# ---------------------------------------------------------------------------
# DBRow — dual dict/attribute access
# ---------------------------------------------------------------------------


def test_dbrow_supports_dict_access() -> None:
    row = DBRow({"name": "alice", "age": 30})
    assert row["name"] == "alice"
    assert row["age"] == 30


def test_dbrow_supports_attribute_access() -> None:
    """DBRow must support attribute access so code like `row.name` works."""
    row = DBRow({"name": "alice"})
    assert row.name == "alice"


def test_dbrow_attribute_access_raises_attributeerror_for_missing() -> None:
    """A missing attribute must raise AttributeError (not KeyError or return None).

    Principle 6: fail loudly. Silent None returns would hide bugs."""
    row = DBRow({"name": "alice"})
    with pytest.raises(AttributeError):
        _ = row.nonexistent


# ---------------------------------------------------------------------------
# sqlite_compat — the shim that lets stores work with SQLite AND Postgres
# ---------------------------------------------------------------------------


def test_sqlite_compat_connect_returns_a_connection(tmp_path: Path) -> None:
    """sqlite_compat.connect() must return a working connection object."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    assert conn is not None
    conn.close()


def test_sqlite_compat_row_factory_works(tmp_path: Path) -> None:
    """sqlite3.Row must support both index and key access (the compat contract)."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("CREATE TABLE t(id INTEGER, name TEXT); INSERT INTO t VALUES (1, 'alice');")
    conn.commit()

    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id, name FROM t WHERE id = 1").fetchone()
    assert row is not None
    assert row["id"] == 1
    assert row["name"] == "alice"
    conn.close()


def test_sqlite_compat_executescript_creates_tables(tmp_path: Path) -> None:
    """executescript() must run multiple statements (used by every SCHEMA constant)."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE a(id INTEGER PRIMARY KEY);
        CREATE TABLE b(id INTEGER PRIMARY KEY);
        CREATE INDEX idx_a ON a(id);
    """)
    conn.commit()
    # Verify both tables exist.
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = [t["name"] if isinstance(t, dict) else t[0] for t in tables]
    assert "a" in table_names
    assert "b" in table_names
    conn.close()


def test_sqlite_compat_parameterized_query(tmp_path: Path) -> None:
    """Parameterized queries must bind correctly (security: prevents SQL injection)."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t(name TEXT)")
    conn.execute("INSERT INTO t VALUES (?)", ("alice",))
    conn.execute("INSERT INTO t VALUES (?)", ("bob",))
    conn.commit()

    result = conn.execute("SELECT name FROM t WHERE name = ?", ("alice",)).fetchone()
    assert result is not None
    # Use key access — works for both sqlite3.Row and dict compat.
    assert result["name"] == "alice"
    conn.close()


# ---------------------------------------------------------------------------
# get_engine — engine caching
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_SQLALCHEMY, reason="SQLAlchemy not installed (optional dep)")
def test_get_engine_caches_engines(tmp_path: Path) -> None:
    """_get_engine() must cache by URL — repeated calls return the same engine."""
    db_path = str(tmp_path / "test.db")
    url = f"sqlite:///{db_path}"
    engine1 = _get_engine(url)
    engine2 = _get_engine(url)
    assert engine1 is engine2, "_get_engine must cache — repeated calls return the same object"


@pytest.mark.skipif(not _HAS_SQLALCHEMY, reason="SQLAlchemy not installed (optional dep)")
def test_get_engine_different_urls_return_different_engines(tmp_path: Path) -> None:
    db_path1 = str(tmp_path / "a.db")
    db_path2 = str(tmp_path / "b.db")
    e1 = _get_engine(f"sqlite:///{db_path1}")
    e2 = _get_engine(f"sqlite:///{db_path2}")
    assert e1 is not e2
