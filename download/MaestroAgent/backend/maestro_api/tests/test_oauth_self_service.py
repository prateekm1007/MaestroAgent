"""Tests for Enterprise OAuth Self-Service — encrypted credential storage."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from maestro_api.main import create_app
from maestro_api.oem_state import oem_state, import_state
from maestro_oem.oauth_config_store import OAuthConfigStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    app_dir = str(Path(__file__).resolve().parents[3])
    monkeypatch.setattr("maestro_api.oem_state._IMPORT_DB_PATH", str(tmp_path / "test_import.db"))
    monkeypatch.setenv("MAESTRO_APP_DIR", app_dir)
    monkeypatch.setenv("MAESTRO_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("MAESTRO_LEARNING_DB", str(tmp_path / "learning.db"))
    monkeypatch.setenv("MAESTRO_ADMIN_PASSWORD", "test")
    monkeypatch.setenv("MAESTRO_RATE_LIMIT_RPM", "10000")
    monkeypatch.setenv("MAESTRO_DEMO_SEED", "true")
    monkeypatch.setenv("MAESTRO_LOCAL_DEV", "true")  # Fix: auth defaults ON without this → 403 on admin endpoints
    oem_state._initialized = False
    oem_state.engine = None
    oem_state.signals = []
    oem_state._demo_seeded = False
    oem_state._contradiction_log = None
    import_state._initialized = False
    app = create_app(db_path=str(tmp_path / "maestro.db"))
    with TestClient(app) as c:
        yield c
    oem_state._initialized = False
    oem_state.engine = None
    oem_state.signals = []


@pytest.fixture
def config_store(tmp_path):
    """A fresh OAuthConfigStore for each test."""
    db_path = str(tmp_path / "test_oauth_config.db")
    return OAuthConfigStore(db_path)


class TestOAuthConfigStore:
    def test_save_and_retrieve_provider(self, config_store):
        """Save a provider config and retrieve it with the secret decrypted."""
        config_store.save_provider(
            provider="github",
            client_id="Iv1.abc123",
            client_secret="super-secret-value",
            scopes=["repo", "read:org"],
        )
        config = config_store.get_provider("github")
        assert config is not None
        assert config["client_id"] == "Iv1.abc123"
        assert config["client_secret"] == "super-secret-value"
        assert "repo" in config["scopes"]

    def test_secret_is_encrypted_at_rest(self, config_store, tmp_path):
        """The stored secret must NOT be readable as plain text in the DB file."""
        config_store.save_provider(
            provider="github",
            client_id="Iv1.abc123",
            client_secret="my-super-secret-value-12345",
        )
        # Read the raw DB file and verify the secret is NOT in plain text
        import sqlite3
        conn = sqlite3.connect(config_store.db_path)
        cur = conn.cursor()
        cur.execute("SELECT client_secret_encrypted FROM oauth_provider_config WHERE provider = 'github'")
        row = cur.fetchone()
        conn.close()

        stored_value = row[0]
        assert "my-super-secret-value-12345" not in stored_value, (
            "Client secret stored in PLAIN TEXT — encryption failed!"
        )

    def test_list_providers_does_not_include_secrets(self, config_store):
        """list_providers must not return the decrypted secret."""
        config_store.save_provider(
            provider="github",
            client_id="Iv1.abc123",
            client_secret="secret123",
        )
        providers = config_store.list_providers()
        assert len(providers) == 1
        assert providers[0]["client_id"] == "Iv1.abc123"
        assert "client_secret" not in providers[0], "Secret leaked in list_providers!"
        assert providers[0]["has_secret"] is True

    def test_delete_provider(self, config_store):
        """Deleting a provider disables it."""
        config_store.save_provider("github", "id", "secret")
        assert config_store.has_provider("github")
        assert config_store.delete_provider("github")
        assert not config_store.has_provider("github")

    def test_update_existing_provider(self, config_store):
        """Saving an existing provider updates it, not creates a duplicate."""
        config_store.save_provider("github", "old-id", "old-secret")
        config_store.save_provider("github", "new-id", "new-secret")
        providers = config_store.list_providers()
        assert len(providers) == 1
        config = config_store.get_provider("github")
        assert config["client_id"] == "new-id"
        assert config["client_secret"] == "new-secret"


class TestOAuthAdminAPI:
    def test_list_providers_endpoint(self, client):
        """GET /api/oauth/admin/providers returns all supported providers."""
        r = client.get("/api/oauth/admin/providers")
        assert r.status_code == 200
        data = r.json()
        provider_names = {p["provider"] for p in data["providers"]}
        assert "github" in provider_names
        assert "jira" in provider_names
        assert "slack" in provider_names
        assert "customer" in provider_names

    def test_list_providers_does_not_leak_secrets(self, client):
        """The list endpoint must not return client_secret."""
        r = client.get("/api/oauth/admin/providers")
        for p in r.json()["providers"]:
            assert "client_secret" not in p, "Secret leaked in list endpoint!"

    def test_save_provider_endpoint(self, client):
        """POST /api/oauth/admin/providers/{provider} saves encrypted config."""
        r = client.post("/api/oauth/admin/providers/github", json={
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["secret_stored"] == "encrypted"

    def test_save_provider_validates_required_fields(self, client):
        """Missing client_id or client_secret returns 400."""
        r = client.post("/api/oauth/admin/providers/github", json={
            "client_id": "",
            "client_secret": "",
        })
        assert r.status_code == 400

    def test_save_provider_rejects_unsupported_provider(self, client):
        """Unsupported providers return 400."""
        r = client.post("/api/oauth/admin/providers/tiktok", json={
            "client_id": "x",
            "client_secret": "y",
        })
        assert r.status_code == 400

    def test_delete_provider_endpoint(self, client):
        """DELETE /api/oauth/admin/providers/{provider} disables config."""
        # Save first
        client.post("/api/oauth/admin/providers/slack", json={
            "client_id": "slack-id",
            "client_secret": "slack-secret",
        })
        # Delete
        r = client.delete("/api/oauth/admin/providers/slack")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_delete_nonexistent_provider_returns_404(self, client):
        """Deleting a provider that's not configured returns 404."""
        r = client.delete("/api/oauth/admin/providers/confluence")
        assert r.status_code == 404

    def test_saved_config_is_used_by_oauth_start(self, client):
        """After saving via admin API, /api/oauth/{provider}/start uses the saved config."""
        # Save config via admin API
        client.post("/api/oauth/admin/providers/github", json={
            "client_id": "my-test-client-id",
            "client_secret": "my-test-secret",
        })
        # Verify /api/oauth/github/start uses the saved client_id
        r = client.get("/api/oauth/github/start")
        assert r.status_code == 200
        data = r.json()
        assert "my-test-client-id" in data.get("auth_url", ""), (
            f"OAuth start did not use the admin-saved client_id: {data}"
        )

    def test_env_fallback_still_works(self, client, monkeypatch):
        """If no DB config exists, env vars are used (backward compatibility)."""
        monkeypatch.setenv("MAESTRO_OAUTH_JIRA_CLIENT_ID", "env-jira-id")
        monkeypatch.setenv("MAESTRO_OAUTH_JIRA_CLIENT_SECRET", "env-jira-secret")
        # Ensure no DB config exists
        # (fresh client fixture ensures this)
        r = client.get("/api/oauth/jira/start")
        assert r.status_code == 200
        data = r.json()
        assert "env-jira-id" in data.get("auth_url", ""), (
            f"OAuth start did not fall back to env var: {data}"
        )

    def test_db_config_takes_priority_over_env(self, client, monkeypatch):
        """DB config takes priority over env vars."""
        monkeypatch.setenv("MAESTRO_OAUTH_GITHUB_CLIENT_ID", "env-github-id")
        monkeypatch.setenv("MAESTRO_OAUTH_GITHUB_CLIENT_SECRET", "env-github-secret")
        # Save a DB config with a different client_id
        client.post("/api/oauth/admin/providers/github", json={
            "client_id": "db-github-id",
            "client_secret": "db-github-secret",
        })
        # Verify the DB config is used, not the env var
        r = client.get("/api/oauth/github/start")
        assert r.status_code == 200
        data = r.json()
        assert "db-github-id" in data.get("auth_url", ""), (
            f"DB config should take priority over env var: {data}"
        )
        assert "env-github-id" not in data.get("auth_url", ""), (
            f"Env var should NOT be used when DB config exists: {data}"
        )


class TestOAuthAdminUI:
    def test_settings_page_has_oauth_config_panel(self, client):
        """The Settings page HTML must include the OAuth configuration panel."""
        import os
        app_dir = os.environ.get("MAESTRO_APP_DIR", ".")
        html = Path(app_dir).joinpath("app.html").read_text()
        assert "oauth-admin-list" in html, "OAuth admin list panel not found in app.html"
        assert "oauth-config-form" in html, "OAuth config form not found in app.html"

    def test_settings_page_has_encryption_notice(self, client):
        """The Settings page must mention encryption."""
        import os
        app_dir = os.environ.get("MAESTRO_APP_DIR", ".")
        html = Path(app_dir).joinpath("app.html").read_text()
        assert "encrypted" in html.lower(), "Encryption notice not found in app.html"
        assert "AES-256" in html, "AES-256 mention not found in app.html"
