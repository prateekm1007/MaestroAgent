"""
Masterpiece endpoints for Commitments + What Changed.

Commitments: one primary (at-risk), rest secondary.
What Changed: 2 material shifts, not a feed.
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-cm"
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
    response = client.post("/api/auth/login", json={"password": "any"})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestCommitmentsMasterpiece:
    """Commitments: one primary (at-risk), rest secondary."""

    def test_empty_returns_no_primary(self, client, auth_headers):
        """No commitments → no primary."""
        response = client.get("/api/commitments/the-one", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["primary"] is None
        assert data["secondary"] == []

    def test_returns_one_primary_not_a_list(self, client, auth_headers):
        """Returns ONE primary commitment, not a list."""
        client.post("/api/signals", json={
            "entity": "Alex", "text": "I will send the proposal by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        response = client.get("/api/commitments/the-one", headers=auth_headers)
        data = response.json()
        assert data["primary"] is not None
        assert isinstance(data["primary"], dict)  # ONE, not a list
        assert "entity" in data["primary"]

    def test_at_risk_commitment_becomes_primary(self, client, auth_headers, temp_db):
        """The stalest commitment should be the primary."""
        from datetime import datetime, timezone, timedelta

        # Old commitment (10 days ago — stale)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        # Insert directly into DB with old timestamp
        import sqlite3, json, uuid
        conn = sqlite3.connect(os.environ["MAESTRO_PERSONAL_DB"])
        conn.execute(
            """INSERT INTO signals (signal_id, entity, text, signal_type, timestamp, metadata, source_acl, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), "Alex", "I will send the old proposal", "commitment_made",
             old_ts, "{}", "public", old_ts),
        )
        conn.commit()
        conn.close()

        # Fresh commitment (just now)
        client.post("/api/signals", json={
            "entity": "Sam", "text": "I will send the new report",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        response = client.get("/api/commitments/the-one", headers=auth_headers)
        data = response.json()
        assert data["primary"] is not None
        # The primary should be the at-risk one (Alex, 10 days stale)
        assert data["primary"]["is_at_risk"] == True or data["primary"]["days_stale"] > 0

    def test_includes_why_primary(self, client, auth_headers):
        """The response explains WHY this is the primary commitment."""
        client.post("/api/signals", json={
            "entity": "Alex", "text": "I will send the proposal by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        response = client.get("/api/commitments/the-one", headers=auth_headers)
        data = response.json()
        assert data["why_primary"]  # non-empty explanation

    def test_secondary_contains_rest(self, client, auth_headers):
        """Secondary list contains the non-primary commitments."""
        for entity in ["Alex", "Sam", "Pat"]:
            client.post("/api/signals", json={
                "entity": entity, "text": f"I will send to {entity}",
                "signal_type": "commitment_made",
            }, headers=auth_headers)

        response = client.get("/api/commitments/the-one", headers=auth_headers)
        data = response.json()
        assert data["primary"] is not None
        # Secondary should have the rest (at least 1)
        assert len(data["secondary"]) >= 1


class TestWhatChangedMasterpiece:
    """What Changed: 2 material shifts, not a feed."""

    def test_empty_returns_silence(self, client, auth_headers):
        """No deltas → silence message."""
        response = client.get("/api/what-changed/the-shifts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["the_shifts"]) == 0
        assert "Nothing material" in data["silence_message"]

    def test_returns_at_most_2_shifts(self, client, auth_headers):
        """Returns at most 2 shifts — not a feed."""
        # Add 5 meaningful signals
        for i in range(5):
            client.post("/api/signals", json={
                "entity": f"Entity{i}",
                "text": f"Meeting moved to Tuesday {i}",
                "signal_type": "meeting.moved",
            }, headers=auth_headers)

        response = client.get("/api/what-changed/the-shifts", headers=auth_headers)
        data = response.json()
        assert len(data["the_shifts"]) <= 2

    def test_returns_meaningful_not_noise(self, client, auth_headers):
        """Only meaningful shifts, not noise."""
        # Meaningful signal
        client.post("/api/signals", json={
            "entity": "Alex", "text": "Meeting moved to Tuesday",
            "signal_type": "meeting.moved",
        }, headers=auth_headers)

        # Noise signal (reported_statement — not meaningful)
        client.post("/api/signals", json={
            "entity": "Sam", "text": "Just checking in",
            "signal_type": "reported_statement",
        }, headers=auth_headers)

        response = client.get("/api/what-changed/the-shifts", headers=auth_headers)
        data = response.json()
        # All shifts must be meaningful
        for shift in data["the_shifts"]:
            assert shift["is_meaningful"] == True
