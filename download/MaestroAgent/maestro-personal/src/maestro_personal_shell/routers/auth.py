"""Auth router — login, revoke, rotate.

Extracted from api.py during the Phase 8 router split. No behavior
changes — same paths, same request/response schemas, same token store.

verify_token + the per-user token store helpers (_init_auth_db,
_create_user_token, _revoke_user_token, _revoke_all_user_tokens)
stay in api.py because verify_token is shared across every router
and the helpers are used by both verify_token and these endpoints.
This router imports them.
"""
from __future__ import annotations

import os
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from maestro_personal_shell.models import LoginRequest, LoginResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# verify_token — pulled lazily from api.py at request time so the router
# can be imported before api.py finishes initializing (avoiding a circular
# import). FastAPI inspects this dependency's signature and injects the
# Authorization header just like it would for `verify_token` directly.
# ---------------------------------------------------------------------------


async def verify_token_dep(authorization: str = Header(None)) -> str:
    """Lazy proxy to api.verify_token.

    FastAPI reads this function's signature, sees `authorization: str =
    Header(None)`, and injects the Authorization header. We then forward
    to api.verify_token (which does the actual token verification) so the
    auth router is decoupled from the api.py module-load order.
    """
    from maestro_personal_shell.api import verify_token as _verify_token
    return await _verify_token(authorization=authorization)


# ---------------------------------------------------------------------------
# Login rate-limit decorator (Phase 1 brute-force protection)
# ---------------------------------------------------------------------------


def _maybe_login_decorator():
    """Return a decorator that applies the login rate limit lazily.

    The lookup of `_api._limiter` is deferred to CALL time so that
    `importlib.reload(api_module)` in tests picks up the freshly-created
    Limiter (and its fresh rate-limit counter). The previous version
    captured the Limiter at IMPORT time, which meant reloads didn't
    reset the rate-limit state and tests would accumulate 429s.
    """
    import functools

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                from maestro_personal_shell import api as _api
                _lim = getattr(_api, "_limiter", None)
                if _lim is not None and getattr(_api, "_rate_limiting_enabled", False):
                    # Re-decorate on each call so we always use the current
                    # Limiter (post-reload). slowapi's decorator returns a
                    # wrapped coroutine; awaiting it runs the rate-limit
                    # check + the underlying function.
                    decorated = _lim.limit("10/minute")(func)
                    return await decorated(*args, **kwargs)
            except Exception:
                pass
            return await func(*args, **kwargs)
        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/login", response_model=LoginResponse)
@_maybe_login_decorator()
async def login(request: Request, req: LoginRequest):
    """Login — returns a bearer token.

    P1 fix: passwordless email login removed. The login now requires
    either:
    1. The MAESTRO_PERSONAL_TOKEN env var (single-user local mode) —
       the caller must provide it as the password. No email-based login.
    2. A per-user token that was previously created via _create_user_token.
       But tokens are never created without the setup password.

    In dev mode (MAESTRO_PERSONAL_ENV not 'production'):
    - Bootstrap token works with password=AUTH_TOKEN (backward compat for tests)
    - Email-only login is REJECTED

    In production mode:
    - Only per-user tokens work (no bootstrap)
    - Login requires password validation against user store (future)

    This closes the P0-2 passwordless login vulnerability.
    """
    from maestro_personal_shell.api import (
        _is_production,
        AUTH_TOKEN,
        _create_user_token,
    )

    env_token = os.environ.get("MAESTRO_PERSONAL_TOKEN", "")

    # F8/S1 fix (independent audit): dev mode must NOT mint tokens for
    # arbitrary emails. The previous code allowed `password=$TOKEN` +
    # `user_email=attacker@evil.com` → minted a valid bearer token for
    # attacker@evil.com in dev mode. Anyone with the bootstrap secret
    # became any user. This is fail-open: a developer who deploys without
    # setting MAESTRO_PERSONAL_ENV=production gets full user impersonation.
    #
    # Fix: default to fail-closed. Allow arbitrary email minting ONLY when
    # MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL=1 is explicitly set (a conscious
    # opt-in for test environments). Otherwise, the shared secret mints only
    # the default user.
    allow_arbitrary_email = os.environ.get(
        "MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL", ""
    ).lower() in ("1", "true", "yes")

    if env_token and req.password == env_token:
        if _is_production() or not allow_arbitrary_email:
            # Production OR dev-without-opt-in: only the default user can
            # login with the shared secret. Arbitrary email minting is blocked.
            if req.user_email and req.user_email != "default@personal.local":
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Arbitrary email login is not permitted. "
                        "Set MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL=1 for test environments, "
                        "or use a proper auth provider for multi-user deployment."
                    ),
                )
            user_email = "default@personal.local"
        else:
            # Explicit opt-in test mode: allow any email
            user_email = req.user_email or "default@personal.local"
        token = _create_user_token(user_email)
        return LoginResponse(token=token, user_email=user_email, message="Login successful")

    # Dev mode: allow bootstrap token as password (for tests)
    # F8 fix: same fail-closed gate applies to the AUTH_TOKEN fallback path
    if not _is_production() and req.password == AUTH_TOKEN:
        if allow_arbitrary_email:
            user_email = req.user_email or "default@personal.local"
            if req.user_email:
                token = _create_user_token(user_email)
            else:
                token = AUTH_TOKEN
            return LoginResponse(token=token, user_email=user_email, message="Login successful (dev mode)")
        else:
            # Fail-closed: bootstrap token only mints the default user
            user_email = "default@personal.local"
            token = AUTH_TOKEN
            return LoginResponse(token=token, user_email=user_email, message="Login successful (default user only)")

    # P1 fix: REJECT passwordless email login
    raise HTTPException(
        status_code=401,
        detail="Invalid credentials. Password required. Set MAESTRO_PERSONAL_TOKEN env var for local mode."
    )


@router.post("/revoke")
async def revoke_token(token: str = Depends(verify_token_dep)):
    """Revoke the current token (P1-4 fix).

    The caller's bearer token (from the Authorization header) is revoked.
    After this call, the token can no longer be used for authentication.
    The user must log in again to get a new token.

    This is the standard 'logout' endpoint — it ensures that even if the
    token is intercepted, it becomes useless after revocation.
    """
    from maestro_personal_shell.api import _revoke_all_user_tokens
    # `token` here is the user_email returned by verify_token.
    # Revoke ALL tokens for this user_email — this is actually more secure
    # (logs out ALL sessions for the user, not just this one).
    count = _revoke_all_user_tokens(token)
    return {
        "revoked": True,
        "tokens_revoked": count,
        "message": f"All tokens for {token} have been revoked. Please log in again.",
    }


@router.post("/rotate")
async def rotate_token(token: str = Depends(verify_token_dep)):
    """Rotate the current token (P1-4 fix).

    Issues a new token and revokes ALL old tokens for the user. This is
    the standard token rotation flow — call this periodically to limit
    the window of opportunity for a compromised token.

    Returns the new token. The old token(s) are immediately invalid.
    """
    from maestro_personal_shell.api import _revoke_all_user_tokens, _create_user_token
    # Revoke all existing tokens for this user
    old_count = _revoke_all_user_tokens(token)
    # Issue a new token
    new_token = _create_user_token(token)
    return {
        "token": new_token,
        "user_email": token,
        "old_tokens_revoked": old_count,
        "message": "Token rotated. Use the new token for subsequent requests.",
    }


# ---------------------------------------------------------------------------
# Issue 6: Push token registration
# ---------------------------------------------------------------------------

from pydantic import BaseModel


class PushTokenRequest(BaseModel):
    push_token: str


@router.post("/push-token")
async def register_push_token(req: PushTokenRequest, token: str = Depends(verify_token_dep)):
    """Store the user's Expo push token for sending notifications.

    Issue 6: Called by the mobile app on login to register the device
    for push notifications. The notification_scheduler uses these tokens
    to send stale-commitment alerts.
    """
    from maestro_personal_shell.db_util import get_db_conn
    from datetime import datetime, timezone
    import os

    db_path = os.environ.get("MAESTRO_PERSONAL_DB", "personal.db")
    db = get_db_conn(db_path)
    try:
        db.execute(
            "INSERT OR REPLACE INTO push_tokens (user_email, expo_token, created_at, active) "
            "VALUES (?, ?, ?, 1)",
            (token, req.push_token, datetime.now(timezone.utc).isoformat()),
        )
        db.commit()
    finally:
        db.close()

    return {"registered": True, "user_email": token}
