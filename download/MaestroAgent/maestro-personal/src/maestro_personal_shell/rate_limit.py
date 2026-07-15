"""Shared rate-limit decorator — P0-6 audit fix (2026-07-15).

The auditor found that 12 rapid requests to /api/ask all returned 200,
because the only limit in place was the app-wide default of 200/minute.
That is far too lax for expensive endpoints (LLM calls, OAuth flows,
account creation).

This module exposes `rate_limit(limit_str)` — a lazy decorator that
applies the slowapi limit at CALL time (not import time). The lazy
lookup is critical for test isolation: when a test reloads the api
module, the Limiter is recreated, and any decorator that captured the
old Limiter at import time would be stale.

Usage:

    from maestro_personal_shell.rate_limit import rate_limit

    @router.post("/expensive")
    @rate_limit("30/minute")
    async def expensive_endpoint(...):
        ...

If slowapi is not installed (dev mode), the decorator is a no-op —
the endpoint runs without rate limiting. This matches the existing
behavior of `_maybe_login_decorator` in routers/auth.py.
"""
from __future__ import annotations

import functools
import logging
from typing import Callable

logger = logging.getLogger(__name__)


def rate_limit(limit_str: str) -> Callable:
    """Return a decorator that applies a slowapi rate limit lazily.

    Args:
        limit_str: slowapi limit string, e.g. "30/minute", "5/hour".

    Returns:
        A decorator that wraps async endpoint handlers.

    IMPORTANT: RateLimitExceeded MUST propagate — do NOT catch it. The
    FastAPI exception handler registered in api.py converts it to a 429
    response. Catching it here would silently bypass the rate limit.

    Test mode: when MAESTRO_TEST_MODE=1, the limit is bypassed entirely
    so the test suite can make rapid requests without tripping 429s.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            import os as _os
            # Test mode: bypass rate limiting entirely.
            if _os.environ.get("MAESTRO_TEST_MODE") == "1":
                return await func(*args, **kwargs)

            from maestro_personal_shell import api as _api
            _lim = getattr(_api, "_limiter", None)
            enabled = getattr(_api, "_rate_limiting_enabled", False)
            if _lim is not None and enabled:
                # Re-decorate on each call so we always use the current
                # Limiter (post-reload). The decorated function raises
                # RateLimitExceeded when the limit is exceeded — we let
                # that propagate so the FastAPI exception handler can
                # convert it to a 429 response.
                decorated = _lim.limit(limit_str)(func)
                return await decorated(*args, **kwargs)
            # Limiter not available (slowapi not installed) — run without limit.
            return await func(*args, **kwargs)
        return wrapper
    return decorator
