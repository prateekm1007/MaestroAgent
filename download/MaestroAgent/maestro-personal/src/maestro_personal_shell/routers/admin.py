"""Admin router — health check.

First extract from the 5,300-line api.py god-module (Phase 8 engineering
quality). No behavior changes — same path, same response schema.

This first extract is intentionally minimal (just /api/health, no auth)
to prove the APIRouter pattern works end-to-end with zero risk. The
llm-status endpoint will move here once the auth router is extracted
(Step 3), because llm-status depends on verify_token which currently
lives in api.py.

Wiring: api.py calls `app.include_router(admin.router)` to mount these.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["admin"])


@router.get("/api/health")
async def health():
    """Health check — no auth required. Includes build canary for deploy verification."""
    # Try git first (works locally), fall back to build-time env var (works in Docker)
    commit = "unknown"
    import subprocess
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, timeout=2
        ).decode().strip()
    except Exception:
        commit = os.environ.get("MAESTRO_BUILD_COMMIT", "unknown")
    return {
        "status": "ok",
        "service": "maestro-personal",
        "version": "11.0.0-session10-final",
        "commit": commit,
        "docs_disabled": True,
        "security_headers": True,
        "build_time": os.environ.get("MAESTRO_BUILD_TIME", "unknown"),
    }
