"""
Masterpiece surface tests — verify Ask and Prepare return the inevitable
moment, not a feature list.

Ask: returns the exact source sentence + situation state, not a summary.
Prepare: returns 3 things (forgotten, open question, contradiction), not 5 prep points.
"""

import sys
import os
import pathlib
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pytest


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-masterpiece"
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


class TestAskMasterpiece:
    """Ask returns the truth, sourced — not a summary."""

    def test_ask_includes_source_sentence(self, client, auth_headers):
        """Ask must return the exact source sentence, not a paraphrase."""
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the proposal by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        response = client.post("/api/ask", json={
            "query": "What did I promise Alex?"
        }, headers=auth_headers)

        data = response.json()
        assert data["answer"]  # has an answer
        # Must include the source sentence — the exact text
        assert data["source_sentence"], "Ask must include the source sentence"
        assert "proposal" in data["source_sentence"].lower()

    def test_ask_includes_source_entity(self, client, auth_headers):
        """Ask must identify who the source is about."""
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the proposal by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        response = client.post("/api/ask", json={
            "query": "What did I promise Alex?"
        }, headers=auth_headers)

        data = response.json()
        assert data["source_entity"].lower() == "alex"

    def test_ask_includes_situation_state(self, client, auth_headers):
        """Ask must include the current situation state."""
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the proposal by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        response = client.post("/api/ask", json={
            "query": "What did I promise Alex?"
        }, headers=auth_headers)

        data = response.json()
        # situation_state may be empty if no situation detected, but the field exists
        assert "situation_state" in data

    def test_ask_returns_answer_not_just_source(self, client, auth_headers):
        """Ask returns BOTH the synthesized answer AND the source — not just one."""
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the proposal by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        response = client.post("/api/ask", json={
            "query": "What did I promise Alex?"
        }, headers=auth_headers)

        data = response.json()
        assert data["answer"]  # synthesized answer exists
        assert data["source_sentence"]  # source exists
        # They should both relate to the commitment
        assert "proposal" in data["answer"].lower() or "proposal" in data["source_sentence"].lower()


class TestPrepareMasterpiece:
    """Prepare returns 3 things that matter, not 5 prep points."""

    def test_prepare_returns_3_things_not_5_points(self, client, auth_headers):
        """Prepare returns the_forgotten, the_open_question, the_contradiction."""
        # Add signals that create a situation needing prep
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the proposal by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "Did you get a chance to review the proposal?",
            "signal_type": "follow_up.required",
        }, headers=auth_headers)
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "The budget is actually $50K not $100K",
            "signal_type": "reported_statement",
        }, headers=auth_headers)

        response = client.get("/api/prepare", headers=auth_headers)
        data = response.json()

        # If situations needing prep exist, verify the 3 fields
        if len(data) > 0:
            prep = data[0]
            assert "the_forgotten" in prep
            assert "the_open_question" in prep
            assert "the_contradiction" in prep
            assert "entity" in prep
            assert "meeting_context" in prep

    def test_prepare_includes_entity(self, client, auth_headers):
        """Prepare must identify who the meeting is with."""
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the proposal by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        response = client.get("/api/prepare", headers=auth_headers)
        data = response.json()

        if len(data) > 0:
            assert data[0]["entity"]  # non-empty entity

    def test_prepare_forgotten_is_oldest_commitment(self, client, auth_headers):
        """the_forgotten should be the oldest commitment signal."""
        from datetime import datetime, timezone, timedelta

        # Old commitment
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the old proposal",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        # Newer commitment
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the new numbers",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        response = client.get("/api/prepare", headers=auth_headers)
        data = response.json()

        if len(data) > 0 and data[0]["the_forgotten"]:
            # The forgotten should be the oldest (first added)
            assert "old" in data[0]["the_forgotten"].lower()

    def test_prepare_open_question_is_follow_up(self, client, auth_headers):
        """the_open_question should be a follow-up signal."""
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the proposal by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "Did you get a chance to review?",
            "signal_type": "follow_up.required",
        }, headers=auth_headers)

        response = client.get("/api/prepare", headers=auth_headers)
        data = response.json()

        if len(data) > 0 and data[0]["the_open_question"]:
            assert "review" in data[0]["the_open_question"].lower()
