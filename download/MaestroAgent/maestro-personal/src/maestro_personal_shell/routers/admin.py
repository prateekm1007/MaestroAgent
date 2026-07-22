"""Admin router — health check.

Single source of truth for build identity. Version is read from
MAESTRO_VERSION env var (set in Dockerfile at build time).
No hardcoded version strings. No git calls. No pyproject import.
"""
from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(tags=["admin"])

# Read version from build-time env var. This is the ONLY source of truth.
# Dockerfile sets: ENV MAESTRO_VERSION=12.0.0-audit-ready
_VERSION = os.environ.get("MAESTRO_VERSION", "0.0.0-unknown")
_COMMIT = os.environ.get("MAESTRO_BUILD_COMMIT", "unknown")
_BUILT = os.environ.get("MAESTRO_BUILD_TIME", "unknown")


@router.get("/api/health")
async def health():
    """Health check — no auth required. Returns deterministic build identity."""
    return {
        "status": "ok",
        "service": "maestro-personal",
        "version": _VERSION,
        "commit": _COMMIT,
        "build_time": _BUILT,
        "docs_disabled": True,
        "security_headers": True,
    }
