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

    Round 68 fix (2026-07-18): the previous implementation re-decorated
    the function on EVERY call (`_lim.limit(limit_str)(func)` inside the
    wrapper). This created a new slowapi decorator instance per request,
    which confused the internal counter — a "10/minute" limit triggered
    at request 5 instead of 11 (the auditor caught this). Now: the
    decorated function is created ONCE (on first call) and cached. The
    lazy lookup still works (the Limiter is looked up at call time, not
    import time, so test-isolation reloads still get the current Limiter).
    """
    def decorator(func: Callable) -> Callable:
        _decorated_cache = None

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            import os as _os
            # Test mode: bypass rate limiting entirely.
            if _os.environ.get("MAESTRO_TEST_MODE") == "1":
                return await func(*args, **kwargs)

            nonlocal _decorated_cache
            from maestro_personal_shell import api as _api
            _lim = getattr(_api, "_limiter", None)
            enabled = getattr(_api, "_rate_limiting_enabled", False)
            if _lim is not None and enabled:
                # Decorate ONCE and cache. Re-decorating on every call was
                # the root cause of the early-trigger bug (Round 68 audit):
                # slowapi's internal counter got confused by repeated
                # decoration, triggering 429 at request 5 instead of 11
                # for a "10/minute" limit. Caching the decorated function
                # gives slowapi a stable decorator instance with a proper
                # counter.
                if _decorated_cache is None:
                    _decorated_cache = _lim.limit(limit_str)(func)
                return await _decorated_cache(*args, **kwargs)
            # Limiter not available (slowapi not installed) — run without limit.
            return await func(*args, **kwargs)
        return wrapper
    return decorator
