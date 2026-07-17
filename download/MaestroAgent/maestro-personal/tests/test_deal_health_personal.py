"""
Integration tests for the personal-shell deal_health wrapper.

P2: untested code is unverified code. These tests verify the WIRING
(P11) — that the enterprise DealHealthEngine is reachable from the
personal shell's production path, and that scores are DERIVED (P13)
from signal history, not caller-supplied.

Test scenarios:
  1. Empty signal store → no deal health
  2. Entity with commitments → score derived
  3. P25 confidence gate: "insufficient calibration history" when <10 deals
  4. Nonexistent entity → 404
  5. GET /deals/health + GET /deals/{entity}/health work
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-deal"
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
        json={"password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test-deal")},
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


class TestDealHealthWiring:
    """P11 wiring tests — verify the enterprise DealHealthEngine is reachable."""

    def test_enterprise_engine_importable(self):
        from maestro_personal_shell.deal_health import ENTERPRISE_DEAL_HEALTH_AVAILABLE
        assert ENTERPRISE_DEAL_HEALTH_AVAILABLE is True, (
            "Enterprise DealHealthEngine not importable — 0% wired (P11)"
        )

    def test_empty_signal_store_returns_no_health(self, isolated_db):
        from maestro_personal_shell.deal_health import get_deal_health
        result = get_deal_health(user_email="u@t.com", entity="AcmeCorp", db_path=isolated_db)
        assert result is None, "Empty signal store should return None"

    def test_deal_health_derived_from_signals(self, isolated_db):
        """P13: a deal health score should be DERIVED from signal history —
        without the caller supplying the score or its inputs."""
        from maestro_personal_shell.deal_health import get_deal_health
        ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        # Insert a kept commitment + a meeting for AcmeCorp
        _insert_signal(
            isolated_db, "sig-dh-1", "AcmeCorp", "Sent the pricing proposal",
            "commitment_kept", ts,
        )
        _insert_signal(
            isolated_db, "sig-dh-2", "AcmeCorp", "Meeting with AcmeCorp",
            "meeting_scheduled", ts,
        )
        result = get_deal_health(
            user_email="default@personal.local", entity="AcmeCorp", db_path=isolated_db
        )
        assert result is not None, "Should derive a deal health score"
        assert result.get("entity") == "AcmeCorp"
        assert 0 <= result.get("score", -1) <= 100, \
            f"Score should be 0-100. Got: {result.get('score')}"
        assert result.get("status") in ("strong", "on_track", "at_risk", "critical"), \
            f"Status should be a valid DealHealthStatus. Got: {result.get('status')}"
        assert result.get("momentum") in ("accelerating", "stable", "decelerating"), \
            f"Momentum should be valid. Got: {result.get('momentum')}"
        # P25: must include confidence_label + calibration_denominator
        assert "confidence_label" in result, "P25: must include confidence_label"
        assert "calibration_denominator" in result, "P25: must include calibration_denominator"
        # Must include risk_factors + positive_indicators
        assert isinstance(result.get("risk_factors"), list)
        assert isinstance(result.get("positive_indicators"), list)

    def test_p25_confidence_gate_insufficient_history(self, isolated_db):
        """P25: with <10 deals in cohort, confidence_label must say
        'insufficient calibration history' — never bare precision."""
        from maestro_personal_shell.deal_health import get_deal_health
        ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        _insert_signal(
            isolated_db, "sig-p25-1", "P25Corp", "Meeting",
            "meeting_scheduled", ts,
        )
        result = get_deal_health(
            user_email="default@personal.local", entity="P25Corp", db_path=isolated_db
        )
        assert result is not None
        assert "insufficient" in result.get("confidence_label", "").lower(), \
            f"P25: should say 'insufficient calibration history' when <10 deals. Got: {result.get('confidence_label')}"

    def test_nonexistent_entity_returns_none(self, isolated_db):
        from maestro_personal_shell.deal_health import get_deal_health
        ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        _insert_signal(
            isolated_db, "sig-real", "AcmeCorp", "Meeting",
            "meeting_scheduled", ts,
        )
        result = get_deal_health(
            user_email="default@personal.local", entity="NonexistentCorp", db_path=isolated_db
        )
        assert result is None, "Nonexistent entity should return None"


# ---------------------------------------------------------------------------
# Endpoint tests (P11 — production entry point)
# ---------------------------------------------------------------------------


class TestDealHealthEndpoints:
    """P11 wiring: the /api/deals/health endpoints must be reachable."""

    def test_all_deals_endpoint_returns_200(self, client, auth_headers):
        response = client.get("/api/deals/health", headers=auth_headers)
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "deals" in data
        assert "engine_available" in data
        assert data["engine_available"] is True
        assert "strong_count" in data
        assert "at_risk_count" in data
        assert "critical_count" in data

    def test_single_deal_endpoint_returns_200_or_404(self, client, auth_headers, isolated_api):
        db_path = os.environ.get("MAESTRO_PERSONAL_DB")
        ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        _insert_signal(
            db_path, "sig-ep-dh-1", "EpCorp", "Meeting with EpCorp",
            "meeting_scheduled", ts,
        )
        # Existing entity → 200
        response = client.get("/api/deals/EpCorp/health", headers=auth_headers)
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["engine_available"] is True
        assert data["deal_health"]["entity"] == "EpCorp"
        # Nonexistent entity → 404
        response404 = client.get("/api/deals/NonexistentCorp/health", headers=auth_headers)
        assert response404.status_code == 404

    def test_deal_health_derived_from_signals(self, client, auth_headers, isolated_api):
        """P13: the endpoint must DERIVE deal health from signal history."""
        db_path = os.environ.get("MAESTRO_PERSONAL_DB")
        ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        _insert_signal(
            db_path, "sig-p13-dh", "P13DealCorp", "Meeting with P13DealCorp",
            "meeting_scheduled", ts,
        )
        response = client.get("/api/deals/health", headers=auth_headers)
        data = response.json()
        assert data["count"] > 0, f"Should derive deal health from signals. Got: {data}"
        found_p13 = any(
            d.get("entity") == "P13DealCorp"
            for d in data.get("deals", [])
        )
        assert found_p13, \
            f"Deal health should reference P13DealCorp (derived from signals). Got: {data}"
