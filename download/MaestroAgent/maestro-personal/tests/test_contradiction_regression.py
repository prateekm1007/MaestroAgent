"""
Contradiction regression test.

Verifies that contradiction queries (e.g., "What is Orion Tech's pricing?")
return ALL pricing data points when the entity has no LivingSituation.

The previous bug: ask_bridge returned "No active situation found for Orion Tech"
even when the ensemble found 5 evidence items. The fix overrides no-situation
refusals with the actual evidence.

Tests the contradiction regression fix in ask.py.
"""
import sys
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "maestro-personal" / "src"))
sys.path.insert(0, str(REPO / "backend"))


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("MAESTRO_PERSONAL_DB", db_path)

    from maestro_personal_shell.api import save_signal_to_db
    signals = [
        {"signal_id": "con1", "entity": "Orion Tech", "text": "Orion Tech quoted us $120k for the annual contract",
         "signal_type": "reported_statement", "timestamp": "2026-06-01T00:00:00Z", "user_email": "test@personal.local"},
        {"signal_id": "con2", "entity": "Orion Tech", "text": "Orion Tech revised the quote down to $95k after negotiation",
         "signal_type": "reported_statement", "timestamp": "2026-06-10T00:00:00Z", "user_email": "test@personal.local"},
        {"signal_id": "con3", "entity": "Orion Tech", "text": "Orion Tech sent the final invoice at $150k — pricing dispute",
         "signal_type": "reported_statement", "timestamp": "2026-07-01T00:00:00Z", "user_email": "test@personal.local"},
    ]
    for sig in signals:
        save_signal_to_db(sig, db_path=db_path)

    from maestro_personal_shell.api import app
    return TestClient(app)


def test_contradiction_query_returns_evidence_not_refusal(client):
    """Contradiction query must return evidence, not 'No active situation found'."""
    login_resp = client.post("/api/auth/login", json={
        "user_email": "test@personal.local",
        "password": "test",
    })
    token = login_resp.json().get("token", "")

    resp = client.post(
        "/api/ask",
        json={"query": "What is Orion Tech's pricing?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    answer = data.get("answer", "")
    evidence = data.get("evidence_refs", [])

    # Must NOT return the no-situation refusal
    assert "No active situation found" not in answer, \
        f"Contradiction regression: got 'No active situation found' instead of evidence. Answer: {answer[:200]}"

    # Must contain at least one pricing data point
    all_text = answer.lower() + " " + " ".join(str(r) for r in evidence).lower()
    has_pricing = any(amt in all_text for amt in ["$120k", "120k", "$95k", "95k", "$150k", "150k"])
    assert has_pricing, \
        f"Expected pricing data in contradiction response, got: {all_text[:300]}"
