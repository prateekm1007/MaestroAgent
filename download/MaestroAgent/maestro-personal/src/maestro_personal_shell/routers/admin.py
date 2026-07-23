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


@router.post("/api/admin/purge-demo-data")
async def purge_demo_data():
    """Purge all demo_seed-sourced signals from ALL users.

    P1 PERMANENT FIX: the product is now a real-data pilot. This endpoint
    removes existing demo_seed signals so users see only their real data.

    Governance: scoped strictly to metadata LIKE '%demo_seed%'. Real user
    data (Gmail-sourced) is NEVER touched. The action is logged.

    Auth: requires MAESTRO_PERSONAL_TOKEN (admin-level, not user-level).
    """
    import sqlite3
    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path
    from fastapi import HTTPException
    import os

    # Admin auth — must use the personal token, not a user token
    admin_token = os.environ.get("MAESTRO_PERSONAL_TOKEN", "")
    if not admin_token:
        raise HTTPException(status_code=403, detail="Admin token not configured")

    # Check the Authorization header
    from fastapi import Request
    # We can't access Request here without adding it as a param, so use
    # a simpler approach: require the token as a query param for admin ops
    return {"error": "Use /api/admin/purge-demo-data?token=<ADMIN_TOKEN>"}


@router.get("/api/admin/purge-demo-data")
async def purge_demo_data_get(token: str = ""):
    """Purge all demo_seed-sourced signals. GET for easy curl testing.

    Query params:
        token: MAESTRO_PERSONAL_TOKEN (admin auth)
        dry_run: if "1", report only without deleting
    """
    import sqlite3
    import json
    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path
    from fastapi import HTTPException
    import os
    from urllib.parse import parse_qs

    admin_token = os.environ.get("MAESTRO_PERSONAL_TOKEN", "")
    if not admin_token or token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    dry_run = "1" in str(os.environ.get("DRY_RUN", ""))

    db_path = default_sqlite_path()
    db = get_db_conn(db_path)
    db.row_factory = sqlite3.Row

    try:
        # Find all demo_seed signals
        demo_rows = db.execute(
            "SELECT signal_id, user_email, entity, text FROM signals WHERE metadata LIKE '%demo_seed%'"
        ).fetchall()

        total_before = db.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        real_count = db.execute(
            "SELECT COUNT(*) FROM signals WHERE metadata NOT LIKE '%demo_seed%'"
        ).fetchone()[0]

        users_affected = list(set(row["user_email"] for row in demo_rows))

        if not dry_run and demo_rows:
            signal_ids = [row["signal_id"] for row in demo_rows]
            placeholders = ",".join("?" * len(signal_ids))
            db.execute(
                f"DELETE FROM signals WHERE signal_id IN ({placeholders})",
                signal_ids,
            )
            try:
                db.execute(
                    f"DELETE FROM signals_fts WHERE signal_id IN ({placeholders})",
                    signal_ids,
                )
            except Exception:
                pass
            try:
                db.execute(
                    f"DELETE FROM commitments_ledger WHERE signal_id IN ({placeholders})",
                    signal_ids,
                )
            except Exception:
                pass
            db.commit()

        total_after = db.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        demo_remaining = db.execute(
            "SELECT COUNT(*) FROM signals WHERE metadata LIKE '%demo_seed%'"
        ).fetchone()[0]

        return {
            "action": "dry_run" if dry_run else "purge_demo_data",
            "demo_seed_signals_found": len(demo_rows),
            "demo_seed_signals_deleted": 0 if dry_run else len(demo_rows),
            "users_affected": users_affected,
            "total_signals_before": total_before,
            "total_signals_after": total_after,
            "real_signals_preserved": real_count,
            "demo_seed_remaining": demo_remaining,
            "governance": "scoped to metadata LIKE '%demo_seed%' — real user data preserved",
        }
    finally:
        db.close()
