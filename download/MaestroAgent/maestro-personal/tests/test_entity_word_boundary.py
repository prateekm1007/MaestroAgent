"""
Entity word-boundary regression test.

Verifies that entity matching uses word boundaries, not substring match.
The previous bug: 'alex' matched 'alexander', 'sam' matched 'sample'.
This caused cross-entity data leakage in /api/ask responses.

Tests the F-S1a/F-S1b fix in ask.py.
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
        {"signal_id": "wb1", "entity": "Alex", "text": "Alex commitment",
         "signal_type": "commitment_made", "timestamp": "2026-07-01T00:00:00Z", "user_email": "test@personal.local"},
        {"signal_id": "wb2", "entity": "Alexander", "text": "Alexander different commitment",
         "signal_type": "commitment_made", "timestamp": "2026-07-01T00:00:00Z", "user_email": "test@personal.local"},
        {"signal_id": "wb3", "entity": "Sam", "text": "Sam promise",
         "signal_type": "commitment_made", "timestamp": "2026-07-01T00:00:00Z", "user_email": "test@personal.local"},
        {"signal_id": "wb4", "entity": "Sample Corp", "text": "Sample Corp report",
         "signal_type": "reported_statement", "timestamp": "2026-07-01T00:00:00Z", "user_email": "test@personal.local"},
    ]
    for sig in signals:
        save_signal_to_db(sig, db_path=db_path)

    from maestro_personal_shell.api import app
    return TestClient(app)


def test_word_boundary_alex_does_not_match_alexander(client):
    """Querying 'Alex' must not return Alexander's data."""
    login_resp = client.post("/api/auth/login", json={
        "user_email": "test@personal.local",
        "password": "test",
    })
    token = login_resp.json().get("token", "")

    resp = client.post(
        "/api/ask",
        json={"query": "What did I promise Alex?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    answer = data.get("answer", "").lower()
    evidence = data.get("evidence_refs", [])

    # Must mention Alex but NOT Alexander's specific data
    assert "alex" in answer, f"Expected 'alex' in answer, got: {answer[:200]}"

    # Must not contain Alexander's unique commitment text
    all_text = answer + " " + " ".join(str(r) for r in evidence).lower()
    assert "alexander different" not in all_text, \
        f"Word-boundary violation: 'Alex' query returned Alexander's data: {all_text[:200]}"


def test_word_boundary_sam_does_not_match_sample(client):
    """Querying 'Sam' must not return Sample Corp's data."""
    login_resp = client.post("/api/auth/login", json={
        "user_email": "test@personal.local",
        "password": "test",
    })
    token = login_resp.json().get("token", "")

    resp = client.post(
        "/api/ask",
        json={"query": "What did I promise Sam?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    answer = data.get("answer", "").lower()
    evidence = data.get("evidence_refs", [])

    all_text = answer + " " + " ".join(str(r) for r in evidence).lower()

    # Must mention Sam
    assert "sam" in all_text, f"Expected 'sam' in response, got: {all_text[:200]}"

    # Must not contain Sample Corp's unique text
    assert "sample corp report" not in all_text, \
        f"Word-boundary violation: 'Sam' query returned Sample Corp data: {all_text[:200]}"
