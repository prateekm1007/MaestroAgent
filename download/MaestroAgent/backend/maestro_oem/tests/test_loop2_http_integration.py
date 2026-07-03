"""Loop 2 — Meeting Intelligence HTTP integration tests.

Per the established pattern (Loop 1 + Loop 1.5 Iteration), capabilities
ship with HTTP endpoints in the same commit. These tests verify the
production delivery path.

HTTP endpoints:
  POST /api/oem/loop2/meeting              — create/schedule a meeting
  GET  /api/oem/loop2/meeting/{meeting_id} — get a meeting by ID
  POST /api/oem/loop2/meeting/{meeting_id}/prepare  — prepare (assemble Situation)
  POST /api/oem/loop2/meeting/{meeting_id}/occur    — record topics + commitments
  POST /api/oem/loop2/meeting/{meeting_id}/outcome  — observe outcome
  GET  /api/oem/loop2/meeting/{meeting_id}/learning — get learning entry
  GET  /api/oem/loop2/patterns             — detect cross-meeting patterns
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """FastAPI TestClient with demo seed enabled + isolated DBs."""
    app_dir = str(Path(__file__).resolve().parents[3])
    monkeypatch.setattr("maestro_api.oem_state._IMPORT_DB_PATH", str(tmp_path / "test_import.db"))
    monkeypatch.setenv("MAESTRO_APP_DIR", app_dir)
    monkeypatch.setenv("MAESTRO_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("MAESTRO_LEARNING_DB", str(tmp_path / "learning.db"))
    monkeypatch.setenv("MAESTRO_WHISPER_DB", str(tmp_path / "whisper.db"))
    monkeypatch.setenv("MAESTRO_ADMIN_PASSWORD", "test")
    monkeypatch.setenv("MAESTRO_RATE_LIMIT_RPM", "10000")
    monkeypatch.setenv("MAESTRO_DEMO_SEED", "true")
    monkeypatch.setenv("MAESTRO_LOCAL_DEV", "true")
    from maestro_api.main import create_app
    from maestro_api.oem_state import oem_state, import_state
    oem_state._initialized = False
    oem_state.engine = None
    oem_state.signals = []
    oem_state._demo_seeded = False
    oem_state._contradiction_log = None
    import_state._initialized = False
    app = create_app(db_path=str(tmp_path / "maestro.db"))
    with TestClient(app) as c:
        yield c
    oem_state._initialized = False
    oem_state.engine = None
    oem_state.signals = []


def _headers():
    return {"Content-Type": "application/json"}


def _create_meeting(client, title="Globex Quarterly Review", entity="Globex"):
    """Helper: create a meeting and return the meeting_id."""
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r = client.post("/api/oem/loop2/meeting", json={
        "title": title,
        "entity": entity,
        "attendees": ["ceo@globex.com", "jane.d@acme.com"],
        "start": tomorrow,
        "end": tomorrow,
    }, headers=_headers())
    assert r.status_code == 200, f"create meeting failed: {r.status_code} {r.text[:200]}"
    return r.json()["meeting_id"]


# ─── 1. Create + Get meeting ───────────────────────────────────────────────

def test_loop2_create_and_get_meeting(client):
    """POST /loop2/meeting creates a meeting; GET retrieves it."""
    meeting_id = _create_meeting(client, title="Test Meeting", entity="TestCorp")

    r = client.get(f"/api/oem/loop2/meeting/{meeting_id}", headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["meeting_id"] == meeting_id
    assert data["title"] == "Test Meeting"
    assert data["entity"] == "TestCorp"
    assert data["status"] == "SCHEDULED"


def test_loop2_get_unknown_meeting_returns_404(client):
    """GET /loop2/meeting/{unknown} returns 404."""
    r = client.get("/api/oem/loop2/meeting/nonexistent-id", headers=_headers())
    assert r.status_code == 404


# ─── 2. Meeting lifecycle through HTTP ─────────────────────────────────────

def test_loop2_full_lifecycle_via_http(client):
    """Full meeting lifecycle through HTTP:
    create → prepare → occur → outcome → learning
    """
    # Create
    meeting_id = _create_meeting(client, title="Globex Review", entity="Globex")

    # Prepare
    r = client.post(f"/api/oem/loop2/meeting/{meeting_id}/prepare", json={}, headers=_headers())
    assert r.status_code == 200, f"prepare failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert data["status"] == "PREPARED"

    # Occur
    r = client.post(f"/api/oem/loop2/meeting/{meeting_id}/occur", json={
        "topics_discussed": ["pricing", "SSO delivery"],
        "commitments_made": ["Deliver SSO by 2024-12-15"],
    }, headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "OCCURRED"
    assert "pricing" in data["topics_discussed"]
    assert len(data["commitments_made"]) == 1

    # Outcome
    r = client.post(f"/api/oem/loop2/meeting/{meeting_id}/outcome", json={
        "outcome": "commitment_honored",
    }, headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "OUTCOME_OBSERVED"
    assert data["outcome"] == "commitment_honored"

    # Learning
    r = client.get(f"/api/oem/loop2/meeting/{meeting_id}/learning", headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "LEARNING_RECORDED"
    entry = data["learning_entry"]
    assert entry, "Learning entry must be non-empty"
    assert len(entry) >= 20, f"Learning entry must be a real sentence. Got: {entry!r}"

    # REJECT placeholders
    FORBIDDEN = ["Learning recorded.", "Meeting complete.", "TODO", "placeholder"]
    for phrase in FORBIDDEN:
        assert phrase.lower() not in entry.lower(), \
            f"Learning entry must not be a placeholder. Got: {entry!r}"

    # Must reference the actual meeting + outcome
    assert "globex" in entry.lower() or "meeting" in entry.lower(), \
        f"Must reference the meeting/entity. Got: {entry!r}"
    assert "honored" in entry.lower() or "commitment" in entry.lower(), \
        f"Must reference the outcome. Got: {entry!r}"


def test_loop2_learning_honest_when_broken(client):
    """When outcome is commitment_broken, the learning entry must honestly
    say so — no spin.
    """
    meeting_id = _create_meeting(client, title="Emergency Review", entity="Globex")

    client.post(f"/api/oem/loop2/meeting/{meeting_id}/prepare", json={}, headers=_headers())
    client.post(f"/api/oem/loop2/meeting/{meeting_id}/occur", json={
        "topics_discussed": ["pricing"],
        "commitments_made": [],
    }, headers=_headers())
    client.post(f"/api/oem/loop2/meeting/{meeting_id}/outcome", json={
        "outcome": "commitment_broken",
    }, headers=_headers())

    r = client.get(f"/api/oem/loop2/meeting/{meeting_id}/learning", headers=_headers())
    assert r.status_code == 200
    entry = r.json()["learning_entry"]
    assert "broken" in entry.lower() or "missed" in entry.lower() or "failed" in entry.lower(), \
        f"Learning entry must honestly say commitment was broken. Got: {entry!r}"
    assert "honored" not in entry.lower() and "fulfilled" not in entry.lower(), \
        f"Learning entry must NOT spin a broken commitment as honored. Got: {entry!r}"


# ─── 3. Cross-meeting pattern detection through HTTP ───────────────────────

def test_loop2_cross_meeting_patterns_via_http(client):
    """Create 3 meetings with the same topic, then GET patterns.

    The patterns endpoint must detect the recurring topic.
    """
    # Create + occur 3 meetings, all discussing "pricing"
    for i in range(3):
        mid = _create_meeting(client, title=f"Globex Review #{i+1}", entity="Globex")
        client.post(f"/api/oem/loop2/meeting/{mid}/prepare", json={}, headers=_headers())
        client.post(f"/api/oem/loop2/meeting/{mid}/occur", json={
            "topics_discussed": ["pricing"],
            "commitments_made": [],
        }, headers=_headers())

    # Detect patterns
    r = client.get("/api/oem/loop2/patterns?min_meetings=2", headers=_headers())
    assert r.status_code == 200, f"patterns failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    patterns = data["patterns"]
    assert len(patterns) >= 1, f"Must detect the recurring pricing pattern. Got: {patterns}"

    pricing_pattern = next(
        (p for p in patterns if "pricing" in p["topic"].lower()),
        None,
    )
    assert pricing_pattern is not None, "Must detect the pricing pattern specifically"
    assert pricing_pattern["meeting_count"] >= 3, \
        f"Pattern must count 3 meetings. Got: {pricing_pattern['meeting_count']}"
