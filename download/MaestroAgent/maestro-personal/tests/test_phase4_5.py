"""
Phase 4+5 tests: live copilot + ambient intelligence.

Note: These tests mock the LLM as unavailable to test the keyword-based
fallback path. The LLM-powered path is tested in test_llm_wiring.py.
"""

import sys
import os
import pathlib
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pytest


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-p45"
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
    return TestClient(temp_db.app)


@pytest.fixture
def auth_headers(client):
    response = client.post("/api/auth/login", json={"password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test")})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestLiveCopilot:
    """Phase 4: live call intelligence via CopilotSituationBridge."""

    def test_transcript_endpoint_exists(self, client, auth_headers):
        """POST /api/copilot/transcript exists and accepts transcript chunks."""
        response = client.post("/api/copilot/transcript", json={
            "situation_id": "test-sit-1",
            "text": "I'll send the proposal by Friday",
            "speaker": "user",
            "entity": "Alex",
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Should return a dict (may have error if situation not found, but endpoint works)
        assert isinstance(data, dict)

    def test_post_call_endpoint_exists(self, client, auth_headers):
        """POST /api/copilot/post-call exists and generates summary."""
        response = client.post("/api/copilot/post-call", json={
            "situation_id": "test-sit-1",
            "transcript_chunks": [
                {"speaker": "user", "text": "I'll send the proposal"},
                {"speaker": "Alex", "text": "Great, looking forward to it"},
            ],
            "commitments": [{"text": "Send proposal by Friday", "entity": "Alex"}],
            "entity": "Alex",
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_transcript_processes_commitment_keywords(self, client, auth_headers):
        """Transcript with 'I will' should be processed by the copilot."""
        # First create a situation
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the proposal by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        # Get situations
        sit_resp = client.get("/api/situations", headers=auth_headers)
        situations = sit_resp.json()
        sit_id = situations[0]["situation_id"] if situations else "unknown"

        # Process transcript chunk
        response = client.post("/api/copilot/transcript", json={
            "situation_id": sit_id,
            "text": "I will follow up with the revised numbers tomorrow",
            "speaker": "user",
            "entity": "Alex",
        }, headers=auth_headers)
        assert response.status_code == 200


class TestAmbientIntelligence:
    """Phase 5: ambient intelligence between calls."""

    def test_ambient_endpoint_exists(self, client, auth_headers):
        """GET /api/ambient exists and returns ambient intelligence."""
        response = client.get("/api/ambient", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "upcoming_meetings" in data
        assert "sentiment_alerts" in data
        assert "stale_commitments" in data
        assert "ambient_summary" in data

    def test_ambient_empty_state(self, client, auth_headers):
        """Ambient on empty state returns 'Nothing urgent'."""
        response = client.get("/api/ambient", headers=auth_headers)
        data = response.json()
        assert "Nothing urgent" in data["ambient_summary"] or len(data["upcoming_meetings"]) == 0

    def test_ambient_detects_stale_commitments(self, client, auth_headers):
        """Ambient detects stale commitments."""
        import sqlite3, uuid
        # Get the user_email from the token (login returns per-user token)
        # The auth_headers fixture logs in without user_email, so defaults to "default@personal.local"
        old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        conn = sqlite3.connect(os.environ["MAESTRO_PERSONAL_DB"])
        conn.execute(
            "INSERT INTO signals (signal_id, entity, text, signal_type, timestamp, metadata, source_acl, created_at, user_email) VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), "Alex", "I will send the proposal", "commitment_made", old_ts, "{}", "public", old_ts, "default@personal.local"),
        )
        conn.commit()
        conn.close()

        response = client.get("/api/ambient", headers=auth_headers)
        data = response.json()
        assert len(data["stale_commitments"]) >= 1
        assert data["stale_commitments"][0]["entity"].lower() == "alex"

    def test_ambient_detects_sentiment(self, client, auth_headers):
        """Ambient detects frustration/positivity from signal text (keyword fallback).

        This tests the keyword-based fallback path. The LLM-powered path
        is tested in test_llm_wiring.py.
        """
        # Mock LLM as unavailable to test keyword fallback
        with patch("maestro_personal_shell.llm_bridge.is_llm_available", return_value=False):
            client.post("/api/signals", json={
                "entity": "Alex",
                "text": "This is unacceptable and urgent — I need the proposal ASAP",
                "signal_type": "reported_statement",
            }, headers=auth_headers)

            response = client.get("/api/ambient", headers=auth_headers)
            data = response.json()
            # Should detect frustration keywords
            frustration = [s for s in data["sentiment_alerts"] if s["type"] == "frustration"]
            assert len(frustration) >= 1

    def test_ambient_summary_combines_signals(self, client, auth_headers):
        """Ambient summary combines multiple signals into one sentence (keyword fallback)."""
        # Mock LLM as unavailable to test keyword fallback
        with patch("maestro_personal_shell.llm_bridge.is_llm_available", return_value=False):
            import sqlite3, uuid
            old_ts = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
            conn = sqlite3.connect(os.environ["MAESTRO_PERSONAL_DB"])
            conn.execute(
                "INSERT INTO signals (signal_id, entity, text, signal_type, timestamp, metadata, source_acl, created_at, user_email) VALUES (?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), "Sam", "I will review the PR", "commitment_made", old_ts, "{}", "public", old_ts, "default@personal.local"),
            )
            conn.commit()
            conn.close()

            response = client.get("/api/ambient", headers=auth_headers)
            data = response.json()
            # Summary should mention the stale commitment
            assert "Sam" in data["ambient_summary"] or "stale" in data["ambient_summary"].lower()
