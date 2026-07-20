"""
S1-01 regression test: IDOR / entity isolation gate.

Verifies that asking about a nonexistent entity (e.g., "Elon Musk") does
NOT return another entity's data. The previous bug dumped all 9 signals
when no match was found — a data-leak class bug.

This test guards against the S1-01 fix being reverted.
"""
import sys
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "maestro-personal" / "src"))
sys.path.insert(0, str(REPO / "backend"))


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a test client with a seeded DB."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("MAESTRO_PERSONAL_DB", db_path)

    from maestro_personal_shell.api import save_signal_to_db
    signals = [
        {"signal_id": "s1", "entity": "Alex Chen", "text": "I will send pricing deck by Friday",
         "signal_type": "commitment_made", "timestamp": "2026-07-01T00:00:00Z", "user_email": "test@personal.local"},
        {"signal_id": "s2", "entity": "Maria Garcia", "text": "Maria asked for proposal",
         "signal_type": "reported_statement", "timestamp": "2026-07-02T00:00:00Z", "user_email": "test@personal.local"},
    ]
    for sig in signals:
        save_signal_to_db(sig, db_path=db_path)

    from maestro_personal_shell.api import app
    return TestClient(app)


def test_s1_01_nonexistent_entity_does_not_leak_data(client):
    """Asking about a nonexistent entity must NOT return other entities' data."""
    login_resp = client.post("/api/auth/login", json={
        "user_email": "test@personal.local",
        "password": "test",
    })
    assert login_resp.status_code == 200
    token = login_resp.json().get("token", "")

    resp = client.post(
        "/api/ask",
        json={"query": "What did I promise Elon Musk?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    answer = data.get("answer", "").lower()
    evidence_refs = data.get("evidence_refs", [])

    assert "don't have" in answer or "no matching" in answer or "no information" in answer, \
        f"Expected abstention, got: {answer[:200]}"
    assert len(evidence_refs) == 0, \
        f"Expected 0 evidence refs for nonexistent entity, got {len(evidence_refs)}"
    assert data.get("confidence", 1.0) == 0.0, \
        f"Expected confidence 0.0 for abstention, got {data.get('confidence')}"


def test_s1_01_known_entity_returns_data(client):
    """Asking about a known entity must return that entity's data (positive case)."""
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
    evidence_refs = data.get("evidence_refs", [])
    all_text = answer + " " + " ".join(str(r) for r in evidence_refs).lower()

    assert "alex" in all_text, \
        f"Expected 'alex' in response, got: {all_text[:200]}"
