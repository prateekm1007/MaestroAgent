"""maestro_auth — authentication, rate limiting, and audit middleware.

This module provides production-grade security for self-hosted MaestroAgent:

1. **API key auth** — a simple local API key (stored in the OS keyring or
   `MAESTRO_API_KEY` env var). Required for all `/api/*` endpoints when
   `MAESTRO_AUTH_ENABLED=true`. The browser PWA sends it via
   `Authorization: Bearer <key>`.

2. **OAuth stub** — pluggable OAuth via Supabase or Auth0. Disabled by
   default; enable by setting `MAESTRO_OAUTH_PROVIDER=supabase|auth0`
   + the provider's credentials. v1.0 ships the stub; full integration
   is v1.1.

3. **Rate limiting** — per-IP token bucket. Default: 100 requests / min.
   Configurable via `MAESTRO_RATE_LIMIT_RPM`.

4. **Input sanitization** — strips control chars + truncates long inputs
   to prevent prompt injection via template args.

5. **Audit logging** — every authenticated API call is written to the
   tamper-evident audit log (reusing the checkpoint store's audit chain).

Usage in FastAPI:
    from maestro_auth import AuthMiddleware, RateLimitMiddleware, AuditMiddleware
    app.add_middleware(AuthMiddleware, store=...)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuditMiddleware, store=...)
"""

from maestro_auth.config import AuthConfig
from maestro_auth.middleware import (
    AuthMiddleware,
    RateLimitMiddleware,
    AuditMiddleware,
    sanitize_input,
)
from maestro_auth.api_keys import (
    generate_api_key,
    hash_api_key,
    verify_api_key,
    ApiKeyStore,
    SQLiteApiKeyStore,
)
from maestro_auth.oauth import OAuthProvider, SupabaseProvider, Auth0Provider

__all__ = [
    "AuthConfig",
    "AuthMiddleware",
    "RateLimitMiddleware",
    "AuditMiddleware",
    "sanitize_input",
    "generate_api_key",
    "hash_api_key",
    "verify_api_key",
    "ApiKeyStore",
    "SQLiteApiKeyStore",
    "OAuthProvider",
    "SupabaseProvider",
    "Auth0Provider",
]
