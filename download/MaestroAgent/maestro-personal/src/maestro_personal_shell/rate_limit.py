"""Shared rate-limit decorator — P0-6 audit fix (2026-07-15).
P67 fix: rate limiting MUST fire in production regardless of MAESTRO_TEST_MODE.
P69 fix: slowapi needs the request object in kwargs to identify the client.
P67/K3 fix (2026-07-25): gate on MAESTRO_LOCAL_DEV (canonical local-dev flag),
NOT MAESTRO_TEST_MODE (test-suite flag that was set on Railway by accident)."""
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
            # P67/K3 fix: only skip in local dev. Test mode does NOT disable
            # rate limiting — tests should use MAESTRO_LOCAL_DEV=true if they
            # need to bypass, or use a separate test fixture that doesn't
            # trigger the rate-limited path.
            if os.environ.get("MAESTRO_LOCAL_DEV") == "true":
                return await func(*args, **kwargs)

            nonlocal _decorated_cache
            from maestro_personal_shell import api as _api
            _lim = getattr(_api, "_limiter", None)
            enabled = getattr(_api, "_rate_limiting_enabled", False)
            if _lim is not None and enabled:
                if _decorated_cache is None:
                    _decorated_cache = _lim.limit(limit_str)(func)
                # P69: slowapi needs the request object to identify the client IP.
                # FastAPI injects it as a parameter, but the slowapi decorator
                # looks for it in kwargs. If 'request' is in args (positional),
                # move it to kwargs so slowapi can find it.
                if 'request' not in kwargs:
                    # Try to find request in args (it's usually the first arg
                    # after self/cls in FastAPI endpoints)
                    from starlette.requests import Request as _StarletteRequest
                    for i, arg in enumerate(args):
                        if isinstance(arg, _StarletteRequest):
                            kwargs['request'] = arg
                            break
                return await _decorated_cache(*args, **kwargs)
            return await func(*args, **kwargs)
        return wrapper
    return decorator
