"""
Integration tests for the personal-shell advanced_analytics wrapper.

P2: untested code is unverified code. These tests verify the WIRING
(P11) — that the enterprise AdvancedAnalyticsEngine is reachable from
the personal shell's production path, and that the report is DERIVED
(P13) from signal history, not caller-supplied.

Test scenarios:
  1. Empty signal store → no report (honest empty state)
  2. Signals with commitments → commitment rates derived
  3. Meeting signals → meeting grades derived
  4. Full report has trends + flywheel_summary
  5. GET /analytics/trends + GET /analytics/flywheel work
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
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = f.name
    f.close()
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-analytics"
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
        json={"password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test-analytics")},
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


class TestAdvancedAnalyticsWiring:
    """P11 wiring tests — verify the enterprise engine is reachable."""

    def test_enterprise_engine_importable(self):
        from maestro_personal_shell.advanced_analytics import ENTERPRISE_ANALYTICS_AVAILABLE
        assert ENTERPRISE_ANALYTICS_AVAILABLE is True, (
            "Enterprise AdvancedAnalyticsEngine not importable — 0% wired (P11)"
        )

    def test_empty_signal_store_returns_no_report(self, isolated_db):
        from maestro_personal_shell.advanced_analytics import get_analytics_report
        result = get_analytics_report(user_email="u@t.com", db_path=isolated_db)
        assert result is None, "Empty signal store should return None"

    def test_report_derived_from_signals(self, isolated_db):
        """P13: the report should be DERIVED from signal history — without
        the caller supplying the metrics."""
        from maestro_personal_shell.advanced_analytics import get_analytics_report
        ts = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        # Insert commitments + meetings
        _insert_signal(isolated_db, "sig-1", "AcmeCorp", "I will send the proposal",
                       "commitment_made", ts)
        _insert_signal(isolated_db, "sig-2", "AcmeCorp", "Sent the proposal",
                       "commitment_kept", ts)
        _insert_signal(isolated_db, "sig-3", "AcmeCorp",
                       "Meeting with AcmeCorp. I will follow up. Decided to proceed.",
                       "meeting_scheduled", ts)
        result = get_analytics_report(
            user_email="default@personal.local", db_path=isolated_db
        )
        assert result is not None, "Should derive a report from signals"
        # Must include commitment rates (derived from commitment signals)
        assert "commitment_kept_rate" in result
        assert "commitment_broken_rate" in result
        # Must include meeting_grade_average (derived from meeting signals)
        assert "meeting_grade_average" in result
        # Must include flywheel_summary
        assert "flywheel_summary" in result
        # Must include trends list
        assert isinstance(result.get("trends"), list)
        # Must include laws + patterns counts
        assert "laws_validated" in result
        assert "patterns_detected" in result

    def test_commitment_rates_derived_correctly(self, isolated_db):
        """P13: commitment kept rate should reflect actual signal counts."""
        from maestro_personal_shell.advanced_analytics import get_analytics_report
        ts = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        # 3 kept + 1 broken = 75% kept rate
        _insert_signal(isolated_db, "sig-k1", "Corp", "Kept 1", "commitment_kept", ts)
        _insert_signal(isolated_db, "sig-k2", "Corp", "Kept 2", "commitment_kept", ts)
        _insert_signal(isolated_db, "sig-k3", "Corp", "Kept 3", "commitment_kept", ts)
        _insert_signal(isolated_db, "sig-b1", "Corp", "Broken 1", "commitment_broken", ts)
        result = get_analytics_report(
            user_email="default@personal.local", db_path=isolated_db
        )
        assert result is not None
        kept_rate = result.get("commitment_kept_rate", 0)
        # 3 kept / 4 total = 0.75
        assert kept_rate >= 0.5, \
            f"Kept rate should be >= 0.5 with 3 kept + 1 broken. Got: {kept_rate}"


# ---------------------------------------------------------------------------
# Endpoint tests (P11 — production entry point)
# ---------------------------------------------------------------------------


class TestAdvancedAnalyticsEndpoints:
    """P11 wiring: the /api/analytics/* endpoints must be reachable."""

    def test_trends_endpoint_returns_200(self, client, auth_headers):
        response = client.get("/api/analytics/trends", headers=auth_headers)
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "engine_available" in data
        assert data["engine_available"] is True
        # Either a report or a "no signals" message
        assert "report" in data or "message" in data

    def test_flywheel_endpoint_returns_200(self, client, auth_headers):
        response = client.get("/api/analytics/flywheel", headers=auth_headers)
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "summary" in data
        assert "engine_available" in data
        assert data["engine_available"] is True

    def test_trends_endpoint_derives_from_signals(self, client, auth_headers, isolated_api):
        """P13: the endpoint must DERIVE the report from signal history."""
        db_path = os.environ.get("MAESTRO_PERSONAL_DB")
        ts = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        _insert_signal(db_path, "sig-ep-1", "EpCorp", "I will send proposal",
                       "commitment_made", ts)
        _insert_signal(db_path, "sig-ep-2", "EpCorp", "Sent proposal",
                       "commitment_kept", ts)
        response = client.get("/api/analytics/trends", headers=auth_headers)
        data = response.json()
        assert data["report"] is not None, \
            f"Should derive a report from signals. Got: {data}"
        report = data["report"]
        # Should reflect the kept commitment
        assert report.get("commitment_kept_rate", 0) > 0, \
            f"Kept rate should be > 0 with a kept commitment. Got: {report}"
        # Flywheel summary should be a non-empty string
        assert isinstance(data.get("flywheel_summary"), str)
        assert len(data.get("flywheel_summary", "")) > 0
