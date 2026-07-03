"""Integration test: prove Evidence Spine is present in all 4 features.

This test FAILS today if any feature doesn't return evidence_spine.
It MUST pass before Phase 2 is marked complete.

Tests:
  1. /whisper returns evidence_spine on each whisper
  2. /ask/conversation returns evidence_spine in evidence field (recall path)
  3. /ask/conversation returns evidence_spine in evidence field (prepare path)
  4. /ask/conversation returns evidence_spine in evidence field (default path)
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from maestro_api.main import create_app
from maestro_api.oem_state import oem_state, import_state


@pytest.fixture
def client(tmp_path, monkeypatch):
    app_dir = str(__import__("pathlib").Path(__file__).resolve().parents[3])
    monkeypatch.setattr("maestro_api.oem_state._IMPORT_DB_PATH", str(tmp_path / "test_import.db"))
    monkeypatch.setenv("MAESTRO_APP_DIR", app_dir)
    monkeypatch.setenv("MAESTRO_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("MAESTRO_LEARNING_DB", str(tmp_path / "learning.db"))
    monkeypatch.setenv("MAESTRO_WHISPER_DB", str(tmp_path / "whisper.db"))
    monkeypatch.setenv("MAESTRO_ADMIN_PASSWORD", "test")
    monkeypatch.setenv("MAESTRO_RATE_LIMIT_RPM", "10000")
    monkeypatch.setenv("MAESTRO_DEMO_SEED", "true")
    monkeypatch.setenv("MAESTRO_LOCAL_DEV", "true")
    oem_state._initialized = False
    oem_state.engine = None
    oem_state.signals = []
    oem_state._demo_seeded = False
    oem_state._contradiction_log = None
    import_state._initialized = False
    # CRITICAL-01 fix: reset the whisper history store singleton so each
    # test gets a fresh DB (otherwise prior tests' shown_count persists)
    import maestro_api.routes.oem as _oem_routes
    _oem_routes._whisper_history_store = None
    app = create_app(db_path=str(tmp_path / "maestro.db"))
    with TestClient(app) as c:
        yield c
    oem_state._initialized = False
    oem_state.engine = None
    oem_state.signals = []
    _oem_routes._whisper_history_store = None


def test_whisper_returns_evidence_spine(client):
    """Every whisper must have an evidence_spine field."""
    r = client.get("/api/oem/whisper?context=meeting&entity=Globex&topic=pricing")
    assert r.status_code == 200
    data = r.json()
    whispers = data.get("whispers", [])
    assert len(whispers) > 0, "Must have at least 1 whisper"
    for w in whispers:
        assert "evidence_spine" in w, f"Missing evidence_spine: {w.get('type', 'unknown')}"
        es = w["evidence_spine"]
        assert "claim" in es, f"evidence_spine missing claim: {es}"
        assert "observed_facts" in es, f"evidence_spine missing observed_facts: {es}"
        assert len(es["observed_facts"]) > 0, f"evidence_spine has no observed_facts: {es}"


def test_ask_conversation_prepare_returns_evidence_spine(client):
    """Prepare-me query must return evidence_spine in evidence field."""
    r = client.post("/api/oem/ask/conversation", json={"query": "Prepare me for the meeting"})
    assert r.status_code == 200
    data = r.json()
    evidence = data.get("evidence", [])
    assert len(evidence) > 0, "Must have at least 1 evidence item"
    for e in evidence:
        assert "evidence_spine" in e, f"Missing evidence_spine in prepare evidence: {e}"
        es = e["evidence_spine"]
        assert "claim" in es, f"evidence_spine missing claim: {es}"
        assert "observed_facts" in es, f"evidence_spine missing observed_facts: {es}"


def test_ask_conversation_default_returns_evidence_spine(client):
    """Default query must return evidence_spine in evidence field — NON-VACUOUS.

    Auditor P3 fix: the old test asserted on an empty list (vacuous pass).
    Now asserts evidence is non-empty AND contains real data (not placeholders).
    """
    r = client.post("/api/oem/ask/conversation", json={"query": "What is the bottleneck?"})
    assert r.status_code == 200
    data = r.json()
    evidence = data.get("evidence", [])
    # NON-VACUOUS: evidence must be non-empty
    assert len(evidence) > 0, "Default path must return at least 1 evidence item"
    for e in evidence:
        assert "evidence_spine" in e, f"Missing evidence_spine in default evidence: {e}"
        es = e["evidence_spine"]
        assert "claim" in es, f"evidence_spine missing claim: {es}"
        assert "observed_facts" in es, f"evidence_spine missing observed_facts: {es}"
        assert len(es.get("observed_facts", [])) > 0, f"evidence_spine has no observed_facts: {es}"
        # Reject placeholder strings
        for fact in es["observed_facts"]:
            text = fact.get("text", "")
            assert text not in ("", "No specific commitments found"), \
                f"Placeholder text in observed_facts: {fact}"


def test_preparation_returns_evidence_spine(client):
    """Preparation must return evidence_spine on each meeting.

    Auditor Debt 2: /preparation/tomorrow was never integrated with Evidence Spine.
    This test will FAIL until preparation_engine.py uses EvidenceBuilder.
    """
    r = client.get("/api/oem/preparation/tomorrow")
    assert r.status_code == 200
    data = r.json()
    meetings = data.get("meetings", [])
    assert len(meetings) > 0, "Must have at least 1 meeting"
    for m in meetings:
        assert "evidence_spine" in m, f"Meeting missing evidence_spine: {m.get('title')}"
        es = m["evidence_spine"]
        assert "claim" in es, f"evidence_spine missing claim: {es}"
        assert "observed_facts" in es, f"evidence_spine missing observed_facts: {es}"
        assert len(es.get("observed_facts", [])) > 0, f"evidence_spine has no observed_facts: {es}"
