"""Shared rate-limit decorator — P0-6 audit fix (2026-07-15)."""
from __future__ import annotations

import functools
import logging
from typing import Callable

logger = logging.getLogger(__name__)


def rate_limit(limit_str: str) -> Callable:
    """Return a decorator that applies a slowapi rate limit lazily."""
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
