"""
OAuth Round-Trip Integration Tests — Phase 3 reliability work.

Tests the FULL connect→ingest→disconnect lifecycle for each provider,
including the OAuth callback success path (code exchange → token stored →
connected=true). The existing test_oauth_e2e.py tests each step in
isolation; these tests verify the steps work TOGETHER as a cycle.

Mock strategy:
  - OAuth token exchange is mocked (no real HTTP call to Google/Slack/GitHub)
  - The ConnectorStore's real SQLite DB is used (temp file, per-test)
  - The API's real auth + routing is used (TestClient)
  - Ingest is mocked (no real Gmail/Slack API calls — returns synthetic signals)

What the user would test with real credentials:
  See scripts/verify_oauth_roundtrip.py
"""
import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

os.environ.setdefault("MAESTRO_PERSONAL_TOKEN", "roundtrip-test")
os.environ.setdefault("MAESTRO_ENV", "dev")
os.environ.setdefault("ENV", "dev")
os.environ["MAESTRO_TEST_MODE"] = "1"
os.environ.pop("OLLAMA_HOST", None)


@pytest.fixture
def fresh_db():
    """Fresh temp DB per test — avoids cross-test state contamination."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    old_db = os.environ.get("MAESTRO_PERSONAL_DB")
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    from maestro_personal_shell.api import init_db
    init_db(db_path)
    yield db_path
    os.environ["MAESTRO_PERSONAL_DB"] = old_db or ""
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.fixture
def client(fresh_db):
    """TestClient with fresh DB."""
    from fastapi.testclient import TestClient
    from maestro_personal_shell.api import app
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    """Login + return auth headers."""
    r = client.post("/api/auth/login", json={"password": os.environ["MAESTRO_PERSONAL_TOKEN"]})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ═══════════════════════════════════════════════════════════════════════════
# FULL LIFECYCLE: connect → (mock callback) → verify connected → ingest → disconnect
# ═══════════════════════════════════════════════════════════════════════════

class TestGmailRoundTrip:
    """Full Gmail connector lifecycle: connect → callback → ingest → disconnect."""

    @pytest.fixture(autouse=True)
    def setup_gmail_creds(self):
        """Set fake Gmail OAuth credentials for the test."""
        os.environ["MAESTRO_GMAIL_CLIENT_ID"] = "test-gmail-id"
        os.environ["MAESTRO_GMAIL_CLIENT_SECRET"] = "test-gmail-secret"
        os.environ["MAESTRO_GMAIL_REDIRECT_URI"] = "http://localhost:8766/api/connectors/gmail/oauth/callback"
        yield

    def test_full_cycle_connect_callback_ingest_disconnect(self, client, auth_headers):
        """FULL LIFECYCLE: connect → callback (mocked) → verify → ingest (mocked) → disconnect."""
        # Step 1: Connect — should return OAuth authorization URL
        r = client.post("/api/connectors/gmail/connect", json={"provider": "gmail"}, headers=auth_headers)
        assert r.status_code == 200, f"Connect failed: {r.text}"
        connect_data = r.json()
        assert connect_data.get("oauth_required") is True
        assert "accounts.google.com" in connect_data.get("authorization_url", "")

        # Step 2: Simulate OAuth callback with a mock code.
        # The callback handler calls GmailOAuthClient().exchange_code_for_tokens(code).
        # We mock the exchange to return a fake token — no real Google API call.
        # The state parameter must encode the user email for the callback to work.
        with patch("maestro_personal_shell.gmail_connector.GmailOAuthClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.exchange_code_for_tokens.return_value = {
                "access_token": "mock-gmail-access-token",
                "refresh_token": "mock-gmail-refresh-token",
                "expires_in": 3600,
            }
            # The callback uses _extract_user_email(state) which looks for "user=" in state
            # The connect handler sets state=<user_email> so we use the same format
            r = client.get("/api/connectors/gmail/oauth/callback?code=mock-auth-code&state=user=default@personal.local")
            assert r.status_code in (200, 302, 307), f"Callback failed: {r.status_code} — {r.text[:300]}"

        # Step 3: Verify connector is now connected
        r = client.get("/api/connectors", headers=auth_headers)
        assert r.status_code == 200
        connectors = r.json()["connectors"]
        gmail = [c for c in connectors if c["provider"] == "gmail"][0]
        assert gmail["connected"] is True, f"Gmail should be connected after callback: {gmail}"

        # Step 4: Ingest (mocked — no real Gmail API call)
        with patch("maestro_personal_shell.connectors.ConnectorStore._fetch_messages") as mock_fetch:
            mock_fetch.return_value = [
                {"entity": "Alice Chen", "text": "I will send the proposal by Friday", "signal_type": "commitment_made"},
                {"entity": "Bob Smith", "text": "The design review is scheduled for Monday", "signal_type": "reported_statement"},
            ]
            r = client.post("/api/connectors/gmail/ingest", headers=auth_headers)
            assert r.status_code == 200, f"Ingest failed: {r.text}"
            ingest_data = r.json()
            assert ingest_data["ingested"] >= 1, f"Should have ingested signals: {ingest_data}"

        # Step 5: Disconnect
        r = client.delete("/api/connectors/gmail", headers=auth_headers)
        assert r.status_code == 200, f"Disconnect failed: {r.text}"

        # Step 6: Verify connector is now disconnected
        r = client.get("/api/connectors", headers=auth_headers)
        connectors = r.json()["connectors"]
        gmail = [c for c in connectors if c["provider"] == "gmail"][0]
        assert gmail["connected"] is False, f"Gmail should be disconnected: {gmail}"

    def test_ingest_without_connect_fails_closed(self, client, auth_headers):
        """Ingesting without connecting first should return 400, not fabricate data."""
        # Make sure gmail is disconnected
        client.delete("/api/connectors/gmail", headers=auth_headers)
        r = client.post("/api/connectors/gmail/ingest", headers=auth_headers)
        assert r.status_code == 400, f"Should fail closed: {r.status_code} — {r.text[:200]}"
        assert "not connected" in r.json().get("detail", "").lower()


class TestSlackRoundTrip:
    """Full Slack connector lifecycle."""

    @pytest.fixture(autouse=True)
    def setup_slack_creds(self):
        os.environ["MAESTRO_SLACK_CLIENT_ID"] = "test-slack-id"
        os.environ["MAESTRO_SLACK_CLIENT_SECRET"] = "test-slack-secret"
        os.environ["MAESTRO_SLACK_REDIRECT_URI"] = "http://localhost:8766/api/connectors/slack/oauth/callback"
        yield

    def test_full_cycle_connect_callback_ingest_disconnect(self, client, auth_headers):
        """FULL LIFECYCLE: connect → callback (mocked) → verify → ingest (mocked) → disconnect."""
        # Step 1: Connect — returns OAuth URL
        r = client.post("/api/connectors/slack/connect", json={"provider": "slack"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json().get("oauth_required") is True
        assert "slack.com/oauth" in r.json().get("authorization_url", "")

        # Step 2: Mock OAuth callback
        with patch("maestro_personal_shell.slack_connector.SlackOAuthClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.exchange_code_for_tokens.return_value = {
                "access_token": "xoxp-mock-slack-token",
                "bot_user_id": "U123",
            }
            r = client.get("/api/connectors/slack/oauth/callback?code=mock-slack-code&state=user=default@personal.local")
            assert r.status_code in (200, 302, 307), f"Callback failed: {r.status_code}"

        # Step 3: Verify connected
        r = client.get("/api/connectors", headers=auth_headers)
        slack = [c for c in r.json()["connectors"] if c["provider"] == "slack"][0]
        assert slack["connected"] is True

        # Step 4: Ingest (mocked)
        with patch("maestro_personal_shell.connectors.ConnectorStore._fetch_messages") as mock_fetch:
            mock_fetch.return_value = [
                {"entity": "Charlie", "text": "I will review the PR by EOD", "signal_type": "commitment_made"},
            ]
            r = client.post("/api/connectors/slack/ingest", headers=auth_headers)
            assert r.status_code == 200
            assert r.json()["ingested"] >= 1

        # Step 5: Disconnect
        r = client.delete("/api/connectors/slack", headers=auth_headers)
        assert r.status_code == 200

        # Step 6: Verify disconnected
        r = client.get("/api/connectors", headers=auth_headers)
        slack = [c for c in r.json()["connectors"] if c["provider"] == "slack"][0]
        assert slack["connected"] is False


class TestGitHubRoundTrip:
    """Full GitHub connector lifecycle."""

    @pytest.fixture(autouse=True)
    def setup_github_creds(self):
        os.environ["MAESTRO_GITHUB_CLIENT_ID"] = "test-gh-id"
        os.environ["MAESTRO_GITHUB_CLIENT_SECRET"] = "test-gh-secret"
        os.environ["MAESTRO_GITHUB_REDIRECT_URI"] = "http://localhost:8766/api/connectors/github/oauth/callback"
        yield

    def test_full_cycle_connect_callback_ingest_disconnect(self, client, auth_headers):
        """FULL LIFECYCLE: connect → callback (mocked) → verify → ingest (mocked) → disconnect."""
        # Step 1: Connect — returns OAuth URL
        r = client.post("/api/connectors/github/connect", json={"provider": "github"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json().get("oauth_required") is True
        assert "github.com/login/oauth" in r.json().get("authorization_url", "")

        # Step 2: Mock OAuth callback
        with patch("maestro_personal_shell.github_connector.GitHubOAuthClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.exchange_code_for_tokens.return_value = {
                "access_token": "gho_mock-github-token",
            }
            r = client.get("/api/connectors/github/oauth/callback?code=mock-gh-code&state=user=default@personal.local")
            assert r.status_code in (200, 302, 307), f"Callback failed: {r.status_code}"

        # Step 3: Verify connected
        r = client.get("/api/connectors", headers=auth_headers)
        github = [c for c in r.json()["connectors"] if c["provider"] == "github"][0]
        assert github["connected"] is True

        # Step 4: Ingest (mocked)
        with patch("maestro_personal_shell.connectors.ConnectorStore._fetch_messages") as mock_fetch:
            mock_fetch.return_value = [
                {"entity": "dev-team", "text": "Issue #42: Fix the login bug", "signal_type": "reported_statement"},
            ]
            r = client.post("/api/connectors/github/ingest", headers=auth_headers)
            assert r.status_code == 200
            assert r.json()["ingested"] >= 1

        # Step 5: Disconnect
        r = client.delete("/api/connectors/github", headers=auth_headers)
        assert r.status_code == 200

        # Step 6: Verify disconnected
        r = client.get("/api/connectors", headers=auth_headers)
        github = [c for c in r.json()["connectors"] if c["provider"] == "github"][0]
        assert github["connected"] is False


class TestCrossProviderIsolation:
    """Verify connecting one provider doesn't affect others."""

    def test_disconnect_gmail_doesnt_affect_slack(self, client, auth_headers):
        """Disconnecting Gmail should not disconnect Slack."""
        os.environ["MAESTRO_SLACK_CLIENT_ID"] = "test-slack-id"
        os.environ["MAESTRO_SLACK_CLIENT_SECRET"] = "test-slack-secret"
        os.environ["MAESTRO_GMAIL_CLIENT_ID"] = "test-gmail-id"
        os.environ["MAESTRO_GMAIL_CLIENT_SECRET"] = "test-gmail-secret"

        # Connect Slack
        with patch("maestro_personal_shell.slack_connector.SlackOAuthClient") as MockClient:
            MockClient.return_value.exchange_code_for_tokens.return_value = {"access_token": "xoxp-slack-token"}
            client.get("/api/connectors/slack/oauth/callback?code=slack-code&state=user=default@personal.local")

        # Connect Gmail
        with patch("maestro_personal_shell.gmail_connector.GmailOAuthClient") as MockClient:
            MockClient.return_value.exchange_code_for_tokens.return_value = {"access_token": "gmail-token"}
            client.get("/api/connectors/gmail/oauth/callback?code=gmail-code&state=user=default@personal.local")

        # Verify both connected
        r = client.get("/api/connectors", headers=auth_headers)
        connectors = {c["provider"]: c for c in r.json()["connectors"]}
        assert connectors["gmail"]["connected"] is True
        assert connectors["slack"]["connected"] is True

        # Disconnect Gmail
        client.delete("/api/connectors/gmail", headers=auth_headers)

        # Verify Gmail is disconnected but Slack is still connected
        r = client.get("/api/connectors", headers=auth_headers)
        connectors = {c["provider"]: c for c in r.json()["connectors"]}
        assert connectors["gmail"]["connected"] is False
        assert connectors["slack"]["connected"] is True, "Slack should still be connected"
