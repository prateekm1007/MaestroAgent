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

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from maestro_api.oem_state import import_state, oem_state
from maestro_oem.historical_engine import parse_since
from maestro_oem.oauth_manager import OAuthError

logger = logging.getLogger(__name__)

router = APIRouter()


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
    if provider not in ("github", "jira", "slack", "confluence", "gmail", "customer"):
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
    code: str | None = Query(None),
    state: str | None = Query(None),
    provider: str | None = Query(None),
    error: str | None = Query(None),
) -> dict[str, Any]:
    """OAuth redirect target.

    The provider passes back `code`, `state`, and (for Atlassian) the
    provider type. We exchange the code for tokens and immediately
    trigger a historical import for the newly-connected provider.
    """
    _ensure_initialized()
    assert import_state.connections is not None

    if error:
        return {"ok": False, "error": error, "provider": provider}

    if not code or not state or not provider:
        raise HTTPException(400, "Missing code, state, or provider")

    try:
        result = import_state.connections.complete_connection(provider, code, state)
    except OAuthError as e:
        return {"ok": False, "error": str(e), "provider": provider}

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
        if p not in ("github", "jira", "slack", "confluence", "gmail"):
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
    """
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
