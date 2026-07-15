"""
notification_scheduler.py — Background job for stale commitment alerts.

Issue 6: Runs hourly via API lifespan. Finds commitments that crossed
the 3-day stale threshold, sends push notifications via Expo, and
deduplicates via the notified_stale table.
"""
from __future__ import annotations

import asyncio
import logging
import os
import json
import urllib.request
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def _send_push_notification(push_token: str, title: str, body: str, data: dict) -> bool:
    """Send a push notification via Expo's push API."""
    if not push_token or not push_token.startswith("ExponentPushToken"):
        return False
    try:
        payload = json.dumps({
            "to": push_token,
            "title": title[:100],
            "body": body[:200],
            "data": data,
            "sound": "default",
            "priority": "high",
        }).encode()
        req = urllib.request.Request(
            EXPO_PUSH_URL,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        return result.get("data", {}).get("status") == "ok"
    except Exception as e:
        logger.warning("Push notification failed: %s", e)
        return False


def _resolve_db_path() -> str:
    """Resolve the DB path using the SAME logic as api.py.

    P0-5 fix (audit 2026-07-15): the previous default `"personal.db"`
    was RELATIVE TO CWD, while api.py uses an ABSOLUTE path under the
    package directory. When the auditor ran `uvicorn` from the repo
    root, the scheduler opened a different DB file than the rest of
    the app — causing the "no such table: signals" startup error.

    This function now mirrors api.py's resolution exactly.
    """
    env = os.environ.get("MAESTRO_PERSONAL_DB")
    if env:
        return env
    from pathlib import Path
    return str(Path(__file__).resolve().parent / "personal.db")


def ensure_scheduler_tables(db) -> None:
    """P0-5 fix: idempotently create the tables the scheduler queries.

    Even if init_db() in api.py runs first, calling this ensures the
    scheduler never crashes on a missing table — including in tests
    that bypass the full app lifespan.
    """
    db.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            signal_id TEXT PRIMARY KEY,
            entity TEXT NOT NULL,
            text TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            source_acl TEXT DEFAULT 'public',
            created_at TEXT NOT NULL,
            user_email TEXT DEFAULT 'bootstrap'
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS push_tokens (
            user_email TEXT NOT NULL,
            expo_token TEXT NOT NULL,
            created_at TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            PRIMARY KEY (user_email, expo_token)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS notified_stale (
            signal_id TEXT PRIMARY KEY,
            notified_at TEXT NOT NULL
        )
    """)
    db.commit()


async def check_stale_commitments():
    """Check for newly stale commitments and send push notifications."""
    from maestro_personal_shell.db_util import get_db_conn

    db_path = _resolve_db_path()
    db = get_db_conn(db_path)

    # P0-5 fix: ensure tables exist before querying (idempotent).
    ensure_scheduler_tables(db)

    three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    try:
        rows = db.execute("""
            SELECT s.signal_id, s.entity, s.text, s.user_email, s.timestamp
            FROM signals s
            WHERE s.signal_type = 'commitment_made'
            AND s.timestamp < ?
            AND s.signal_id NOT IN (SELECT signal_id FROM notified_stale)
            AND s.user_email IN (SELECT user_email FROM push_tokens WHERE active = 1)
        """, (three_days_ago,)).fetchall()
    except Exception as e:
        db.close()
        logger.warning("Stale commitment check failed: %s", e)
        return

    for row in rows:
        signal_id, entity, text, user_email, timestamp = row
        try:
            days_stale = (datetime.now(timezone.utc) - datetime.fromisoformat(
                timestamp.replace("Z", "+00:00")
            )).days
        except Exception:
            days_stale = 0

        # Get push tokens for this user
        token_rows = db.execute(
            "SELECT expo_token FROM push_tokens WHERE user_email = ? AND active = 1",
            (user_email,),
        ).fetchall()

        for (push_token,) in token_rows:
            _send_push_notification(
                push_token,
                title=f"{entity} · {days_stale} days stale",
                body=f"{text[:80]} — {entity} is waiting.",
                data={
                    "type": "stale_commitment",
                    "entity": entity,
                    "signal_id": signal_id,
                },
            )

        # Mark as notified
        db.execute(
            "INSERT OR IGNORE INTO notified_stale (signal_id, notified_at) VALUES (?, ?)",
            (signal_id, datetime.now(timezone.utc).isoformat()),
        )
        db.commit()

    db.close()
    if rows:
        logger.info("Notification scheduler: sent %d stale commitment alerts", len(rows))


async def notification_loop(interval_seconds: int = 3600):
    """Background loop — checks every hour."""
    logger.info("Notification scheduler loop started (interval=%ds)", interval_seconds)
    while True:
        try:
            await check_stale_commitments()
        except Exception as e:
            logger.error("Notification cycle crashed: %s", e)
        await asyncio.sleep(interval_seconds)
