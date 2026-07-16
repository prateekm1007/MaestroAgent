"""
Tests for the GitHub OAuth2 connector (Phase D).

Same pattern as test_gmail_connector.py and test_slack_connector.py:
  1. GitHubOAuthClient: authorization URL generation, token exchange (mocked)
  2. GitHubAPIClient: issue listing, comment posting (mocked HTTP)
  3. GitHubIngester: action item extraction from issue bodies
  4. ConnectorStore integration: _fetch_messages uses real GitHub when configured
  5. resolve_draft: posts comment via real GitHub API when configured
  6. OAuth callback endpoint: exchanges code for tokens
  7. Recipient parsing: "owner/repo#123" format
  8. Fallback: returns mock data when OAuth NOT configured (demo mode)
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
def github_env():
    """Set fake GitHub OAuth credentials in env."""
    old = os.environ.copy()
    os.environ["MAESTRO_GITHUB_CLIENT_ID"] = "test-gh-client-id"
    os.environ["MAESTRO_GITHUB_CLIENT_SECRET"] = "test-gh-client-secret"
    os.environ["MAESTRO_GITHUB_REDIRECT_URI"] = "http://localhost:8766/api/connectors/github/oauth/callback"
    yield
    os.environ.clear()
    os.environ.update(old)


@pytest.fixture
def no_github_env():
    """Ensure GitHub OAuth is NOT configured (demo mode)."""
    old = os.environ.copy()
    for k in ("MAESTRO_GITHUB_CLIENT_ID", "MAESTRO_GITHUB_CLIENT_SECRET", "MAESTRO_GITHUB_REDIRECT_URI"):
        os.environ.pop(k, None)
    yield
    os.environ.clear()
    os.environ.update(old)


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-github"
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
# 1. GitHubOAuthClient
# ---------------------------------------------------------------------------

class TestGitHubOAuthClient:
    """OAuth2 authorization URL + token exchange."""

    def test_authorization_url_contains_required_params(self, github_env):
        from maestro_personal_shell.github_connector import GitHubOAuthClient
        client = GitHubOAuthClient()
        url = client.get_authorization_url(state="user=test@example.com")
        assert "client_id=test-gh-client-id" in url
        assert "redirect_uri=" in url
        assert "scope=repo+user" in url or "scope=repo%20user" in url
        assert "state=" in url
        assert "github.com" in url

    def test_authorization_url_raises_when_not_configured(self, no_github_env):
        from maestro_personal_shell.github_connector import GitHubOAuthClient
        client = GitHubOAuthClient()
        with pytest.raises(ValueError, match="not configured"):
            client.get_authorization_url()

    @patch("urllib.request.urlopen")
    def test_exchange_code_returns_tokens(self, mock_urlopen, github_env):
        from maestro_personal_shell.github_connector import GitHubOAuthClient
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "access_token": "gho_test-access-token",
            "token_type": "bearer",
            "scope": "repo user",
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = GitHubOAuthClient()
        tokens = client.exchange_code_for_tokens("test-code")
        assert tokens["access_token"] == "gho_test-access-token"
        assert tokens["scope"] == "repo user"
        assert "expires_at" in tokens

    @patch("urllib.request.urlopen")
    def test_exchange_code_handles_error(self, mock_urlopen, github_env):
        """P28: edge case — GitHub returns an error."""
        from maestro_personal_shell.github_connector import GitHubOAuthClient
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "error": "bad_verification_code",
            "error_description": "The code passed is incorrect or expired.",
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = GitHubOAuthClient()
        tokens = client.exchange_code_for_tokens("bad-code")
        assert "error" in tokens

    def test_get_valid_access_token_returns_existing(self, github_env):
        """GitHub tokens don't expire by default — should return stored token."""
        from maestro_personal_shell.github_connector import GitHubOAuthClient
        client = GitHubOAuthClient()
        stored = json.dumps({
            "access_token": "gho_valid",
            "token_type": "bearer",
            "scope": "repo user",
        })
        token, updated = client.get_valid_access_token(stored)
        assert token == "gho_valid"
        assert updated == stored


# ---------------------------------------------------------------------------
# 2. GitHubAPIClient
# ---------------------------------------------------------------------------

class TestGitHubAPIClient:
    """GitHub REST API calls (mocked HTTP)."""

    @patch("urllib.request.urlopen")
    def test_list_assigned_issues(self, mock_urlopen):
        from maestro_personal_shell.github_connector import GitHubAPIClient
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps([
            {
                "number": 42,
                "title": "Fix the login bug",
                "body": "I will fix this by Friday",
                "html_url": "https://github.com/owner/repo/issues/42",
                "repository_url": "https://api.github.com/repos/owner/repo",
                "created_at": "2026-07-10T10:00:00Z",
                "updated_at": "2026-07-11T15:00:00Z",
                "user": {"login": "reporter1"},
                "state": "open",
            },
        ]).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = GitHubAPIClient("gho-token")
        issues = client.list_assigned_issues()
        assert len(issues) == 1
        assert issues[0]["number"] == 42
        assert issues[0]["title"] == "Fix the login bug"
        assert issues[0]["repository"] == "owner/repo"

    @patch("urllib.request.urlopen")
    def test_list_assigned_issues_skips_prs(self, mock_urlopen):
        """P28: edge case — PRs show up in issues endpoint but should be skipped."""
        from maestro_personal_shell.github_connector import GitHubAPIClient
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps([
            {"number": 1, "title": "Real issue", "body": "", "repository_url": "https://api.github.com/repos/o/r", "html_url": "url", "user": {"login": "u"}, "state": "open"},
            {"number": 2, "title": "PR", "body": "", "repository_url": "https://api.github.com/repos/o/r", "html_url": "url", "user": {"login": "u"}, "state": "open", "pull_request": {"url": "pr-url"}},
        ]).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = GitHubAPIClient("gho-token")
        issues = client.list_assigned_issues()
        assert len(issues) == 1  # PR skipped
        assert issues[0]["title"] == "Real issue"

    @patch("urllib.request.urlopen")
    def test_post_issue_comment(self, mock_urlopen):
        from maestro_personal_shell.github_connector import GitHubAPIClient
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "id": 123456789,
            "html_url": "https://github.com/owner/repo/issues/42#issuecomment-123456789",
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = GitHubAPIClient("gho-token")
        result = client.post_issue_comment("owner", "repo", 42, "Following up on this — I committed to fix this by Friday.")
        assert result["id"] == 123456789
        assert "issuecomment" in result["html_url"]


# ---------------------------------------------------------------------------
# 3. GitHubIngester — action item extraction
# ---------------------------------------------------------------------------

class TestGitHubIngester:
    """Extract action items from GitHub issues."""

    def test_commitment_detection_finds_i_will(self):
        from maestro_personal_shell.github_connector import GitHubIngester
        ingester = GitHubIngester("token")
        issue = {
            "number": 42,
            "title": "Fix login bug",
            "body": "I will fix this by Friday",
            "repository": "owner/repo",
            "html_url": "https://github.com/owner/repo/issues/42",
            "updated_at": "2026-07-11T15:00:00Z",
        }
        signals = ingester._extract_action_items_from_issue(issue)
        assert len(signals) >= 1
        assert any("fix this by Friday" in s["text"] for s in signals)
        assert all(s["source"] == "github:issue" for s in signals)
        # Commitments get signal_type=commitment_made
        commitments = [s for s in signals if s["signal_type"] == "commitment_made"]
        assert len(commitments) >= 1

    def test_action_item_detection_finds_todo(self):
        from maestro_personal_shell.github_connector import GitHubIngester
        ingester = GitHubIngester("token")
        issue = {
            "number": 43,
            "title": "Refactor API",
            "body": "TODO: split the api module into routers",
            "repository": "owner/repo",
            "html_url": "url",
            "updated_at": "2026-07-11T15:00:00Z",
        }
        signals = ingester._extract_action_items_from_issue(issue)
        # Should find the TODO
        action_items = [s for s in signals if s["signal_type"] == "reported_statement"]
        assert len(action_items) >= 1
        assert any("split the api module" in s["text"] for s in action_items)

    def test_action_item_detection_finds_needs_to(self):
        from maestro_personal_shell.github_connector import GitHubIngester
        ingester = GitHubIngester("token")
        issue = {
            "number": 44,
            "title": "Security review",
            "body": "This needs to be reviewed by the security team",
            "repository": "owner/repo",
            "html_url": "url",
            "updated_at": "2026-07-11T15:00:00Z",
        }
        signals = ingester._extract_action_items_from_issue(issue)
        action_items = [s for s in signals if s["signal_type"] == "reported_statement"]
        assert len(action_items) >= 1
        assert any("reviewed by the security team" in s["text"] for s in action_items)

    def test_no_action_items_captures_title(self):
        """P28: edge case — no action items found, capture the title."""
        from maestro_personal_shell.github_connector import GitHubIngester
        ingester = GitHubIngester("token")
        issue = {
            "number": 45,
            "title": "Investigate performance issue",
            "body": "Just noting this for now.",
            "repository": "owner/repo",
            "html_url": "url",
            "updated_at": "2026-07-11T15:00:00Z",
        }
        signals = ingester._extract_action_items_from_issue(issue)
        assert len(signals) == 1
        assert "Investigate performance issue" in signals[0]["text"]
        assert signals[0]["signal_type"] == "reported_statement"

    def test_metadata_included_in_signals(self):
        """Signals should include repo, issue_number, url metadata."""
        from maestro_personal_shell.github_connector import GitHubIngester
        ingester = GitHubIngester("token")
        issue = {
            "number": 42,
            "title": "Fix bug",
            "body": "I will fix this",
            "repository": "owner/repo",
            "html_url": "https://github.com/owner/repo/issues/42",
            "updated_at": "2026-07-11T15:00:00Z",
        }
        signals = ingester._extract_action_items_from_issue(issue)
        assert len(signals) >= 1
        assert signals[0]["metadata"]["repo"] == "owner/repo"
        assert signals[0]["metadata"]["issue_number"] == 42
        assert signals[0]["metadata"]["url"] == "https://github.com/owner/repo/issues/42"


# ---------------------------------------------------------------------------
# 4. Recipient parsing
# ---------------------------------------------------------------------------

class TestRecipientParsing:
    """Parse 'owner/repo#123' format for sending comments."""

    def test_parse_hash_format(self):
        from maestro_personal_shell.github_connector import parse_github_recipient
        owner, repo, num = parse_github_recipient("prateekm1007/MaestroAgent#42")
        assert owner == "prateekm1007"
        assert repo == "MaestroAgent"
        assert num == 42

    def test_parse_issues_path_format(self):
        from maestro_personal_shell.github_connector import parse_github_recipient
        owner, repo, num = parse_github_recipient("prateekm1007/MaestroAgent/issues/42")
        assert owner == "prateekm1007"
        assert repo == "MaestroAgent"
        assert num == 42

    def test_parse_invalid_format_returns_zeros(self):
        """P28: edge case — invalid recipient."""
        from maestro_personal_shell.github_connector import parse_github_recipient
        owner, repo, num = parse_github_recipient("not-a-valid-recipient")
        assert owner == ""
        assert repo == ""
        assert num == 0

    def test_parse_empty_returns_zeros(self):
        from maestro_personal_shell.github_connector import parse_github_recipient
        owner, repo, num = parse_github_recipient("")
        assert (owner, repo, num) == ("", "", 0)


# ---------------------------------------------------------------------------
# 5. ConnectorStore integration — _fetch_messages uses real GitHub
# ---------------------------------------------------------------------------

class TestGitHubIngestionIntegration:
    """Verify _fetch_messages calls real GitHub API when configured."""

    def test_falls_back_to_mock_when_oauth_not_configured(self, no_github_env, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        store.connect("user@test.com", "github", json.dumps({"access_token": "x"}))
        messages = store._fetch_messages("user@test.com", "github")
        assert len(messages) > 0
        assert any("github" in m.get("source", "") for m in messages)

    def test_calls_real_github_when_configured(self, github_env, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        token_json = json.dumps({"access_token": "gho_valid"})
        store.connect("user@test.com", "github", token_json)

        mock_signals = [
            {"entity": "owner/repo", "text": "I will fix this by Friday", "signal_type": "commitment_made", "timestamp": "2026-07-11T15:00:00Z", "source": "github:issue"},
        ]
        with patch(
            "maestro_personal_shell.github_connector.fetch_real_github_messages",
            return_value=(mock_signals, token_json),
        ):
            messages = store._fetch_messages("user@test.com", "github")
        assert messages == mock_signals
        assert messages[0]["entity"] == "owner/repo"


# ---------------------------------------------------------------------------
# 6. resolve_draft — posts comment via real GitHub
# ---------------------------------------------------------------------------

class TestGitHubSendIntegration:
    """Verify resolve_draft posts comment via real GitHub API when configured."""

    def test_send_fails_closed_when_not_configured(self, no_github_env, tmp_path):
        """P0 honesty: when GitHub OAuth is not configured, resolve_draft must
        FAIL CLOSED (status=send_failed), not fabricate a simulated `msg-` ID.

        Before commit 9dbf00b: the code fabricated `msg-<uuid>` and reported
        status=approved — a P0 fabrication. Test updated to match honest behavior.
        """
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        draft = store.create_draft("u@t.com", "github", "owner/repo#42", "", "Body", "commitment")
        result = store.resolve_draft(draft["draft_id"], "approve", user_email="u@t.com")
        assert result["status"] == "send_failed", \
            f"Must fail closed when OAuth not configured, got: {result}"
        assert not result.get("sent_message_id", "").startswith("msg-"), \
            f"Fabricated simulated message ID — P0 fabrication: {result}"
        assert "send_error" in result, f"Must include send_error explaining why: {result}"

    def test_send_calls_real_github_when_configured(self, github_env, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        token_json = json.dumps({"access_token": "gho_valid"})
        store.connect("u@t.com", "github", token_json)
        draft = store.create_draft("u@t.com", "github", "owner/repo#42", "", "Body", "commitment")

        with patch(
            "maestro_personal_shell.github_connector.send_real_github_comment",
            return_value=({"id": 123456789, "html_url": "url"}, token_json),
        ):
            result = store.resolve_draft(draft["draft_id"], "approve", user_email="u@t.com")
        assert result["status"] == "approved"
        assert result["sent_message_id"] == "123456789"

    def test_send_failure_on_invalid_recipient(self, github_env, tmp_path):
        """P28: edge case — invalid recipient format."""
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        token_json = json.dumps({"access_token": "gho_valid"})
        store.connect("u@t.com", "github", token_json)
        draft = store.create_draft("u@t.com", "github", "invalid-recipient", "", "Body", "commitment")

        result = store.resolve_draft(draft["draft_id"], "approve", user_email="u@t.com")
        assert result["status"] == "send_failed"
        assert "Invalid GitHub recipient" in result["send_error"]

    def test_send_failure_marks_send_failed(self, github_env, tmp_path):
        from maestro_personal_shell.connectors import ConnectorStore
        store = ConnectorStore(db_path=str(tmp_path / "test.db"))
        token_json = json.dumps({"access_token": "gho_valid"})
        store.connect("u@t.com", "github", token_json)
        draft = store.create_draft("u@t.com", "github", "owner/repo#42", "", "Body", "commitment")

        with patch(
            "maestro_personal_shell.github_connector.send_real_github_comment",
            return_value=({"error": "GitHub API error: 404 Not Found"}, token_json),
        ):
            result = store.resolve_draft(draft["draft_id"], "approve", user_email="u@t.com")
        assert result["status"] == "send_failed"
        assert "404" in result["send_error"]


# ---------------------------------------------------------------------------
# 7. OAuth callback endpoint
# ---------------------------------------------------------------------------

class TestGitHubOAuthCallback:
    """OAuth callback endpoint + connect endpoint with OAuth flow."""

    def test_connect_returns_auth_url_when_oauth_configured(self, client, auth_headers, github_env):
        response = client.post(
            "/api/connectors/github/connect",
            headers=auth_headers,
            json={"provider": "github", "oauth_token": ""},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["oauth_required"] is True
        assert "github.com" in data["authorization_url"]

    def test_connect_stores_token_directly_when_oauth_token_provided(self, client, auth_headers, no_github_env):
        response = client.post(
            "/api/connectors/github/connect",
            headers=auth_headers,
            json={"provider": "github", "oauth_token": "fake-demo-token"},
        )
        assert response.status_code == 200
        assert response.json()["connected"] is True

    def test_oauth_callback_exchanges_code(self, client, github_env):
        with patch(
            "maestro_personal_shell.github_connector.GitHubOAuthClient.exchange_code_for_tokens",
            return_value={
                "access_token": "gho_access",
                "token_type": "bearer",
                "scope": "repo user",
                "expires_at": "2026-12-31T23:59:59+00:00",
            },
        ):
            response = client.get(
                "/api/connectors/github/oauth/callback?code=test-code&state=user=test@example.com",
            )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["provider"] == "github"
        assert data["user_email"] == "test@example.com"
        assert "comments" in data["message"].lower()

    def test_oauth_callback_returns_error_on_oauth_error(self, client, github_env):
        response = client.get(
            "/api/connectors/github/oauth/callback?error=access_denied",
        )
        assert response.status_code == 400
        assert "access_denied" in response.json()["detail"]

    def test_oauth_callback_returns_400_when_not_configured(self, client, no_github_env):
        response = client.get(
            "/api/connectors/github/oauth/callback?code=test-code&state=user=test@example.com",
        )
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 8. is_github_configured helper
# ---------------------------------------------------------------------------

class TestGitHubConfiguration:
    """Configuration detection."""

    def test_is_github_configured_true_when_env_set(self, github_env):
        from maestro_personal_shell.github_connector import is_github_configured
        assert is_github_configured() is True

    def test_is_github_configured_false_when_env_missing(self, no_github_env):
        from maestro_personal_shell.github_connector import is_github_configured
        assert is_github_configured() is False
