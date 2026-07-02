"""
API routes for OAuth flows and historical imports.

Endpoints:
  GET  /api/oauth/status                          — connection status for all 5 providers
  GET  /api/oauth/{provider}/start                — get authorization URL
  GET  /api/oauth/callback                        — OAuth redirect target
  POST /api/oauth/{provider}/disconnect           — revoke tokens

  GET  /api/imports                               — list all import jobs
  POST /api/imports/start                         — start a new import job
  GET  /api/imports/{job_id}                      — get job progress
  POST /api/imports/{job_id}/cancel               — cancel a running job
  GET  /api/imports/{job_id}/checkpoints          — list checkpoints for a job
  WS   /api/imports/{job_id}/stream               — live progress stream

All endpoints are async. The WebSocket streams JSON snapshots at ~4 Hz.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from maestro_api.oem_state import import_state, oem_state
from maestro_oem.historical_engine import parse_since
from maestro_oem.oauth_manager import OAuthError
from maestro_auth.permissions import is_auth_enabled, require_user, require_admin

# Round 65 C2 fix: ONE canonical provider list, used everywhere.
# No more dual whitelists that drift.
SUPPORTED_IMPORT_PROVIDERS = ("github", "jira", "slack", "confluence", "gmail", "customer")

logger = logging.getLogger(__name__)

# Round 77 C3 fix: uniform auth enforcement on the imports router.
# Previously this router had NO auth dependency — security depended on
# per-route checks, which were missing on admin endpoints (C2) and broken
# in oauth_callback (C1). Now all routes require authentication when auth
# is enabled. Admin endpoints additionally require admin role.
#
# NOTE: using a named function with Request type annotation instead of a
# lambda — FastAPI's dependency resolution needs the type annotation to
# know to inject the Request object. A bare lambda `lambda r: ...` causes
# FastAPI to treat `r` as a query parameter (422 error).
def _require_user_if_auth_enabled(request: Request) -> None:
    """Router-level auth dependency: require authentication when auth is enabled."""
    if is_auth_enabled():
        require_user(request)  # Raises 401 if not authed


router = APIRouter(dependencies=[Depends(_require_user_if_auth_enabled)])


# ─── Helpers ───

def _ensure_initialized() -> None:
    import_state.ensure_initialized()


# ─── OAuth status ───

@router.get("/api/oauth/status")
async def oauth_status() -> dict[str, Any]:
    """Connection status for all 5 providers."""
    _ensure_initialized()
    assert import_state.oauth is not None
    return {"providers": import_state.oauth.status()}


# ─── Start OAuth flow ───

@router.get("/api/oauth/{provider}/start")
async def oauth_start(provider: str) -> dict[str, Any]:
    """Get the authorization URL for a provider. UI should redirect the user here.

    Supports: github, jira, slack, confluence, gmail, customer (Salesforce).
    """
    _ensure_initialized()
    assert import_state.connections is not None
    # Round 65 C2 fix: use the canonical SUPPORTED_IMPORT_PROVIDERS list
    # (defined at the bottom of this file). No more dual whitelists.
    if provider not in SUPPORTED_IMPORT_PROVIDERS:
        raise HTTPException(404, f"Unknown provider: {provider}")
    try:
        url, state = import_state.connections.get_authorization_url(provider)
    except OAuthError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        # OAuth not configured (env vars missing)
        raise HTTPException(400, str(e))
    return {"provider": provider, "auth_url": url, "state": state}


# ─── OAuth callback ───

@router.get("/api/oauth/callback")
async def oauth_callback(
    request: Request,
    code: str | None = Query(None),
    state: str | None = Query(None),
    provider: str | None = Query(None),
    error: str | None = Query(None),
) -> dict[str, Any]:
    """OAuth redirect target.

    The provider passes back `code`, `state`, and (for Atlassian) the
    provider type. We exchange the code for tokens and immediately
    trigger a historical import for the newly-connected provider.

    Round 77 C1 fix: the prior version called `require_user(request)` but
    `request` was not a parameter — a NameError fired every time auth was
    enabled, swallowed by `except Exception: pass`, so org_id silently
    defaulted to "default". Every authenticated OAuth callback routed
    imports to the default tenant — a cross-tenant data leak. Now the
    function accepts `request: Request` and FAILS CLOSED when auth is
    enabled but org_id can't be resolved (no silent default in production).
    """
    _ensure_initialized()
    assert import_state.connections is not None

    if error:
        return {"ok": False, "error": error, "provider": provider}

    # Round 57 C1 fix: if provider is not in query params, parse it from the
    # state token. Most OAuth providers (GitHub, Google, Slack) do not include
    # the provider name in their redirect — they only return code and state.
    if not provider and state:
        parts = state.split(":", 3)
        if len(parts) >= 1:
            provider = parts[0]

    if not code or not state or not provider:
        raise HTTPException(400, "Missing code, state, or provider")

    # Round 77 C1 fix: extract org_id from the authenticated session.
    # FAIL CLOSED: if auth is enabled but org_id can't be resolved, reject
    # the callback rather than silently defaulting to "default" (which would
    # route the import to the wrong tenant). Principle 6: fail closed, not
    # silent. Principle 7: test the real scoped object graph.
    org_id = "default"
    if is_auth_enabled():
        user_info = require_user(request)  # Raises 401 if not authed
        org_id = user_info.get("org_id") if user_info else None
        if not org_id:
            # Fail closed: authenticated user with no org_id → reject.
            # This prevents cross-tenant contamination via default fallback.
            logger.error(
                "OAuth callback for provider %s: authenticated user has no org_id — "
                "rejecting to prevent cross-tenant data routing", provider,
            )
            raise HTTPException(
                403,
                "Authenticated user has no org_id — OAuth callback cannot "
                "determine which tenant to route the import to. Contact admin.",
            )
    result = await import_state.connections.complete_connection(provider, code, state, org_id=org_id)
    return {"ok": True, **result}


# ─── Disconnect ───

@router.post("/api/oauth/{provider}/disconnect")
async def oauth_disconnect(provider: str) -> dict[str, Any]:
    """Revoke tokens for a provider and mark as disconnected."""
    _ensure_initialized()
    assert import_state.connections is not None
    import_state.connections.disconnect(provider)
    return {"ok": True, "provider": provider, "connected": False}


# ─── List import jobs ───

@router.get("/api/imports")
async def list_imports() -> dict[str, Any]:
    """List all import jobs (most recent first)."""
    _ensure_initialized()
    assert import_state.engine is not None
    jobs = import_state.engine.list_jobs()
    # Merge with persisted jobs from the store
    assert import_state.store is not None
    persisted = import_state.store.list_jobs()
    seen = {j["job_id"] for j in jobs}
    for p in persisted:
        if p["job_id"] not in seen:
            jobs.append(p)
    return {"jobs": jobs}


# ─── Start an import ───

class StartImportRequest(BaseModel):
    providers: list[str] = Field(..., min_length=1)
    since: str | None = Field("5y", description="5y | 2y | 1y | 6mo | 30d | ISO date | None")


@router.post("/api/imports/start")
async def start_import(req: StartImportRequest) -> dict[str, Any]:
    """Start a new historical import job. Returns immediately with a job_id."""
    _ensure_initialized()
    assert import_state.engine is not None
    assert import_state.connections is not None

    # Validate providers
    for p in req.providers:
        if p not in SUPPORTED_IMPORT_PROVIDERS:
            raise HTTPException(400, f"Unknown provider: {p}")
        if not import_state.connections.is_connected(p):
            raise HTTPException(400, f"Provider {p} is not connected")

    # Validate since
    if req.since and req.since.lower() not in ("none", "all"):
        parsed = parse_since(req.since)
        if parsed is None:
            raise HTTPException(400, f"Invalid 'since' value: {req.since}")

    since = None if (req.since and req.since.lower() in ("none", "all")) else req.since

    try:
        job_id = await import_state.engine.start_import(
            providers=req.providers,
            since=since,
        )
    except Exception as e:
        logger.exception("Failed to start import")
        raise HTTPException(500, str(e))

    return {"job_id": job_id, "providers": req.providers, "since": since}


# ─── Get job progress ───

@router.get("/api/imports/{job_id}")
async def get_import(job_id: str) -> dict[str, Any]:
    """Get current progress for an import job."""
    _ensure_initialized()
    assert import_state.engine is not None
    job = import_state.engine.get_job(job_id)
    if not job:
        # Check the persisted store
        assert import_state.store is not None
        persisted = import_state.store.get_job(job_id)
        if not persisted:
            raise HTTPException(404, "Job not found")
        persisted["job_id"] = persisted["job_id"]
        return persisted
    return job


# ─── Cancel a job ───

@router.post("/api/imports/{job_id}/cancel")
async def cancel_import(job_id: str) -> dict[str, Any]:
    """Cancel a running import job."""
    _ensure_initialized()
    assert import_state.engine is not None
    import_state.engine.cancel_job(job_id)
    return {"ok": True, "job_id": job_id, "status": "cancelled"}


# ─── List checkpoints ───

@router.get("/api/imports/{job_id}/checkpoints")
async def list_checkpoints(job_id: str) -> dict[str, Any]:
    """List all checkpoints for a job (per-provider, per-resource)."""
    _ensure_initialized()
    assert import_state.store is not None
    checkpoints = import_state.store.list_checkpoints(job_id)
    return {"job_id": job_id, "checkpoints": checkpoints}


# ─── Live OEM snapshot (for "patterns discovered / laws emerging" UI) ───

@router.get("/api/oem/snapshot")
async def oem_snapshot() -> dict[str, Any]:
    """Get the current OEM state snapshot (live, reflects in-flight imports)."""
    return oem_state.snapshot()


# ─── WebSocket for live progress ───

@router.websocket("/api/imports/{job_id}/stream")
async def import_progress_ws(websocket: WebSocket, job_id: str) -> None:
    """Stream live progress updates for an import job.

    Client receives JSON snapshots at ~4 Hz until the job completes or
    the client disconnects.

    Round 70 RESIDUAL-9: Added authentication check before accept.
    Same pattern as /ws/ambient/pulse — token from query param or header.
    """
    # Auth check — same pattern as /ws/ambient/pulse
    from maestro_auth.permissions import is_auth_enabled
    if is_auth_enabled():
        token = (
            websocket.query_params.get("token")
            or websocket.headers.get("Authorization", "").replace("Bearer ", "")
        )
        if not token:
            await websocket.close(code=4401, reason="Authentication required")
            return
        try:
            from maestro_auth.sessions import SessionManager
            from maestro_auth.models import AuthStore
            import os as _os
            _auth_db = _os.environ.get("MAESTRO_AUTH_DB", "auth.db")
            _store = AuthStore(_auth_db)
            _sm = SessionManager(_store)
            user = _sm.validate_session(token)
            if not user:
                await websocket.close(code=4401, reason="Invalid token")
                return
        except Exception:
            await websocket.close(code=4401, reason="Authentication failed")
            return

    await websocket.accept()
    _ensure_initialized()
    assert import_state.tracker is not None

    # Use a queue to bridge sync callbacks → async WS send
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def callback(snapshot: dict[str, Any]) -> None:
        try:
            queue.put_nowait(snapshot)
        except asyncio.QueueFull:
            pass  # Drop if backed up

    import_state.tracker.subscribe(job_id, callback)

    try:
        # Send an initial snapshot
        job = import_state.tracker.get_job(job_id)
        if job:
            await websocket.send_json(job.to_dict())
        else:
            await websocket.send_json({"job_id": job_id, "status": "not_found"})

        while True:
            try:
                snapshot = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(snapshot)
                if snapshot.get("status") in ("completed", "failed", "cancelled"):
                    break
            except asyncio.TimeoutError:
                # Heartbeat
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WS error: %s", e)
    finally:
        import_state.tracker.unsubscribe(job_id, callback)
        try:
            await websocket.close()
        except Exception:
            pass


# ─── Enterprise OAuth Self-Service: Admin API ──────────────────────────────
# Allows admins to configure OAuth providers (GitHub, Jira, Slack, etc.)
# through the UI without setting environment variables. Client secrets
# are encrypted at rest using the existing KMS/EncryptionManager.
# ═══════════════════════════════════════════════════════════════════════════

# All supported providers
SUPPORTED_OAUTH_PROVIDERS = SUPPORTED_IMPORT_PROVIDERS  # Round 65: unified


@router.get("/api/oauth/admin/providers", dependencies=[Depends(require_admin)])
async def list_oauth_provider_configs() -> dict[str, Any]:
    """List all configured OAuth providers (without secrets).

    Returns provider name, client_id (not secret), scopes, and whether
    the provider is configured via DB or env vars.
    """
    from maestro_oem.oauth_config_store import get_oauth_config_store
    from maestro_oem.oauth_manager import _load_config, _DEFAULT_ENDPOINTS

    store = get_oauth_config_store()
    db_providers = {p["provider"]: p for p in store.list_providers()}

    result = []
    for provider in SUPPORTED_OAUTH_PROVIDERS:
        # Check DB
        db_config = db_providers.get(provider)
        # Check env
        import os as _os
        env_prefix = f"MAESTRO_OAUTH_{provider.upper()}_"
        env_client_id = _os.environ.get(f"{env_prefix}CLIENT_ID", "")
        has_env = bool(env_client_id)

        result.append({
            "provider": provider,
            "label": _provider_label(provider),
            "configured": bool(db_config) or has_env,
            "configured_via": "database" if db_config else ("env" if has_env else "none"),
            "client_id": db_config["client_id"] if db_config else env_client_id,
            "has_secret": db_config["has_secret"] if db_config else bool(_os.environ.get(f"{env_prefix}CLIENT_SECRET")),
            "scopes": db_config["scopes"] if db_config else _DEFAULT_ENDPOINTS.get(provider, {}).get("scopes", []),
            "redirect_uri": db_config["redirect_uri"] if db_config else "",
            "configured_at": db_config["configured_at"] if db_config else None,
            "endpoints": {
                "auth_url": _DEFAULT_ENDPOINTS.get(provider, {}).get("auth_url", ""),
                "token_url": _DEFAULT_ENDPOINTS.get(provider, {}).get("token_url", ""),
            },
        })

    return {"providers": result, "total": len(result)}


@router.post("/api/oauth/admin/providers/{provider}", dependencies=[Depends(require_admin)])
async def save_oauth_provider_config(
    provider: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Save OAuth provider configuration (Client ID + Secret).

    The client_secret is encrypted with AES-256-GCM before storage.
    It is NEVER stored in plain text. When the OAuth flow initiates,
    the secret is decrypted in memory, used for the token exchange,
    and immediately discarded.

    Payload: {
        client_id: str (required),
        client_secret: str (required),
        scopes?: list[str],
        redirect_uri?: str,
    }
    """
    if provider not in SUPPORTED_OAUTH_PROVIDERS:
        raise HTTPException(400, f"Unsupported provider: {provider}. Supported: {SUPPORTED_OAUTH_PROVIDERS}")

    client_id = payload.get("client_id", "").strip()
    client_secret = payload.get("client_secret", "").strip()

    if not client_id or not client_secret:
        raise HTTPException(400, "client_id and client_secret are required")

    from maestro_oem.oauth_config_store import get_oauth_config_store
    store = get_oauth_config_store()

    store.save_provider(
        provider=provider,
        client_id=client_id,
        client_secret=client_secret,
        scopes=payload.get("scopes"),
        redirect_uri=payload.get("redirect_uri", ""),
        configured_by=payload.get("configured_by", "admin"),
    )

    return {
        "ok": True,
        "provider": provider,
        "client_id": client_id,
        "secret_stored": "encrypted",
        "message": f"OAuth provider '{provider}' configured. Client secret encrypted at rest.",
    }


@router.delete("/api/oauth/admin/providers/{provider}", dependencies=[Depends(require_admin)])
async def delete_oauth_provider_config(provider: str) -> dict[str, Any]:
    """Disable an OAuth provider configuration (DB-stored).

    Does NOT remove environment variables — those persist for backward
    compatibility. Only removes the DB-stored configuration.
    """
    if provider not in SUPPORTED_OAUTH_PROVIDERS:
        raise HTTPException(400, f"Unsupported provider: {provider}")

    from maestro_oem.oauth_config_store import get_oauth_config_store
    store = get_oauth_config_store()

    deleted = store.delete_provider(provider)
    if not deleted:
        raise HTTPException(404, f"Provider '{provider}' not configured in DB")

    return {
        "ok": True,
        "provider": provider,
        "message": f"OAuth provider '{provider}' disabled. Env var fallback still active if set.",
    }


def _provider_label(provider: str) -> str:
    labels = {
        "github": "GitHub",
        "jira": "Jira (Atlassian)",
        "slack": "Slack",
        "confluence": "Confluence (Atlassian)",
        "gmail": "Gmail / Google Workspace",
        "customer": "Salesforce (Customer CRM)",
    }
    return labels.get(provider, provider.title())
