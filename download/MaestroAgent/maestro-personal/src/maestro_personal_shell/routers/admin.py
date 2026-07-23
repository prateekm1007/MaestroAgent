"""Admin router — health check.

Single source of truth for build identity. Version is read from
MAESTRO_VERSION env var (set in Dockerfile at build time).
No hardcoded version strings. No git calls. No pyproject import.

S0 ROBUST COMMIT REPORTING (anti-entropy fix):
The commit SHA is sourced from Railway's native RAILWAY_GIT_COMMIT_SHA
env var FIRST (platform-sourced, always accurate), falling back to
MAESTRO_BUILD_COMMIT (set via variableUpsert), then "unknown".
This retires the fragile static-env-var stopgap that drifted on every
deploy because Railway's native deploy doesn't inject BUILD_COMMIT as
a Docker build arg.
"""
from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["admin"])

# Read version from build-time env var. This is the ONLY source of truth.
# Dockerfile sets: ENV MAESTRO_VERSION=12.0.0-audit-ready
_VERSION = os.environ.get("MAESTRO_VERSION", "0.0.0-unknown")

# S0 ROBUST COMMIT REPORTING:
# 1. RAILWAY_GIT_COMMIT_SHA — Railway's native platform-sourced SHA (most reliable)
# 2. MAESTRO_BUILD_COMMIT — fallback (set via variableUpsert or Docker build arg)
# 3. "unknown" — last resort
_COMMIT = (
    os.environ.get("RAILWAY_GIT_COMMIT_SHA")
    or os.environ.get("MAESTRO_BUILD_COMMIT")
    or "unknown"
)
_BUILT = os.environ.get("MAESTRO_BUILD_TIME", "unknown")


@router.get("/api/health")
async def health():
    """Health check — no auth required. Returns deterministic build identity.

    Uses JSONResponse with Cache-Control: no-store to prevent Railway's
    edge proxy from caching the response and serving stale version strings.
    """
    return JSONResponse(
        content={
            "status": "ok",
            "service": "maestro-personal",
            "version": _VERSION,
            "commit": _COMMIT,
            "docs_disabled": True,
            "security_headers": True,
            "build_time": _BUILT,
        },
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        },
    )
