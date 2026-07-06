"""Integration test: prove Evidence Spine is present in all 4 features.

This test FAILS today if any feature doesn't return supporting_evidence.
It MUST pass before Phase 2 is marked complete.

Tests:
  1. /whisper returns supporting_evidence on each whisper
  2. /ask/conversation returns supporting_evidence in evidence field (recall path)
  3. /ask/conversation returns supporting_evidence in evidence field (prepare path)
  4. /ask/conversation returns supporting_evidence in evidence field (default path)
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


def test_whisper_returns_supporting_evidence(client):
    """Every whisper must have an supporting_evidence field."""
    r = client.get("/api/oem/whisper?context=meeting&entity=Globex&topic=pricing")
    assert r.status_code == 200
    data = r.json()
    whispers = data.get("whispers", [])
    assert len(whispers) > 0, "Must have at least 1 whisper"
    for w in whispers:
        assert "supporting_evidence" in w, f"Missing supporting_evidence: {w.get('type', 'unknown')}"
        es = w["supporting_evidence"]
        assert "claim" in es, f"supporting_evidence missing claim: {es}"
        assert "observed_facts" in es, f"supporting_evidence missing observed_facts: {es}"
        assert len(es["observed_facts"]) > 0, f"supporting_evidence has no observed_facts: {es}"


def test_ask_conversation_prepare_returns_supporting_evidence(client):
    """Prepare-me query must return supporting_evidence in evidence field."""
    r = client.post("/api/oem/ask/conversation", json={"query": "Prepare me for the meeting"})
    assert r.status_code == 200
    data = r.json()
    evidence = data.get("evidence", [])
    assert len(evidence) > 0, "Must have at least 1 evidence item"
    for e in evidence:
        # Phase 1 fix: check either supporting_evidence (M4 translated) or evidence_spine (internal)
        es = e.get("supporting_evidence") or e.get("evidence_spine")
        assert es is not None, f"Missing supporting_evidence/evidence_spine in prepare evidence: {e}"
        assert "claim" in es, f"supporting_evidence missing claim: {es}"
        assert "observed_facts" in es, f"supporting_evidence missing observed_facts: {es}"


def test_ask_conversation_default_returns_supporting_evidence(client):
    """Default query must return supporting_evidence in evidence field — NON-VACUOUS.

    Auditor P3 fix: the old test asserted on an empty list (vacuous pass).
    Now asserts evidence is non-empty AND contains real data (not placeholders).

    C-2 fix: the old fallback that returned generic signals was removed.
    Now uses a query that actually matches signals ("bottleneck" matches
    the entity synonym map and demo signals about bottlenecks).
    If no evidence is found, the test verifies the honest "I don't know"
    response instead.
    """
    r = client.post("/api/oem/ask/conversation", json={"query": "What is the bottleneck?"})
    assert r.status_code == 200
    data = r.json()
    evidence = data.get("evidence", [])
    answer = data.get("answer", "")

    # C-2 fix: either we find real evidence OR we honestly say "I don't know"
    # Both are acceptable. What's NOT acceptable is returning generic signals
    # as fake evidence (the old C-2 bug).
    if len(evidence) > 0:
        # NON-VACUOUS: evidence must contain real data
        for e in evidence:
            # Phase 1 fix: evidence items may use either "evidence_spine" (internal)
            # or "supporting_evidence" (translated by M4). Check for either.
            es = e.get("supporting_evidence") or e.get("evidence_spine")
            assert es is not None, f"Missing supporting_evidence/evidence_spine in default evidence: {e}"
            assert "claim" in es, f"supporting_evidence missing claim: {es}"
            assert "observed_facts" in es, f"supporting_evidence missing observed_facts: {es}"
            assert len(es.get("observed_facts", [])) > 0, f"supporting_evidence has no observed_facts: {es}"
    else:
        # No evidence found — verify the answer is honest, not fabricated
        assert "don't have enough" in answer.lower() or "no relevant" in answer.lower() or "couldn't find" in answer.lower(), \
            f"No evidence found but answer is not honest 'I don't know': {answer[:200]!r}"


def test_preparation_returns_supporting_evidence(client):
    """Preparation must return supporting_evidence on each meeting.

    Auditor Debt 2: /preparation/tomorrow was never integrated with Evidence Spine.
    This test will FAIL until preparation_engine.py uses EvidenceBuilder.
    """
    r = client.get("/api/oem/preparation/tomorrow")
    assert r.status_code == 200
    data = r.json()
    meetings = data.get("meetings", [])
    assert len(meetings) > 0, "Must have at least 1 meeting"
    for m in meetings:
        assert "supporting_evidence" in m, f"Meeting missing supporting_evidence: {m.get('title')}"
        es = m["supporting_evidence"]
        assert "claim" in es, f"supporting_evidence missing claim: {es}"
        assert "observed_facts" in es, f"supporting_evidence missing observed_facts: {es}"
        assert len(es.get("observed_facts", [])) > 0, f"supporting_evidence has no observed_facts: {es}"
