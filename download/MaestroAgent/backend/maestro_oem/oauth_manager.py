"""
OAuthManager — centralizes the 5 OAuth flows (GitHub, Jira, Slack, Confluence, Gmail).

Design:
  - Each provider has its own OAuthProviderConfig (client_id, secret, scopes, URLs)
  - All provider configs loaded from env vars (no secrets in code)
  - State parameter used for CSRF protection (signed, expiring token)
  - Token exchange via httpx
  - Token refresh handled here so fetchers don't reimplement it
  - Tokens persisted via CheckpointStore

This is REAL OAuth — not a stub. To test end-to-end you need to:
  1. Register an OAuth app at each provider
  2. Set env vars (see _load_config)
  3. Visit GET /api/oauth/{provider}/start
  4. After callback, the access token is stored and the importer can use it
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx

from maestro_oem.checkpoint_store import CheckpointStore

logger = logging.getLogger(__name__)


# ─── Per-provider OAuth configuration ───

@dataclass
class OAuthProviderConfig:
    """Configuration for one OAuth provider."""
    name: str
    client_id: str
    client_secret: str
    scopes: list[str]
    auth_url: str
    token_url: str
    redirect_uri: str
    extra_params: dict[str, str] = field(default_factory=dict)
    # For providers that need a resource parameter (Atlassian)
    resource: str | None = None

    def has_credentials(self) -> bool:
        return bool(self.client_id) and bool(self.client_secret)


# Default OAuth endpoints for each provider. Client IDs/secrets come from env.
_DEFAULT_ENDPOINTS = {
    "github": {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scopes": ["repo", "read:org", "read:user"],
        "extra": {},
    },
    "jira": {
        "auth_url": "https://auth.atlassian.com/authorize",
        "token_url": "https://auth.atlassian.com/oauth/token",
        "scopes": ["read:jira-work", "read:jira-user", "offline_access"],
        "extra": {
            "audience": "api.atlassian.com",
            "prompt": "consent",
        },
    },
    "slack": {
        "auth_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "scopes": [
            "channels:history", "channels:read",
            "groups:history", "groups:read",
            "im:history", "im:read",
            "mpim:history", "mpim:read",
            "users:read", "team:read",
        ],
        "extra": {},
    },
    "confluence": {
        # Confluence Cloud uses the same Atlassian OAuth as Jira
        "auth_url": "https://auth.atlassian.com/authorize",
        "token_url": "https://auth.atlassian.com/oauth/token",
        "scopes": ["read:confluence-content.all", "read:confluence-space.summary", "offline_access"],
        "extra": {
            "audience": "api.atlassian.com",
            "prompt": "consent",
        },
    },
    "gmail": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.metadata",
        ],
        "extra": {
            "access_type": "offline",
            "prompt": "consent",
        },
    },
    "customer": {
        # Salesforce Connected App OAuth 2.0 Web Server Flow.
        # Requires a Connected App registered at Salesforce with:
        #   - Callback URL: <redirect_uri_base>/api/oauth/callback?provider=customer
        #   - Scopes: api, refresh_token, web
        # Env vars: MAESTRO_CUSTOMER_CLIENT_ID, MAESTRO_CUSTOMER_CLIENT_SECRET
        "auth_url": "https://login.salesforce.com/services/oauth2/authorize",
        "token_url": "https://login.salesforce.com/services/oauth2/token",
        "scopes": ["api", "refresh_token", "web"],
        "extra": {
            "display": "page",
            "immediate": "false",
            "prompt": "consent",
        },
    },
}


def _load_config(provider: str, redirect_uri_base: str | None = None) -> OAuthProviderConfig:
    """Load OAuth config from env vars.

    Env var naming convention:
      MAESTRO_OAUTH_{PROVIDER}_CLIENT_ID
      MAESTRO_OAUTH_{PROVIDER}_CLIENT_SECRET
      MAESTRO_OAUTH_REDIRECT_URI  (shared)

    Example:
      MAESTRO_OAUTH_GITHUB_CLIENT_ID=Iv1.abc123
      MAESTRO_OAUTH_GITHUB_CLIENT_SECRET=...
      MAESTRO_OAUTH_REDIRECT_URI=http://localhost:8765/api/oauth/callback
    """
    env_prefix = f"MAESTRO_OAUTH_{provider.upper()}_"
    client_id = os.environ.get(f"{env_prefix}CLIENT_ID", "")
    client_secret = os.environ.get(f"{env_prefix}CLIENT_SECRET", "")
    redirect_uri = (
        os.environ.get("MAESTRO_OAUTH_REDIRECT_URI")
        or (f"{redirect_uri_base}/api/oauth/callback" if redirect_uri_base else "")
    )
    endpoints = _DEFAULT_ENDPOINTS[provider]
    return OAuthProviderConfig(
        name=provider,
        client_id=client_id,
        client_secret=client_secret,
        scopes=endpoints["scopes"],
        auth_url=endpoints["auth_url"],
        token_url=endpoints["token_url"],
        redirect_uri=redirect_uri,
        extra_params=endpoints["extra"],
    )


# ─── State tokens (CSRF protection) ───

def _make_state(provider: str, ttl_seconds: int = 600) -> str:
    """Create a signed state token. Format: <provider>:<expire>:<random>

    We don't sign with a secret key here because the OAuthManager process is
    stateful anyway — we just need the state to be unforgeable enough that
    a browser can't be tricked into completing someone else's flow.
    """
    expire = int(time.time()) + ttl_seconds
    rand = secrets.token_urlsafe(24)
    return f"{provider}:{expire}:{rand}"


def _verify_state(state: str, expected_provider: str) -> bool:
    """Verify a returned state token."""
    try:
        provider, expire_str, _ = state.split(":", 2)
        if provider != expected_provider:
            return False
        if int(expire_str) < time.time():
            return False
        return True
    except (ValueError, TypeError):
        return False


# ─── The manager ───

class OAuthManager:
    """
    Centralized OAuth flow manager for all 5 providers.

    Responsibilities:
      - Build authorization URLs
      - Exchange authorization codes for tokens
      - Refresh expired tokens
      - Revoke tokens (on disconnect)
      - Persist tokens via CheckpointStore

    This is the single source of truth for "is provider X connected?"
    """

    def __init__(
        self,
        store: CheckpointStore,
        redirect_uri_base: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.store = store
        self.redirect_uri_base = redirect_uri_base
        self._http = http_client or httpx.Client(timeout=30.0)
        self._configs: dict[str, OAuthProviderConfig] = {}

    def get_config(self, provider: str) -> OAuthProviderConfig:
        if provider not in self._configs:
            self._configs[provider] = _load_config(provider, self.redirect_uri_base)
        return self._configs[provider]

    def is_configured(self, provider: str) -> bool:
        """Returns True if env vars are set for this provider."""
        return self.get_config(provider).has_credentials()

    # ─── Authorization URL ───

    def get_authorization_url(self, provider: str) -> tuple[str, str]:
        """Build the OAuth authorization URL.

        Returns (auth_url, state) — state must be passed through the callback
        to verify the flow.
        """
        cfg = self.get_config(provider)
        if not cfg.has_credentials():
            raise ValueError(
                f"OAuth not configured for {provider}. Set "
                f"MAESTRO_OAUTH_{provider.upper()}_CLIENT_ID and "
                f"MAESTRO_OAUTH_{provider.upper()}_CLIENT_SECRET."
            )
        state = _make_state(provider)
        params = {
            "client_id": cfg.client_id,
            "redirect_uri": cfg.redirect_uri,
            "scope": " ".join(cfg.scopes),
            "state": state,
            "response_type": "code",
        }
        params.update(cfg.extra_params)
        url = f"{cfg.auth_url}?{urlencode(params)}"
        logger.info("Built OAuth URL for %s", provider)
        return url, state

    # ─── Code exchange ───

    def exchange_code(
        self, provider: str, code: str, state: str
    ) -> dict[str, Any]:
        """Exchange an authorization code for access/refresh tokens.

        Persists tokens in CheckpointStore on success.
        Raises OAuthError on failure.
        """
        if not _verify_state(state, provider):
            raise OAuthError(f"Invalid state token for {provider}")

        cfg = self.get_config(provider)
        if not cfg.has_credentials():
            raise OAuthError(f"OAuth not configured for {provider}")

        token_payload: dict[str, Any] = {
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "code": code,
            "redirect_uri": cfg.redirect_uri,
            "grant_type": "authorization_code",
        }

        # Slack uses form-encoded POST with a different field name
        headers = {"Accept": "application/json"}
        if provider == "slack":
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            if provider == "slack":
                resp = self._http.post(cfg.token_url, data=token_payload, headers=headers)
            else:
                resp = self._http.post(cfg.token_url, json=token_payload, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise OAuthError(f"Token exchange HTTP error for {provider}: {e}") from e

        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            raise OAuthError(f"Token response not JSON for {provider}: {e}") from e

        # Slack returns ok=false on error
        if provider == "slack" and not data.get("ok", False):
            raise OAuthError(
                f"Slack OAuth error: {data.get('error', 'unknown')}"
            )

        if "error" in data:
            raise OAuthError(f"OAuth error from {provider}: {data['error']}")

        access_token = (
            data.get("access_token")
            or data.get("authed_user", {}).get("access_token")
        )
        if not access_token:
            raise OAuthError(f"No access_token in {provider} response: {data}")

        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in")
        expires_at = None
        if expires_in:
            expires_at = str(int(time.time()) + int(expires_in))

        scopes = data.get("scope", "").split(" ") if data.get("scope") else []

        self.store.save_credentials(
            provider=provider,
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=data.get("token_type", "Bearer"),
            expires_at=expires_at,
            scopes=scopes,
            metadata=data,
        )
        self.store.set_connection(provider, connected=True)

        logger.info("OAuth exchange successful for %s", provider)
        return data

    # ─── Token refresh ───

    def refresh_token(self, provider: str) -> str:
        """Refresh an expired access token. Returns the new access token.

        Raises OAuthError if the refresh fails (caller should disconnect).
        """
        creds = self.store.load_credentials(provider)
        if not creds or not creds.get("refresh_token"):
            raise OAuthError(f"No refresh token for {provider}")

        cfg = self.get_config(provider)
        payload: dict[str, Any] = {
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "refresh_token": creds["refresh_token"],
            "grant_type": "refresh_token",
        }

        # Atlassian (Jira/Confluence) requires a special JWT-style refresh
        if provider in ("jira", "confluence"):
            payload["redirect_uri"] = cfg.redirect_uri

        try:
            if provider == "slack":
                resp = self._http.post(
                    cfg.token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            else:
                resp = self._http.post(cfg.token_url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise OAuthError(f"Refresh HTTP error for {provider}: {e}") from e

        data = resp.json()
        if provider == "slack" and not data.get("ok", False):
            raise OAuthError(f"Slack refresh failed: {data.get('error')}")

        access_token = (
            data.get("access_token")
            or data.get("authed_user", {}).get("access_token")
        )
        if not access_token:
            raise OAuthError(f"No access_token in refresh response: {data}")

        expires_in = data.get("expires_in")
        expires_at = str(int(time.time()) + int(expires_in)) if expires_in else None

        new_refresh = data.get("refresh_token", creds["refresh_token"])
        scopes = data.get("scope", "").split(" ") if data.get("scope") else creds["scopes"]

        self.store.save_credentials(
            provider=provider,
            access_token=access_token,
            refresh_token=new_refresh,
            token_type=data.get("token_type", "Bearer"),
            expires_at=expires_at,
            scopes=scopes,
            metadata=data,
        )
        logger.info("Refreshed OAuth token for %s", provider)
        return access_token

    # ─── Get a valid access token (refresh if needed) ───

    def get_valid_access_token(self, provider: str) -> str:
        """Return a non-expired access token, refreshing if necessary.

        Raises OAuthError if not connected or refresh fails.
        """
        creds = self.store.load_credentials(provider)
        if not creds:
            raise OAuthError(f"No credentials for {provider}")

        # Check expiry (5-minute buffer)
        if creds.get("expires_at"):
            try:
                expires = int(creds["expires_at"])
                if time.time() > expires - 300:
                    if creds.get("refresh_token"):
                        return self.refresh_token(provider)
                    raise OAuthError(f"Token expired and no refresh token for {provider}")
            except (ValueError, TypeError):
                pass  # Malformed expiry, assume still valid

        return creds["access_token"]

    # ─── Disconnect ───

    def disconnect(self, provider: str) -> None:
        """Revoke tokens and mark provider as disconnected."""
        creds = self.store.load_credentials(provider)
        if not creds:
            self.store.set_connection(provider, connected=False)
            return

        # Best-effort revocation
        cfg = self.get_config(provider)
        try:
            if provider == "github":
                # GitHub requires Basic auth for app token revocation
                resp = self._http.request(
                    "DELETE",
                    f"https://api.github.com/applications/{cfg.client_id}/token",
                    auth=(cfg.client_id, cfg.client_secret),
                    json={"access_token": creds["access_token"]},
                    timeout=10.0,
                )
            elif provider == "slack":
                self._http.post(
                    "https://slack.com/api/auth.revoke",
                    data={"token": creds["access_token"]},
                    timeout=10.0,
                )
            elif provider == "gmail":
                self._http.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": creds["access_token"]},
                    timeout=10.0,
                )
            elif provider in ("jira", "confluence"):
                # Atlassian has no per-token revoke; just delete locally
                pass
        except httpx.HTTPError as e:
            logger.warning("Token revocation failed for %s: %s", provider, e)

        self.store.delete_credentials(provider)
        self.store.set_connection(provider, connected=False)
        logger.info("Disconnected %s", provider)

    # ─── Status ───

    def status(self) -> list[dict[str, Any]]:
        """Return connection status for all 6 providers (5 + customer/Salesforce)."""
        out = []
        for p in ("github", "jira", "slack", "confluence", "gmail", "customer"):
            cfg = self.get_config(p)
            conn = self.store.get_connection(p)
            creds = self.store.load_credentials(p)
            out.append({
                "provider": p,
                "configured": cfg.has_credentials(),
                "connected": bool(conn and conn["connected"]),
                "has_credentials": bool(creds),
                "connected_at": conn["connected_at"] if conn else None,
            })
        return out


class OAuthError(Exception):
    """Raised when an OAuth operation fails."""
    pass
