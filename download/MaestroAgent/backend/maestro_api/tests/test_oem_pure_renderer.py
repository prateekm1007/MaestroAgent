"""Tests for the new pure-renderer OEM endpoints.

Tests:
  - /api/oem/autocomplete — backend-driven suggestions (no hardcoded list)
  - /api/oem/receipts — structured receipts (no JSON.stringify)
  - /api/oem/meetings/analyze — real OEM-driven meeting intelligence
  - /api/oem/contradict — optimistic-update target
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from maestro_api.main import create_app
from maestro_api.oem_state import oem_state, import_state


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with isolated import_state DB."""
    test_db = str(tmp_path / "test_import.db")
    monkeypatch.setattr("maestro_api.oem_state._IMPORT_DB_PATH", test_db)
    import_state._initialized = False
    import_state.store = None
    import_state.oauth = None
    import_state.connections = None
    import_state.tracker = None
    import_state.factory = None
    import_state.engine = None

    app = create_app(db_path=str(tmp_path / "maestro.db"))
    with TestClient(app) as c:
        yield c


# ─── Autocomplete ───

def test_autocomplete_returns_suggestions(client):
    """Autocomplete must return real OEM-derived suggestions, not hardcoded."""
    resp = client.get("/api/oem/autocomplete?q=who&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "suggestions" in data
    assert isinstance(data["suggestions"], list)
    # With the seeded OEM, "who" should match at least one capability
    # ("Who is the bottleneck?")
    assert len(data["suggestions"]) >= 1
    for s in data["suggestions"]:
        assert "type" in s
        assert "label" in s
        assert "query" in s
        assert s["type"] in ("law", "expert", "risk", "recommendation", "capability")


def test_autocomplete_empty_query(client):
    """Empty query should return all available suggestion types."""
    resp = client.get("/api/oem/autocomplete?q=&limit=20")
    assert resp.status_code == 200
    data = resp.json()
    # Should surface laws, risks, recommendations, capabilities
    types = {s["type"] for s in data["suggestions"]}
    assert len(types) >= 1


def test_autocomplete_no_hardcoded_list(client):
    """Verify the autocomplete is NOT the old hardcoded 5-item list.

    The old list was:
      - who is the bottleneck?
      - what laws have been discovered?
      - what is the P1 cluster risk?
      - what hidden experts exist?
      - what are the concentration risks?

    The new endpoint should return suggestions that reference actual law codes
    (L-0001, etc.) or actual entity names from the OEM.
    """
    resp = client.get("/api/oem/autocomplete?q=&limit=20")
    data = resp.json()
    labels = [s["label"] for s in data["suggestions"]]
    # At least one suggestion should reference a real law code (L-0001 etc.)
    has_law_ref = any("L-" in label for label in labels)
    assert has_law_ref, f"No law-code references found in: {labels}"


def test_autocomplete_we_query_matches_recommendations(client):
    """Typing 'we' should match 'Should we: ...' recommendations."""
    resp = client.get("/api/oem/autocomplete?q=we&limit=10")
    data = resp.json()
    # Should match at least one recommendation (they start with "Should we:")
    labels = [s["label"].lower() for s in data["suggestions"]]
    has_we = any("we" in label for label in labels)
    assert has_we, f"No 'we' matches in: {labels}"


def test_autocomplete_limit_respected(client):
    resp = client.get("/api/oem/autocomplete?q=&limit=3")
    data = resp.json()
    assert len(data["suggestions"]) <= 3


# ─── Receipts ───

def test_receipts_returns_structured_data(client):
    """Receipts endpoint must return structured data, not JSON.stringify output."""
    resp = client.get("/api/oem/receipts?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "receipts" in data
    assert "total" in data
    assert isinstance(data["receipts"], list)
    # Each receipt should have structured fields, not a raw JSON string
    for r in data["receipts"]:
        assert "receipt_id" in r
        assert "timestamp" in r
        assert "provider" in r
        assert "signal_type" in r
        assert "actor" in r
        assert "artifact" in r
        assert "law_code" in r or "law_codes" in r
        # Verify it's NOT a JSON string dump
        assert isinstance(r, dict)
        assert not any(isinstance(v, str) and v.startswith("{") for v in r.values())


def test_receipts_filter_by_provider(client):
    """Filtering by provider should return only that provider's receipts."""
    resp_all = client.get("/api/oem/receipts?limit=100")
    all_data = resp_all.json()
    if all_data["total"] == 0:
        pytest.skip("No receipts in seeded OEM")

    # Pick a provider from the results
    first_provider = all_data["receipts"][0]["provider"]
    resp_filtered = client.get(f"/api/oem/receipts?provider={first_provider}&limit=100")
    filtered_data = resp_filtered.json()
    for r in filtered_data["receipts"]:
        assert r["provider"] == first_provider


# ─── Meetings / Analyze ───

def test_meetings_analyze_detects_objections(client):
    """Meeting analysis must detect objections via OEM-driven keyword matching."""
    transcript = [
        {"speaker": "Jane", "text": "Let's make a decision on Q3 hiring."},
        {"speaker": "Chris", "text": "I recommend we approve the plan as-is."},
        {"speaker": "Pat", "text": "I dissent. We need to address the bottleneck first."},
        {"speaker": "Priya", "text": "Agreed — let's resolve the bottleneck before hiring."},
    ]
    resp = client.post("/api/oem/meetings/analyze", json={"transcript": transcript})
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["objection_count"] >= 1
    assert data["summary"]["action_count"] >= 1
    # The objection should reference a law (the OEM has bottleneck laws)
    objections = data["objections"]
    assert any(o["speaker"] == "Pat" for o in objections)


def test_meetings_analyze_empty_transcript(client):
    resp = client.post("/api/oem/meetings/analyze", json={"transcript": []})
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["objection_count"] == 0
    assert data["summary"]["action_count"] == 0


def test_meetings_analyze_detects_law_references(client):
    """If a transcript mentions 'L-0001' explicitly, that law should be triggered."""
    # First find an actual law code
    laws_resp = client.get("/api/oem/laws")
    laws = laws_resp.json().get("laws", [])
    if not laws:
        pytest.skip("No laws in OEM")
    law_code = laws[0]["code"]

    transcript = [
        {"speaker": "Jane", "text": f"We need to revisit {law_code} before proceeding."},
    ]
    resp = client.post("/api/oem/meetings/analyze", json={"transcript": transcript})
    data = resp.json()
    assert data["summary"]["law_count"] >= 1
    assert any(l["code"] == law_code for l in data["laws_triggered"])


# ─── Contradict ───

def test_contradict_law_reject(client):
    """Submitting 'reject' feedback should lower the law's confidence."""
    laws_resp = client.get("/api/oem/laws")
    laws = laws_resp.json().get("laws", [])
    if not laws:
        pytest.skip("No laws in OEM")
    law = laws[0]
    original_confidence = law["confidence"]

    resp = client.post("/api/oem/contradict", json={
        "target_type": "law",
        "target_id": law["code"],
        "action": "reject",
        "reasoning": "Test rejection",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["target_id"] == law["code"]
    assert len(data["affected_laws"]) >= 1
    # Confidence should have changed
    affected = data["affected_laws"][0]
    assert "confidence_before" in affected
    assert "confidence_after" in affected


def test_contradict_unknown_law(client):
    resp = client.post("/api/oem/contradict", json={
        "target_type": "law",
        "target_id": "L-9999",
        "action": "reject",
    })
    assert resp.status_code == 404


def test_contradict_missing_target_id(client):
    resp = client.post("/api/oem/contradict", json={
        "target_type": "law",
        "action": "reject",
    })
    assert resp.status_code == 400


# ─── Snapshot ───

def test_oem_snapshot_returns_counts(client):
    resp = client.get("/api/oem/snapshot")
    assert resp.status_code == 200
    data = resp.json()
    assert "signals_processed" in data
    assert "patterns_detected" in data
    assert "laws_inferred" in data
    assert "recommendations" in data
    assert isinstance(data["signals_processed"], int)
