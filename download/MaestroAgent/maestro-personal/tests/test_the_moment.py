"""
The Moment — the masterpiece endpoint test.

Tests that /api/the-moment returns ONE commitment (the most important)
or silence (has_moment=False). Not a list. One card. The Spotlight moment.
"""

import sys
import os
import pathlib
import tempfile
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pytest


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-moment"
    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)
    yield api_module
    os.unlink(db_path)
    del os.environ["MAESTRO_PERSONAL_DB"]
    del os.environ["MAESTRO_PERSONAL_TOKEN"]


@pytest.fixture
def client(temp_db):
    from fastapi.testclient import TestClient
    from unittest.mock import patch, AsyncMock
    # Mock the materiality gate so Moment tests don't depend on LLM availability.
    # The materiality gate returns "speak" (permissive) so the rule-based scoring
    # determines the Moment — not the LLM.
    with patch(
        "maestro_personal_shell.materiality_gate.evaluate_materiality",
        new_callable=AsyncMock,
        return_value={"should_speak": True, "materiality_score": 0.5, "urgency": "medium", "reasoning": "test", "llm_powered": False},
    ):
        yield TestClient(temp_db.app)


@pytest.fixture
def auth_headers(client):
    response = client.post("/api/auth/login", json={"password": "any"})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestTheMoment:
    """The masterpiece endpoint — one card, not a list."""

    def test_empty_state_returns_silence(self, client, auth_headers):
        """When no signals exist, the moment is silence (has_moment=False)."""
        response = client.get("/api/the-moment", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["has_moment"] == False
        assert data["commitment"] is None

    def test_returns_one_commitment_not_a_list(self, client, auth_headers):
        """The moment returns ONE commitment, not a list."""
        # Add 3 commitments
        for i, entity in enumerate(["Alex", "Sam", "Pat"]):
            client.post("/api/signals", json={
                "entity": entity,
                "text": f"I will send item {i} by Friday",
                "signal_type": "commitment_made",
            }, headers=auth_headers)

        response = client.get("/api/the-moment", headers=auth_headers)
        data = response.json()
        assert data["has_moment"] == True
        # Must be ONE commitment, not a list
        assert isinstance(data["commitment"], dict)
        assert "entity" in data["commitment"]
        assert "text" in data["commitment"]

    def test_stale_commitment_wins_over_fresh(self, client, auth_headers):
        """The stalest commitment should be the moment — the one at risk."""
        # Add a stale commitment (10 days ago)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the old proposal",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        # Add a fresh commitment (just now)
        client.post("/api/signals", json={
            "entity": "Sam",
            "text": "I will send the new report",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        response = client.get("/api/the-moment", headers=auth_headers)
        data = response.json()
        assert data["has_moment"] == True
        # The old commitment should win (age + stale bonus)
        assert "old" in data["commitment"]["text"].lower() or "alex" in data["commitment"]["entity"].lower()

    def test_includes_why_this_one(self, client, auth_headers):
        """The moment explains WHY this commitment, not just WHAT."""
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the proposal by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        response = client.get("/api/the-moment", headers=auth_headers)
        data = response.json()
        assert data["has_moment"] == True
        assert data["why_this_one"]  # non-empty explanation

    def test_includes_source_evidence(self, client, auth_headers):
        """The moment includes the source evidence — the original signal."""
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the proposal by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        response = client.get("/api/the-moment", headers=auth_headers)
        data = response.json()
        assert data["has_moment"] == True
        assert len(data["source_evidence"]) > 0
        assert "proposal" in data["source_evidence"][0]["text"].lower()

    def test_silence_when_only_neutral_signals(self, client, auth_headers):
        """If no commitments exist, the moment is silence — not a random signal."""
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "The weather is nice today.",
            "signal_type": "reported_statement",
        }, headers=auth_headers)

        response = client.get("/api/the-moment", headers=auth_headers)
        data = response.json()
        # No commitments → silence
        assert data["has_moment"] == False

    def test_commitment_made_scores_higher_than_received(self, client, auth_headers):
        """A commitment the USER made (promise) scores higher than one received."""
        # User's promise
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the proposal",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        # Received commitment (someone else's promise — less actionable)
        client.post("/api/signals", json={
            "entity": "Sam",
            "text": "They said they will send the report",
            "signal_type": "personal.promise",
        }, headers=auth_headers)

        response = client.get("/api/the-moment", headers=auth_headers)
        data = response.json()
        assert data["has_moment"] == True
        # The user's own promise should win
        assert "proposal" in data["commitment"]["text"].lower()
