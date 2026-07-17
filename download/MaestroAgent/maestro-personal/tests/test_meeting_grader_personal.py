"""
Integration tests for the personal-shell meeting_grader wrapper.

P2: untested code is unverified code. These tests verify the WIRING
(P11) — that the enterprise MeetingGrader is reachable from the personal
shell's production path, and that meeting data is DERIVED (P13) from
signal history, not caller-supplied.

Test scenarios:
  1. Empty signal store → no grades
  2. Meeting with transcript → grade derived with action items
  3. Grade report has transparent factor breakdown
  4. User override works
  5. GET /meetings/grades + GET /meetings/{id}/grade + POST override work
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-grader"
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
        json={"password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test-grader")},
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


class TestMeetingGraderWiring:
    """P11 wiring tests — verify the enterprise MeetingGrader is reachable."""

    def test_enterprise_grader_importable(self):
        """P11: the enterprise MeetingGrader must be importable."""
        from maestro_personal_shell.meeting_grader import ENTERPRISE_GRADER_AVAILABLE
        assert ENTERPRISE_GRADER_AVAILABLE is True, (
            "Enterprise MeetingGrader not importable — 0% wired (P11)"
        )

    def test_empty_signal_store_returns_no_grades(self, isolated_db):
        """P13: with no signals, no grades should be derived."""
        from maestro_personal_shell.meeting_grader import grade_all_meetings
        result = grade_all_meetings(user_email="u@t.com", db_path=isolated_db)
        assert result == [], f"Empty signal store should return no grades. Got: {result}"

    def test_meeting_grade_derived_from_signals(self, isolated_db):
        """P13: a meeting signal should DERIVE a grade with action items —
        without the caller supplying the transcript or metrics."""
        from maestro_personal_shell.meeting_grader import grade_meeting
        ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        # Insert a meeting with a transcript containing action items
        _insert_signal(
            isolated_db, "sig-grade-1", "AcmeCorp",
            "Meeting with AcmeCorp about renewal. I will send the pricing proposal by Friday. "
            "Maria will review the contract terms.",
            "meeting_scheduled", ts,
            metadata={
                "title": "AcmeCorp Renewal Call",
                "start_time": ts,
                "duration_minutes": 45,
                "talk_ratio_balance": 0.6,
                "sentiment_score": 0.8,
                "participants": 3,
            },
        )
        result = grade_meeting(
            user_email="default@personal.local",
            meeting_id="sig-grade-1",
            db_path=isolated_db,
        )
        assert result is not None, "Meeting should be found + graded"
        # Must have a letter grade (A-F)
        assert result.get("grade") in ("A", "B", "C", "D", "F"), \
            f"Grade should be A-F. Got: {result.get('grade')}"
        # Must have a score (0-100)
        assert 0 <= result.get("score", -1) <= 100, \
            f"Score should be 0-100. Got: {result.get('score')}"
        # Must have transparent factor breakdown
        assert "factors" in result, "Must include transparent factor breakdown"
        # Must have action items extracted from the transcript
        assert isinstance(result.get("action_items"), list), \
            "Must include action_items list"
        # The transcript contains "I will send" + "Maria will review" → action items
        assert len(result.get("action_items", [])) > 0, \
            f"Should extract action items from transcript. Got: {result.get('action_items')}"

    def test_nonexistent_meeting_returns_none(self, isolated_db):
        """A meeting_id that doesn't exist should return None (honest)."""
        from maestro_personal_shell.meeting_grader import grade_meeting
        ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        _insert_signal(
            isolated_db, "sig-real", "AcmeCorp", "Real meeting",
            "meeting_scheduled", ts,
        )
        result = grade_meeting(
            user_email="default@personal.local",
            meeting_id="sig-nonexistent",
            db_path=isolated_db,
        )
        assert result is None, "Nonexistent meeting should return None"

    def test_user_override_changes_effective_grade(self, isolated_db):
        """P11: the user can override the computed grade."""
        from maestro_personal_shell.meeting_grader import grade_meeting, set_user_override
        ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        _insert_signal(
            isolated_db, "sig-override-1", "BetaCorp",
            "Quick sync with BetaCorp. I will follow up next week.",
            "meeting_scheduled", ts,
            metadata={"title": "BetaCorp Sync", "start_time": ts},
        )
        # Get the computed grade
        computed = grade_meeting("default@personal.local", "sig-override-1", db_path=isolated_db)
        assert computed is not None
        # Override to A
        overridden = set_user_override(
            "default@personal.local", "sig-override-1", "A", db_path=isolated_db
        )
        assert overridden is not None
        assert overridden.get("user_override") == "A", \
            f"Override should be recorded. Got: {overridden.get('user_override')}"
        assert overridden.get("effective_grade") == "A", \
            f"Effective grade should be A after override. Got: {overridden.get('effective_grade')}"


# ---------------------------------------------------------------------------
# Endpoint tests (P11 — production entry point)
# ---------------------------------------------------------------------------


class TestMeetingGraderEndpoints:
    """P11 wiring: the /api/meetings/*/grade endpoints must be reachable."""

    def test_all_grades_endpoint_returns_200(self, client, auth_headers):
        response = client.get("/api/meetings/grades", headers=auth_headers)
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "grades" in data
        assert "engine_available" in data
        assert data["engine_available"] is True
        assert "average_score" in data

    def test_single_grade_endpoint_returns_200_or_404(self, client, auth_headers, isolated_api):
        """Should return 200 if meeting exists, 404 if not."""
        db_path = os.environ.get("MAESTRO_PERSONAL_DB")
        ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        _insert_signal(
            db_path, "sig-ep-grade-1", "GammaCorp",
            "Meeting with GammaCorp. I will send the proposal.",
            "meeting_scheduled", ts,
            metadata={"title": "GammaCorp Call", "start_time": ts},
        )
        # Existing meeting → 200
        response = client.get("/api/meetings/sig-ep-grade-1/grade", headers=auth_headers)
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["engine_available"] is True
        assert data["grade"]["grade"] in ("A", "B", "C", "D", "F")
        # Nonexistent meeting → 404
        response404 = client.get("/api/meetings/sig-nonexistent/grade", headers=auth_headers)
        assert response404.status_code == 404

    def test_override_endpoint_returns_200(self, client, auth_headers, isolated_api):
        """POST /meetings/{id}/grade/override should work."""
        db_path = os.environ.get("MAESTRO_PERSONAL_DB")
        ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        _insert_signal(
            db_path, "sig-ep-override-1", "DeltaCorp",
            "Meeting with DeltaCorp.",
            "meeting_scheduled", ts,
            metadata={"title": "DeltaCorp Call", "start_time": ts},
        )
        response = client.post(
            "/api/meetings/sig-ep-override-1/grade/override",
            headers=auth_headers,
            json={"grade": "A"},
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["grade"]["user_override"] == "A"
        assert data["grade"]["effective_grade"] == "A"

    def test_grades_derived_from_signals(self, client, auth_headers, isolated_api):
        """P13: the endpoint must DERIVE grades from signal history."""
        db_path = os.environ.get("MAESTRO_PERSONAL_DB")
        ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        _insert_signal(
            db_path, "sig-p13-grade", "EpsilonCorp",
            "Meeting with EpsilonCorp. I will send pricing. Maria will review.",
            "meeting_scheduled", ts,
            metadata={"title": "EpsilonCorp Call", "start_time": ts},
        )
        response = client.get("/api/meetings/grades", headers=auth_headers)
        data = response.json()
        assert data["count"] > 0, f"Should derive grades from signals. Got: {data}"
        # Should reference EpsilonCorp — derived from signals
        found_epsilon = any(
            g.get("entity") == "EpsilonCorp"
            for g in data.get("grades", [])
        )
        assert found_epsilon, \
            f"Grade should reference EpsilonCorp (derived from signals). Got: {data}"
