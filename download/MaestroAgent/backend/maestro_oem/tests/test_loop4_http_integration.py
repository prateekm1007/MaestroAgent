"""Loop 4 — Organizational Learning HTTP integration tests.

Per the established pattern, capabilities ship with HTTP endpoints in
the same commit.

HTTP endpoints:
  POST /api/oem/loop4/commitment-learning  — record a commitment learning
  POST /api/oem/loop4/meeting-learning     — record a meeting learning
  POST /api/oem/loop4/decision-learning    — record a decision learning
  GET  /api/oem/loop4/entries              — get all learning entries
  GET  /api/oem/loop4/patterns             — detect cross-loop patterns
  GET  /api/oem/loop4/policies             — learn delivery policies
  GET  /api/oem/loop4/compose              — compose the Org Learning entry
"""
from __future__ import annotations

import pytest
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
    monkeypatch.setenv("MAESTRO_MEETING_DB", str(tmp_path / "meetings.db"))
    monkeypatch.setenv("MAESTRO_DECISION_DB", str(tmp_path / "decisions.db"))
    monkeypatch.setenv("MAESTRO_ORG_LEARNING_DB", str(tmp_path / "org_learning.db"))
    monkeypatch.setenv("MAESTRO_MUTATION_DB", str(tmp_path / "mutations.db"))
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
    # C1 fix: reset ALL store singletons
    import maestro_api.routes.oem as _oem_routes
    _oem_routes._whisper_history_store = None
    _oem_routes._loop3_decision_store = None
    _oem_routes._loop2_meeting_store = None
    _oem_routes._loop4_ledger = None
    _oem_routes._loop1_5_mutation_tracker = None
    app = create_app(db_path=str(tmp_path / "maestro.db"))
    with TestClient(app) as c:
        yield c
    oem_state._initialized = False
    _oem_routes._whisper_history_store = None
    _oem_routes._loop3_decision_store = None
    _oem_routes._loop2_meeting_store = None
    _oem_routes._loop4_ledger = None
    _oem_routes._loop1_5_mutation_tracker = None
    oem_state.engine = None
    oem_state.signals = []


def _headers():
    return {"Content-Type": "application/json"}


def _seed_commitment_learnings(client, count=3, action="ignored", outcome="broken"):
    """Seed commitment learnings via HTTP."""
    for i in range(count):
        client.post("/api/oem/loop4/commitment-learning", json={
            "entity": f"Entity{i}",
            "whisper_id": f"wspr-{i}",
            "action": action,
            "outcome": outcome,
            "learning_entry": f"Entity{i} {outcome} its commitment after the exec {action} the Whisper.",
        }, headers=_headers())


# ─── 1. Record learnings from all 3 loops ──────────────────────────────────

def test_loop4_record_commitment_learning(client):
    """POST /loop4/commitment-learning records a commitment learning."""
    r = client.post("/api/oem/loop4/commitment-learning", json={
        "entity": "Globex",
        "whisper_id": "wspr-1",
        "action": "ignored",
        "outcome": "broken",
        "learning_entry": "Globex broke its commitment after the exec ignored the Whisper.",
    }, headers=_headers())
    assert r.status_code == 200, f"record failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert data["status"] == "recorded"
    assert data["source_loop"] == "commitment"


def test_loop4_record_meeting_learning(client):
    """POST /loop4/meeting-learning records a meeting learning."""
    r = client.post("/api/oem/loop4/meeting-learning", json={
        "entity": "Globex",
        "meeting_id": "mtg-1",
        "outcome": "commitment_broken",
        "learning_entry": "The Globex meeting ended with a broken commitment.",
    }, headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "recorded"
    assert data["source_loop"] == "meeting"


def test_loop4_record_decision_learning(client):
    """POST /loop4/decision-learning records a decision learning."""
    r = client.post("/api/oem/loop4/decision-learning", json={
        "entity": "Globex",
        "decision_id": "dec-1",
        "hypothesis": "SSO will ship by Q4",
        "outcome": "SSO missed Q4",
        "learning_entry": "The decision was based on a wrong hypothesis.",
    }, headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "recorded"
    assert data["source_loop"] == "decision"


# ─── 2. Get all entries ────────────────────────────────────────────────────

def test_loop4_get_all_entries(client):
    """GET /loop4/entries returns all learning entries from all 3 loops."""
    _seed_commitment_learnings(client, count=2)
    client.post("/api/oem/loop4/meeting-learning", json={
        "entity": "Globex", "meeting_id": "mtg-1", "outcome": "broken",
        "learning_entry": "Meeting learning.",
    }, headers=_headers())
    client.post("/api/oem/loop4/decision-learning", json={
        "entity": "Globex", "decision_id": "dec-1", "hypothesis": "x", "outcome": "missed",
        "learning_entry": "Decision learning.",
    }, headers=_headers())

    r = client.get("/api/oem/loop4/entries", headers=_headers())
    assert r.status_code == 200
    data = r.json()
    sources = {e["source_loop"] for e in data["entries"]}
    assert "commitment" in sources
    assert "meeting" in sources
    assert "decision" in sources


# ─── 3. Cross-loop pattern detection ───────────────────────────────────────

def test_loop4_cross_loop_patterns(client):
    """GET /loop4/patterns detects cross-loop patterns."""
    # 3 cases: ignored → broken
    _seed_commitment_learnings(client, count=3, action="ignored", outcome="broken")

    r = client.get("/api/oem/loop4/patterns", headers=_headers())
    assert r.status_code == 200, f"patterns failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    patterns = data["patterns"]
    assert len(patterns) >= 1, f"Must detect patterns. Got: {patterns}"
    ignored_broken = next(
        (p for p in patterns if "ignored" in p["description"].lower() and "broken" in p["description"].lower()),
        None,
    )
    assert ignored_broken is not None, "Must detect the ignored→broken pattern"
    assert ignored_broken["case_count"] >= 3


# ─── 4. Compose the Organizational Learning entry ──────────────────────────

def test_loop4_compose_entry(client):
    """GET /loop4/compose composes the Organizational Learning Ledger entry."""
    _seed_commitment_learnings(client, count=3, action="ignored", outcome="broken")

    r = client.get("/api/oem/loop4/compose", headers=_headers())
    assert r.status_code == 200, f"compose failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    entry = data["organizational_learning_entry"]
    assert entry, "Entry must be non-empty"
    assert len(entry) >= 80, f"Entry must be rich (≥80 chars). Got: {entry!r} (len={len(entry)})"

    # REJECT placeholders
    FORBIDDEN = ["Learning recorded.", "System learned.", "TODO", "placeholder"]
    for phrase in FORBIDDEN:
        assert phrase.lower() not in entry.lower(), \
            f"Entry must not be a placeholder. Got: {entry!r}"

    # Must reference the cross-loop pattern
    assert "ignored" in entry.lower() or "broken" in entry.lower() or "pattern" in entry.lower(), \
        f"Entry must reference the cross-loop pattern. Got: {entry!r}"

    # Must acknowledge sample-size limitations
    assert any(word in entry.lower() for word in ["sample", "data point", "not a trend", "limited", "small", "may not"]), \
        f"Entry must acknowledge sample-size limitations. Got: {entry!r}"
