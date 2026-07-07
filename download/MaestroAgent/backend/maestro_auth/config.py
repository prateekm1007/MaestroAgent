"""Auth configuration — env-driven, zero-config for local dev."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AuthConfig:
    """Auth configuration loaded from environment variables."""

    # Master toggle. When false (default for local dev), no auth is required.
    enabled: bool = True  # Auth ON by default (safe); OFF only when MAESTRO_LOCAL_DEV=true
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
        # Round 60 Fix 1: auth defaults to ON in non-local environments.
        # The old default was "false" — every endpoint was open by default.
        # Now: auth is ON unless MAESTRO_LOCAL_DEV=true or MAESTRO_AUTH_ENABLED=false.
        env = os.environ.get("MAESTRO_ENV", "development")
        is_local_dev = env == "development" and os.environ.get("MAESTRO_LOCAL_DEV", "false").lower() in ("1", "true", "yes")
        auth_default = "false" if is_local_dev else "true"
        enabled = os.environ.get("MAESTRO_AUTH_ENABLED", auth_default).lower() in ("1", "true", "yes")
        api_key = os.environ.get("MAESTRO_API_KEY")
        rate_limit = int(os.environ.get("MAESTRO_RATE_LIMIT_RPM", "100"))
        oauth_provider = os.environ.get("MAESTRO_OAUTH_PROVIDER") or None
        cors = os.environ.get("MAESTRO_CORS_ORIGINS")
        # Round 60 Fix 5: tighten CORS when not explicitly configured.
        # In local dev: allow localhost. Otherwise: no wildcard.
        if cors:
            cors_origins = [o.strip() for o in cors.split(",")]
        elif is_local_dev:
            cors_origins = ["http://localhost:1420", "http://127.0.0.1:1420", "http://localhost:8765", "http://127.0.0.1:8765"]
        else:
            cors_origins = []  # No wildcard — must be explicitly configured
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
