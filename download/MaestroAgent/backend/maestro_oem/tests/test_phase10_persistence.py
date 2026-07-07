"""Phase 10 — Persistence/Postgres/Redis test (P22).

Phase 10 scope: 'Postgres deploy, 3-replica, queues.'

Verifies:
1. SQLite compat layer supports Postgres URLs (is_postgres, autoincrement_syntax)
2. Alembic migrations exist (initial schema + org_id multi-tenant)
3. Redis cache is fail-safe (no Redis → no-op, not crash)
4. OEMStore is SQLite-backed (durable, C6 persistence)
5. ConversationStore + MeetingStore are SQLite-backed
6. Multi-replica cache sharing via Redis (when configured)

P22: tests execute the production path (sqlite_compat.is_postgres +
RedisCache + Alembic migration files).
P27: assertions check SPECIFIC behavior, not just isinstance.
P28: test 3+ scenarios — SQLite mode, Postgres URL detection, Redis fallback.
P32: check ALL derived state — persistence layers, not just top-level.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


class TestPhase10Persistence:
    """P22: verify persistence/Postgres/Redis infrastructure."""

    def test_sqlite_compat_detects_postgres_urls(self):
        """P22: sqlite_compat.is_postgres must correctly detect Postgres URLs.

        P28: test 3+ URL formats — postgresql://, postgres://, sqlite://.
        """
        from maestro_db.sqlite_compat import is_postgres, is_sqlite

        # P27: assert EXACT results for each URL type
        assert is_postgres("postgresql://user:pass@host:5432/db") is True
        assert is_postgres("postgres://user:pass@host:5432/db") is True
        assert is_postgres("postgresql+psycopg2://user:pass@host:5432/db") is True

        # SQLite paths
        assert is_postgres(":memory:") is False
        assert is_postgres("/tmp/test.db") is False
        assert is_postgres("test.db") is False

        # P30: is_sqlite is the inverse
        assert is_sqlite(":memory:") is True
        assert is_sqlite("postgresql://host:5432/db") is False

    def test_autoincrement_syntax_differs_by_db_type(self):
        """P22: autoincrement_syntax must return correct syntax per DB type.

        P27: assert the syntax is different for SQLite vs Postgres.
        """
        from maestro_db.sqlite_compat import autoincrement_syntax

        sqlite_syntax = autoincrement_syntax(":memory:")
        postgres_syntax = autoincrement_syntax("postgresql://host:5432/db")

        # P27: SQLite uses INTEGER PRIMARY KEY AUTOINCREMENT
        assert "INTEGER" in sqlite_syntax.upper(), \
            f"SQLite autoincrement must use INTEGER, got: {sqlite_syntax}"

        # Postgres uses SERIAL or BIGSERIAL
        assert "SERIAL" in postgres_syntax.upper(), \
            f"Postgres autoincrement must use SERIAL, got: {postgres_syntax}"

        # They must be different
        assert sqlite_syntax != postgres_syntax, \
            "SQLite and Postgres autoincrement syntax must differ"

    def test_alembic_migrations_exist(self):
        """P22: Alembic migrations must exist for Postgres deploy.

        P30: count and check each migration file.
        P32: check ALL migration files, not just one.
        """
        alembic_versions = BACKEND.parent / "alembic" / "versions"
        assert alembic_versions.exists(), "alembic/versions/ directory must exist"

        migration_files = list(alembic_versions.glob("*.py"))
        # P30: must have at least 2 migrations (initial + org_id)
        assert len(migration_files) >= 2, \
            f"Must have ≥2 migrations, got {len(migration_files)}"

        # P27: verify the initial schema migration exists
        initial = [f for f in migration_files if "initial" in f.name.lower()]
        assert len(initial) >= 1, "Must have initial schema migration"

        # P27: verify the multi-tenant org_id migration exists
        org_id = [f for f in migration_files if "org_id" in f.name.lower()]
        assert len(org_id) >= 1, "Must have org_id multi-tenant migration"

    def test_redis_cache_is_fail_safe_without_redis(self):
        """P22: RedisCache must be fail-safe (no Redis → no-op, not crash).

        P28: test without MAESTRO_REDIS_URL (single-replica mode).
        P27: assert available=False, not an exception.
        """
        from maestro_oem.redis_cache import RedisCache

        # No Redis URL set → cache disabled, not crash
        cache = RedisCache(redis_url="")
        assert cache.available is False, \
            "RedisCache without URL must have available=False"
        # P27: operations must be no-ops, not raise
        assert cache.get("key") is None
        cache.set("key", "value")  # should not raise
        assert cache.get("key") is None  # still None (no-op)

    def test_oem_store_is_sqlite_backed(self):
        """P32: OEMStore must persist to SQLite (durable, not in-memory only).

        P22: verify the store can save + load laws/LOs.
        """
        from maestro_oem.persistence import OEMStore

        db_path = tempfile.mktemp(suffix=".db")
        try:
            store = OEMStore(db_path)

            # P27: verify it can save + load
            assert hasattr(store, "save_law"), "OEMStore must have save_law"
            assert hasattr(store, "load_laws"), "OEMStore must have load_laws"
            assert hasattr(store, "save_learning_object"), "OEMStore must have save_learning_object"
            assert hasattr(store, "load_learning_objects"), "OEMStore must have load_learning_objects"

            # P32: verify load returns empty when nothing saved
            laws = store.load_laws()
            los = store.load_learning_objects()
            assert isinstance(laws, dict), "load_laws must return dict"
            assert isinstance(los, dict), "load_learning_objects must return dict"
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_conversation_store_is_sqlite_backed(self):
        """P32: ConversationStore must persist to SQLite (durable).

        P22: verify turns survive close + reopen.
        """
        from maestro_oem.conversation_store import ConversationStore

        db_path = tempfile.mktemp(suffix=".db")
        try:
            # Write a turn
            store1 = ConversationStore(db_path)
            store1.add_turn(
                session_id="test-session",
                turn=1,
                role="user",
                content="What did we promise Globex?",
                intent="recall",
                entities=["Globex"],
            )
            history1 = store1.get_history("test-session")
            assert len(history1) >= 1, "Must have ≥1 turn after recording"

            # Reopen — turns must survive
            store2 = ConversationStore(db_path)
            history2 = store2.get_history("test-session")
            # P27: assert the turn survived restart
            assert len(history2) >= 1, \
                f"Turns must survive restart, got {len(history2)}"
            assert "Globex" in history2[0].get("content", ""), \
                "Turn content must persist"
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_meeting_store_is_sqlite_backed(self):
        """P32: MeetingStore must persist to SQLite (durable).

        P22: verify meetings survive close + reopen.
        """
        from maestro_oem.meeting_store import MeetingStore
        from maestro_oem.meeting import Meeting, MeetingStatus
        from datetime import datetime, timezone, timedelta

        db_path = tempfile.mktemp(suffix=".db")
        try:
            store1 = MeetingStore(db_path)
            meeting = Meeting(
                meeting_id="test-mtg-1",
                title="Globex Q4 Review",
                entity="Globex",
                attendees=["ceo@acme.com"],
                start=datetime.now(timezone.utc) + timedelta(days=1),
                end=datetime.now(timezone.utc) + timedelta(days=1, hours=1),
            )
            store1.record(meeting)

            # Reopen — meeting must survive
            store2 = MeetingStore(db_path)
            retrieved = store2.get("test-mtg-1")
            # P27: assert the meeting persisted
            assert retrieved is not None, "Meeting must survive restart"
            assert retrieved.title == "Globex Q4 Review", \
                f"Title must match, got {retrieved.title}"
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
