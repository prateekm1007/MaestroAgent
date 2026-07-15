"""
Task 59-7: Per-connector consent API tests.

Tests the GET /api/consent/settings and PUT /api/consent/settings endpoints
that power the granular per-connector consent toggles.
"""
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
os.environ.setdefault("MAESTRO_PERSONAL_TOKEN", "test")
os.environ.setdefault("MAESTRO_ENV", "dev")
os.environ.pop("OLLAMA_HOST", None)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from maestro_personal_shell.api import app, init_db
    # Ensure env vars are set (test-isolation fix — other tests may overwrite)
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test"
    os.environ["MAESTRO_ENV"] = "dev"
    os.environ.pop("OLLAMA_HOST", None)
    init_db()  # Ensure tables exist
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    r = client.post("/api/auth/login", json={"user_email": "default@personal.local", "password": "test"})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestConsentSettings:
    """Per-connector consent API (Task 59-7)."""

    def test_get_consent_settings_returns_defaults(self, client, auth_headers):
        """GET /api/consent/settings returns defaults for all 8 providers."""
        r = client.get("/api/consent/settings", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "consent" in data
        assert "defaults" in data
        # 8 providers
        assert len(data["defaults"]) >= 8
        # Gmail has 3 scopes
        assert "gmail" in data["defaults"]
        assert "read_emails" in data["defaults"]["gmail"]
        assert "create_drafts" in data["defaults"]["gmail"]
        assert "send_emails" in data["defaults"]["gmail"]

    def test_put_consent_setting_toggles_scope(self, client, auth_headers):
        """PUT /api/consent/settings with {provider, scope, enabled} updates the setting."""
        r = client.put(
            "/api/consent/settings",
            json={"provider": "gmail", "scope": "create_drafts", "enabled": False},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["provider"] == "gmail"
        assert r.json()["scope"] == "create_drafts"
        assert r.json()["enabled"] is False

    def test_put_consent_setting_persists(self, client, auth_headers):
        """The updated setting persists across GET calls."""
        # Set to False
        client.put(
            "/api/consent/settings",
            json={"provider": "slack", "scope": "post_messages", "enabled": True},
            headers=auth_headers,
        )
        # Verify it persisted
        r = client.get("/api/consent/settings", headers=auth_headers)
        slack = r.json()["consent"].get("slack", {})
        assert slack.get("post_messages") is True

    def test_put_rejects_unknown_provider(self, client, auth_headers):
        """PUT with an unknown provider returns 400."""
        r = client.put(
            "/api/consent/settings",
            json={"provider": "unknown_provider", "scope": "read", "enabled": True},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_put_rejects_unknown_scope(self, client, auth_headers):
        """PUT with an unknown scope for a known provider returns 400."""
        r = client.put(
            "/api/consent/settings",
            json={"provider": "gmail", "scope": "unknown_scope", "enabled": True},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_get_requires_auth(self, client):
        """GET without a token returns 401."""
        r = client.get("/api/consent/settings")
        assert r.status_code in (401, 403)

    def test_all_providers_have_read_scope(self, client, auth_headers):
        """Every provider has at least one read_* scope enabled by default."""
        r = client.get("/api/consent/settings", headers=auth_headers)
        defaults = r.json()["defaults"]
        for provider, scopes in defaults.items():
            read_scopes = [k for k in scopes if k.startswith("read_")]
            assert len(read_scopes) >= 1, f"{provider} has no read_* scope"
            # At least one read scope should be True by default
            assert any(scopes[k] for k in read_scopes), f"{provider} has no read scope enabled by default"

    def test_write_scopes_off_by_default(self, client, auth_headers):
        """Destructive write actions (send_*, post_*, create_issues) are off by default.

        Note: create_drafts is ON by default because drafts are reviewed
        before sending — they don't send anything without explicit approval.
        """
        r = client.get("/api/consent/settings", headers=auth_headers)
        defaults = r.json()["defaults"]
        DESTRUCTIVE_SCOPES = {"send_emails", "post_messages", "create_issues", "create_events"}
        for provider, scopes in defaults.items():
            for scope, enabled in scopes.items():
                if scope in DESTRUCTIVE_SCOPES:
                    assert enabled is False, f"{provider}.{scope} should be off by default"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
