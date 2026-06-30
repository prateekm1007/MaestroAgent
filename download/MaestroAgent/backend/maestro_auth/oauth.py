"""OAuth provider stubs (Supabase, Auth0).

v1.0 ships the interface + stubs. Full integration (token verification,
user management, multi-tenant) is v1.1. The stubs RAISE
OAuthNotImplementedError so configuring `MAESTRO_OAUTH_PROVIDER=supabase`
produces a clear error rather than silent fallback or confusion.

SECURITY NOTE: The stubs do NOT authenticate users. They raise rather
than return None, so auth fails closed. If you need Supabase or Auth0
SSO before v1.1, use the OIDC provider (oidc.py) which IS fully
implemented with signature verification via PyJWT.
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


class OAuthNotImplementedError(NotImplementedError):
    """Raised when a stub OAuth provider is invoked.

    This is a fail-closed error — the user is NOT authenticated. The
    error message directs the user to the OIDC provider (which IS
    implemented) as the alternative.
    """


class SupabaseProvider(OAuthProvider):
    """Supabase OAuth provider (stub — NOT IMPLEMENTED in v1.0).

    Raises OAuthNotImplementedError on any auth attempt. Use the OIDC
    provider (oidc.py) for Supabase SSO — it's fully implemented with
    signature verification via PyJWT.
    """

    name = "supabase"

    def __init__(self, client_id: str, client_secret: str, redirect_url: str, base_url: str | None = None) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_url = redirect_url
        self.base_url = base_url or "https://your-project.supabase.co"

    async def verify_token(self, token: str) -> OAuthUser | None:
        raise OAuthNotImplementedError(
            "Supabase OAuth is not implemented in v1.0. "
            "Use the OIDC provider (oidc.py) for Supabase SSO — it's fully "
            "implemented with PyJWT signature verification. Set "
            "MAESTRO_OIDC_ISSUER=https://<your-project>.supabase.co/auth/v1 "
            "and MAESTRO_OIDC_CLIENT_ID=<your-client-id>."
        )

    async def get_authorize_url(self, state: str) -> str:
        return (
            f"{self.base_url}/auth/v1/authorize"
            f"?client_id={self.client_id}"
            f"&redirect_to={self.redirect_url}"
            f"&response_type=code"
            f"&state={state}"
        )

    async def exchange_code(self, code: str) -> tuple[str, OAuthUser] | None:
        raise OAuthNotImplementedError(
            "Supabase OAuth code exchange is not implemented in v1.0. "
            "Use the OIDC provider (oidc.py) instead."
        )


class Auth0Provider(OAuthProvider):
    """Auth0 OAuth provider (stub — NOT IMPLEMENTED in v1.0).

    Raises OAuthNotImplementedError on any auth attempt. Use the OIDC
    provider (oidc.py) for Auth0 SSO — it's fully implemented with
    signature verification via PyJWT.
    """

    name = "auth0"

    def __init__(self, client_id: str, client_secret: str, redirect_url: str, domain: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_url = redirect_url
        self.domain = domain

    async def verify_token(self, token: str) -> OAuthUser | None:
        raise OAuthNotImplementedError(
            "Auth0 OAuth is not implemented in v1.0. "
            "Use the OIDC provider (oidc.py) for Auth0 SSO — it's fully "
            "implemented with PyJWT signature verification. Set "
            "MAESTRO_OIDC_ISSUER=https://<your-domain>.auth0.com/ "
            "and MAESTRO_OIDC_CLIENT_ID=<your-client-id>."
        )

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
        raise OAuthNotImplementedError(
            "Auth0 OAuth code exchange is not implemented in v1.0. "
            "Use the OIDC provider (oidc.py) instead."
        )


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
