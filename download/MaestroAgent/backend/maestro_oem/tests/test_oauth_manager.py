"""Unit tests for OAuthManager — uses httpx MockTransport."""

import json
import os
import tempfile
import time
from unittest.mock import patch

import httpx
import pytest

from maestro_oem.checkpoint_store import CheckpointStore
from maestro_oem.oauth_manager import (
    OAuthManager, OAuthError, _make_state, _verify_state,
)


@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        s = CheckpointStore(path)
        yield s
        s.close()
    finally:
        os.unlink(path)


@pytest.fixture
def oauth(store):
    return OAuthManager(store, redirect_uri_base="http://localhost:8765")


# ─── State tokens ───

def test_state_token_roundtrip():
    state = _make_state("github")
    assert _verify_state(state, "github") is True


def test_state_token_wrong_provider():
    state = _make_state("github")
    assert _verify_state(state, "jira") is False


def test_state_token_expired():
    state = _make_state("github", ttl_seconds=-100)
    assert _verify_state(state, "github") is False


def test_state_token_malformed():
    assert _verify_state("garbage", "github") is False
    assert _verify_state("", "github") is False


# ─── Authorization URL ───

def test_get_authorization_url_github(oauth):
    with patch.dict(os.environ, {
        "MAESTRO_OAUTH_GITHUB_CLIENT_ID": "Iv1.test123",
        "MAESTRO_OAUTH_GITHUB_CLIENT_SECRET": "secret456",
        "MAESTRO_OAUTH_REDIRECT_URI": "http://localhost:8765/api/oauth/callback",
    }):
        oauth._configs.clear()
        url, state = oauth.get_authorization_url("github")
        assert "github.com/login/oauth/authorize" in url
        assert "client_id=Iv1.test123" in url
        assert "redirect_uri=" in url
        assert "scope=" in url
        assert "repo" in url  # GitHub scope
        assert state.startswith("github:")


def test_get_authorization_url_unconfigured(oauth):
    oauth._configs.clear()
    with pytest.raises(ValueError, match="OAuth not configured"):
        oauth.get_authorization_url("github")


def test_get_authorization_url_per_provider(oauth):
    """Each provider gets the right auth URL."""
    for provider, expected_url in [
        ("github", "github.com/login/oauth/authorize"),
        ("jira", "auth.atlassian.com/authorize"),
        ("slack", "slack.com/oauth/v2/authorize"),
        ("confluence", "auth.atlassian.com/authorize"),
        ("gmail", "accounts.google.com/o/oauth2/v2/auth"),
    ]:
        with patch.dict(os.environ, {
            f"MAESTRO_OAUTH_{provider.upper()}_CLIENT_ID": "test_id",
            f"MAESTRO_OAUTH_{provider.upper()}_CLIENT_SECRET": "test_secret",
            "MAESTRO_OAUTH_REDIRECT_URI": "http://localhost:8765/api/oauth/callback",
        }):
            oauth._configs.clear()
            url, _ = oauth.get_authorization_url(provider)
            assert expected_url in url, f"{provider} URL should contain {expected_url}"


# ─── Code exchange ───

def test_exchange_code_github(oauth, store):
    """GitHub OAuth code exchange."""
    def handler(request):
        assert request.url.path == "/login/oauth/access_token"
        body = json.loads(request.content)
        assert body["code"] == "test_code"
        assert body["client_id"] == "test_id"
        return httpx.Response(200, json={
            "access_token": "gho_test123",
            "token_type": "bearer",
            "scope": "repo read:org",
            "expires_in": 3600,
        })

    oauth._http = httpx.Client(transport=httpx.MockTransport(handler))
    with patch.dict(os.environ, {
        "MAESTRO_OAUTH_GITHUB_CLIENT_ID": "test_id",
        "MAESTRO_OAUTH_GITHUB_CLIENT_SECRET": "test_secret",
        "MAESTRO_OAUTH_REDIRECT_URI": "http://localhost:8765/api/oauth/callback",
    }):
        oauth._configs.clear()
        state = _make_state("github")
        result = oauth.exchange_code("github", "test_code", state)
        assert result["access_token"] == "gho_test123"

        # Verify persisted
        creds = store.load_credentials("github")
        assert creds["access_token"] == "gho_test123"
        assert creds["refresh_token"] is None  # GitHub doesn't return refresh
        assert "repo" in creds["scopes"]


def test_exchange_code_invalid_state(oauth):
    """Invalid state should raise OAuthError."""
    with pytest.raises(OAuthError, match="Invalid state"):
        oauth.exchange_code("github", "code", "garbage")


def test_exchange_code_provider_error(oauth):
    """Provider returning an error should raise OAuthError."""
    def handler(request):
        return httpx.Response(200, json={"error": "bad_verification_code"})

    oauth._http = httpx.Client(transport=httpx.MockTransport(handler))
    with patch.dict(os.environ, {
        "MAESTRO_OAUTH_GITHUB_CLIENT_ID": "test_id",
        "MAESTRO_OAUTH_GITHUB_CLIENT_SECRET": "test_secret",
        "MAESTRO_OAUTH_REDIRECT_URI": "http://localhost:8765/api/oauth/callback",
    }):
        oauth._configs.clear()
        state = _make_state("github")
        with pytest.raises(OAuthError, match="bad_verification_code"):
            oauth.exchange_code("github", "code", state)


# ─── Token refresh ───

def test_refresh_token(oauth, store):
    """Refresh token exchange."""
    store.save_credentials(
        provider="jira",
        access_token="old_token",
        refresh_token="old_refresh",
        scopes=["read:jira-work"],
    )

    def handler(request):
        body = json.loads(request.content)
        assert body["grant_type"] == "refresh_token"
        assert body["refresh_token"] == "old_refresh"
        return httpx.Response(200, json={
            "access_token": "new_token",
            "refresh_token": "new_refresh",
            "expires_in": 3600,
            "scope": "read:jira-work",
        })

    oauth._http = httpx.Client(transport=httpx.MockTransport(handler))
    with patch.dict(os.environ, {
        "MAESTRO_OAUTH_JIRA_CLIENT_ID": "test_id",
        "MAESTRO_OAUTH_JIRA_CLIENT_SECRET": "test_secret",
        "MAESTRO_OAUTH_REDIRECT_URI": "http://localhost:8765/api/oauth/callback",
    }):
        oauth._configs.clear()
        new_token = oauth.refresh_token("jira")
        assert new_token == "new_token"

        creds = store.load_credentials("jira")
        assert creds["access_token"] == "new_token"
        assert creds["refresh_token"] == "new_refresh"


def test_refresh_token_no_refresh(oauth, store):
    """If no refresh token, refresh should fail."""
    store.save_credentials(provider="github", access_token="token", refresh_token=None)
    with pytest.raises(OAuthError, match="No refresh token"):
        oauth.refresh_token("github")


def test_get_valid_access_token_no_refresh_needed(oauth, store):
    """If token is not expired, return it directly."""
    future_expiry = str(int(time.time()) + 3600)
    store.save_credentials(
        provider="github", access_token="valid_token",
        expires_at=future_expiry, scopes=["repo"],
    )
    assert oauth.get_valid_access_token("github") == "valid_token"


def test_get_valid_access_token_refreshes_if_expired(oauth, store):
    """If token is expired and refresh token exists, refresh."""
    past_expiry = str(int(time.time()) - 100)
    store.save_credentials(
        provider="jira", access_token="expired_token",
        refresh_token="old_refresh", expires_at=past_expiry,
        scopes=["read:jira-work"],
    )

    def handler(request):
        return httpx.Response(200, json={
            "access_token": "refreshed_token",
            "expires_in": 3600,
        })

    oauth._http = httpx.Client(transport=httpx.MockTransport(handler))
    with patch.dict(os.environ, {
        "MAESTRO_OAUTH_JIRA_CLIENT_ID": "test_id",
        "MAESTRO_OAUTH_JIRA_CLIENT_SECRET": "test_secret",
        "MAESTRO_OAUTH_REDIRECT_URI": "http://localhost:8765/api/oauth/callback",
    }):
        oauth._configs.clear()
        token = oauth.get_valid_access_token("jira")
        assert token == "refreshed_token"


# ─── Disconnect ───

def test_disconnect(oauth, store):
    store.save_credentials(
        provider="github", access_token="token", scopes=["repo"],
    )
    store.set_connection("github", connected=True)
    assert store.load_credentials("github") is not None
    assert store.get_connection("github")["connected"] is True

    # Mock revocation endpoint
    def handler(request):
        return httpx.Response(200, json={})
    oauth._http = httpx.Client(transport=httpx.MockTransport(handler))

    with patch.dict(os.environ, {
        "MAESTRO_OAUTH_GITHUB_CLIENT_ID": "test_id",
        "MAESTRO_OAUTH_GITHUB_CLIENT_SECRET": "test_secret",
        "MAESTRO_OAUTH_REDIRECT_URI": "http://localhost:8765/api/oauth/callback",
    }):
        oauth._configs.clear()
        oauth.disconnect("github")

        assert store.load_credentials("github") is None
        assert store.get_connection("github")["connected"] is False


# ─── Status ───

def test_status(oauth, store):
    store.save_credentials(provider="github", access_token="token", scopes=["repo"])
    store.set_connection("github", connected=True)

    status = oauth.status()
    # RC16 fix: SUPPORTED_IMPORT_PROVIDERS now has 6 entries (github, jira,
    # slack, confluence, gmail, customer). Was 5 before 'customer' was added.
    assert len(status) == 6
    github_status = next(s for s in status if s["provider"] == "github")
    assert github_status["connected"] is True
    assert github_status["has_credentials"] is True
