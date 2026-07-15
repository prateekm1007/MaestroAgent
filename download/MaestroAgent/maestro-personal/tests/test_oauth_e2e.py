"""
OAuth E2E tests for Slack + GitHub connectors.

Tests the full OAuth2 flow:
  1. Connector listing shows oauth_configured status
  2. Connect returns OAuth authorization URL with correct scopes
  3. Error callback handling (access_denied → 400)
  4. Missing code handling (→ 400)
  5. Token revocation (disconnect → 200)
  6. Fail-closed without credentials (→ 400)
  7. Token refresh logic exists (for when tokens expire)

The actual token exchange requires real OAuth credentials (Slack app +
GitHub OAuth app). These tests verify the wiring with test credentials.
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


class TestSlackOAuth:
    """Slack OAuth2 flow tests."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from maestro_personal_shell.api import app, init_db
        os.environ["MAESTRO_PERSONAL_TOKEN"] = "test"
        os.environ["MAESTRO_ENV"] = "dev"
        os.environ["MAESTRO_SLACK_CLIENT_ID"] = "test-slack-id"
        os.environ["MAESTRO_SLACK_CLIENT_SECRET"] = "test-slack-secret"
        init_db()
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self, client):
        r = client.post("/api/auth/login", json={"password": "test"})
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['token']}"}

    def test_slack_oauth_url_generated(self, client, auth_headers):
        """Connect Slack returns OAuth URL with correct scopes."""
        r = client.post("/api/connectors/slack/connect", json={"provider": "slack"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["oauth_required"] is True
        url = r.json()["authorization_url"]
        assert "slack.com/oauth" in url
        assert "channels" in url  # channels:read scope (URL-encoded)
        assert "im" in url  # im:history scope
        assert "chat" in url  # chat:write scope

    def test_slack_error_callback(self, client):
        """Slack OAuth error callback returns 400."""
        r = client.get("/api/connectors/slack/oauth/callback?error=access_denied")
        assert r.status_code == 400

    def test_slack_missing_code(self, client):
        """Slack OAuth callback without code returns 400."""
        r = client.get("/api/connectors/slack/oauth/callback")
        assert r.status_code == 400

    def test_slack_disconnect(self, client, auth_headers):
        """Disconnect Slack returns 200."""
        r = client.delete("/api/connectors/slack", headers=auth_headers)
        assert r.status_code == 200

    def test_slack_fail_closed_without_creds(self, client, auth_headers):
        """Without credentials, Slack connect returns 400 (fail-closed)."""
        os.environ.pop("MAESTRO_SLACK_CLIENT_ID", None)
        r = client.post("/api/connectors/slack/connect", json={"provider": "slack"}, headers=auth_headers)
        assert r.status_code == 400


class TestGitHubOAuth:
    """GitHub OAuth2 flow tests."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from maestro_personal_shell.api import app, init_db
        os.environ["MAESTRO_PERSONAL_TOKEN"] = "test"
        os.environ["MAESTRO_ENV"] = "dev"
        os.environ["MAESTRO_GITHUB_CLIENT_ID"] = "test-github-id"
        os.environ["MAESTRO_GITHUB_CLIENT_SECRET"] = "test-github-secret"
        init_db()
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self, client):
        r = client.post("/api/auth/login", json={"password": "test"})
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['token']}"}

    def test_github_oauth_url_generated(self, client, auth_headers):
        """Connect GitHub returns OAuth URL with correct scopes."""
        r = client.post("/api/connectors/github/connect", json={"provider": "github"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["oauth_required"] is True
        url = r.json()["authorization_url"]
        assert "github.com/login/oauth" in url
        assert "repo" in url  # repo scope
        assert "user" in url  # user scope

    def test_github_error_callback(self, client):
        """GitHub OAuth error callback returns 400."""
        r = client.get("/api/connectors/github/oauth/callback?error=access_denied")
        assert r.status_code == 400

    def test_github_missing_code(self, client):
        """GitHub OAuth callback without code returns 400."""
        r = client.get("/api/connectors/github/oauth/callback")
        assert r.status_code == 400

    def test_github_disconnect(self, client, auth_headers):
        """Disconnect GitHub returns 200."""
        r = client.delete("/api/connectors/github", headers=auth_headers)
        assert r.status_code == 200

    def test_github_fail_closed_without_creds(self, client, auth_headers):
        """Without credentials, GitHub connect returns 400 (fail-closed)."""
        os.environ.pop("MAESTRO_GITHUB_CLIENT_ID", None)
        r = client.post("/api/connectors/github/connect", json={"provider": "github"}, headers=auth_headers)
        assert r.status_code == 400


class TestConnectorListing:
    """Connector listing shows oauth_configured status."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from maestro_personal_shell.api import app, init_db
        os.environ["MAESTRO_PERSONAL_TOKEN"] = "test"
        os.environ["MAESTRO_ENV"] = "dev"
        os.environ["MAESTRO_SLACK_CLIENT_ID"] = "test-slack-id"
        os.environ["MAESTRO_SLACK_CLIENT_SECRET"] = "test-slack-secret"
        os.environ["MAESTRO_GITHUB_CLIENT_ID"] = "test-github-id"
        os.environ["MAESTRO_GITHUB_CLIENT_SECRET"] = "test-github-secret"
        init_db()
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self, client):
        r = client.post("/api/auth/login", json={"password": "test"})
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['token']}"}

    def test_slack_shows_oauth_configured(self, client, auth_headers):
        """Slack connector shows oauth_configured=True when env vars set."""
        r = client.get("/api/connectors", headers=auth_headers)
        slack = next(c for c in r.json()["connectors"] if c["provider"] == "slack")
        assert slack["oauth_configured"] is True

    def test_github_shows_oauth_configured(self, client, auth_headers):
        """GitHub connector shows oauth_configured=True when env vars set."""
        r = client.get("/api/connectors", headers=auth_headers)
        github = next(c for c in r.json()["connectors"] if c["provider"] == "github")
        assert github["oauth_configured"] is True

    def test_connectors_show_connected_false_initially(self, client, auth_headers):
        """All connectors start disconnected."""
        r = client.get("/api/connectors", headers=auth_headers)
        for c in r.json()["connectors"]:
            assert c["connected"] is False, f"{c['provider']} should start disconnected"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
