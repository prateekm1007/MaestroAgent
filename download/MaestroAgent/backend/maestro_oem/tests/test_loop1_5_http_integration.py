"""Loop 1.5 Iteration — HTTP integration tests for the 5 capabilities.

CEO directive: Option A — Loop 1.5 Iteration. Wire HTTP endpoints for
the 5 capabilities built in commit a7c981e. Same pattern as Loop 1
Iteration: write HTTP integration tests first, watch them fail, build
until they pass.

The 5 capabilities + their HTTP endpoints:
  1. Commitment mutation tracking
     - POST /api/oem/loop1.5/mutation/record  — record a commitment (detects mutation)
     - GET  /api/oem/loop1.5/mutation/{entity} — get mutation history + events
  2. Disagreement detection
     - POST /api/oem/loop1.5/disagreements/detect — post evidence list, get disagreements
  3. delivery_decision
     - POST /api/oem/loop1.5/delivery-decision — post inputs, get decision
  4. Situation
     - GET /api/oem/loop1.5/situation/{entity} — get the Situation for an entity
  5. Cold-start mode
     - GET /api/oem/loop1.5/cold-start — get current rung + suppression state

These tests exercise the HTTP path (request → router → endpoint → response),
not direct module calls. They will FAIL until the endpoints are wired.
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


# ─── 1. Commitment Mutation Tracking — HTTP ────────────────────────────────

def test_loop1_5_mutation_tracking_via_http(client):
    """POST a commitment, then POST a mutated commitment, then GET history.

    The history must contain BOTH wordings. The mutations list must
    contain the mutation event (old → new).
    """
    # Record the original commitment
    r = client.post("/api/oem/loop1.5/mutation/record", json={
        "entity": "TestCorp",
        "commitment_text": "Deliver SSO by 2024-12-15",
        "actor": "jane.d@acme.com",
        "artifact": "crm:testcorp-1",
        "timestamp": "2026-06-01T10:00:00+00:00",
    }, headers=_headers())
    assert r.status_code == 200, f"record original failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert data["status"] == "recorded"
    assert data["mutation_detected"] is False, "First commitment → no mutation"

    # Record a mutated commitment (deadline moved)
    r = client.post("/api/oem/loop1.5/mutation/record", json={
        "entity": "TestCorp",
        "commitment_text": "Deliver SSO by 2025-01-31",
        "actor": "jane.d@acme.com",
        "artifact": "crm:testcorp-2",
        "timestamp": "2026-06-25T10:00:00+00:00",
    }, headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "recorded"
    assert data["mutation_detected"] is True, "Second commitment (different wording) → mutation detected"

    # GET the mutation history
    r = client.get("/api/oem/loop1.5/mutation/TestCorp", headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["entity"] == "TestCorp"
    assert len(data["history"]) >= 2, \
        f"History must contain BOTH wordings. Got {len(data['history'])}"
    wordings = [entry["commitment_text"] for entry in data["history"]]
    assert "Deliver SSO by 2024-12-15" in wordings, "Original wording must be preserved"
    assert "Deliver SSO by 2025-01-31" in wordings, "Mutated wording must be preserved"
    assert len(data["mutations"]) >= 1, "At least 1 mutation event must be recorded"
    mutation = data["mutations"][0]
    assert mutation["old_text"] == "Deliver SSO by 2024-12-15"
    assert mutation["new_text"] == "Deliver SSO by 2025-01-31"


def test_loop1_5_mutation_no_false_positive_via_http(client):
    """POST the same commitment twice → no mutation detected."""
    # Record original
    client.post("/api/oem/loop1.5/mutation/record", json={
        "entity": "StableCorp",
        "commitment_text": "Deliver API by Q3",
        "actor": "jane.d@acme.com",
        "artifact": "crm:stable-1",
        "timestamp": "2026-06-01T10:00:00+00:00",
    }, headers=_headers())

    # Record identical wording
    r = client.post("/api/oem/loop1.5/mutation/record", json={
        "entity": "StableCorp",
        "commitment_text": "Deliver API by Q3",  # SAME wording
        "actor": "jane.d@acme.com",
        "artifact": "crm:stable-2",
        "timestamp": "2026-06-25T10:00:00+00:00",
    }, headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["mutation_detected"] is False, \
        "Same wording twice → no mutation (avoid false positives)"

    r = client.get("/api/oem/loop1.5/mutation/StableCorp", headers=_headers())
    data = r.json()
    assert len(data["mutations"]) == 0, "No mutations should be recorded"


# ─── 2. Disagreement Detection — HTTP ──────────────────────────────────────

def test_loop1_5_disagreement_detection_via_http(client):
    """POST two conflicting Evidence objects (different claim_types), GET disagreements.

    Engineering's reported_statement ('SSO is on track') vs customer's
    observed_fact ('SSO missed the deadline'). Must detect the disagreement
    and favor the observed_fact (more epistemically reliable).
    """
    r = client.post("/api/oem/loop1.5/disagreements/detect", json={
        "entity": "Globex",
        "topic": "SSO",
        "evidence": [
            {
                "claim": "SSO is on track for Q4",
                "claim_type": "reported_statement",
                "observed_facts": [{"source": "engineering", "date": "2026-06-15", "text": "SSO on track", "people": []}],
            },
            {
                "claim": "SSO missed the Q4 deadline",
                "claim_type": "observed_fact",
                "observed_facts": [{"source": "customer signals", "date": "2026-07-01", "text": "SSO missed", "people": []}],
            },
        ],
    }, headers=_headers())
    assert r.status_code == 200, f"disagreements/detect failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert len(data["disagreements"]) >= 1, \
        f"Must detect the disagreement. Got: {data}"
    d = data["disagreements"][0]
    assert d["claim_a_claim_type"] != d["claim_b_claim_type"], \
        "Disagreement must be between different claim_types"
    # Resolution must favor the observed_fact (more epistemically reliable)
    favored_type = d["claim_a_claim_type"] if d["resolution_favors"] == "a" else d["claim_b_claim_type"]
    assert favored_type == "observed_fact", \
        f"Resolution should favor observed_fact. Got: {favored_type}"


def test_loop1_5_disagreement_no_false_positive_via_http(client):
    """POST two aligned Evidence objects → no disagreements detected."""
    r = client.post("/api/oem/loop1.5/disagreements/detect", json={
        "entity": "Globex",
        "topic": "SSO",
        "evidence": [
            {
                "claim": "SSO is on track for Q4",
                "claim_type": "reported_statement",
                "observed_facts": [],
            },
            {
                "claim": "SSO was delivered for Q4",
                "claim_type": "observed_fact",
                "observed_facts": [],
            },
        ],
    }, headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert len(data["disagreements"]) == 0, \
        f"No disagreement when claims align. Got: {data['disagreements']}"


# ─── 3. delivery_decision — HTTP ───────────────────────────────────────────

def test_loop1_5_delivery_decision_suppress_already_understood_via_http(client):
    """POST inputs where exec already acted + nothing changed → SUPPRESS_ALREADY_UNDERSTOOD."""
    r = client.post("/api/oem/loop1.5/delivery-decision", json={
        "exec_already_acted": True,
        "materially_changed_since_last_shown": False,
        "has_high_stakes_signal": False,
        "is_cold_start": False,
        "shown_count": 1,
    }, headers=_headers())
    assert r.status_code == 200, f"delivery-decision failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert data["decision"] == "SUPPRESS_ALREADY_UNDERSTOOD", \
        f"Exec already acted + nothing changed → SUPPRESS_ALREADY_UNDERSTOOD. Got: {data['decision']}"


def test_loop1_5_delivery_decision_deliver_now_via_http(client):
    """POST inputs with high stakes + materially changed → DELIVER_NOW."""
    r = client.post("/api/oem/loop1.5/delivery-decision", json={
        "exec_already_acted": False,
        "materially_changed_since_last_shown": True,
        "has_high_stakes_signal": True,
        "is_cold_start": False,
        "shown_count": 0,
    }, headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["decision"] == "DELIVER_NOW", \
        f"High stakes + materially changed → DELIVER_NOW. Got: {data['decision']}"


def test_loop1_5_delivery_decision_defer_in_cold_start_via_http(client):
    """POST inputs in cold-start mode WITHOUT high-stakes → DEFER_UNTIL_EVIDENCE.

    CRITICAL-01 fix: cold-start with high-stakes no longer defers.
    """
    r = client.post("/api/oem/loop1.5/delivery-decision", json={
        "exec_already_acted": False,
        "materially_changed_since_last_shown": True,
        "has_high_stakes_signal": False,  # No high-stakes → defer
        "is_cold_start": True,
        "shown_count": 0,
    }, headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["decision"] == "DEFER_UNTIL_EVIDENCE", \
        f"Cold-start (no high-stakes) → DEFER_UNTIL_EVIDENCE. Got: {data['decision']}"

    # Cold-start + high-stakes → does NOT defer (safety valve)
    r2 = client.post("/api/oem/loop1.5/delivery-decision", json={
        "exec_already_acted": False,
        "materially_changed_since_last_shown": True,
        "has_high_stakes_signal": True,
        "is_cold_start": True,
        "shown_count": 0,
    }, headers=_headers())
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["decision"] != "DEFER_UNTIL_EVIDENCE", \
        f"Cold-start + high-stakes → must NOT defer. Got: {data2['decision']}"


# ─── 4. Situation — HTTP ───────────────────────────────────────────────────

def test_loop1_5_situation_via_http(client):
    """GET /api/oem/loop1.5/situation/{entity} returns a Situation with 7 fields.

    With demo seed, Globex has signals → Situation must be populated.
    """
    r = client.get("/api/oem/loop1.5/situation/Globex", headers=_headers())
    assert r.status_code == 200, f"situation GET failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    situation = data["situation"]
    # Verify all 7 fields are present
    for field in ["what_is_happening", "entities", "commitments", "evidence", "current_state", "prior_whispers", "timeline"]:
        assert field in situation, f"Situation missing field: {field}"
    # With demo seed, Globex has signals → entities must contain Globex
    assert "Globex" in situation["entities"], \
        f"Globex must be in entities. Got: {situation['entities']}"
    # current_state must be one of the valid values
    assert situation["current_state"] in ("at_risk", "on_track", "unknown"), \
        f"Invalid current_state: {situation['current_state']}"


def test_loop1_5_situation_unknown_entity_via_http(client):
    """GET /api/oem/loop1.5/situation/{unknown} returns 404 or empty situation."""
    r = client.get("/api/oem/loop1.5/situation/NonexistentCorp", headers=_headers())
    # Either 404 or 200 with empty situation (both are honest — let the implementation decide)
    assert r.status_code in (200, 404), \
        f"Unknown entity should return 200 or 404. Got: {r.status_code}"


# ─── 5. Cold-Start Mode — HTTP ─────────────────────────────────────────────

def test_loop1_5_cold_start_mode_via_http(client):
    """GET /api/oem/loop1.5/cold-start returns the current rung + suppression state.

    The response must include:
      - rung (one of RETRIEVAL_ONLY, LOW_CONFIDENCE_WHISPERS, FULL_WHISPERS)
      - signal_count
      - should_suppress_whispers (bool)
      - whisper_confidence_level ('low' or 'full')
    """
    r = client.get("/api/oem/loop1.5/cold-start", headers=_headers())
    assert r.status_code == 200, f"cold-start GET failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert "rung" in data, "Response missing rung"
    assert data["rung"] in ("RETRIEVAL_ONLY", "LOW_CONFIDENCE_WHISPERS", "FULL_WHISPERS"), \
        f"Invalid rung: {data['rung']}"
    assert "signal_count" in data, "Response missing signal_count"
    assert "should_suppress_whispers" in data, "Response missing should_suppress_whispers"
    assert isinstance(data["should_suppress_whispers"], bool), \
        "should_suppress_whispers must be a bool"
    assert "whisper_confidence_level" in data, "Response missing whisper_confidence_level"
    assert data["whisper_confidence_level"] in ("low", "full"), \
        f"Invalid whisper_confidence_level: {data['whisper_confidence_level']}"


def test_loop1_5_cold_start_mode_with_few_signals_via_http(client):
    """With few signals, cold-start mode should suppress whispers.

    This test seeds a fresh state with few signals and verifies the
    suppression. We use a separate endpoint parameter to control the
    signal count for testing purposes.
    """
    # The cold-start endpoint with a signal_count override (for testing)
    r = client.get("/api/oem/loop1.5/cold-start?signal_count=3&has_high_stakes_signal=false", headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["rung"] == "RETRIEVAL_ONLY", \
        f"3 signals → RETRIEVAL_ONLY. Got: {data['rung']}"
    assert data["should_suppress_whispers"] is True, \
        "Retrieval-only mode must suppress whispers"

    # With high-stakes override
    r = client.get("/api/oem/loop1.5/cold-start?signal_count=3&has_high_stakes_signal=true", headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["rung"] == "RETRIEVAL_ONLY", "Rung is based on signal count (still 3)"
    assert data["should_suppress_whispers"] is False, \
        "High-stakes signal must override suppression — Maestro must speak"
