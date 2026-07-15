"""
Tests for the Slack OAuth2 connector (Phase C).

Same pattern as test_gmail_connector.py:
  1. SlackOAuthClient: authorization URL generation, token exchange (mocked)
  2. SlackAPIClient: DM listing, history, send (mocked HTTP)
  3. SlackIngester: commitment extraction from Slack messages
  4. ConnectorStore integration: _fetch_messages uses real Slack when configured
  5. resolve_draft: sends via real Slack API when configured
  6. OAuth callback endpoint: exchanges code for tokens
  7. Fallback: returns mock data when OAuth NOT configured (demo mode)
"""

import sys
import os
import tempfile
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def slack_env():
    """Set fake Slack OAuth credentials in env."""
    old = os.environ.copy()
    os.environ["MAESTRO_SLACK_CLIENT_ID"] = "test-slack-client-id"
    os.environ["MAESTRO_SLACK_CLIENT_SECRET"] = "test-slack-client-secret"
    os.environ["MAESTRO_SLACK_REDIRECT_URI"] = "http://localhost:8766/api/connectors/slack/oauth/callback"
    yield
    os.environ.clear()
    os.environ.update(old)


@pytest.fixture
def no_slack_env():
    """Ensure Slack OAuth is NOT configured (demo mode)."""
    old = os.environ.copy()
    for k in ("MAESTRO_SLACK_CLIENT_ID", "MAESTRO_SLACK_CLIENT_SECRET", "MAESTRO_SLACK_REDIRECT_URI"):
        os.environ.pop(k, None)
    yield
    os.environ.clear()
    os.environ.update(old)


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-slack"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)
    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)
    try:
        from maestro_personal_shell.semantic_retrieval import init_fts_index, rebuild_fts_index
        init_fts_index(db_path)
        rebuild_fts_index(db_path)
    except Exception:
        pass
    yield api_module
    os.unlink(db_path)
    os.environ.pop("MAESTRO_PERSONAL_DB", None)
    os.environ.pop("MAESTRO_PERSONAL_TOKEN", None)


@pytest.fixture
def client(isolated_api):
    return TestClient(isolated_api.app)


@pytest.fixture
def auth_headers(client):
    response = client.post(
        "/api/auth/login",
        json={"password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test")},
    )
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. SlackOAuthClient
# ---------------------------------------------------------------------------

class TestSlackOAuthClient:
    """OAuth2 authorization URL + token exchange."""

    def test_authorization_url_contains_required_params(self, slack_env):
        from maestro_personal_shell.slack_connector import SlackOAuthClient
        client = SlackOAuthClient()
        url = client.get_authorization_url(state="user=test@example.com")
        assert "client_id=test-slack-client-id" in url
        assert "redirect_uri=" in url
        assert "response_type=code" in url
        assert "channels%3Aread" in url or "channels:read" in url  # URL-encoded or not
        assert "im%3Aread" in url or "im:read" in url
        assert "chat%3Awrite" in url or "chat:write" in url
        assert "state=" in url

    def test_authorization_url_raises_when_not_configured(self, no_slack_env):
        from maestro_personal_shell.slack_connector import SlackOAuthClient
        client = SlackOAuthClient()
        with pytest.raises(ValueError, match="not configured"):
            client.get_authorization_url()

    @patch("urllib.request.urlopen")
    def test_exchange_code_returns_tokens(self, mock_urlopen, slack_env):
        from maestro_personal_shell.slack_connector import SlackOAuthClient
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "ok": True,
            "access_token": "xoxb-test-access",
            "token_type": "bot",
            "scope": "channels:read,im:read,chat:write",
            "bot_user_id": "U123",
            "team": {"name": "Test Team"},
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = SlackOAuthClient()
        tokens = client.exchange_code_for_tokens("test-code")
        assert tokens["access_token"] == "xoxb-test-access"
        assert tokens["bot_user_id"] == "U123"
        assert "expires_at" in tokens

    @patch("urllib.request.urlopen")
    def test_exchange_code_handles_slack_error(self, mock_urlopen, slack_env):
        """P28: edge case — Slack returns ok=false with an error."""
        from maestro_personal_shell.slack_connector import SlackOAuthClient
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "ok": False,
            "error": "invalid_code",
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = SlackOAuthClient()
        tokens = client.exchange_code_for_tokens("bad-code")
        assert "error" in tokens
        assert "invalid_code" in tokens["error"]

    def test_get_valid_access_token_returns_existing(self, slack_env):
        """Slack tokens don't expire by default — should return stored token."""
        from maestro_personal_shell.slack_connector import SlackOAuthClient
        client = SlackOAuthClient()
        stored = json.dumps({
            "access_token": "xoxb-valid",
            "bot_user_id": "U123",
        })
        token, updated = client.get_valid_access_token(stored)
        assert token == "xoxb-valid"
        assert updated == stored  # unchanged


# ---------------------------------------------------------------------------
# 2. SlackAPIClient
# ---------------------------------------------------------------------------

class TestSlackAPIClient:
    """Slack Web API calls (mocked HTTP)."""

    @patch("urllib.request.urlopen")
    def test_list_dm_channels(self, mock_urlopen):
        from maestro_personal_shell.slack_connector import SlackAPIClient
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "ok": True,
            "channels": [{"id": "D111"}, {"id": "D222"}],
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = SlackAPIClient("xoxb-token")
        ids = client.list_dm_channels()
        assert ids == ["D111", "D222"]

    @patch("urllib.request.urlopen")
    def test_get_dm_history(self, mock_urlopen):
        from maestro_personal_shell.slack_connector import SlackAPIClient
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "ok": True,
            "messages": [
                {"text": "I will send the report", "user": "U111", "ts": "1625000000.000123"},
                {"text": "Thanks", "user": "U222", "ts": "1625000100.000456"},
            ],
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = SlackAPIClient("xoxb-token")
        messages = client.get_dm_history("D111")
        assert len(messages) == 2
        assert messages[0]["text"] == "I will send the report"

    @patch("urllib.request.urlopen")
    def test_get_user_info(self, mock_urlopen):
        from maestro_personal_shell.slack_connector import SlackAPIClient
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "ok": True,
            "user": {
                "name": "maria",
                "real_name": "Maria Garcia",
                "profile": {"email": "maria@example.com"},
            },
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = SlackAPIClient("xoxb-token")
        info = client.get_user_info("U111")
        assert info["real_name"] == "Maria Garcia"
        assert info["email"] == "maria@example.com"

    @patch("urllib.request.urlopen")
    def test_send_message(self, mock_urlopen):
        from maestro_personal_shell.slack_connector import SlackAPIClient
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "ok": True,
            "channel": "D111",
            "ts": "1625000200.000789",
            "message": {"text": "test message"},
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = SlackAPIClient("xoxb-token")
        result = client.send_message("D111", "test message")
        assert result["ok"] is True
        assert result["ts"] == "1625000200.000789"


# ---------------------------------------------------------------------------
# 3. SlackIngester — commitment extraction
# ---------------------------------------------------------------------------

class TestSlackIngester:
    """Extract commitments from Slack messages."""

    def test_keyword_commitment_detection_finds_i_will(self):
        from maestro_personal_shell.slack_connector import SlackIngester
        ingester = SlackIngester("token")
        commitments = ingester._keyword_commitment_detection(
            "I will send the pricing proposal by Friday",
            "Maria",
            "2026-07-10T10:00:00Z",
        )
        assert len(commitments) >= 1
        assert any("send the pricing proposal" in c["text"] for c in commitments)
        assert all(c["signal_type"] == "commitment_made" for c in commitments)
        assert all(c["source"] == "slack:dm" for c in commitments)

    def test_keyword_commitment_detection_no_false_positives(self):
        """P28: edge case — no commitment language."""
        from maestro_personal_shell.slack_connector import SlackIngester
        ingester = SlackIngester("token")
        commitments = ingester._keyword_commitment_detection(
            "Thanks for the update!",
            "Maria",
            "2026-07-10T10:00:00Z",
        )
        assert len(commitments) == 0

    def test_strip_mentions_replaces_user_ids(self):
        from maestro_personal_shell.slack_connector import SlackIngester
        ingester = SlackIngester("token")
        # Mock the user info lookup
        with patch.object(ingester, "_get_user_name", return_value="Maria"):
            cleaned = ingester._strip_mentions("Hey <@U111>, I will send the report")
        assert "@Maria" in cleaned
        assert "<@U111>" not in cleaned

    def test_parse_slack_ts(self):
        from maestro_personal_shell.slack_connector import SlackIngester
        ingester = SlackIngester("token")
        iso = ingester._parse_slack_ts("1625000000.000123")
        assert "2021" in iso  # 1625000000 = June 2021
        # Empty ts → now (not crash)
        iso2 = ingester._parse_slack_ts("")
        assert "T" in iso2

    @patch("urllib.request.urlopen")
    def test_ingest_recent_extracts_commitments(self, mock_urlopen, slack_env):
        """Integration: ingest_recent pulls DMs and extracts commitments."""
        from maestro_personal_shell.slack_connector import SlackIngester

        # Mock the two API calls: conversations.list + conversations.history + users.info
        responses = [
            # conversations.list (DMs)
            json.dumps({"ok": True, "channels": [{"id": "D111"}]}).encode(),
            # conversations.history for D111
            json.dumps({"ok": True, "messages": [
                {"text": "I will send the report by Friday", "user": "U111", "ts": "1625000000.000123"},
            ]}).encode(),
            # users.info for U111
            json.dumps({"ok": True, "user": {"name": "maria", "real_name": "Maria Garcia"}}).encode(),
        ]
        call_count = [0]

        def mock_read():
            idx = min(call_count[0], len(responses) - 1)
            return responses[idx]

        mock_resp = MagicMock()
        mock_resp.read = mock_read
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        # Patch the call counter increment
        original_read = mock_resp.read
        def counting_read():
            r = original_read()
            call_count[0] += 1
            return r
        mock_resp.read = counting_read

        ingester = SlackIngester("xoxb-token")
        result = ingester.ingest_recent(days_back=30)
        assert result["channels_scanned"] == 1
        assert result["commitments_found"] >= 1
        assert len(result["signals"]) >= 1


# ---------------------------------------------------------------------------
# 4. ConnectorStore integration — _fetch_messages uses real Slack
# ---------------------------------------------------------------------------

class TestSlackIngestionIntegration:
    """Verify _fetch_messages calls real Slack API when configured."""

    def test_falls_back_to_mock_when_oauth_not_configured(self, no_slack_env, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        store.connect("user@test.com", "slack", json.dumps({"access_token": "x"}))
        messages = store._fetch_messages("user@test.com", "slack")
        assert len(messages) > 0
        assert any("slack" in m.get("source", "") for m in messages)

    def test_calls_real_slack_when_configured(self, slack_env, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        token_json = json.dumps({"access_token": "xoxb-valid"})
        store.connect("user@test.com", "slack", token_json)

        mock_signals = [
            {"entity": "Maria", "text": "I will send the report", "signal_type": "commitment_made", "timestamp": "2026-07-10T10:00:00Z", "source": "slack:dm"},
        ]
        with patch(
            "maestro_personal_shell.slack_connector.fetch_real_slack_messages",
            return_value=(mock_signals, token_json),
        ):
            messages = store._fetch_messages("user@test.com", "slack")
        assert messages == mock_signals
        assert messages[0]["entity"] == "Maria"


# ---------------------------------------------------------------------------
# 5. resolve_draft — sends via real Slack
# ---------------------------------------------------------------------------

class TestSlackSendIntegration:
    """Verify resolve_draft sends via real Slack API when configured."""

    def test_send_falls_back_to_simulated_when_not_configured(self, no_slack_env, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        draft = store.create_draft("u@t.com", "slack", "D111", "", "Body", "commitment")
        result = store.resolve_draft(draft["draft_id"], "approve", user_email="u@t.com")
        assert result["status"] == "approved"
        assert result["sent_message_id"].startswith("msg-")  # simulated

    def test_send_calls_real_slack_when_configured(self, slack_env, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        token_json = json.dumps({"access_token": "xoxb-valid"})
        store.connect("u@t.com", "slack", token_json)
        draft = store.create_draft("u@t.com", "slack", "D111", "", "Body", "commitment")

        with patch(
            "maestro_personal_shell.slack_connector.send_real_slack_message",
            return_value=({"ok": True, "ts": "1625000200.000789", "channel": "D111"}, token_json),
        ):
            result = store.resolve_draft(draft["draft_id"], "approve", user_email="u@t.com")
        assert result["status"] == "approved"
        assert result["sent_message_id"] == "1625000200.000789"

    def test_send_failure_marks_send_failed(self, slack_env, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        token_json = json.dumps({"access_token": "xoxb-valid"})
        store.connect("u@t.com", "slack", token_json)
        draft = store.create_draft("u@t.com", "slack", "D111", "", "Body", "commitment")

        with patch(
            "maestro_personal_shell.slack_connector.send_real_slack_message",
            return_value=({"error": "Slack API error: not_in_channel"}, token_json),
        ):
            result = store.resolve_draft(draft["draft_id"], "approve", user_email="u@t.com")
        assert result["status"] == "send_failed"
        assert "not_in_channel" in result["send_error"]


# ---------------------------------------------------------------------------
# 6. OAuth callback endpoint
# ---------------------------------------------------------------------------

class TestSlackOAuthCallback:
    """OAuth callback endpoint + connect endpoint with OAuth flow."""

    def test_connect_returns_auth_url_when_oauth_configured(self, client, auth_headers, slack_env):
        response = client.post(
            "/api/connectors/slack/connect",
            headers=auth_headers,
            json={"provider": "slack", "oauth_token": ""},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["oauth_required"] is True
        assert "slack.com" in data["authorization_url"]

    def test_connect_stores_token_directly_when_oauth_token_provided(self, client, auth_headers, no_slack_env):
        response = client.post(
            "/api/connectors/slack/connect",
            headers=auth_headers,
            json={"provider": "slack", "oauth_token": "fake-demo-token"},
        )
        assert response.status_code == 200
        assert response.json()["connected"] is True

    def test_oauth_callback_exchanges_code(self, client, slack_env):
        with patch(
            "maestro_personal_shell.slack_connector.SlackOAuthClient.exchange_code_for_tokens",
            return_value={
                "access_token": "xoxb-access",
                "token_type": "bot",
                "bot_user_id": "U123",
                "expires_at": "2026-12-31T23:59:59+00:00",
            },
        ):
            response = client.get(
                "/api/connectors/slack/oauth/callback?code=test-code&state=user=test@example.com",
            )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["provider"] == "slack"
        assert data["user_email"] == "test@example.com"

    def test_oauth_callback_returns_error_on_oauth_error(self, client, slack_env):
        response = client.get(
            "/api/connectors/slack/oauth/callback?error=access_denied",
        )
        assert response.status_code == 400
        assert "access_denied" in response.json()["detail"]

    def test_oauth_callback_returns_400_when_not_configured(self, client, no_slack_env):
        response = client.get(
            "/api/connectors/slack/oauth/callback?code=test-code&state=user=test@example.com",
        )
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 7. is_slack_configured helper
# ---------------------------------------------------------------------------

class TestSlackConfiguration:
    """Configuration detection."""

    def test_is_slack_configured_true_when_env_set(self, slack_env):
        from maestro_personal_shell.slack_connector import is_slack_configured
        assert is_slack_configured() is True

    def test_is_slack_configured_false_when_env_missing(self, no_slack_env):
        from maestro_personal_shell.slack_connector import is_slack_configured
        assert is_slack_configured() is False
