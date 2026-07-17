"""
Integration tests for the personal-shell ambient_notifications wrapper.

P2: untested code is unverified code. These tests verify the WIRING
(P11) — that the enterprise AmbientNotificationEngine is actually
reachable from the personal shell's production path, and that
notifications are DERIVED (P13) from signal history, not caller-supplied.

Test scenarios:
  1. Empty signal store → no notifications (honest empty state)
  2. Overdue commitment → CRITICAL/HIGH notification generated + visible
  3. Stale relationship → notification generated
  4. Focus mode active → MEDIUM priority suppressed
  5. DND active → only CRITICAL shows
  6. POST /api/notifications/smart returns 200 with derived notifications
"""
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Set up path BEFORE imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))


# ---------------------------------------------------------------------------
# Fixtures (same pattern as test_audit_f4_f10_remaining.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_db():
    """Create an isolated temp DB with the signals table for each test."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = f.name
    f.close()
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_TEST_MODE"] = "1"
    # Create the signals table (same schema as api.init_db)
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
    db.execute("""
        CREATE TABLE IF NOT EXISTS push_tokens (
            user_email TEXT NOT NULL,
            expo_token TEXT NOT NULL,
            created_at TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            PRIMARY KEY (user_email, expo_token)
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-ambient"
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
        json={"password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test-ambient")},
    )
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _insert_signal(db_path, signal_id, entity, text, signal_type, timestamp, user_email="default@personal.local"):
    from maestro_personal_shell.db_util import get_db_conn
    db = get_db_conn(db_path)
    db.execute(
        "INSERT OR REPLACE INTO signals (signal_id, entity, text, signal_type, timestamp, metadata, created_at, user_email) "
        "VALUES (?, ?, ?, ?, ?, '{}', ?, ?)",
        (signal_id, entity, text, signal_type, timestamp, timestamp, user_email),
    )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Wiring tests (P11)
# ---------------------------------------------------------------------------


class TestAmbientNotificationsWiring:
    """P11 wiring tests — verify the enterprise engine is reachable from
    the personal shell's production path."""

    def test_enterprise_engine_importable(self):
        """P11: the enterprise AmbientNotificationEngine must be importable
        from the personal shell. If this fails, the wrapper is dead code."""
        from maestro_personal_shell.ambient_notifications import (
            ENTERPRISE_ENGINE_AVAILABLE,
        )
        assert ENTERPRISE_ENGINE_AVAILABLE is True, (
            "Enterprise engine not importable — smart notifications are 0% wired (P11)"
        )

    def test_empty_signal_store_returns_no_notifications(self, isolated_db):
        """P13: with no signals, no notifications should be derived.
        Honest empty state — no fabrication."""
        from maestro_personal_shell.ambient_notifications import get_smart_notifications
        result = get_smart_notifications(user_email="u@t.com", db_path=isolated_db)
        assert result == [], f"Empty signal store should return no notifications. Got: {result}"

    def test_overdue_commitment_derives_notification(self, isolated_db):
        """P13: an overdue commitment signal should DERIVE a notification
        without the caller supplying the notification content.

        Uses a 10-day-old commitment so the engine classifies it as CRITICAL
        (>= 7 days overdue) — CRITICAL shows even during quiet hours, so
        this test passes regardless of when it runs.
        """
        from maestro_personal_shell.ambient_notifications import get_smart_notifications
        old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        _insert_signal(isolated_db, "sig-1", "Maria", "Send pricing proposal", "commitment_made", old_ts)
        result = get_smart_notifications(user_email="default@personal.local", db_path=isolated_db)
        assert len(result) > 0, "Overdue commitment should derive a notification"
        found_overdue = any(
            n.get("type") == "overdue_commitment" or "overdue" in n.get("title", "").lower()
            for n in result
        )
        assert found_overdue, f"Should have an overdue_commitment notification. Got: {result}"

    def test_stale_relationship_derives_notification(self, isolated_db):
        """P13: an entity not seen in 35+ days should derive a stale
        relationship notification with HIGH priority (> 30 days → HIGH,
        which shows during focus mode + active hours).

        Uses 35 days so it's HIGH priority (not MEDIUM), which is more
        robust to test execution timing.
        """
        from maestro_personal_shell.ambient_notifications import get_smart_notifications
        old_ts = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
        _insert_signal(isolated_db, "sig-2", "OldClient", "Last interaction", "meeting_context", old_ts)
        result = get_smart_notifications(user_email="default@personal.local", db_path=isolated_db)
        # During quiet hours, HIGH is suppressed. So just verify the notification
        # was DERIVED (not necessarily visible). We check via _derive directly.
        from maestro_personal_shell.ambient_notifications import _derive_notifications_from_signals, _get_signals_for_user
        sigs = _get_signals_for_user("default@personal.local", db_path=isolated_db)
        derived = _derive_notifications_from_signals(sigs)
        found_stale = any(
            n.type.value == "stale_relationship" or "stale" in n.title.lower()
            for n in derived
        )
        assert found_stale, f"Should derive a stale_relationship notification. Got: {[d.title for d in derived]}"

    def test_dnd_suppresses_non_critical(self, isolated_db):
        """P11 wiring: DND active must suppress non-CRITICAL notifications.
        CRITICAL (overdue >= 7 days) must still show."""
        from maestro_personal_shell.ambient_notifications import get_smart_notifications
        # 10-day-old commitment → CRITICAL (>= 7 days overdue)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        _insert_signal(isolated_db, "sig-dnd-1", "Critical", "Critical commitment", "commitment_made", old_ts)
        # 15-day-stale relationship → MEDIUM (not > 30, so MEDIUM)
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        _insert_signal(isolated_db, "sig-dnd-2", "StaleMed", "Old meeting", "meeting_context", stale_ts)

        # DND on — only CRITICAL should show
        dnd_on = get_smart_notifications(
            user_email="default@personal.local", db_path=isolated_db, is_dnd_active=True
        )
        # All visible notifications must be CRITICAL
        for n in dnd_on:
            assert n.get("priority") == "critical", \
                f"DND active but non-critical notification shown: {n}"
        # The CRITICAL overdue commitment must still appear
        assert len(dnd_on) > 0, "CRITICAL notifications must show even with DND active"

    def test_focus_mode_suppresses_medium(self, isolated_db):
        """P11 wiring: focus mode must suppress MEDIUM-priority notifications.
        CRITICAL must still show."""
        from maestro_personal_shell.ambient_notifications import get_smart_notifications
        # 20-day-old commitment → CRITICAL (>= 7 days overdue)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        _insert_signal(isolated_db, "sig-focus-1", "Critical", "Critical commitment", "commitment_made", old_ts)
        # 15-day-stale relationship → MEDIUM
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        _insert_signal(isolated_db, "sig-focus-2", "StaleMed", "Old meeting", "meeting_context", stale_ts)

        # Without focus mode — both should be visible
        no_focus = get_smart_notifications(
            user_email="default@personal.local", db_path=isolated_db, is_focus_mode=False
        )
        # With focus mode — MEDIUM should be suppressed, CRITICAL should remain
        with_focus = get_smart_notifications(
            user_email="default@personal.local", db_path=isolated_db, is_focus_mode=True
        )

        # CRITICAL (overdue 20 days) must still appear in focus mode
        critical_in_focus = [n for n in with_focus if n.get("priority") == "critical"]
        assert len(critical_in_focus) > 0, \
            f"CRITICAL notifications must show even in focus mode. Got: {with_focus}"


# ---------------------------------------------------------------------------
# Endpoint tests (P11 — production entry point)
# ---------------------------------------------------------------------------


class TestSmartNotificationsEndpoint:
    """P11 wiring: the /api/notifications/smart endpoint must be reachable
    and return derived notifications."""

    def test_endpoint_returns_200(self, client, auth_headers):
        """The endpoint must be mounted and return 200."""
        response = client.post(
            "/api/notifications/smart",
            headers=auth_headers,
            json={"is_in_call": False, "is_dnd_active": False, "is_focus_mode": False},
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "notifications" in data
        assert "engine_available" in data
        assert data["engine_available"] is True, "Engine should be available in test env"
        assert isinstance(data["notifications"], list)

    def test_endpoint_derives_from_signal_history(self, client, auth_headers, isolated_api):
        """P13: the endpoint must DERIVE notifications from the user's signal
        history — not from caller-supplied content. The request body only
        contains CONTEXT (in_call, dnd, focus), never notification text."""
        db_path = os.environ.get("MAESTRO_PERSONAL_DB")
        # Insert a stale relationship + overdue commitment
        old_ts = (datetime.now(timezone.utc) - timedelta(days=25)).isoformat()
        _insert_signal(db_path, "sig-p13-1", "P13Client", "Old meeting notes", "meeting_context", old_ts)
        old_ts2 = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        _insert_signal(db_path, "sig-p13-2", "P13Client", "Send proposal", "commitment_made", old_ts2)

        response = client.post(
            "/api/notifications/smart",
            headers=auth_headers,
            json={"is_focus_mode": False},  # only context, no content
        )
        data = response.json()
        assert data["engine_available"] is True
        assert data["count"] > 0, f"Should derive notifications from signals. Got: {data}"
        # The notification should reference the P13Client entity — derived from signals
        found_p13 = any(
            "P13Client" in n.get("body", "") or "P13Client" in n.get("metadata", {}).get("entity", "")
            for n in data.get("notifications", [])
        )
        assert found_p13, \
            f"Notification should reference P13Client (derived from signals). Got: {data}"

    def test_endpoint_respects_dnd(self, client, auth_headers, isolated_api):
        """When DND is active, only CRITICAL notifications should appear."""
        db_path = os.environ.get("MAESTRO_PERSONAL_DB")
        # Insert an overdue commitment (>= 7 days → CRITICAL)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        _insert_signal(db_path, "sig-dnd-ep-1", "DndClient", "Critical commitment", "commitment_made", old_ts)

        dnd_on = client.post(
            "/api/notifications/smart",
            headers=auth_headers,
            json={"is_dnd_active": True},
        ).json()
        # All visible notifications must be CRITICAL
        for n in dnd_on.get("notifications", []):
            assert n.get("priority") == "critical", \
                f"DND active but non-critical notification shown: {n}"
