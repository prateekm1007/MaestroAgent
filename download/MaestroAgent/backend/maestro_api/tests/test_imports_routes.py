"""Unit tests for the API routes — imports, oauth, snapshot."""

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from maestro_api.main import create_app
from maestro_api.oem_state import oem_state, import_state, _IMPORT_DB_PATH


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with isolated import_state DB."""
    test_db = str(tmp_path / "test_import.db")
    monkeypatch.setattr("maestro_api.oem_state._IMPORT_DB_PATH", test_db)
    # Reset singletons
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


def test_oauth_status_endpoint(client):
    resp = client.get("/api/oauth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    assert len(data["providers"]) == 5
    for p in data["providers"]:
        assert p["provider"] in ("github", "jira", "slack", "confluence", "gmail")
        assert "configured" in p
        assert "connected" in p


def test_oauth_start_unknown_provider(client):
    resp = client.get("/api/oauth/unknown/start")
    assert resp.status_code == 404


def test_oauth_start_unconfigured_provider(client):
    """Without env vars, /start should return 400."""
    # Make sure no env vars are set
    for p in ("github", "jira", "slack", "confluence", "gmail"):
        for var in (f"MAESTRO_OAUTH_{p.upper()}_CLIENT_ID",
                    f"MAESTRO_OAUTH_{p.upper()}_CLIENT_SECRET"):
            os.environ.pop(var, None)
    import_state.oauth._configs.clear()
    resp = client.get("/api/oauth/github/start")
    assert resp.status_code == 400


def test_oauth_callback_missing_params(client):
    resp = client.get("/api/oauth/callback")
    assert resp.status_code == 400


def test_oauth_callback_with_error(client):
    resp = client.get("/api/oauth/callback?error=access_denied&provider=github")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["error"] == "access_denied"


def test_list_imports_empty(client):
    resp = client.get("/api/imports")
    assert resp.status_code == 200
    data = resp.json()
    assert "jobs" in data
    assert isinstance(data["jobs"], list)


def test_start_import_not_connected(client):
    resp = client.post("/api/imports/start", json={
        "providers": ["github"], "since": "5y",
    })
    assert resp.status_code == 400
    assert "not connected" in resp.json()["detail"].lower()


def test_start_import_unknown_provider(client):
    # Pretend "unknown" is connected so we get to the unknown-provider check
    import_state.store.set_connection("unknown", connected=True)
    resp = client.post("/api/imports/start", json={
        "providers": ["unknown"], "since": "5y",
    })
    assert resp.status_code == 400


def test_start_import_invalid_since(client):
    import_state.store.set_connection("github", connected=True)
    import_state.store.save_credentials(provider="github", access_token="t", scopes=[])
    resp = client.post("/api/imports/start", json={
        "providers": ["github"], "since": "garbage",
    })
    assert resp.status_code == 400


def test_get_import_not_found(client):
    resp = client.get("/api/imports/nonexistent-job-id")
    assert resp.status_code == 404


def test_oem_snapshot(client):
    resp = client.get("/api/oem/snapshot")
    assert resp.status_code == 200
    data = resp.json()
    assert "signals_processed" in data
    assert "patterns_detected" in data
    assert "laws_inferred" in data
