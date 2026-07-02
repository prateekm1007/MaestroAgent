"""
Permission middleware and FastAPI dependencies.

Usage in routes:
    from maestro_auth.permissions import require_permission, current_user, require_admin

    @router.get("/api/oem/dashboard")
    async def dashboard(user: dict = Depends(require_permission(Permissions.OEM_READ))):
        ...

    @router.post("/api/auth/users")
    async def create_user(user: dict = Depends(require_admin)):
        ...
"""

from __future__ import annotations

import logging
import os
import hmac
from typing import Any, Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from maestro_auth.models import AuthStore, Permissions, ALL_PERMISSIONS
from maestro_auth.sessions import SessionManager, SESSION_COOKIE, REFRESH_COOKIE, CSRF_COOKIE

logger = logging.getLogger(__name__)


# ─── Global auth state (initialized by main.py) ───

_auth_store: AuthStore | None = None
_session_manager: SessionManager | None = None


def init_auth(store: AuthStore) -> None:
    """Initialize the global auth state. Called once at app startup."""
    global _auth_store, _session_manager
    _auth_store = store
    _session_manager = SessionManager(store)


def get_auth_store() -> AuthStore:
    if _auth_store is None:
        raise RuntimeError("Auth not initialized. Call init_auth() at startup.")
    return _auth_store


def get_session_manager() -> SessionManager:
    if _session_manager is None:
        raise RuntimeError("Auth not initialized. Call init_auth() at startup.")
    return _session_manager


def is_auth_enabled() -> bool:
    """Auth is enabled by default in non-local environments.

    Round 61 fix: this function previously had its own logic that defaulted
    to False — separate from AuthConfig.from_env() in config.py. The RBAC
    gate calls THIS function, not AuthConfig. So the config.py fix was dead
    code. Now this function delegates to AuthConfig.from_env().enabled —
    one source of truth, no dual-path drift.

    Auth is enabled if:
    1. MAESTRO_AUTH_ENABLED=true (explicit), OR
    2. Any OIDC/SAML/SCIM provider is configured, OR
    3. MAESTRO_LOCAL_DEV is NOT set (defaults to ON)

    Auth is disabled ONLY if:
    - MAESTRO_LOCAL_DEV=true, OR
    - MAESTRO_AUTH_ENABLED=false (explicit)
    """
    from maestro_auth.config import AuthConfig
    return AuthConfig.from_env().enabled


# ─── Public paths (no auth required) ───

PUBLIC_PATHS = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/oidc/{provider}/login",
    "/api/auth/oidc/{provider}/callback",
    "/api/auth/saml/{provider}/login",
    "/api/auth/saml/{provider}/acs",
    "/api/auth/saml/metadata",
    "/api/auth/scim/v2/Users",  # SCIM uses its own bearer token
    "/docs",
    "/openapi.json",
    "/redoc",
}


def is_public_path(path: str) -> bool:
    """Check if a path is public (no auth required)."""
    # Exact matches
    if path in PUBLIC_PATHS:
        return True
    # Static assets
    if path.startswith("/static/") or path.endswith((".css", ".js", ".svg", ".png", ".ico")):
        return True
    # Health
    if path == "/api/health":
        return True
    # OIDC callback paths
    if path.startswith("/api/auth/oidc/") and (path.endswith("/login") or path.endswith("/callback")):
        return True
    # SAML paths
    if path.startswith("/api/auth/saml/"):
        return True
    # SCIM paths (use bearer token via middleware)
    if path.startswith("/scim/v2/"):
        return True
    return False


# ─── CSRF protection ───

def verify_csrf(request: Request) -> bool:
    """Verify the CSRF token using double-submit cookie pattern.

    For state-changing requests (POST/PUT/PATCH/DELETE), the client must send:
      1. The maestro_csrf cookie (set by the server on login)
      2. The X-CSRF-Token header matching the cookie
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True

    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get("X-CSRF-Token")

    if not cookie_token or not header_token:
        return False

    return hmac.compare_digest(cookie_token, header_token)


# ─── FastAPI dependencies ───

def current_user(request: Request) -> dict[str, Any] | None:
    """Get the current user from the session cookie. Returns None if not authed.

    If the session is expired but a valid refresh token exists, attempts a
    silent refresh (rotates the refresh token).
    """
    if not is_auth_enabled():
        # Auth disabled — return a default admin user
        store = get_auth_store()
        admin = store.get_user_by_email("admin@local") or store.create_user(
            email="admin@local", display_name="Local Admin", is_admin=True,
        )
        if not store.get_user_roles(admin["id"]):
            store.assign_role(admin["id"], "admin")
        return {"user": admin, "session": None}

    session_id = request.cookies.get(SESSION_COOKIE)
    result = get_session_manager().validate_session(session_id) if session_id else None

    if result:
        return result

    # Try silent refresh
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if refresh_token:
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")
        new_session = get_session_manager().refresh(refresh_token, ip_address=client_ip)
        if new_session:
            session = get_session_manager().validate_session(new_session["session_id"])
            if session:
                # Store the new cookies on the request state so middleware can set them
                request.state._new_session = new_session
                return session

    return None


def require_user(request: Request) -> dict[str, Any]:
    """Require an authenticated user. Raises 401 if not authed."""
    result = current_user(request)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": 'Bearer realm="maestro"'},
        )
    # Verify CSRF for state-changing requests
    if not verify_csrf(request):
        store = get_auth_store()
        store.audit(
            event_type="permission_denied",
            user_id=result["user"]["id"],
            email=result["user"]["email"],
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent", ""),
            resource=str(request.url.path),
            detail={"reason": "csrf_failed", "method": request.method},
            success=False,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token invalid")
    return result


def require_permission(permission: str) -> Callable:
    """Require a specific permission. Returns a FastAPI dependency."""
    def dependency(request: Request) -> dict[str, Any]:
        result = require_user(request)
        user = result["user"]
        store = get_auth_store()

        if user.get("is_admin"):
            return result

        if not store.has_permission(user["id"], permission):
            store.audit(
                event_type="permission_denied",
                user_id=user["id"],
                email=user["email"],
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent", ""),
                resource=str(request.url.path),
                detail={"reason": "missing_permission", "required": permission},
                success=False,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: requires {permission}",
            )
        return result
    return dependency


def require_admin(request: Request) -> dict[str, Any]:
    """Require an admin user."""
    result = require_user(request)
    if not result["user"].get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return result


def require_any_permission(*permissions: str) -> Callable:
    """Require any of the given permissions."""
    def dependency(request: Request) -> dict[str, Any]:
        result = require_user(request)
        user = result["user"]
        store = get_auth_store()

        if user.get("is_admin"):
            return result

        user_perms = store.get_user_permissions(user["id"])
        if not any(p in user_perms for p in permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: requires one of {permissions}",
            )
        return result
    return dependency


# ─── Bearer token auth (for API clients + SCIM) ───

_bearer_scheme = HTTPBearer(auto_error=False)


async def bearer_user(request: Request, credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme)) -> dict[str, Any] | None:
    """Authenticate via Bearer token (API key or SCIM token).

    For SCIM endpoints, the token must match MAESTRO_SCIM_TOKEN.
    For other endpoints, the token must be a valid session ID.
    """
    if not credentials:
        return None
    token = credentials.credentials

    # SCIM token check
    if request.url.path.startswith("/scim/"):
        from maestro_auth.scim import SCIMManager
        if SCIMManager.is_enabled() and SCIMManager.verify_token(token):
            # Return a system user for SCIM operations
            store = get_auth_store()
            scim_user = store.get_user_by_email("scim@system") or store.create_user(
                email="scim@system", display_name="SCIM System", is_admin=True,
            )
            return {"user": scim_user, "session": None}

    # Session token check (for API clients that received a session cookie)
    result = get_session_manager().validate_session(token)
    if result:
        return result

    return None
