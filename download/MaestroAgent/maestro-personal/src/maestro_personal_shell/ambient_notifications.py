"""Personal-shell wrapper for the AmbientNotificationEngine."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Import the enterprise engine (lives in backend/maestro_oem/). We use
# the engine directly — no enterprise-specific dependencies in the engine
# itself, just stdlib + dataclasses.
import sys as _sys
from pathlib import Path as _Path

# Add backend/ to sys.path so we can import the enterprise module.
# This is the SAME pattern the personal shell uses for other enterprise
# bridges (e.g. copilot_live.py imports from maestro_oem).
_BACKEND_ROOT = _Path(__file__).resolve().parent.parent.parent.parent / "backend"
if str(_BACKEND_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_BACKEND_ROOT))

try:
    from maestro_oem.ambient_notifications import (  # type: ignore[import]
        AmbientNotificationEngine,
        Notification,
        NotificationContext,
        NotificationPriority,
        NotificationType,
    )
    ENTERPRISE_ENGINE_AVAILABLE = True
except ImportError as e:
    logger.warning(
        "Enterprise AmbientNotificationEngine not available — "
        "smart notifications disabled. Import error: %s", e
    )
    ENTERPRISE_ENGINE_AVAILABLE = False


def _resolve_db_path() -> str:
    """Resolve the DB path using the SAME logic as api.py + notification_scheduler.py."""
    env = os.environ.get("MAESTRO_PERSONAL_DB")
    if env:
        return env
    from pathlib import Path
    return str(Path(__file__).resolve().parent / "personal.db")


def _get_signals_for_user(user_email: str, db_path: str = "") -> list[dict]:
    """Fetch all signals for a user from the personal shell's SQLite DB.

    P13: inputs are DERIVED from stored evidence, not caller-supplied.
    """
    from maestro_personal_shell.db_util import get_db_conn
    path = db_path or _resolve_db_path()
    db = get_db_conn(path)
    try:
        rows = db.execute(
            "SELECT signal_id, entity, text, signal_type, timestamp, metadata "
            "FROM signals WHERE user_email = ? ORDER BY timestamp DESC",
            (user_email,),
        ).fetchall()
        return [
            {
                "signal_id": r[0],
                "entity": r[1],
                "text": r[2],
                "signal_type": r[3],
                "timestamp": r[4],
                "metadata": r[5],
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("Failed to fetch signals for %s: %s", user_email, e)
        return []
    finally:
        db.close()


def _derive_notifications_from_signals(signals: list[dict]) -> list[Notification]:
    """P13: DERIVE notifications from the user's signal history.

    This is the bridge between the personal shell's signal store and the
    enterprise AmbientNotificationEngine. We inspect the signals and
    generate Notification objects for each actionable pattern:

      - Overdue commitments (commitment_made signals older than 3 days
        with no corresponding commitment_completed signal)
      - Stale relationships (entity last seen > 14 days ago)
      - Daily digest (counts of meetings + overdue + at-risk)
    """
    if not ENTERPRISE_ENGINE_AVAILABLE:
        return []

    engine = AmbientNotificationEngine()
    now = datetime.now(timezone.utc)

    # Group signals by entity for relationship staleness analysis
    entity_last_seen: dict[str, datetime] = {}
    commitment_signals: list[dict] = []
    meeting_count = 0

    for sig in signals:
        entity = sig.get("entity", "")
        ts_str = sig.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            ts = now

        if entity:
            if entity not in entity_last_seen or ts > entity_last_seen[entity]:
                entity_last_seen[entity] = ts

        sig_type = sig.get("signal_type", "")
        if sig_type == "commitment_made":
            commitment_signals.append(sig)
        if sig_type in ("meeting_scheduled", "meeting_context", "pre_call_briefing"):
            meeting_count += 1

    # 1. Overdue commitments
    three_days_ago = now - timedelta(days=3)
    for sig in commitment_signals:
        ts_str = sig.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            continue

        if ts < three_days_ago:
            days_overdue = (now - ts).days
            entity = sig.get("entity", "unknown")
            text = sig.get("text", "")[:100]
            notif = engine.generate_overdue_commitment_notification(
                commitment_text=text,
                days_overdue=days_overdue,
                entity=entity,
            )
            engine.add_notification(notif)

    # 2. Stale relationships
    fourteen_days_ago = now - timedelta(days=14)
    for entity, last_seen in entity_last_seen.items():
        if last_seen < fourteen_days_ago:
            days_since = (now - last_seen).days
            notif = engine.generate_stale_relationship_notification(
                entity=entity,
                days_since_interaction=days_since,
            )
            engine.add_notification(notif)

    # 3. Daily digest
    overdue_count = len(commitment_signals)  # simplified
    at_risk_count = sum(
        1 for entity, last_seen in entity_last_seen.items()
        if last_seen < fourteen_days_ago
    )
    digest = engine.generate_daily_digest(
        meeting_count=meeting_count,
        overdue_count=overdue_count,
        at_risk_count=at_risk_count,
    )
    engine.add_notification(digest)

    return list(engine._notifications)


def get_smart_notifications(
    user_email: str,
    is_in_call: bool = False,
    is_dnd_active: bool = False,
    is_focus_mode: bool = False,
    user_timezone: str = "UTC",
    db_path: str = "",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Get context-aware notifications for a user.

    P11: this is the production entry point. It:
      1. DERIVES notifications from the user's signal history (P13)
      2. Applies context-aware filtering (quiet hours, DND, focus, fatigue)
      3. Returns visible notifications as dicts ready for the mobile app

    Args:
        user_email: the user to fetch notifications for
        is_in_call: suppress non-critical during calls
        is_dnd_active: suppress non-critical when DND is on
        is_focus_mode: suppress medium-priority during focus blocks
        user_timezone: for quiet-hours calculation (UTC for now)
        db_path: override the DB path (for tests)
        limit: max notifications to return

    Returns:
        list of notification dicts with keys:
          notification_id, type, priority, title, body, action_url,
          action_label, created_at, metadata
    """
    if not ENTERPRISE_ENGINE_AVAILABLE:
        logger.debug("Smart notifications unavailable — enterprise engine not importable")
        return []

    # P13: DERIVE notifications from stored evidence
    signals = _get_signals_for_user(user_email, db_path=db_path)
    if not signals:
        return []

    # Build the context — the caller supplies CONTEXT (am I in a call?),
    # not the notification content. This is P13-compliant.
    context = NotificationContext(
        current_time=datetime.now(timezone.utc),
        is_in_call=is_in_call,
        is_dnd_active=is_dnd_active,
        is_focus_mode=is_focus_mode,
        user_timezone=user_timezone,
    )

    # P11 fix: populate the engine ONCE, then call get_visible_notifications
    # on the SAME engine. The previous version called _derive_notifications
    # twice (once to populate a throwaway engine, once to get the list),
    # which created NEW Notification objects with NEW timestamps — the
    # engine's internal _notifications deque was empty when filtering ran.
    engine = AmbientNotificationEngine()
    for notif in _derive_notifications_from_signals(signals):
        engine.add_notification(notif)

    visible = engine.get_visible_notifications(context, limit=limit)
    return [n.to_dict() for n in visible]


def check_and_push_smart_notifications() -> int:
    """Background loop entry point — checks all users with push tokens
    and sends smart push notifications for any visible CRITICAL/HIGH items.

    Called by the notification_scheduler.py background loop (hourly).

    Returns: count of push notifications sent.
    """
    if not ENTERPRISE_ENGINE_AVAILABLE:
        return 0

    from maestro_personal_shell.db_util import get_db_conn
    from maestro_personal_shell.notification_scheduler import _send_push_notification

    db_path = _resolve_db_path()
    db = get_db_conn(db_path)
    try:
        # Get all users with active push tokens
        token_rows = db.execute(
            "SELECT DISTINCT user_email FROM push_tokens WHERE active = 1"
        ).fetchall()
    except Exception as e:
        logger.warning("Failed to fetch push token users: %s", e)
        db.close()
        return 0

    sent_count = 0
    for (user_email,) in token_rows:
        try:
            # For background pushes, use default context (not in call, no DND)
            notifications = get_smart_notifications(user_email, limit=3)
            if not notifications:
                continue

            # Get this user's push tokens
            user_tokens = db.execute(
                "SELECT expo_token FROM push_tokens WHERE user_email = ? AND active = 1",
                (user_email,),
            ).fetchall()

            for notif in notifications:
                # Only push CRITICAL + HIGH (don't spam LOW digest)
                if notif.get("priority") not in ("critical", "high"):
                    continue
                for (push_token,) in user_tokens:
                    if _send_push_notification(
                        push_token,
                        title=notif.get("title", ""),
                        body=notif.get("body", ""),
                        data={
                            "type": notif.get("type", ""),
                            "notification_id": notif.get("notification_id", ""),
                            **notif.get("metadata", {}),
                        },
                    ):
                        sent_count += 1
        except Exception as e:
            logger.warning(
                "Smart notification push failed for %s: %s", user_email, e
            )

    db.close()
    if sent_count:
        logger.info("Smart notification scheduler: sent %d pushes", sent_count)
    return sent_count
