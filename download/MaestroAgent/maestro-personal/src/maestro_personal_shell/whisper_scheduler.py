"""
Whisper Scheduler — background job that generates whispers hourly and
sends push notifications for new ones.

Issue 13-B: The "automated post-it" system. This scheduler runs hourly,
generates whispers via WhisperSurface, deduplicates via the
notified_whispers table, and sends push notifications via Expo.

Usage:
  # Run once (for testing):
  python -m maestro_personal_shell.whisper_scheduler --once

  # Run as background loop (for production):
  python -m maestro_personal_shell.whisper_scheduler --loop

  # Start via API lifespan (automatic when API starts):
  # The scheduler is started by the API lifespan handler.
"""
from __future__ import annotations

import os
import json
import time
import logging
import asyncio
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database setup — notified_whispers table for deduplication
# ---------------------------------------------------------------------------

def init_whisper_scheduler_db(db_path: str | None = None) -> None:
    """Create the notified_whispers table if it doesn't exist."""
    from maestro_personal_shell.db_util import get_db_conn
    conn = get_db_conn(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notified_whispers (
            user_email TEXT NOT NULL,
            whisper_hash TEXT NOT NULL,
            entity TEXT NOT NULL,
            whisper_type TEXT NOT NULL,
            priority TEXT NOT NULL,
            body_preview TEXT,
            notified_at TEXT NOT NULL,
            PRIMARY KEY (user_email, whisper_hash)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_notified_whispers_user
        ON notified_whispers(user_email, notified_at)
    """)
    conn.commit()
    conn.close()
    logger.info("Whisper scheduler DB initialized (notified_whispers table)")


def _compute_whisper_hash(w: dict, user_email: str) -> str:
    """Compute a stable hash for a whisper to detect duplicates."""
    import hashlib
    key = f"{user_email}:{w.get('entity','')}:{w.get('type','')}:{w.get('body','')[:100]}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _is_already_notified(user_email: str, whisper_hash: str, db_path: str | None = None) -> bool:
    """Check if a whisper has already been notified to this user."""
    from maestro_personal_shell.db_util import get_db_conn
    conn = get_db_conn(db_path)
    row = conn.execute(
        "SELECT 1 FROM notified_whispers WHERE user_email = ? AND whisper_hash = ?",
        (user_email, whisper_hash),
    ).fetchone()
    conn.close()
    return row is not None


def _mark_notified(user_email: str, w: dict, whisper_hash: str, db_path: str | None = None) -> None:
    """Record that a whisper has been notified to this user."""
    from maestro_personal_shell.db_util import get_db_conn
    conn = get_db_conn(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO notified_whispers
           (user_email, whisper_hash, entity, whisper_type, priority, body_preview, notified_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_email, whisper_hash,
         w.get("entity", ""), w.get("type", ""), w.get("priority", ""),
         w.get("body", "")[:200],
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Push notification via Expo
# ---------------------------------------------------------------------------

def _send_push_notification(expo_token: str, title: str, body: str, data: dict | None = None) -> bool:
    """Send a push notification via Expo's push API."""
    if not expo_token or not expo_token.startswith("ExponentPushToken"):
        return False
    try:
        payload = json.dumps({
            "to": expo_token,
            "title": title[:100],
            "body": body[:200],
            "data": data or {},
            "sound": "default",
            "priority": "high",
        }).encode()
        req = urllib.request.Request(
            "https://exp.host/--/api/v2/push/send",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        return result.get("data", {}).get("status") == "ok"
    except Exception as e:
        logger.warning("Push notification failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Get push tokens for a user
# ---------------------------------------------------------------------------

def _get_push_tokens(user_email: str, db_path: str | None = None) -> list[str]:
    """Get all registered push tokens for a user."""
    from maestro_personal_shell.db_util import get_db_conn
    conn = get_db_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT expo_token FROM push_tokens WHERE user_email = ? AND active = 1",
            (user_email,),
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        # push_tokens table may not exist yet
        conn.close()
        return []


# ---------------------------------------------------------------------------
# Main scheduler loop
# ---------------------------------------------------------------------------

def run_whisper_cycle(db_path: str | None = None) -> dict:
    """Run one whisper cycle: generate whispers, deduplicate, push notify.

    Returns a summary dict with counts.
    """
    from maestro_personal_shell.api import build_shell
    from maestro_personal_shell.surfaces.whisper import WhisperSurface

    init_whisper_scheduler_db(db_path)

    # Get all users who have push tokens
    from maestro_personal_shell.db_util import get_db_conn
    conn = get_db_conn(db_path)
    try:
        users = conn.execute(
            "SELECT DISTINCT user_email FROM push_tokens WHERE active = 1"
        ).fetchall()
    except Exception:
        users = []
    conn.close()

    summary = {
        "users_checked": len(users),
        "whispers_generated": 0,
        "whispers_notified": 0,
        "whispers_deduplicated": 0,
        "push_notifications_sent": 0,
        "errors": [],
    }

    for (user_email,) in users:
        try:
            shell = build_shell(user_email=user_email, signal_limit=500)
            surface = WhisperSurface(shell=shell)
            whispers = surface.get_active_whispers()

            tokens = _get_push_tokens(user_email, db_path)

            for w in whispers:
                w_hash = _compute_whisper_hash(w, user_email)
                summary["whispers_generated"] += 1

                if _is_already_notified(user_email, w_hash, db_path):
                    summary["whispers_deduplicated"] += 1
                    continue

                # Send push notification if user has tokens
                if tokens:
                    title = f"💌 {w.get('entity', 'Attention')}: {w.get('title', '')}"
                    body = w.get("body", "")[:150]
                    deep_link_data = {
                        "type": "whisper",
                        "entity": w.get("entity", ""),
                        "whisper_type": w.get("type", ""),
                        "priority": w.get("priority", ""),
                    }
                    for token in tokens:
                        if _send_push_notification(token, title, body, deep_link_data):
                            summary["push_notifications_sent"] += 1

                _mark_notified(user_email, w, w_hash, db_path)
                summary["whispers_notified"] += 1

        except Exception as e:
            summary["errors"].append(f"{user_email}: {e}")
            logger.warning("Whisper cycle failed for %s: %s", user_email, e)

    logger.info("Whisper cycle complete: %s", summary)
    return summary


async def whisper_loop(interval_seconds: int = 3600, db_path: str | None = None):
    """Background loop that runs the whisper cycle every interval.

    Default interval: 1 hour (3600s).
    """
    logger.info("Whisper scheduler loop started (interval=%ds)", interval_seconds)
    while True:
        try:
            run_whisper_cycle(db_path)
        except Exception as e:
            logger.error("Whisper cycle crashed: %s", e)
        await asyncio.sleep(interval_seconds)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--loop", action="store_true", help="Run as background loop")
    parser.add_argument("--interval", type=int, default=3600, help="Loop interval in seconds")
    args = parser.parse_args()

    if args.once:
        result = run_whisper_cycle()
        print(json.dumps(result, indent=2))
    elif args.loop:
        asyncio.run(whisper_loop(args.interval))
    else:
        print("Use --once or --loop")
