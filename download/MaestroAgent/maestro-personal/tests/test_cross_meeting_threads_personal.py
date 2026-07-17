"""
Integration tests for the personal-shell cross_meeting_threads wrapper.

P2: untested code is unverified code. These tests verify the WIRING
(P11) — that the enterprise CrossMeetingThreadBuilder is reachable from
the personal shell's production path, and that threads are DERIVED (P13)
from signal history, not caller-supplied.

Test scenarios:
  1. Empty signal store → no threads (honest empty state)
  2. Single meeting → no threads (need >= 2 to thread)
  3. Two meetings same entity + overlapping topics → thread created
  4. Two meetings different entities → no thread (entity mismatch)
  5. Decision history derived from signals
  6. POST /api/threads + GET /api/threads/{entity} + decisions endpoint
"""
import os
import sys
import tempfile
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Set up path BEFORE imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_db():
    """Create an isolated temp DB with the signals table for each test."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = f.name
    f.close()
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_TEST_MODE"] = "1"
    from maestro_personal_shell.db_util import get_db_conn
    db = get_db_conn(db_path)
    db.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            signal_id TEXT PRIMARY KEY,
            entity TEXT NOT NULL,
            text TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            source_acl TEXT DEFAULT 'public',
            created_at TEXT NOT NULL,
            user_email TEXT DEFAULT 'bootstrap'
        )
    """)
    db.commit()
    db.close()
    yield db_path
    try:
        os.unlink(db_path)
    except OSError:
        pass
    os.environ.pop("MAESTRO_PERSONAL_DB", None)


@pytest.fixture
def isolated_api():
    """Full app instance with isolated DB — for endpoint tests."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = f.name
    f.close()
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-threads"
    os.environ["MAESTRO_TEST_MODE"] = "1"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)

    yield api_module
    try:
        os.unlink(db_path)
    except OSError:
        pass
    os.environ.pop("MAESTRO_PERSONAL_DB", None)
    os.environ.pop("MAESTRO_PERSONAL_TOKEN", None)


@pytest.fixture
def client(isolated_api):
    return TestClient(isolated_api.app)


@pytest.fixture
def auth_headers(client):
    response = client.post(
        "/api/auth/login",
        json={"password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test-threads")},
    )
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _insert_signal(db_path, signal_id, entity, text, signal_type, timestamp,
                   metadata=None, user_email="default@personal.local"):
    from maestro_personal_shell.db_util import get_db_conn
    db = get_db_conn(db_path)
    db.execute(
        "INSERT OR REPLACE INTO signals (signal_id, entity, text, signal_type, timestamp, metadata, created_at, user_email) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (signal_id, entity, text, signal_type, timestamp,
         json.dumps(metadata or {}), timestamp, user_email),
    )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Wiring tests (P11)
# ---------------------------------------------------------------------------


class TestCrossMeetingThreadsWiring:
    """P11 wiring tests — verify the enterprise builder is reachable."""

    def test_enterprise_builder_importable(self):
        """P11: the enterprise CrossMeetingThreadBuilder must be importable."""
        from maestro_personal_shell.cross_meeting_threads import (
            ENTERPRISE_THREAD_BUILDER_AVAILABLE,
        )
        assert ENTERPRISE_THREAD_BUILDER_AVAILABLE is True, (
            "Enterprise CrossMeetingThreadBuilder not importable — 0% wired (P11)"
        )

    def test_empty_signal_store_returns_no_threads(self, isolated_db):
        """P13: with no signals, no threads should be derived."""
        from maestro_personal_shell.cross_meeting_threads import get_cross_meeting_threads
        result = get_cross_meeting_threads(user_email="u@t.com", db_path=isolated_db)
        assert result == [], f"Empty signal store should return no threads. Got: {result}"

    def test_single_meeting_returns_no_threads(self, isolated_db):
        """Need at least 2 meetings to build a thread."""
        from maestro_personal_shell.cross_meeting_threads import get_cross_meeting_threads
        ts = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        _insert_signal(
            isolated_db, "sig-m1", "AcmeCorp", "Q3 renewal discussion",
            "meeting_scheduled", ts,
            metadata={"title": "Q3 renewal discussion", "start_time": ts},
        )
        result = get_cross_meeting_threads(
            user_email="default@personal.local", db_path=isolated_db
        )
        assert result == [], f"Single meeting should return no threads. Got: {result}"

    def test_two_meetings_same_entity_overlapping_topics_creates_thread(self, isolated_db):
        """P13: two meetings with the same entity + overlapping topics should
        DERIVE a thread — without the caller supplying the meetings."""
        from maestro_personal_shell.cross_meeting_threads import get_cross_meeting_threads
        # Two meetings about "renewal" + "pricing" with AcmeCorp
        ts1 = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        ts2 = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        _insert_signal(
            isolated_db, "sig-m1", "AcmeCorp", "Q3 renewal pricing discussion",
            "meeting_scheduled", ts1,
            metadata={"title": "Q3 renewal pricing discussion", "start_time": ts1},
        )
        _insert_signal(
            isolated_db, "sig-m2", "AcmeCorp", "Renewal pricing follow-up call",
            "meeting_scheduled", ts2,
            metadata={"title": "Renewal pricing follow-up call", "start_time": ts2},
        )
        result = get_cross_meeting_threads(
            user_email="default@personal.local", db_path=isolated_db
        )
        assert len(result) > 0, \
            "Two meetings with same entity + overlapping topics should create a thread"
        thread = result[0]
        assert thread.get("entity") == "AcmeCorp"
        assert thread.get("meeting_count") >= 2, \
            f"Thread should link >=2 meetings. Got: {thread.get('meeting_count')}"
        # Must include topic_evolution (even if empty list)
        assert "topic_evolution" in thread
        assert "decision_chain" in thread
        # Must include confidence + confidence_level
        assert "confidence" in thread
        assert "confidence_level" in thread

    def test_two_meetings_different_entities_no_thread(self, isolated_db):
        """Meetings with different entities should NOT be threaded together."""
        from maestro_personal_shell.cross_meeting_threads import get_cross_meeting_threads
        ts1 = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        ts2 = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        _insert_signal(
            isolated_db, "sig-m1", "AcmeCorp", "Renewal pricing discussion",
            "meeting_scheduled", ts1,
            metadata={"title": "Renewal pricing discussion", "start_time": ts1},
        )
        _insert_signal(
            isolated_db, "sig-m2", "BetaCorp", "Renewal pricing discussion",
            "meeting_scheduled", ts2,
            metadata={"title": "Renewal pricing discussion", "start_time": ts2},
        )
        result = get_cross_meeting_threads(
            user_email="default@personal.local", db_path=isolated_db
        )
        # Should NOT thread meetings across different entities
        assert len(result) == 0, \
            f"Meetings with different entities should not thread. Got: {result}"

    def test_entity_filter_returns_only_matching_threads(self, isolated_db):
        """The entity_filter parameter should limit results to one entity."""
        from maestro_personal_shell.cross_meeting_threads import get_cross_meeting_threads
        # AcmeCorp thread (2 meetings)
        ts1 = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        ts2 = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        _insert_signal(
            isolated_db, "sig-a1", "AcmeCorp", "Renewal pricing discussion",
            "meeting_scheduled", ts1,
            metadata={"title": "Renewal pricing discussion", "start_time": ts1},
        )
        _insert_signal(
            isolated_db, "sig-a2", "AcmeCorp", "Renewal pricing follow-up",
            "meeting_scheduled", ts2,
            metadata={"title": "Renewal pricing follow-up", "start_time": ts2},
        )
        # GammaCorp thread (2 meetings)
        _insert_signal(
            isolated_db, "sig-g1", "GammaCorp", "Renewal pricing discussion",
            "meeting_scheduled", ts1,
            metadata={"title": "Renewal pricing discussion", "start_time": ts1},
        )
        _insert_signal(
            isolated_db, "sig-g2", "GammaCorp", "Renewal pricing follow-up",
            "meeting_scheduled", ts2,
            metadata={"title": "Renewal pricing follow-up", "start_time": ts2},
        )
        # Filter to AcmeCorp only
        result = get_cross_meeting_threads(
            user_email="default@personal.local", db_path=isolated_db,
            entity_filter="AcmeCorp",
        )
        assert len(result) > 0, "Should find AcmeCorp threads"
        for t in result:
            assert t.get("entity") == "AcmeCorp", \
                f"Entity filter should exclude non-matching. Got: {t.get('entity')}"


# ---------------------------------------------------------------------------
# Endpoint tests (P11 — production entry point)
# ---------------------------------------------------------------------------


class TestCrossMeetingThreadsEndpoints:
    """P11 wiring: the /api/threads endpoints must be reachable."""

    def test_threads_endpoint_returns_200(self, client, auth_headers):
        response = client.post(
            "/api/threads",
            headers=auth_headers,
            json={"entity_filter": ""},
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "threads" in data
        assert "engine_available" in data
        assert data["engine_available"] is True
        assert "high_confidence_count" in data

    def test_threads_for_entity_endpoint_returns_200(self, client, auth_headers):
        response = client.get(
            "/api/threads/AcmeCorp",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "threads" in data
        assert data["engine_available"] is True
        assert data["entity"] == "AcmeCorp"

    def test_decision_history_endpoint_returns_200(self, client, auth_headers):
        response = client.get(
            "/api/threads/AcmeCorp/decisions",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "decisions" in data
        assert data["engine_available"] is True
        assert data["entity"] == "AcmeCorp"

    def test_threads_endpoint_derives_from_signals(self, client, auth_headers, isolated_api):
        """P13: the endpoint must DERIVE threads from signal history."""
        db_path = os.environ.get("MAESTRO_PERSONAL_DB")
        ts1 = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        ts2 = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        from maestro_personal_shell.db_util import get_db_conn
        db = get_db_conn(db_path)
        db.execute(
            "INSERT OR REPLACE INTO signals (signal_id, entity, text, signal_type, timestamp, metadata, created_at, user_email) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("sig-ep-1", "ThreadCorp", "Pricing renewal discussion",
             "meeting_scheduled", ts1, json.dumps({"title": "Pricing renewal discussion", "start_time": ts1}),
             ts1, "default@personal.local"),
        )
        db.execute(
            "INSERT OR REPLACE INTO signals (signal_id, entity, text, signal_type, timestamp, metadata, created_at, user_email) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("sig-ep-2", "ThreadCorp", "Pricing renewal follow-up",
             "meeting_scheduled", ts2, json.dumps({"title": "Pricing renewal follow-up", "start_time": ts2}),
             ts2, "default@personal.local"),
        )
        db.commit()
        db.close()

        response = client.post("/api/threads", headers=auth_headers, json={"entity_filter": "ThreadCorp"})
        data = response.json()
        # Should derive a thread from the two ThreadCorp meetings
        assert data["count"] > 0, f"Should derive threads from signals. Got: {data}"
        found_thread = any(
            t.get("entity") == "ThreadCorp" and t.get("meeting_count", 0) >= 2
            for t in data.get("threads", [])
        )
        assert found_thread, \
            f"Thread should reference ThreadCorp (derived from signals). Got: {data}"
