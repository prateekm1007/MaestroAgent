"""Auth configuration — env-driven, zero-config for local dev."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AuthConfig:
    """Auth configuration loaded from environment variables."""

    # Master toggle. When false (default for local dev), no auth is required.
    enabled: bool = False
    # Local API key. If set, all /api/* requests must include it as
    # `Authorization: Bearer <key>`. Auto-generated on first run if
    # MAESTRO_AUTH_ENABLED=true and no key is set.
    api_key: str | None = None
    # Rate limiting (requests per minute per IP).
    rate_limit_rpm: int = 100
    # OAuth provider (supabase | auth0 | None).
    oauth_provider: str | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_redirect_url: str | None = None
    # CORS — comma-separated origins. Default * (all) for local dev;
    # tighten in production.
    cors_origins: list[str] | None = None
    # Trusted proxy count (for X-Forwarded-For parsing behind nginx/Caddy).
    trusted_proxy_count: int = 0

    @classmethod
    def from_env(cls) -> "AuthConfig":
        enabled = os.environ.get("MAESTRO_AUTH_ENABLED", "false").lower() in ("1", "true", "yes")
        api_key = os.environ.get("MAESTRO_API_KEY")
        rate_limit = int(os.environ.get("MAESTRO_RATE_LIMIT_RPM", "100"))
        oauth_provider = os.environ.get("MAESTRO_OAUTH_PROVIDER") or None
        cors = os.environ.get("MAESTRO_CORS_ORIGINS")
        cors_origins = [o.strip() for o in cors.split(",")] if cors else None
        return cls(
            enabled=enabled,
            api_key=api_key,
            rate_limit_rpm=rate_limit,
            oauth_provider=oauth_provider,
            oauth_client_id=os.environ.get("MAESTRO_OAUTH_CLIENT_ID"),
            oauth_client_secret=os.environ.get("MAESTRO_OAUTH_CLIENT_SECRET"),
            oauth_redirect_url=os.environ.get("MAESTRO_OAUTH_REDIRECT_URL"),
            cors_origins=cors_origins,
            trusted_proxy_count=int(os.environ.get("MAESTRO_TRUSTED_PROXY_COUNT", "0")),
        )

    def to_dict(self) -> dict:
        """Public-safe dict (never exposes secrets)."""
        return {
            "enabled": self.enabled,
            "oauth_provider": self.oauth_provider,
            "rate_limit_rpm": self.rate_limit_rpm,
            "cors_origins": self.cors_origins or ["*"],
            "api_key_configured": self.api_key is not None,
        }
