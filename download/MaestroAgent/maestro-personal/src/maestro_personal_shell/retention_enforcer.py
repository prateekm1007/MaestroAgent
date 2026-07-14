"""
retention_enforcer.py — Automated data retention TTL enforcement.

Step 15: Runs daily via API lifespan. Purges data that exceeds its
retention TTL, ensuring the system doesn't retain user data longer
than necessary (GDPR/CCPA data minimization).

TTLs (configurable via env vars):
  - Auth tokens: 30 days (expired tokens cleaned up)
  - Audit log entries: 90 days (compliance standard)
  - Pending drafts: 30 days (stale drafts that were never resolved)
  - Notified_stale entries: 30 days (dedup table cleanup)
  - Inactive push tokens: 90 days (devices that haven't connected in 90 days)
  - Signals: NO TTL (user's core data — kept until account deletion)

Usage:
  python -m maestro_personal_shell.retention_enforcer --once  # Run once
  python -m maestro_personal_shell.retention_enforcer --loop  # Background loop
"""
from __future__ import annotations

import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# TTL configuration (days) — overridable via env vars
TTL_AUTH_TOKENS_DAYS = int(os.environ.get("MAESTRO_TTL_AUTH_TOKENS", "30"))
TTL_AUDIT_LOG_DAYS = int(os.environ.get("MAESTRO_TTL_AUDIT_LOG", "90"))
TTL_PENDING_DRAFTS_DAYS = int(os.environ.get("MAESTRO_TTL_PENDING_DRAFTS", "30"))
TTL_NOTIFIED_STALE_DAYS = int(os.environ.get("MAESTRO_TTL_NOTIFIED_STALE", "30"))
TTL_INACTIVE_PUSH_TOKENS_DAYS = int(os.environ.get("MAESTRO_TTL_INACTIVE_PUSH", "90"))


async def enforce_retention(db_path: str | None = None) -> dict:
    """Run one retention enforcement cycle.

    Purges data that exceeds its TTL. Returns a summary of what was deleted.
    """
    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path

    path = db_path or default_sqlite_path()
    db = get_db_conn(path)
    now = datetime.now(timezone.utc).isoformat()

    summary = {
        "auth_tokens_purged": 0,
        "audit_log_purged": 0,
        "pending_drafts_purged": 0,
        "notified_stale_purged": 0,
        "inactive_push_tokens_purged": 0,
        "timestamp": now,
    }

    # 1. Purge expired auth tokens (older than TTL_AUTH_TOKENS_DAYS)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=TTL_AUTH_TOKENS_DAYS)).isoformat()
    try:
        cursor = db.execute(
            "DELETE FROM auth_tokens WHERE created_at < ? AND active = 0",
            (cutoff,),
        )
        summary["auth_tokens_purged"] = cursor.rowcount
    except Exception as e:
        logger.debug("auth_tokens purge skipped: %s", e)

    # 2. Purge old audit log entries (older than TTL_AUDIT_LOG_DAYS)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=TTL_AUDIT_LOG_DAYS)).isoformat()
    try:
        cursor = db.execute(
            "DELETE FROM connector_audit WHERE timestamp < ?",
            (cutoff,),
        )
        summary["audit_log_purged"] = cursor.rowcount
    except Exception as e:
        logger.debug("connector_audit purge skipped: %s", e)

    # 3. Purge stale pending drafts (older than TTL_PENDING_DRAFTS_DAYS)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=TTL_PENDING_DRAFTS_DAYS)).isoformat()
    try:
        cursor = db.execute(
            "DELETE FROM drafts WHERE status = 'pending' AND created_at < ?",
            (cutoff,),
        )
        summary["pending_drafts_purged"] = cursor.rowcount
    except Exception as e:
        logger.debug("drafts purge skipped: %s", e)

    # 4. Purge old notified_stale entries (dedup table cleanup)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=TTL_NOTIFIED_STALE_DAYS)).isoformat()
    try:
        cursor = db.execute(
            "DELETE FROM notified_stale WHERE notified_at < ?",
            (cutoff,),
        )
        summary["notified_stale_purged"] = cursor.rowcount
    except Exception as e:
        logger.debug("notified_stale purge skipped: %s", e)

    # 5. Purge inactive push tokens (not seen in TTL_INACTIVE_PUSH_TOKENS_DAYS)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=TTL_INACTIVE_PUSH_TOKENS_DAYS)).isoformat()
    try:
        cursor = db.execute(
            "DELETE FROM push_tokens WHERE active = 0 AND created_at < ?",
            (cutoff,),
        )
        summary["inactive_push_tokens_purged"] = cursor.rowcount
    except Exception as e:
        logger.debug("push_tokens purge skipped: %s", e)

    db.commit()
    db.close()

    total_purged = sum(v for k, v in summary.items() if isinstance(v, int))
    if total_purged > 0:
        logger.info("Retention enforcement: purged %d records: %s", total_purged, summary)
    else:
        logger.debug("Retention enforcement: nothing to purge")

    return summary


async def retention_loop(interval_seconds: int = 86400):
    """Background loop — runs daily (default 86400s = 24 hours)."""
    logger.info("Retention enforcer loop started (interval=%ds)", interval_seconds)
    while True:
        try:
            await enforce_retention()
        except Exception as e:
            logger.error("Retention enforcement crashed: %s", e)
        await asyncio.sleep(interval_seconds)


def get_retention_policy() -> dict:
    """Return the current retention TTL configuration."""
    return {
        "auth_tokens_days": TTL_AUTH_TOKENS_DAYS,
        "audit_log_days": TTL_AUDIT_LOG_DAYS,
        "pending_drafts_days": TTL_PENDING_DRAFTS_DAYS,
        "notified_stale_days": TTL_NOTIFIED_STALE_DAYS,
        "inactive_push_tokens_days": TTL_INACTIVE_PUSH_TOKENS_DAYS,
        "signals": "no TTL — kept until account deletion (user's core data)",
        "oauth_tokens": "no TTL — kept until connector disconnected or account deletion",
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()

    if args.once:
        import json
        result = asyncio.run(enforce_retention())
        print(json.dumps(result, indent=2))
    elif args.loop:
        asyncio.run(retention_loop())
    else:
        print("Use --once or --loop")
