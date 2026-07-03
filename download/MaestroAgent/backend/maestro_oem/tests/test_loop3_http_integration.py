"""Loop 3 — Decision Intelligence HTTP integration tests.

Per the established pattern, capabilities ship with HTTP endpoints in
the same commit. These tests verify the production delivery path.

HTTP endpoints:
  POST /api/oem/loop3/decision                       — create/propose a decision
  GET  /api/oem/loop3/decision/{decision_id}         — get a decision by ID
  POST /api/oem/loop3/decision/{decision_id}/assumptions  — record assumptions
  POST /api/oem/loop3/decision/{decision_id}/hypothesis   — state hypothesis
  POST /api/oem/loop3/decision/{decision_id}/decide       — make the decision
  POST /api/oem/loop3/decision/{decision_id}/outcome      — observe outcome
  GET  /api/oem/loop3/decision/{decision_id}/learning     — get/write learning entry
  GET  /api/oem/loop3/patterns                            — detect cross-decision patterns
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


def _create_decision(client, intent="Prioritize SSO delivery to Globex", entity="Globex"):
    """Helper: create a decision and return the decision_id."""
    r = client.post("/api/oem/loop3/decision", json={
        "intent": intent,
        "entity": entity,
    }, headers=_headers())
    assert r.status_code == 200, f"create decision failed: {r.status_code} {r.text[:200]}"
    return r.json()["decision_id"]


# ─── 1. Create + Get decision ──────────────────────────────────────────────

def test_loop3_create_and_get_decision(client):
    """POST /loop3/decision creates a decision; GET retrieves it."""
    decision_id = _create_decision(client, intent="Test decision", entity="TestCorp")

    r = client.get(f"/api/oem/loop3/decision/{decision_id}", headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["decision_id"] == decision_id
    assert data["intent"] == "Test decision"
    assert data["entity"] == "TestCorp"
    assert data["status"] == "PROPOSED"


def test_loop3_get_unknown_decision_returns_404(client):
    """GET /loop3/decision/{unknown} returns 404."""
    r = client.get("/api/oem/loop3/decision/nonexistent-id", headers=_headers())
    assert r.status_code == 404


# ─── 2. Full decision lifecycle through HTTP ───────────────────────────────

def test_loop3_full_lifecycle_via_http(client):
    """Full decision lifecycle through HTTP:
    create → record_assumptions → state_hypothesis → decide → outcome → learning
    """
    decision_id = _create_decision(client, intent="Prioritize SSO for Globex", entity="Globex")

    # Record assumptions
    r = client.post(f"/api/oem/loop3/decision/{decision_id}/assumptions", json={
        "assumptions": [
            {"text": "Globex will renew if SSO ships by Q4", "source": "sales"},
            {"text": "Engineering can deliver SSO by Q4", "source": "eng"},
        ],
    }, headers=_headers())
    assert r.status_code == 200, f"assumptions failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert data["status"] == "ASSUMPTIONS_RECORDED"
    assert len(data["assumptions"]) == 2
    for a in data["assumptions"]:
        assert a["claim_type"] == "assumption"

    # State hypothesis
    r = client.post(f"/api/oem/loop3/decision/{decision_id}/hypothesis", json={
        "hypothesis": "SSO will ship by Q4 and Globex will renew",
    }, headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "HYPOTHESIS_STATED"
    assert data["hypothesis"]["claim_type"] == "prediction"

    # Decide
    r = client.post(f"/api/oem/loop3/decision/{decision_id}/decide", json={
        "decision_text": "Prioritize SSO over Initech integration for Q4",
    }, headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "DECIDED"
    assert data["decision_text"] == "Prioritize SSO over Initech integration for Q4"

    # Observe outcome
    r = client.post(f"/api/oem/loop3/decision/{decision_id}/outcome", json={
        "outcome": "SSO shipped by Q4, Globex renewed",
    }, headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "OUTCOME_OBSERVED"
    assert data["outcome"]["claim_type"] == "outcome"

    # Learning
    r = client.get(f"/api/oem/loop3/decision/{decision_id}/learning", headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "LEARNING_RECORDED"
    entry = data["learning_entry"]
    assert entry, "Learning entry must be non-empty"
    assert len(entry) >= 50, f"Learning entry must be rich (≥50 chars). Got: {entry!r}"

    # REJECT placeholders
    FORBIDDEN = ["Learning recorded.", "Decision complete.", "TODO", "placeholder"]
    for phrase in FORBIDDEN:
        assert phrase.lower() not in entry.lower(), \
            f"Learning entry must not be a placeholder. Got: {entry!r}"

    # Must reference the actual decision + outcome
    assert "globex" in entry.lower() or "sso" in entry.lower() or "decision" in entry.lower(), \
        f"Must reference the decision/entity. Got: {entry!r}"
    assert "renewed" in entry.lower() or "shipped" in entry.lower() or "outcome" in entry.lower(), \
        f"Must reference the outcome. Got: {entry!r}"

    # Richness lesson: must acknowledge causality uncertainty
    assert "does not know" in entry.lower() or "uncertain" in entry.lower() or "caus" in entry.lower() or "may have" in entry.lower(), \
        f"Learning entry must acknowledge causality uncertainty. Got: {entry!r}"


def test_loop3_learning_honest_when_hypothesis_wrong(client):
    """When the hypothesis was wrong, the learning entry must honestly say so."""
    decision_id = _create_decision(client, intent="Ship on time for Globex", entity="Globex")

    client.post(f"/api/oem/loop3/decision/{decision_id}/assumptions", json={
        "assumptions": [{"text": "Globex will renew if we ship on time", "source": "sales"}],
    }, headers=_headers())
    client.post(f"/api/oem/loop3/decision/{decision_id}/hypothesis", json={
        "hypothesis": "Shipping on time will lead to renewal",
    }, headers=_headers())
    client.post(f"/api/oem/loop3/decision/{decision_id}/decide", json={
        "decision_text": "Ship on time",
    }, headers=_headers())
    client.post(f"/api/oem/loop3/decision/{decision_id}/outcome", json={
        "outcome": "SSO missed Q4, Globex churned",
    }, headers=_headers())

    r = client.get(f"/api/oem/loop3/decision/{decision_id}/learning", headers=_headers())
    assert r.status_code == 200
    entry = r.json()["learning_entry"]
    assert any(word in entry.lower() for word in ["wrong", "incorrect", "missed", "churned", "did not", "failed"]), \
        f"Learning entry must honestly say the hypothesis was wrong. Got: {entry!r}"


# ─── 3. Cross-decision pattern detection through HTTP ──────────────────────

def test_loop3_cross_decision_patterns_via_http(client):
    """Create 3 decisions with the same wrong assumption, then GET patterns."""
    for i in range(3):
        did = _create_decision(client, intent=f"Decision #{i+1}", entity="Globex")
        client.post(f"/api/oem/loop3/decision/{did}/assumptions", json={
            "assumptions": [{"text": "Globex will renew if we ship on time", "source": "sales"}],
        }, headers=_headers())
        client.post(f"/api/oem/loop3/decision/{did}/hypothesis", json={
            "hypothesis": "Shipping on time will lead to renewal",
        }, headers=_headers())
        client.post(f"/api/oem/loop3/decision/{did}/decide", json={
            "decision_text": f"Ship on time #{i+1}",
        }, headers=_headers())
        client.post(f"/api/oem/loop3/decision/{did}/outcome", json={
            "outcome": "Shipped on time, Globex did not renew",
        }, headers=_headers())
        client.get(f"/api/oem/loop3/decision/{did}/learning", headers=_headers())

    r = client.get("/api/oem/loop3/patterns?min_decisions=2", headers=_headers())
    assert r.status_code == 200, f"patterns failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    patterns = data["patterns"]
    assert len(patterns) >= 1, f"Must detect the recurring wrong-assumption pattern. Got: {patterns}"

    renewal_pattern = next(
        (p for p in patterns if "renew" in p["assumption_text"].lower()),
        None,
    )
    assert renewal_pattern is not None, "Must detect the renewal assumption pattern"
    assert renewal_pattern["decision_count"] >= 3, \
        f"Pattern must count 3 decisions. Got: {renewal_pattern['decision_count']}"
