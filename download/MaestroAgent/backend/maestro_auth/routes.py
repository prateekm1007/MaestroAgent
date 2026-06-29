"""
Enterprise auth API routes.

Endpoints:
  POST /api/auth/login              — email/password login (with MFA support)
  POST /api/auth/mfa/verify         — verify MFA code after password login
  POST /api/auth/refresh            — rotate refresh token
  POST /api/auth/logout             — revoke session
  GET  /api/auth/me                 — current user info
  GET  /api/auth/sessions           — list active sessions

  GET  /api/auth/oidc/providers     — list configured OIDC providers
  GET  /api/auth/oidc/{p}/login     — start OIDC flow
  GET  /api/auth/oidc/{p}/callback  — OIDC callback

  GET  /api/auth/saml/providers     — list configured SAML providers
  GET  /api/auth/saml/{p}/login     — start SAML flow
  POST /api/auth/saml/{p}/acs       — SAML Assertion Consumer Service
  GET  /api/auth/saml/metadata      — SP metadata

  POST /api/auth/mfa/setup          — generate TOTP secret + QR code
  POST /api/auth/mfa/enable         — verify code and enable MFA
  POST /api/auth/mfa/disable        — disable MFA
  GET  /api/auth/mfa/backup-codes   — generate new backup codes

  GET  /api/auth/audit              — list audit events (admin only)
  GET  /api/auth/users              — list users (admin only)
  POST /api/auth/users/{id}/roles   — assign role (admin only)
  GET  /api/auth/roles              — list roles

  # SCIM 2.0 (Bearer token auth via MAESTRO_SCIM_TOKEN)
  GET    /scim/v2/Users
  POST   /scim/v2/Users
  GET    /scim/v2/Users/{id}
  PUT    /scim/v2/Users/{id}
  PATCH  /scim/v2/Users/{id}
  DELETE /scim/v2/Users/{id}
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse, PlainTextResponse
from pydantic import BaseModel, Field

from maestro_auth.models import (
    AuthStore, Permissions, ALL_PERMISSIONS, SYSTEM_ROLES,
    _totp_secret, totp_verify, generate_family_id,
)
from maestro_auth.sessions import (
    SessionManager, SESSION_COOKIE, REFRESH_COOKIE, CSRF_COOKIE,
    SESSION_TTL_SECONDS, REFRESH_TTL_SECONDS,
)
from maestro_auth.permissions import (
    get_auth_store, get_session_manager, is_auth_enabled,
    current_user, require_user, require_permission, require_admin,
    bearer_user, init_auth,
)
from maestro_auth.oidc import OIDCManager, OIDCError, PROVIDER_DEFAULTS as OIDC_PROVIDERS
from maestro_auth.saml import SAMLManager, SAMLError
from maestro_auth.scim import SCIMManager, SCIMError, SCIMNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter()
scim_router = APIRouter()


# ─── Helpers ───

def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")


def _is_secure(request: Request) -> bool:
    """Determine if the request is over HTTPS (for cookie Secure flag)."""
    if request.url.scheme == "https":
        return True
    if request.headers.get("x-forwarded-proto") == "https":
        return True
    return False


def _set_auth_cookies(response: Response, session_info: dict[str, Any], secure: bool) -> None:
    """Set session, refresh, and CSRF cookies on a response."""
    response.set_cookie(
        SESSION_COOKIE, session_info["session_id"],
        max_age=SESSION_TTL_SECONDS,
        httponly=True, secure=secure, samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE, session_info["refresh_token"],
        max_age=REFRESH_TTL_SECONDS,
        httponly=True, secure=secure, samesite="strict",
        path="/api/auth",
    )
    response.set_cookie(
        CSRF_COOKIE, session_info["csrf_token"],
        max_age=SESSION_TTL_SECONDS,
        httponly=False, secure=secure, samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clear all auth cookies."""
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    response.delete_cookie(CSRF_COOKIE, path="/")


# ─── Login ───

class LoginRequest(BaseModel):
    email: str
    password: str
    mfa_code: str | None = None


class MFAVerifyRequest(BaseModel):
    mfa_token: str  # Temporary token issued after password verification
    code: str


@router.post("/api/auth/login")
async def login(req: LoginRequest, request: Request) -> dict[str, Any]:
    """Email/password login with optional MFA."""
    store = get_auth_store()
    sm = get_session_manager()
    ip = _client_ip(request)
    ua = _user_agent(request)

    user = store.get_user_by_email(req.email)
    if not user or not user["password_hash"]:
        store.audit(event_type="login_failed", email=req.email, ip_address=ip,
                     user_agent=ua, detail={"reason": "unknown_user"}, success=False)
        raise HTTPException(401, "Invalid credentials")

    if not user["is_active"]:
        store.audit(event_type="login_failed", email=req.email, ip_address=ip,
                     user_agent=ua, detail={"reason": "inactive"}, success=False)
        raise HTTPException(403, "Account inactive")

    if not store.verify_password(user["id"], req.password):
        store.audit(event_type="login_failed", user_id=user["id"], email=req.email,
                     ip_address=ip, user_agent=ua, detail={"reason": "bad_password"}, success=False)
        raise HTTPException(401, "Invalid credentials")

    # MFA check
    if user["mfa_enabled"]:
        if not req.mfa_code:
            # Issue a temporary MFA challenge token
            import secrets as _s
            mfa_token = _s.token_urlsafe(32)
            # Store the MFA token (in a real system, use Redis with TTL)
            # For now, we accept the password + MFA in a single call
            store.audit(event_type="mfa_challenge", user_id=user["id"], email=req.email,
                         ip_address=ip, user_agent=ua, success=True)
            return {"mfa_required": True, "mfa_token": mfa_token}
        if not sm.verify_mfa(user["id"], req.mfa_code):
            raise HTTPException(401, "Invalid MFA code")

    # Issue session
    session_info = sm.login(user_id=user["id"], ip_address=ip, user_agent=ua)
    secure = _is_secure(request)
    response = JSONResponse({
        "ok": True,
        "user": {"id": user["id"], "email": user["email"], "display_name": user["display_name"],
                 "is_admin": bool(user["is_admin"]), "mfa_enabled": bool(user["mfa_enabled"])},
        "csrf_token": session_info["csrf_token"],
    })
    _set_auth_cookies(response, session_info, secure)
    return response


@router.post("/api/auth/refresh")
async def refresh_token(request: Request) -> dict[str, Any]:
    """Rotate the refresh token. Returns new CSRF token."""
    sm = get_session_manager()
    refresh_cookie = request.cookies.get(REFRESH_COOKIE)
    if not refresh_cookie:
        raise HTTPException(401, "No refresh token")

    ip = _client_ip(request)
    new_session = sm.refresh(refresh_cookie, ip_address=ip)
    if not new_session:
        _clear_auth_cookies(JSONResponse({}))
        raise HTTPException(401, "Invalid or expired refresh token")

    secure = _is_secure(request)
    response = JSONResponse({
        "ok": True,
        "csrf_token": new_session["csrf_token"],
    })
    _set_auth_cookies(response, new_session, secure)
    return response


@router.post("/api/auth/logout")
async def logout(request: Request) -> dict[str, Any]:
    """Revoke the current session."""
    sm = get_session_manager()
    session_id = request.cookies.get(SESSION_COOKIE)
    ip = _client_ip(request)
    sm.logout(session_id, ip_address=ip)
    response = JSONResponse({"ok": True})
    _clear_auth_cookies(response)
    return response


@router.get("/api/auth/me")
async def me(request: Request) -> dict[str, Any]:
    """Get the current user info."""
    result = current_user(request)
    if not result:
        raise HTTPException(401, "Not authenticated")
    user = result["user"]
    store = get_auth_store()
    roles = store.get_user_roles(user["id"])
    perms = store.get_user_permissions(user["id"])
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "is_admin": bool(user["is_admin"]),
        "mfa_enabled": bool(user["mfa_enabled"]),
        "roles": [{"name": r["name"], "description": r["description"]} for r in roles],
        "permissions": sorted(perms),
    }


@router.get("/api/auth/sessions")
async def list_sessions(request: Request) -> dict[str, Any]:
    """List the current user's active sessions."""
    result = require_user(request)
    store = get_auth_store()
    sessions = store.list_user_sessions(result["user"]["id"])
    return {
        "sessions": [
            {
                "id": s["id"],
                "created_at": s["created_at"],
                "last_used_at": s["last_used_at"],
                "ip_address": s["ip_address"],
                "user_agent": s["user_agent"],
                "is_current": s["id"] == request.cookies.get(SESSION_COOKIE),
                "revoked": bool(s["revoked_at"]),
            }
            for s in sessions if not s["revoked_at"]
        ]
    }


# ─── OIDC ───

@router.get("/api/auth/oidc/providers")
async def list_oidc_providers() -> dict[str, Any]:
    """List configured OIDC providers."""
    from maestro_auth.oidc import PROVIDER_DEFAULTS
    import os
    providers = []
    for p in PROVIDER_DEFAULTS:
        env_prefix = f"MAESTRO_OIDC_{p.upper()}_"
        configured = bool(os.environ.get(f"{env_prefix}CLIENT_ID")) and bool(os.environ.get(f"{env_prefix}CLIENT_SECRET"))
        providers.append({"provider": p, "configured": configured})
    return {"providers": providers}


@router.get("/api/auth/oidc/{provider}/login")
async def oidc_login(provider: str, request: Request, redirect_to: str = "/") -> RedirectResponse:
    """Start the OIDC flow for a provider."""
    if provider not in OIDC_PROVIDERS:
        raise HTTPException(404, f"Unknown OIDC provider: {provider}")
    base_url = str(request.base_url).rstrip("/")
    from maestro_auth.permissions import _auth_store
    store = get_auth_store()
    manager = OIDCManager(store, redirect_uri_base=base_url)
    if not manager.is_configured(provider):
        raise HTTPException(400, f"OIDC provider {provider} not configured. Set MAESTRO_OIDC_{provider.upper()}_CLIENT_ID and _CLIENT_SECRET.")
    try:
        url = manager.get_authorization_url(provider, redirect_to=redirect_to)
    except OIDCError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(url)


@router.get("/api/auth/oidc/{provider}/callback")
async def oidc_callback(
    provider: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    """OIDC callback — exchange code for tokens, JIT-provision user."""
    if error:
        return JSONResponse({"ok": False, "error": error}, status_code=400)

    if not code or not state:
        raise HTTPException(400, "Missing code or state")

    if provider not in OIDC_PROVIDERS:
        raise HTTPException(404, f"Unknown OIDC provider: {provider}")

    base_url = str(request.base_url).rstrip("/")
    store = get_auth_store()
    sm = get_session_manager()
    manager = OIDCManager(store, redirect_uri_base=base_url)

    try:
        user_info = manager.exchange_code(provider, code, state)
    except OIDCError as e:
        store.audit(event_type="login_failed", email=user_info.get("email") if "user_info" in dir() else None,
                     ip_address=_client_ip(request), user_agent=_user_agent(request),
                     detail={"reason": "oidc_failed", "provider": provider, "error": str(e)}, success=False)
        raise HTTPException(400, f"OIDC exchange failed: {e}")

    # JIT-provision user
    email = user_info.get("email") or f"{user_info['sub']}@{provider}.oidc"
    existing = store.get_user_by_external_id(user_info["sub"], f"oidc:{provider}") or store.get_user_by_email(email)
    if existing:
        store.update_user(
            existing["id"],
            display_name=user_info.get("name") or existing["display_name"],
            external_id=user_info["sub"],
            external_provider=f"oidc:{provider}",
        )
        user_record = existing
    else:
        user_record = store.create_user(
            email=email,
            display_name=user_info.get("name", ""),
            external_id=user_info["sub"],
            external_provider=f"oidc:{provider}",
        )
        # Assign default 'viewer' role
        store.assign_role(user_record["id"], "viewer")

    if not user_record["is_active"]:
        raise HTTPException(403, "Account inactive")

    # Issue session
    session_info = sm.login(user_id=user_record["id"], ip_address=_client_ip(request), user_agent=_user_agent(request))
    secure = _is_secure(request)
    response = JSONResponse({
        "ok": True,
        "user": {"id": user_record["id"], "email": user_record["email"], "display_name": user_record["display_name"]},
    })
    _set_auth_cookies(response, session_info, secure)
    return response


# ─── SAML ───

@router.get("/api/auth/saml/providers")
async def list_saml_providers() -> dict[str, Any]:
    """List configured SAML providers."""
    import os
    providers = []
    for p in ("azure", "okta", "google", "custom"):
        env_prefix = f"MAESTRO_SAML_{p.upper()}_"
        configured = bool(os.environ.get(f"{env_prefix}ENTITY_ID")) and bool(os.environ.get(f"{env_prefix}SSO_URL")) and bool(os.environ.get(f"{env_prefix}CERT"))
        providers.append({"provider": p, "configured": configured})
    return {"providers": providers}


@router.get("/api/auth/saml/{provider}/login")
async def saml_login(provider: str, request: Request, relay_state: str = "/") -> RedirectResponse:
    """Start the SAML flow."""
    base_url = str(request.base_url).rstrip("/")
    store = get_auth_store()
    manager = SAMLManager(store, sp_base_url=base_url)
    if not manager.is_configured(provider):
        raise HTTPException(400, f"SAML provider {provider} not configured")
    try:
        url = manager.get_redirect_url(provider, relay_state)
    except SAMLError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(url)


@router.post("/api/auth/saml/{provider}/acs")
async def saml_acs(provider: str, request: Request) -> Response:
    """SAML Assertion Consumer Service — process the SAMLResponse."""
    form = await request.form()
    saml_response = form.get("SAMLResponse")
    relay_state = form.get("RelayState", "/")
    if not saml_response:
        raise HTTPException(400, "Missing SAMLResponse")

    base_url = str(request.base_url).rstrip("/")
    store = get_auth_store()
    sm = get_session_manager()
    manager = SAMLManager(store, sp_base_url=base_url)

    try:
        user_info = manager.parse_response(provider, saml_response, relay_state)
    except SAMLError as e:
        raise HTTPException(400, f"SAML parsing failed: {e}")

    # JIT-provision
    email = user_info["email"]
    existing = store.get_user_by_external_id(user_info["sub"], f"saml:{provider}") or (store.get_user_by_email(email) if email else None)
    if existing:
        store.update_user(existing["id"], display_name=user_info.get("name") or existing["display_name"],
                          external_id=user_info["sub"], external_provider=f"saml:{provider}")
        user_record = existing
    else:
        user_record = store.create_user(
            email=email or f"{user_info['sub']}@{provider}.saml",
            display_name=user_info.get("name", ""),
            external_id=user_info["sub"],
            external_provider=f"saml:{provider}",
        )
        store.assign_role(user_record["id"], "viewer")

    session_info = sm.login(user_id=user_record["id"], ip_address=_client_ip(request), user_agent=_user_agent(request))
    secure = _is_secure(request)
    response = JSONResponse({"ok": True, "user": {"id": user_record["id"], "email": user_record["email"]}})
    _set_auth_cookies(response, session_info, secure)
    return response


@router.get("/api/auth/saml/metadata")
async def saml_metadata(request: Request) -> PlainTextResponse:
    """SAML SP metadata XML."""
    base_url = str(request.base_url).rstrip("/")
    entity_id = f"{base_url}/api/auth/saml/metadata"
    acs_url = f"{base_url}/api/auth/saml/custom/acs"
    metadata = f"""<?xml version="1.0" encoding="UTF-8"?>
<EntityDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata" entityID="{entity_id}">
  <SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</NameIDFormat>
    <AssertionConsumerService index="0" Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" Location="{acs_url}"/>
  </SPSSODescriptor>
</EntityDescriptor>"""
    return PlainTextResponse(metadata, media_type="application/xml")


# ─── MFA ───

class MFASetupRequest(BaseModel):
    pass


class MFAEnableRequest(BaseModel):
    secret: str
    code: str


@router.post("/api/auth/mfa/setup")
async def mfa_setup(request: Request) -> dict[str, Any]:
    """Generate a TOTP secret + QR code URL for MFA setup."""
    result = require_user(request)
    secret = _totp_secret()
    # Build otpauth URI
    email = result["user"]["email"]
    issuer = "Maestro"
    otpauth_uri = f"otpauth://totp/{issuer}:{email}?secret={secret}&issuer={issuer}&digits=6&period=30"
    return {"secret": secret, "otpauth_uri": otpauth_uri}


@router.post("/api/auth/mfa/enable")
async def mfa_enable(req: MFAEnableRequest, request: Request) -> dict[str, Any]:
    """Verify the code and enable MFA."""
    result = require_user(request)
    user = result["user"]
    if not totp_verify(req.secret, req.code):
        raise HTTPException(400, "Invalid MFA code")

    store = get_auth_store()
    store.enable_mfa(user["id"], req.secret)

    # Generate backup codes
    import secrets as _s
    backup_codes = [_s.token_urlsafe(8) for _ in range(10)]
    store.set_backup_codes(user["id"], backup_codes)

    store.audit(event_type="mfa_success", user_id=user["id"], email=user["email"],
                 detail={"action": "enabled"}, success=True)

    return {"ok": True, "backup_codes": backup_codes}


@router.post("/api/auth/mfa/disable")
async def mfa_disable(request: Request) -> dict[str, Any]:
    """Disable MFA."""
    result = require_user(request)
    store = get_auth_store()
    store.disable_mfa(result["user"]["id"])
    store.audit(event_type="mfa_success", user_id=result["user"]["id"], email=result["user"]["email"],
                 detail={"action": "disabled"}, success=True)
    return {"ok": True}


@router.post("/api/auth/mfa/backup-codes")
async def mfa_backup_codes(request: Request) -> dict[str, Any]:
    """Generate new backup codes (invalidates old ones)."""
    result = require_user(request)
    user = result["user"]
    if not user["mfa_enabled"]:
        raise HTTPException(400, "MFA not enabled")
    import secrets as _s
    backup_codes = [_s.token_urlsafe(8) for _ in range(10)]
    store = get_auth_store()
    store.set_backup_codes(user["id"], backup_codes)
    return {"backup_codes": backup_codes}


# ─── Admin: users, roles, audit ───

@router.get("/api/auth/users")
async def list_users(request: Request) -> dict[str, Any]:
    """List all users (admin only)."""
    require_admin(request)
    store = get_auth_store()
    users = store.list_users()
    return {
        "users": [
            {
                "id": u["id"],
                "email": u["email"],
                "display_name": u["display_name"],
                "is_active": bool(u["is_active"]),
                "is_admin": bool(u["is_admin"]),
                "mfa_enabled": bool(u["mfa_enabled"]),
                "external_provider": u["external_provider"],
                "last_login_at": u["last_login_at"],
                "roles": [r["name"] for r in store.get_user_roles(u["id"])],
            }
            for u in users
        ]
    }


class AssignRoleRequest(BaseModel):
    role: str
    scope_org_id: str | None = None


@router.post("/api/auth/users/{user_id}/roles")
async def assign_role(user_id: str, req: AssignRoleRequest, request: Request) -> dict[str, Any]:
    """Assign a role to a user (admin only)."""
    admin = require_admin(request)
    store = get_auth_store()
    if req.role not in SYSTEM_ROLES:
        raise HTTPException(400, f"Unknown role: {req.role}. Available: {list(SYSTEM_ROLES.keys())}")
    store.assign_role(user_id, req.role, req.scope_org_id)
    store.audit(event_type="role_change", user_id=user_id, resource=f"role:{req.role}",
                 detail={"action": "assign", "role": req.role, "assigned_by": admin["user"]["id"]}, success=True)
    return {"ok": True}


@router.delete("/api/auth/users/{user_id}/roles/{role}")
async def revoke_role(user_id: str, role: str, request: Request) -> dict[str, Any]:
    """Revoke a role from a user (admin only)."""
    admin = require_admin(request)
    store = get_auth_store()
    store.revoke_role(user_id, role)
    store.audit(event_type="role_change", user_id=user_id, resource=f"role:{role}",
                 detail={"action": "revoke", "role": role, "revoked_by": admin["user"]["id"]}, success=True)
    return {"ok": True}


@router.get("/api/auth/roles")
async def list_roles(request: Request) -> dict[str, Any]:
    """List all available roles."""
    store = get_auth_store()
    roles = store.list_roles()
    return {
        "roles": [
            {
                "name": r["name"],
                "description": r["description"],
                "is_system": bool(r["is_system"]),
            }
            for r in roles
        ]
    }


@router.get("/api/auth/audit")
async def list_audit(request: Request, limit: int = 100, event_type: str | None = None) -> dict[str, Any]:
    """List audit events (admin only)."""
    require_admin(request)
    store = get_auth_store()
    events = store.list_audit_events(limit=limit, event_type=event_type)
    return {"events": events, "count": len(events)}


# ─── SOC2 monitoring endpoints ───

@router.get("/api/auth/soc2/access-review")
async def soc2_access_review(request: Request) -> dict[str, Any]:
    """Generate an access review report for SOC2 auditors (admin only)."""
    require_admin(request)
    from maestro_auth.security import SOC2Monitor
    store = get_auth_store()
    monitor = SOC2Monitor(store)
    return monitor.access_review()


@router.get("/api/auth/soc2/change-log")
async def soc2_change_log(request: Request, limit: int = 100) -> dict[str, Any]:
    """Recent role/permission changes for SOC2 change management (admin only)."""
    require_admin(request)
    from maestro_auth.security import SOC2Monitor
    store = get_auth_store()
    monitor = SOC2Monitor(store)
    events = monitor.change_log(limit=limit)
    return {"events": events, "count": len(events)}


@router.get("/api/auth/soc2/sessions")
async def soc2_session_inventory(request: Request) -> dict[str, Any]:
    """Active session inventory for SOC2 monitoring (admin only)."""
    require_admin(request)
    from maestro_auth.security import SOC2Monitor
    store = get_auth_store()
    monitor = SOC2Monitor(store)
    return monitor.session_inventory()


@router.get("/api/auth/soc2/posture")
async def soc2_security_posture(request: Request) -> dict[str, Any]:
    """Security posture summary for SOC2 monitoring (admin only)."""
    require_admin(request)
    from maestro_auth.security import SOC2Monitor
    store = get_auth_store()
    monitor = SOC2Monitor(store)
    return monitor.security_posture()


@router.post("/api/auth/soc2/cleanup-sessions")
async def soc2_cleanup_sessions(request: Request) -> dict[str, Any]:
    """Manually trigger expired session cleanup (admin only)."""
    require_admin(request)
    from maestro_auth.security import SessionExpiryManager
    store = get_auth_store()
    manager = SessionExpiryManager(store)
    count = manager.cleanup_expired_sessions()
    store.audit(
        event_type="session_cleanup",
        user_id=request.state.user_data["user"]["id"] if hasattr(request.state, "user_data") else None,
        detail={"revoked_count": count},
        success=True,
    )
    return {"ok": True, "revoked_count": count}


# ─── SCIM 2.0 endpoints ───

def _scim_auth(request: Request) -> dict[str, Any]:
    """Authenticate SCIM requests via Bearer token."""
    from maestro_auth.scim import SCIMManager
    if not SCIMManager.is_enabled():
        raise HTTPException(503, "SCIM not enabled. Set MAESTRO_SCIM_TOKEN.")
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "SCIM requires Bearer token")
    token = auth[7:]
    if not SCIMManager.verify_token(token):
        raise HTTPException(401, "Invalid SCIM token")
    return {"ok": True}


@scim_router.get("/scim/v2/Users")
async def scim_list_users(request: Request, filter: str | None = None, startIndex: int = 1, count: int = 100) -> dict[str, Any]:
    _scim_auth(request)
    store = get_auth_store()
    manager = SCIMManager(store)
    return manager.list_users(filter_expr=filter, start_index=startIndex, count=count)


@scim_router.post("/scim/v2/Users")
async def scim_create_user(request: Request) -> dict[str, Any]:
    _scim_auth(request)
    store = get_auth_store()
    manager = SCIMManager(store)
    body = await request.json()
    try:
        return manager.create_user(body)
    except SCIMError as e:
        raise HTTPException(400, str(e))


@scim_router.get("/scim/v2/Users/{user_id}")
async def scim_get_user(user_id: str, request: Request) -> dict[str, Any]:
    _scim_auth(request)
    store = get_auth_store()
    manager = SCIMManager(store)
    try:
        return manager.get_user(user_id)
    except SCIMNotFoundError:
        raise HTTPException(404, "User not found")


@scim_router.put("/scim/v2/Users/{user_id}")
async def scim_put_user(user_id: str, request: Request) -> dict[str, Any]:
    _scim_auth(request)
    store = get_auth_store()
    manager = SCIMManager(store)
    body = await request.json()
    try:
        return manager.update_user(user_id, body)
    except SCIMNotFoundError:
        raise HTTPException(404, "User not found")


@scim_router.patch("/scim/v2/Users/{user_id}")
async def scim_patch_user(user_id: str, request: Request) -> dict[str, Any]:
    _scim_auth(request)
    store = get_auth_store()
    manager = SCIMManager(store)
    body = await request.json()
    try:
        return manager.patch_user(user_id, body)
    except SCIMNotFoundError:
        raise HTTPException(404, "User not found")


@scim_router.delete("/scim/v2/Users/{user_id}")
async def scim_delete_user(user_id: str, request: Request) -> Response:
    _scim_auth(request)
    store = get_auth_store()
    manager = SCIMManager(store)
    try:
        manager.delete_user(user_id)
    except SCIMNotFoundError:
        raise HTTPException(404, "User not found")
    return Response(status_code=204)
