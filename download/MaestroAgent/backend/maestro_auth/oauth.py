"""OAuth provider stubs (Supabase, Auth0).

v1.0 ships the interface + stubs. Full integration (token verification,
user management, multi-tenant) is v1.1. The stubs let users configure
`MAESTRO_OAUTH_PROVIDER=supabase` today and get a clear "not yet
implemented" error rather than silent breakage.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class OAuthUser:
    """A user resolved from an OAuth token."""

    id: str
    email: str | None = None
    name: str | None = None
    provider: str = ""
    scopes: list[str] | None = None


class OAuthProvider(ABC):
    """Abstract OAuth provider."""

    name: str = "abstract"

    @abstractmethod
    async def verify_token(self, token: str) -> OAuthUser | None: ...

    @abstractmethod
    async def get_authorize_url(self, state: str) -> str: ...

    @abstractmethod
    async def exchange_code(self, code: str) -> tuple[str, OAuthUser] | None:
        """Exchange an auth code for an access token + user."""
        ...


class SupabaseProvider(OAuthProvider):
    """Supabase OAuth provider (stub for v1.0)."""

    name = "supabase"

    def __init__(self, client_id: str, client_secret: str, redirect_url: str, base_url: str | None = None) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_url = redirect_url
        self.base_url = base_url or "https://your-project.supabase.co"

    async def verify_token(self, token: str) -> OAuthUser | None:
        # TODO(v1.1): call Supabase's /auth/v1/user endpoint with the JWT.
        # For v1.0, log a warning and return None (auth falls back to API key).
        logger.warning("Supabase OAuth not yet implemented in v1.0; use API key auth")
        return None

    async def get_authorize_url(self, state: str) -> str:
        return (
            f"{self.base_url}/auth/v1/authorize"
            f"?client_id={self.client_id}"
            f"&redirect_to={self.redirect_url}"
            f"&response_type=code"
            f"&state={state}"
        )

    async def exchange_code(self, code: str) -> tuple[str, OAuthUser] | None:
        # TODO(v1.1): POST to Supabase's /auth/v1/token?grant_type=authorization_code
        logger.warning("Supabase OAuth code exchange not yet implemented in v1.0")
        return None


class Auth0Provider(OAuthProvider):
    """Auth0 OAuth provider (stub for v1.0)."""

    name = "auth0"

    def __init__(self, client_id: str, client_secret: str, redirect_url: str, domain: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_url = redirect_url
        self.domain = domain

    async def verify_token(self, token: str) -> OAuthUser | None:
        # TODO(v1.1): verify the JWT against Auth0's JWKS.
        logger.warning("Auth0 OAuth not yet implemented in v1.0; use API key auth")
        return None

    async def get_authorize_url(self, state: str) -> str:
        return (
            f"https://{self.domain}/authorize"
            f"?client_id={self.client_id}"
            f"&redirect_uri={self.redirect_url}"
            f"&response_type=code"
            f"&scope=openid profile email"
            f"&state={state}"
        )

    async def exchange_code(self, code: str) -> tuple[str, OAuthUser] | None:
        # TODO(v1.1): POST to https://<domain>/oauth/token
        logger.warning("Auth0 OAuth code exchange not yet implemented in v1.0")
        return None


def make_provider(config: Any) -> OAuthProvider | None:
    """Build an OAuth provider from AuthConfig, or None if disabled."""
    if not config.oauth_provider:
        return None
    if config.oauth_provider == "supabase":
        if not (config.oauth_client_id and config.oauth_client_secret and config.oauth_redirect_url):
            logger.error("Supabase OAuth requires client_id, client_secret, and redirect_url")
            return None
        return SupabaseProvider(
            config.oauth_client_id, config.oauth_client_secret, config.oauth_redirect_url
        )
    if config.oauth_provider == "auth0":
        if not (config.oauth_client_id and config.oauth_client_secret and config.oauth_redirect_url):
            logger.error("Auth0 OAuth requires client_id, client_secret, and redirect_url")
            return None
        domain = config.oauth_redirect_url.split("//")[1].split("/")[0]
        return Auth0Provider(
            config.oauth_client_id, config.oauth_client_secret, config.oauth_redirect_url, domain
        )
    logger.error("Unknown OAuth provider: %s", config.oauth_provider)
    return None
