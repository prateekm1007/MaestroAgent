"""
API tests for Maestro Personal HTTP layer.

Tests all 8 endpoints + auth + health check. Uses FastAPI TestClient
(no need for a running server).

Per build directions Layer 1: separate FastAPI process on port 8766,
SQLite persistence, bearer auth, 8 endpoints.
"""

import sys
import os
import pathlib
import tempfile

# Set up paths
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def temp_db():
    """Use a temp DB for each test (isolation)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Set env before importing the API
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-token-12345"

    # Import after env is set
    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)

    api_module.init_db(db_path)

    yield api_module

    # Cleanup
    os.unlink(db_path)
    del os.environ["MAESTRO_PERSONAL_DB"]
    del os.environ["MAESTRO_PERSONAL_TOKEN"]


@pytest.fixture
def client(temp_db):
    """FastAPI TestClient with auth token."""
    from fastapi.testclient import TestClient
    c = TestClient(temp_db.app)
    return c


@pytest.fixture
def auth_headers(client):
    """Get auth headers by logging in."""
    response = client.post("/api/auth/login", json={"password": "any"})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestHealthAndAuth:
    """Health check + auth tests."""

    def test_health_no_auth_required(self, client):
        """Health endpoint must work without auth."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "maestro-personal"

    def test_login_returns_token(self, client):
        """Login must return a bearer token."""
        response = client.post("/api/auth/login", json={"password": "any"})
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert len(data["token"]) > 10

    def test_protected_endpoint_without_token_returns_401(self, client):
        """Situations endpoint must reject requests without auth."""
        response = client.get("/api/situations")
        assert response.status_code == 401

    def test_protected_endpoint_with_wrong_token_returns_401(self, client):
        """Situations endpoint must reject wrong token."""
        response = client.get(
            "/api/situations",
            headers={"Authorization": "Bearer wrong-token"}
        )
        assert response.status_code == 401

    def test_protected_endpoint_with_valid_token_works(self, client, auth_headers):
        """Situations endpoint must accept valid token."""
        response = client.get("/api/situations", headers=auth_headers)
        assert response.status_code == 200


class TestSignalManagement:
    """Signal create + list tests."""

    def test_create_signal(self, client, auth_headers):
        """POST /api/signals creates a signal."""
        response = client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the proposal by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["entity"] == "Alex"
        assert "proposal" in data["text"]
        assert data["signal_id"]

    def test_list_signals_empty(self, client, auth_headers):
        """GET /api/signals returns empty list when no signals."""
        response = client.get("/api/signals", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_list_signals_after_create(self, client, auth_headers):
        """GET /api/signals returns signals after creation."""
        # Create a signal
        client.post("/api/signals", json={
            "entity": "Alex",
            "text": "I will send the proposal by Friday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        # List signals
        response = client.get("/api/signals", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["entity"] == "Alex"

    def test_signal_persists_across_shell_rebuilds(self, client, auth_headers, temp_db):
        """Signals must persist in SQLite — survive shell rebuilds."""
        # Create a signal
        client.post("/api/signals", json={
            "entity": "Sam",
            "text": "Review the PR by Tuesday",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        # Build a fresh shell (simulates restart)
        shell = temp_db.build_shell()
        signals = shell.oem_state.signals

        assert len(signals) >= 1
        assert any(s.entity == "Sam" for s in signals)


class TestSurfaces:
    """Tests for the 4 surface endpoints."""

    @pytest.fixture
    def populated_client(self, client, auth_headers):
        """Client with test signals already created."""
        signals = [
            {"entity": "Alex", "text": "I will send the proposal by Friday", "signal_type": "commitment_made"},
            {"entity": "Alex", "text": "Following up on the proposal", "signal_type": "reported_statement"},
            {"entity": "Alex", "text": "Meeting moved to Tuesday", "signal_type": "calendar_change"},
        ]
        for sig in signals:
            client.post("/api/signals", json=sig, headers=auth_headers)
        return client

    def test_get_situations(self, populated_client, auth_headers):
        """GET /api/situations returns detected situations."""
        response = populated_client.get("/api/situations", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Should detect at least 1 situation about Alex
        assert len(data) >= 1
        entities = [s["entity"] for s in data]
        assert any("alex" in e.lower() for e in entities)

    def test_get_commitments(self, populated_client, auth_headers):
        """GET /api/commitments returns active commitments."""
        response = populated_client.get("/api/commitments", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Should find the "I will send the proposal" commitment
        assert len(data) >= 1
        assert any("proposal" in c["text"].lower() for c in data)

    def test_post_ask(self, populated_client, auth_headers):
        """POST /api/ask answers a question."""
        response = populated_client.post("/api/ask", json={
            "query": "What did I promise Alex?"
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert data["query"] == "What did I promise Alex?"

    def test_get_what_changed(self, populated_client, auth_headers):
        """GET /api/what-changed returns deltas."""
        response = populated_client.get("/api/what-changed", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Should have at least some deltas
        assert isinstance(data, list)

    def test_get_prepare(self, populated_client, auth_headers):
        """GET /api/prepare returns preparation (may be empty if no situations need prep)."""
        response = populated_client.get("/api/prepare", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestNoDilutionInAPI:
    """Verify the API layer does NOT reimplement Core logic — it calls the shell."""

    def test_api_imports_shell_not_core_directly(self):
        """The API must import PersonalShell, not SituationEngine directly.

        The API layer is a thin HTTP wrapper. Intelligence lives in the
        shell (which calls Core). The API must NOT call Core directly.
        """
        import pathlib
        api_file = pathlib.Path(__file__).resolve().parents[1] / "src" / "maestro_personal_shell" / "api.py"
        source = api_file.read_text()

        # The API must import the shell
        assert "from maestro_personal_shell.shell import PersonalShell" in source, (
            "API must import PersonalShell, not call Core directly"
        )

        # The API must NOT import SituationEngine directly (that's the shell's job)
        # Allow importing the surfaces (they're part of the shell layer)
        # but NOT the Core engine directly
        assert "from maestro_cognitive_council.situation_engine import" not in source, (
            "API must NOT import SituationEngine directly — use the shell"
        )
        assert "from maestro_cognitive_council.judgment_synthesizer import" not in source, (
            "API must NOT import JudgmentSynthesizer directly — use the shell"
        )
