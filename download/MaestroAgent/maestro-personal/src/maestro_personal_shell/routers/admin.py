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

import os

from fastapi import APIRouter

router = APIRouter(tags=["admin"])


@router.get("/api/health")
async def health():
    """Health check — no auth required. Includes build canary for deploy verification."""
    # Use MAESTRO_BUILD_COMMIT env var (set in Dockerfile at build time).
    # Do NOT call subprocess git — git is not installed in python:3.12-slim
    # and the subprocess call causes FileNotFoundError → 500 error →
    # Railway healthcheck failure → deploy stuck.
    return {
        "status": "ok",
        "service": "maestro-personal",
        "version": "11.0.0-session10-final",
        "commit": os.environ.get("MAESTRO_BUILD_COMMIT", "unknown"),
        "build_time": os.environ.get("MAESTRO_BUILD_TIME", "unknown"),
        "docs_disabled": True,
        "security_headers": True,
    }
