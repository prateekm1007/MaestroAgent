"""Shared rate-limit decorator — P0-6 audit fix (2026-07-15).
P67 fix (seventh audit): rate limiting MUST fire in production regardless
of MAESTRO_TEST_MODE. The prior code bypassed rate limiting entirely when
MAESTRO_TEST_MODE=1, which meant production deployments with that env var
set had NO rate limiting — all 30 rapid requests returned 200/401."""
from __future__ import annotations

import functools
import logging
import os
from typing import Callable

logger = logging.getLogger(__name__)


def rate_limit(limit_str: str) -> Callable:
    """Return a decorator that applies a slowapi rate limit lazily."""
    def decorator(func: Callable) -> Callable:
        _decorated_cache = None

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # P67 fix: only bypass rate limiting in test mode AND when NOT
            # in production. In production (MAESTRO_PERSONAL_ENV=production),
            # rate limiting ALWAYS fires regardless of MAESTRO_TEST_MODE.
            _is_prod = os.environ.get("MAESTRO_PERSONAL_ENV") == "production"
            _is_test = os.environ.get("MAESTRO_TEST_MODE") == "1"
            if _is_test and not _is_prod:
                return await func(*args, **kwargs)

            nonlocal _decorated_cache
            from maestro_personal_shell import api as _api
            _lim = getattr(_api, "_limiter", None)
            enabled = getattr(_api, "_rate_limiting_enabled", False)
            if _lim is not None and enabled:
                if _decorated_cache is None:
                    _decorated_cache = _lim.limit(limit_str)(func)
                return await _decorated_cache(*args, **kwargs)
            # Limiter not available (slowapi not installed) — run without limit.
            return await func(*args, **kwargs)
        return wrapper
    return decorator
