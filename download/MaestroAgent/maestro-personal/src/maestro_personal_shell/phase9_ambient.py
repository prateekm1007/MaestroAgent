"""Personal-shell wrapper for Phase 9 ambient engines:"""
from __future__ import annotations

import logging
import os
import sys as _sys
from datetime import datetime, timezone, timedelta
from pathlib import Path as _Path
from typing import Any

logger = logging.getLogger(__name__)

# Add backend/ to sys.path so we can import the enterprise modules.
_BACKEND_ROOT = _Path(__file__).resolve().parent.parent.parent.parent / "backend"
if str(_BACKEND_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_BACKEND_ROOT))

try:
    from maestro_oem.calendar_awareness import (  # type: ignore[import]
        CalendarAwarenessEngine,
        MeetingContext,
        MeetingUrgency,
        PreparationStatus,
    )
    from maestro_oem.commitment_escalation import (  # type: ignore[import]
        CommitmentEscalationEngine,
        CommitmentEscalation,
        CommitmentHealth,
        EscalationLevel,
    )
    ENTERPRISE_ENGINES_AVAILABLE = True
except ImportError as e:
    logger.warning(
        "Enterprise Phase 9 engines not available — calendar awareness + "
        "commitment escalation disabled. Import error: %s", e
    )
    ENTERPRISE_ENGINES_AVAILABLE = False


def _resolve_db_path() -> str:
    """Resolve the DB path using the SAME logic as api.py."""
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
        import json as _json
        return [
            {
                "signal_id": r[0],
                "entity": r[1],
                "text": r[2],
                "signal_type": r[3],
                "timestamp": r[4],
                "metadata": _json.loads(r[5]) if r[5] else {},
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("Failed to fetch signals for %s: %s", user_email, e)
        return []
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Calendar awareness (Phase 9a)
# ---------------------------------------------------------------------------


def get_calendar_awareness(
    user_email: str,
    hours_ahead: int = 48,
    db_path: str = "",
) -> list[dict[str, Any]]:
    """Get calendar awareness for upcoming meetings.

    P11: this is the production entry point for calendar awareness.
    P13: meeting context is DERIVED from the user's signal history —
    the caller supplies only the user_email + time horizon.

    Args:
        user_email: the user to fetch calendar awareness for
        hours_ahead: how far ahead to look (default 48 hours)
        db_path: override the DB path (for tests)

    Returns:
        list of meeting context dicts, each with:
          meeting_id, title, start_time, end_time, urgency,
          preparation_status, entity, talking_points, risks,
          opportunities, open_commitments, overdue_commitments
    """
    if not ENTERPRISE_ENGINES_AVAILABLE:
        return []

    signals = _get_signals_for_user(user_email, db_path=db_path)
    if not signals:
        return []

    # DERIVE calendar events from the user's signals — meetings are stored
    # as signals with signal_type in (meeting_scheduled, meeting_context, etc.)
    # This is P13-compliant: we don't take events as a parameter, we derive
    # them from the user's stored evidence.
    events = _derive_calendar_events_from_signals(signals, hours_ahead)
    if not events:
        return []

    engine = CalendarAwarenessEngine(oem_state=None, calendar_source=None)
    contexts = []
    for event in events:
        try:
            ctx = _build_meeting_context_with_signals(engine, event, signals)
            if ctx:
                contexts.append(ctx.to_dict())
        except Exception as e:
            logger.debug("Failed to build meeting context for %s: %s", event.get("id"), e)

    return contexts


def _derive_calendar_events_from_signals(
    signals: list[dict], hours_ahead: int
) -> list[dict]:
    """P13: DERIVE calendar events from the user's signal history.

    Meetings appear in signals with signal_type like:
      - meeting_scheduled
      - meeting_context
      - pre_call_briefing
    The event time is parsed from the signal's metadata or timestamp.
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=hours_ahead)
    events = []

    for sig in signals:
        sig_type = sig.get("signal_type", "")
        if sig_type not in ("meeting_scheduled", "meeting_context", "pre_call_briefing"):
            continue

        meta = sig.get("metadata", {}) or {}
        # Parse meeting start time from metadata, fall back to signal timestamp
        start_str = meta.get("start_time") or meta.get("meeting_time") or sig.get("timestamp", "")
        try:
            start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
        except Exception:
            continue

        # Only include upcoming meetings within the horizon
        if start < now or start > horizon:
            continue

        events.append({
            "id": sig.get("signal_id", f"meeting-{len(events)}"),
            "title": meta.get("title") or sig.get("text", "Untitled Meeting"),
            "start": start,
            "end": start + timedelta(hours=meta.get("duration_hours", 1)),
            "attendees": meta.get("attendees", []),
            "entity": sig.get("entity", ""),
        })

    return events


def _build_meeting_context_with_signals(
    engine: CalendarAwarenessEngine,
    event: dict,
    signals: list[dict],
) -> MeetingContext | None:
    """Build a meeting context, populating commitments from the user's signals."""
    try:
        ctx = _safe_build_context(engine, event)
        if ctx is None:
            return None
        # P13 fix: the enterprise _extract_entity uses KNOWN_ENTITIES (empty
        # by default) + attendee domains. In the personal shell, we DERIVE
        # the entity from the signal's entity field directly — it's already
        # known because the signal was ingested with an entity label.
        entity = event.get("entity") or ctx.entity
        if entity:
            ctx.entity = entity
            open_comms, overdue_comms = _get_commitments_for_entity_from_signals(entity, signals)
            ctx.open_commitments = open_comms
            ctx.overdue_commitments = overdue_comms
        return ctx
    except Exception as e:
        logger.debug("Meeting context build failed: %s", e)
        return None


def _safe_build_context(engine: CalendarAwarenessEngine, event: dict) -> MeetingContext | None:
    """Call the engine's build_context_for_event, handling async + sync variants.

    The enterprise _build_meeting_context is declared async but does no actual
    await — it's sync in practice. We run it in a worker thread with a fresh
    event loop to avoid the 'event loop already running' error inside FastAPI.
    """
    import asyncio
    import threading
    holder: dict[str, Any] = {}

    def _runner() -> None:
        try:
            holder["result"] = asyncio.run(engine._build_meeting_context(event))
        except Exception as exc:  # noqa: BLE001
            holder["error"] = exc

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()
    if "error" in holder:
        logger.debug("_safe_build_context failed: %s", holder["error"])
        return None
    return holder.get("result")


def _get_commitments_for_entity_from_signals(
    entity: str, signals: list[dict]
) -> tuple[list[dict], list[dict]]:
    """P13: DERIVE open + overdue commitments for an entity from signal history."""
    now = datetime.now(timezone.utc)
    three_days_ago = now - timedelta(days=3)
    open_commitments: list[dict] = []
    overdue_commitments: list[dict] = []

    entity_lower = entity.lower()
    for sig in signals:
        if sig.get("entity", "").lower() != entity_lower:
            continue
        if sig.get("signal_type") != "commitment_made":
            continue

        ts_str = sig.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            continue

        commit_dict = {
            "id": sig.get("signal_id", ""),
            "text": sig.get("text", ""),
            "entity": entity,
            "timestamp": ts_str,
        }
        if ts < three_days_ago:
            overdue_commitments.append(commit_dict)
        else:
            open_commitments.append(commit_dict)

    return open_commitments, overdue_commitments


# ---------------------------------------------------------------------------
# Commitment escalation (Phase 9b)
# ---------------------------------------------------------------------------


def get_commitment_escalations(
    user_email: str,
    db_path: str = "",
) -> list[dict[str, Any]]:
    """Get commitment escalations for the user.

    P11: this is the production entry point for commitment escalation.
    P13: commitments are DERIVED from the user's signal history —
    the caller supplies only the user_email.

    Returns:
        list of escalation dicts, each with:
          commitment_id, commitment_text, owner, entity, due_date,
          health, escalation_level, days_until_due, days_overdue,
          nudge_text, nudge_channel, nudge_draft,
          failure_probability, failure_reason, related_commitments
    """
    if not ENTERPRISE_ENGINES_AVAILABLE:
        return []

    signals = _get_signals_for_user(user_email, db_path=db_path)
    if not signals:
        return []

    # DERIVE commitments from signals (P13)
    commitments = _derive_commitments_from_signals(signals)
    if not commitments:
        return []

    engine = CommitmentEscalationEngine(oem_state=None)
    escalations = []
    for commit in commitments:
        try:
            esc = engine.evaluate_commitment(commit)
            if esc:
                escalations.append(esc.to_dict())
        except Exception as e:
            logger.debug("Failed to evaluate commitment %s: %s", commit.get("id"), e)

    # Sort by escalation level (CRITICAL first)
    priority_order = {"critical": 0, "overdue": 1, "soon": 2, "none": 3}
    escalations.sort(key=lambda e: priority_order.get(e.get("escalation_level", "none"), 4))
    return escalations


def _derive_commitments_from_signals(signals: list[dict]) -> list[dict]:
    """P13: DERIVE commitment dicts from signal history.

    The enterprise engine expects dicts with: id, text, actor, entity,
    timestamp, due_date. We parse these from the personal shell's signals.
    """
    commitments = []
    for sig in signals:
        if sig.get("signal_type") != "commitment_made":
            continue
        meta = sig.get("metadata", {}) or {}
        # Parse due date from metadata if available
        due_date = meta.get("due_date") or meta.get("deadline")
        commitments.append({
            "id": sig.get("signal_id", f"commit-{len(commitments)}"),
            "text": sig.get("text", ""),
            "actor": meta.get("actor", ""),
            "entity": sig.get("entity", ""),
            "timestamp": sig.get("timestamp", ""),
            "due_date": due_date,
        })
    return commitments


# ---------------------------------------------------------------------------
# Preparation gap detection (used by /api/whisper)
# ---------------------------------------------------------------------------


def get_preparation_gaps(
    user_email: str,
    hours_ahead: int = 2,
    db_path: str = "",
) -> list[dict[str, Any]]:
    """Detect meetings in the next `hours_ahead` hours with no preparation done.

    P11: wires the enterprise CalendarAwarenessEngine's prep-gap detection
    into the personal shell. Used by /api/whisper to surface "Meeting in
    30 min — no prep done" whispers.

    Returns:
        list of prep-gap dicts: {meeting_id, title, minutes_to_start, talking_points}
    """
    if not ENTERPRISE_ENGINES_AVAILABLE:
        return []

    # Get upcoming meetings via calendar awareness
    contexts = get_calendar_awareness(
        user_email, hours_ahead=hours_ahead, db_path=db_path
    )
    gaps = []
    now = datetime.now(timezone.utc)
    for ctx in contexts:
        prep_status = ctx.get("preparation_status", "")
        if prep_status in ("not_started", "stale"):
            try:
                start_str = ctx.get("start_time", "")
                start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                minutes_to_start = int((start - now).total_seconds() / 60)
                if 0 <= minutes_to_start <= hours_ahead * 60:
                    gaps.append({
                        "meeting_id": ctx.get("meeting_id", ""),
                        "title": ctx.get("title", ""),
                        "minutes_to_start": minutes_to_start,
                        "talking_points": ctx.get("talking_points", [])[:3],
                        "entity": ctx.get("entity", ""),
                    })
            except Exception:
                continue
    return gaps
