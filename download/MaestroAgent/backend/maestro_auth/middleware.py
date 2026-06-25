"""ASGI middleware: auth, rate limiting, audit, input sanitization.

These are added to the FastAPI app in `maestro_api.main.create_app`:

    app.add_middleware(AuditMiddleware, store=...)
    app.add_middleware(RateLimitMiddleware, config=...)
    app.add_middleware(AuthMiddleware, config=..., key_store=...)

Order matters: the LAST `add_middleware` runs FIRST in the request
lifecycle. We add audit last (so it wraps everything), rate-limit
second, auth first (so auth is checked before rate-limiting counts).

Wait — actually FastAPI middleware runs in reverse add order, so:
  add_middleware(AuthMiddleware)     → runs first (outermost)
  add_middleware(RateLimitMiddleware) → runs second
  add_middleware(AuditMiddleware)     → runs third (innermost, wraps the route)

So we add auth LAST to make it outermost. See create_app.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# --- Input sanitization ---

# Strip control characters (except newline/tab) and limit length.
_CTRL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
MAX_INPUT_LENGTH = 10_000  # per-field; protects against prompt injection via huge args


def sanitize_input(value: Any, max_length: int = MAX_INPUT_LENGTH) -> Any:
    """Recursively sanitize input: strip control chars, truncate long strings.

    This is a defense-in-depth measure against prompt injection via
    template arguments, run goals, and agent specs. It does NOT replace
    proper sandboxing — all tool execution still happens in Docker.
    """
    if isinstance(value, str):
        cleaned = _CTRL_RE.sub("", value)
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length] + "...[truncated]"
        return cleaned
    if isinstance(value, dict):
        return {k: sanitize_input(v, max_length) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_input(v, max_length) for v in value]
    return value


# --- Auth middleware ---

# Paths that don't require auth (even when auth is enabled).
PUBLIC_PATHS = {"/api/health", "/api/auth/login", "/api/auth/callback", "/docs", "/openapi.json", "/redoc"}


class AuthMiddleware(BaseHTTPMiddleware):
    """API key + OAuth auth middleware.

    - If auth is disabled, passes through.
    - If auth is enabled, checks `Authorization: Bearer <key>` against
      the API key store. Public paths (health, login, docs) are exempt.
    - On failure, returns 401 with a JSON error.
    """

    def __init__(self, app: Any, config: Any, key_store: Any = None, oauth_provider: Any = None) -> None:
        super().__init__(app)
        self.config = config
        self.key_store = key_store
        self.oauth_provider = oauth_provider

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if not self.config.enabled:
            return await call_next(request)

        path = request.url.path

        # Public paths bypass auth.
        if path in PUBLIC_PATHS or path.startswith("/ws/") or path.startswith("/assets/") or path.startswith("/icons/"):
            return await call_next(request)

        # Static file serving (PWA bundle) bypasses auth.
        if not path.startswith("/api/"):
            return await call_next(request)

        # Extract bearer token.
        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

        # Try API key first.
        if self.key_store and token:
            ok, key_info = await self.key_store.verify(token)
            if ok:
                request.state.user = {"method": "api_key", "name": key_info.get("name", "")}
                request.state.auth_scopes = key_info.get("scopes", ["*"])
                return await call_next(request)

        # Try OAuth (v1.1).
        if self.oauth_provider and token:
            user = await self.oauth_provider.verify_token(token)
            if user:
                request.state.user = {"method": "oauth", "name": user.name or user.email or user.id}
                request.state.auth_scopes = user.scopes or ["*"]
                return await call_next(request)

        # No valid auth.
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized. Provide a valid API key via Authorization: Bearer <key>."},
        )


# --- Rate limiting middleware ---

@dataclass
class _TokenBucket:
    """Simple token bucket: refills `capacity` tokens per `period`."""

    capacity: float
    period: float  # seconds
    tokens: float = 0
    last_refill: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        self.tokens = self.capacity

    def consume(self, n: float = 1) -> bool:
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * (self.capacity / self.period))
        self.last_refill = now
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP token bucket rate limiter.

    Default: `MAESTRO_RATE_LIMIT_RPM` requests per minute per IP.
    Returns 429 with Retry-After header when exceeded.
    """

    def __init__(self, app: Any, config: Any) -> None:
        super().__init__(app)
        self.rpm = config.rate_limit_rpm
        self._buckets: dict[str, _TokenBucket] = defaultdict(
            lambda: _TokenBucket(capacity=self.rpm, period=60.0)
        )

    def _client_ip(self, request: Request) -> str:
        # Honor X-Forwarded-For if behind a trusted proxy.
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            # Take the first IP (closest to the client).
            return xff.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # Don't rate-limit static assets or the WS upgrade.
        path = request.url.path
        if path.startswith("/assets/") or path.startswith("/icons/") or path.startswith("/ws/"):
            return await call_next(request)

        ip = self._client_ip(request)
        bucket = self._buckets[ip]
        if not bucket.consume():
            logger.warning("Rate limit exceeded for %s on %s", ip, path)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)


# --- Audit middleware ---

class AuditMiddleware(BaseHTTPMiddleware):
    """Logs every authenticated API call to the tamper-evident audit log.

    Writes to the same `audit` table used by the checkpoint store, so
    audit entries are hash-chained and tamper-evident.
    """

    def __init__(self, app: Any, store: Any = None) -> None:
        super().__init__(app)
        self.store = store

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # Skip non-API + health checks.
        path = request.url.path
        if not path.startswith("/api/") or path == "/api/health":
            return await call_next(request)

        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000

        # Write to audit log (best-effort; never fail the request over audit).
        if self.store is not None:
            try:
                user = getattr(request.state, "user", None)
                await self.store.audit(
                    "__api__",
                    "api.call",
                    {
                        "method": request.method,
                        "path": path,
                        "status": response.status_code,
                        "duration_ms": round(duration_ms, 1),
                        "user": user,
                        "ip": request.client.host if request.client else None,
                    },
                )
            except Exception as exc:
                logger.warning("audit log write failed: %s", exc)

        return response
