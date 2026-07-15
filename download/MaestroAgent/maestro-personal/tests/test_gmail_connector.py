"""
Tests for the Gmail OAuth2 connector (Phase B).

Verifies:
  1. GmailOAuthClient: authorization URL generation, token exchange (mocked), refresh
  2. GmailAPIClient: message listing, body extraction, send (mocked HTTP)
  3. GmailIngester: commitment extraction from message bodies
  4. ConnectorStore integration: _fetch_messages uses real Gmail when configured
  5. resolve_draft: sends via real Gmail API when configured
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
def gmail_env():
    """Set fake Gmail OAuth credentials in env."""
    old = os.environ.copy()
    os.environ["MAESTRO_GMAIL_CLIENT_ID"] = "test-client-id"
    os.environ["MAESTRO_GMAIL_CLIENT_SECRET"] = "test-client-secret"
    os.environ["MAESTRO_GMAIL_REDIRECT_URI"] = "http://localhost:8766/api/connectors/gmail/oauth/callback"
    yield
    os.environ.clear()
    os.environ.update(old)


@pytest.fixture
def no_gmail_env():
    """Ensure Gmail OAuth is NOT configured (demo mode)."""
    old = os.environ.copy()
    for k in ("MAESTRO_GMAIL_CLIENT_ID", "MAESTRO_GMAIL_CLIENT_SECRET", "MAESTRO_GMAIL_REDIRECT_URI"):
        os.environ.pop(k, None)
    yield
    os.environ.clear()
    os.environ.update(old)


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-gmail"
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
# 1. GmailOAuthClient
# ---------------------------------------------------------------------------

class TestGmailOAuthClient:
    """OAuth2 authorization URL + token exchange + refresh."""

    def test_authorization_url_contains_required_params(self, gmail_env):
        from maestro_personal_shell.gmail_connector import GmailOAuthClient
        client = GmailOAuthClient()
        url = client.get_authorization_url(state="user=test@example.com")
        assert "client_id=test-client-id" in url
        assert "redirect_uri=" in url
        assert "response_type=code" in url
        assert "access_type=offline" in url
        assert "prompt=consent" in url
        assert "gmail.readonly" in url
        assert "gmail.send" in url
        # state is URL-encoded (= becomes %3D, @ becomes %40)
        assert "test%40example.com" in url  # the email is in the state
        assert "state=" in url

    def test_authorization_url_raises_when_not_configured(self, no_gmail_env):
        from maestro_personal_shell.gmail_connector import GmailOAuthClient
        client = GmailOAuthClient()
        with pytest.raises(ValueError, match="not configured"):
            client.get_authorization_url()

    @patch("urllib.request.urlopen")
    def test_exchange_code_returns_tokens(self, mock_urlopen, gmail_env):
        from maestro_personal_shell.gmail_connector import GmailOAuthClient
        # Mock the HTTP response
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "access_token": "ya29.test-access",
            "refresh_token": "1//test-refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = GmailOAuthClient()
        tokens = client.exchange_code_for_tokens("test-code")
        assert tokens["access_token"] == "ya29.test-access"
        assert tokens["refresh_token"] == "1//test-refresh"
        assert "expires_at" in tokens

    @patch("urllib.request.urlopen")
    def test_refresh_access_token(self, mock_urlopen, gmail_env):
        from maestro_personal_shell.gmail_connector import GmailOAuthClient
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "access_token": "ya29.new-access",
            "expires_in": 3600,
            "token_type": "Bearer",
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = GmailOAuthClient()
        result = client.refresh_access_token("old-refresh-token")
        assert result["access_token"] == "ya29.new-access"
        assert "expires_at" in result

    def test_get_valid_access_token_returns_existing_if_not_expired(self, gmail_env):
        from maestro_personal_shell.gmail_connector import GmailOAuthClient
        client = GmailOAuthClient()
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        stored = json.dumps({
            "access_token": "ya29.valid",
            "refresh_token": "1//refresh",
            "expires_at": future,
        })
        token, updated = client.get_valid_access_token(stored)
        assert token == "ya29.valid"
        assert updated == stored  # unchanged

    def test_get_valid_access_token_refreshes_when_expired(self, gmail_env):
        from maestro_personal_shell.gmail_connector import GmailOAuthClient
        client = GmailOAuthClient()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        stored = json.dumps({
            "access_token": "ya29.expired",
            "refresh_token": "1//refresh",
            "expires_at": past,
        })
        with patch.object(client, "refresh_access_token", return_value={
            "access_token": "ya29.refreshed",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }):
            token, updated = client.get_valid_access_token(stored)
        assert token == "ya29.refreshed"
        updated_data = json.loads(updated)
        assert updated_data["access_token"] == "ya29.refreshed"
        assert updated_data["refresh_token"] == "1//refresh"  # preserved


# ---------------------------------------------------------------------------
# 2. GmailAPIClient
# ---------------------------------------------------------------------------

class TestGmailAPIClient:
    """Gmail REST API calls (mocked HTTP)."""

    @patch("urllib.request.urlopen")
    def test_list_messages(self, mock_urlopen):
        from maestro_personal_shell.gmail_connector import GmailAPIClient
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "messages": [{"id": "msg1"}, {"id": "msg2"}],
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = GmailAPIClient("ya29.token")
        ids = client.list_messages(query="newer_than:30d", max_results=10)
        assert ids == ["msg1", "msg2"]

    @patch("urllib.request.urlopen")
    def test_get_message_extracts_body(self, mock_urlopen):
        from maestro_personal_shell.gmail_connector import GmailAPIClient
        import base64
        body_text = "I will send the proposal by Friday."
        encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "id": "msg1",
            "threadId": "t1",
            "snippet": body_text[:50],
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "From", "value": "Maria Garcia <maria@example.com>"},
                    {"name": "To", "value": "me"},
                    {"name": "Subject", "value": "Proposal"},
                    {"name": "Date", "value": "Mon, 10 Jul 2026 10:00:00 +0000"},
                ],
                "body": {"data": encoded_body},
            },
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = GmailAPIClient("ya29.token")
        msg = client.get_message("msg1")
        assert msg["from"] == "Maria Garcia <maria@example.com>"
        assert msg["subject"] == "Proposal"
        assert "proposal by Friday" in msg["body_text"]

    @patch("urllib.request.urlopen")
    def test_get_message_extracts_multipart_body(self, mock_urlopen):
        from maestro_personal_shell.gmail_connector import GmailAPIClient
        import base64
        body_text = "I will send the report by Monday."
        encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "id": "msg1",
            "payload": {
                "mimeType": "multipart/alternative",
                "headers": [
                    {"name": "From", "value": "alex@example.com"},
                    {"name": "Subject", "value": "Report"},
                ],
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": encoded_body}},
                    {"mimeType": "text/html", "body": {"data": encoded_body}},
                ],
            },
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = GmailAPIClient("ya29.token")
        msg = client.get_message("msg1")
        assert "report by Monday" in msg["body_text"]


# ---------------------------------------------------------------------------
# 3. GmailIngester — commitment extraction
# ---------------------------------------------------------------------------

class TestGmailIngester:
    """Extract commitments from Gmail message bodies."""

    def test_keyword_commitment_detection_finds_i_will(self):
        from maestro_personal_shell.gmail_connector import GmailIngester
        ingester = GmailIngester("token")
        commitments = ingester._keyword_commitment_detection(
            "Hi Maria, I will send the pricing proposal by Friday. Thanks!",
            "Maria",
            "2026-07-10T10:00:00Z",
        )
        assert len(commitments) >= 1
        assert any("send the pricing proposal" in c["text"] for c in commitments)
        assert all(c["signal_type"] == "commitment_made" for c in commitments)

    def test_keyword_commitment_detection_finds_ill(self):
        from maestro_personal_shell.gmail_connector import GmailIngester
        ingester = GmailIngester("token")
        commitments = ingester._keyword_commitment_detection(
            "I'll get back to you tomorrow.",
            "Sam",
            "2026-07-10T10:00:00Z",
        )
        assert len(commitments) >= 1
        assert any("get back to you" in c["text"] for c in commitments)

    def test_keyword_commitment_detection_finds_promise(self):
        from maestro_personal_shell.gmail_connector import GmailIngester
        ingester = GmailIngester("token")
        commitments = ingester._keyword_commitment_detection(
            "I promise to deliver the report by end of week.",
            "Alex",
            "2026-07-10T10:00:00Z",
        )
        assert len(commitments) >= 1
        assert any("deliver the report" in c["text"] for c in commitments)

    def test_keyword_commitment_detection_no_false_positives(self):
        """P28: test edge case — no commitment language."""
        from maestro_personal_shell.gmail_connector import GmailIngester
        ingester = GmailIngester("token")
        commitments = ingester._keyword_commitment_detection(
            "Thanks for the update. The weather is nice today.",
            "Maria",
            "2026-07-10T10:00:00Z",
        )
        assert len(commitments) == 0

    def test_extract_name_from_header(self):
        from maestro_personal_shell.gmail_connector import GmailIngester
        ingester = GmailIngester("token")
        assert ingester._extract_name("Maria Garcia <maria@example.com>") == "Maria Garcia"
        assert ingester._extract_name("alex@example.com") == "alex"
        assert ingester._extract_name("") == ""

    def test_parse_email_date(self):
        from maestro_personal_shell.gmail_connector import GmailIngester
        ingester = GmailIngester("token")
        iso = ingester._parse_email_date("Mon, 10 Jul 2026 10:00:00 +0000")
        assert "2026-07-10" in iso
        # Empty date → now (not crash)
        iso2 = ingester._parse_email_date("")
        assert "T" in iso2  # ISO format


# ---------------------------------------------------------------------------
# 4. ConnectorStore integration — _fetch_messages uses real Gmail
# ---------------------------------------------------------------------------

class TestGmailIngestionIntegration:
    """Verify _fetch_messages calls real Gmail API when configured."""

    def test_falls_back_to_mock_when_oauth_not_configured(self, no_gmail_env, tmp_path):
        """When OAuth not configured, returns mock data (demo mode)."""
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        store.connect("user@test.com", "gmail", json.dumps({"access_token": "x"}))
        messages = store._fetch_messages("user@test.com", "gmail")
        # Should return mock data (not crash, not empty)
        assert len(messages) > 0
        assert any("gmail" in m.get("source", "") for m in messages)

    def test_calls_real_gmail_when_configured(self, gmail_env, tmp_path):
        """When OAuth IS configured, calls fetch_real_gmail_messages."""
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        # Store a fake token
        token_json = json.dumps({
            "access_token": "ya29.fake",
            "refresh_token": "1//fake",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        })
        store.connect("user@test.com", "gmail", token_json)

        # Mock the real Gmail API call
        mock_signals = [
            {"entity": "Maria", "text": "I will send the proposal", "signal_type": "commitment_made", "timestamp": "2026-07-10T10:00:00Z", "source": "gmail:inbox"},
        ]
        with patch(
            "maestro_personal_shell.gmail_connector.fetch_real_gmail_messages",
            return_value=(mock_signals, token_json),
        ):
            messages = store._fetch_messages("user@test.com", "gmail")
        assert messages == mock_signals
        assert len(messages) == 1
        assert messages[0]["entity"] == "Maria"

    def test_persists_refreshed_token(self, gmail_env, tmp_path):
        """When Gmail API refreshes the token, the new token is persisted."""
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        old_token = json.dumps({
            "access_token": "ya29.old",
            "refresh_token": "1//refresh",
            "expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        })
        store.connect("user@test.com", "gmail", old_token)

        new_token = json.dumps({
            "access_token": "ya29.new",
            "refresh_token": "1//refresh",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        })
        with patch(
            "maestro_personal_shell.gmail_connector.fetch_real_gmail_messages",
            return_value=([], new_token),
        ):
            store._fetch_messages("user@test.com", "gmail")

        # Verify the new token was persisted
        stored = store.get_stored_token("user@test.com", "gmail")
        assert json.loads(stored)["access_token"] == "ya29.new"


# ---------------------------------------------------------------------------
# 5. resolve_draft — sends via real Gmail
# ---------------------------------------------------------------------------

class TestGmailSendIntegration:
    """Verify resolve_draft sends via real Gmail API when configured."""

    def test_send_falls_back_to_simulated_when_not_configured(self, no_gmail_env, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        draft = store.create_draft("u@t.com", "gmail", "maria@x.com", "Subject", "Body", "commitment")
        result = store.resolve_draft(draft["draft_id"], "approve", user_email="u@t.com")
        assert result["status"] == "approved"
        assert result["sent_message_id"].startswith("msg-")  # simulated

    def test_send_calls_real_gmail_when_configured(self, gmail_env, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        token_json = json.dumps({
            "access_token": "ya29.valid",
            "refresh_token": "1//refresh",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        })
        store.connect("u@t.com", "gmail", token_json)
        draft = store.create_draft("u@t.com", "gmail", "maria@x.com", "Subject", "Body", "commitment")

        with patch(
            "maestro_personal_shell.gmail_connector.send_real_gmail_message",
            return_value=({"id": "gmail-msg-123"}, token_json),
        ):
            result = store.resolve_draft(draft["draft_id"], "approve", user_email="u@t.com")
        assert result["status"] == "approved"
        assert result["sent_message_id"] == "gmail-msg-123"

    def test_send_failure_marks_send_failed(self, gmail_env, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        token_json = json.dumps({
            "access_token": "ya29.valid",
            "refresh_token": "1//refresh",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        })
        store.connect("u@t.com", "gmail", token_json)
        draft = store.create_draft("u@t.com", "gmail", "maria@x.com", "Subject", "Body", "commitment")

        with patch(
            "maestro_personal_shell.gmail_connector.send_real_gmail_message",
            return_value=({"error": "Gmail API error: 403"}, token_json),
        ):
            result = store.resolve_draft(draft["draft_id"], "approve", user_email="u@t.com")
        assert result["status"] == "send_failed"
        assert "403" in result["send_error"]


# ---------------------------------------------------------------------------
# 6. OAuth callback endpoint
# ---------------------------------------------------------------------------

class TestGmailOAuthCallback:
    """OAuth callback endpoint + connect endpoint with OAuth flow."""

    def test_connect_returns_auth_url_when_oauth_configured(self, client, auth_headers, gmail_env):
        response = client.post(
            "/api/connectors/gmail/connect",
            headers=auth_headers,
            json={"provider": "gmail", "oauth_token": ""},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["oauth_required"] is True
        assert "accounts.google.com" in data["authorization_url"]

    def test_connect_stores_token_directly_when_oauth_token_provided(self, client, auth_headers, no_gmail_env):
        """Demo mode: if oauth_token provided, store it directly (no OAuth flow)."""
        response = client.post(
            "/api/connectors/gmail/connect",
            headers=auth_headers,
            json={"provider": "gmail", "oauth_token": "fake-demo-token"},
        )
        assert response.status_code == 200
        assert response.json()["connected"] is True

    def test_oauth_callback_exchanges_code(self, client, gmail_env):
        """The OAuth callback exchanges code for tokens."""
        with patch(
            "maestro_personal_shell.gmail_connector.GmailOAuthClient.exchange_code_for_tokens",
            return_value={
                "access_token": "ya29.access",
                "refresh_token": "1//refresh",
                "expires_in": 3600,
                "expires_at": "2026-12-31T23:59:59+00:00",
            },
        ):
            response = client.get(
                "/api/connectors/gmail/oauth/callback?code=test-code&state=user=test@example.com",
            )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["provider"] == "gmail"
        assert data["user_email"] == "test@example.com"

    def test_oauth_callback_returns_error_on_oauth_error(self, client, gmail_env):
        response = client.get(
            "/api/connectors/gmail/oauth/callback?error=access_denied",
        )
        assert response.status_code == 400
        assert "access_denied" in response.json()["detail"]

    def test_oauth_callback_returns_400_when_not_configured(self, client, no_gmail_env):
        response = client.get(
            "/api/connectors/gmail/oauth/callback?code=test-code&state=user=test@example.com",
        )
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 7. is_gmail_configured helper
# ---------------------------------------------------------------------------

class TestGmailConfiguration:
    """Configuration detection."""

    def test_is_gmail_configured_true_when_env_set(self, gmail_env):
        from maestro_personal_shell.gmail_connector import is_gmail_configured
        assert is_gmail_configured() is True

    def test_is_gmail_configured_false_when_env_missing(self, no_gmail_env):
        from maestro_personal_shell.gmail_connector import is_gmail_configured
        assert is_gmail_configured() is False
