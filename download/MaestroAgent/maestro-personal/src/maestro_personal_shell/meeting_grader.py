"""
Personal-shell wrapper for the MeetingGrader (Phase 16).

P11 fix (wiring): the enterprise MeetingGrader was built + tested (14
tests pass) but never wired into the personal shell — the actual product
the mobile app uses. The personal shell had no meeting grading: no
effectiveness score, no action item extraction, no follow-up tracking.

This module DERIVES meeting data from the user's stored evidence (signal
history) — per P13, the caller does NOT supply the transcript or metrics.
The grader inspects meeting_context signals + their metadata to extract:
  - transcript text (from the signal's text field)
  - duration (from metadata.duration_minutes)
  - talk ratio balance (from metadata.talk_ratio_balance)
  - sentiment score (from metadata.sentiment_score)
  - participants (from metadata.participants)

Then grades the meeting on 4 factors (30% action items, 30% sentiment,
20% participation, 20% duration) → A-F letter grade with transparent
factor breakdown. Allows user override.
"""
from __future__ import annotations

import logging
import os
import sys as _sys
from datetime import datetime, timezone
from pathlib import Path as _Path
from typing import Any

logger = logging.getLogger(__name__)

# Add backend/ to sys.path so we can import the enterprise module.
_BACKEND_ROOT = _Path(__file__).resolve().parent.parent.parent.parent / "backend"
if str(_BACKEND_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_BACKEND_ROOT))

try:
    from maestro_oem.meeting_grader import (  # type: ignore[import]
        MeetingGrader,
        MeetingGrade,
        MeetingGradeReport,
        ActionItem,
    )
    ENTERPRISE_GRADER_AVAILABLE = True
except ImportError as e:
    logger.warning(
        "Enterprise MeetingGrader not available — meeting grading disabled. "
        "Import error: %s", e
    )
    ENTERPRISE_GRADER_AVAILABLE = False


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
    import json as _json
    path = db_path or _resolve_db_path()
    db = get_db_conn(path)
    try:
        rows = db.execute(
            "SELECT signal_id, entity, text, signal_type, timestamp, metadata "
            "FROM signals WHERE user_email = ? ORDER BY timestamp ASC",
            (user_email,),
        ).fetchall()
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


def _derive_meeting_data_from_signals(
    meeting_id: str,
    signals: list[dict],
) -> dict[str, Any] | None:
    """P13: DERIVE meeting data from the user's signal history.

    Given a meeting_id (signal_id of a meeting_scheduled/meeting_context
    signal), find the meeting signal + all related signals (same entity,
    nearby time) and derive:
      - transcript: concatenation of the meeting signal's text + related
        commitment/statement signals
      - duration_minutes: from metadata, default 30
      - talk_ratio_balance: from metadata, default 0.5
      - sentiment_score: from metadata, default 0.5
      - participants: from metadata, default 2

    Returns None if the meeting signal isn't found.
    """
    # Find the meeting signal
    meeting_sig = None
    for sig in signals:
        if sig.get("signal_id") == meeting_id:
            meeting_sig = sig
            break

    if not meeting_sig:
        return None

    meta = meeting_sig.get("metadata", {}) or {}

    # DERIVE transcript from the meeting signal + related signals (same entity)
    entity = meeting_sig.get("entity", "")
    transcript_parts = [meeting_sig.get("text", "")]

    if entity:
        entity_lower = entity.lower()
        try:
            meeting_time = datetime.fromisoformat(
                meeting_sig.get("timestamp", "").replace("Z", "+00:00")
            )
            if meeting_time.tzinfo is None:
                meeting_time = meeting_time.replace(tzinfo=timezone.utc)
        except Exception:
            meeting_time = datetime.now(timezone.utc)

        # Include related signals within ±1 day of the meeting
        from datetime import timedelta
        for sig in signals:
            if sig.get("signal_id") == meeting_id:
                continue
            if sig.get("entity", "").lower() != entity_lower:
                continue
            try:
                sig_time = datetime.fromisoformat(
                    sig.get("timestamp", "").replace("Z", "+00:00")
                )
                if sig_time.tzinfo is None:
                    sig_time = sig_time.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if abs((sig_time - meeting_time).total_seconds()) < 86400:  # ±1 day
                transcript_parts.append(sig.get("text", ""))

    transcript = "\n".join(t for t in transcript_parts if t)

    return {
        "meeting_id": meeting_id,
        "transcript": transcript,
        "duration_minutes": meta.get("duration_minutes", 30),
        "talk_ratio_balance": meta.get("talk_ratio_balance", 0.5),
        "sentiment_score": meta.get("sentiment_score", 0.5),
        "participants": meta.get("participants", 2),
        "entity": entity,
        "title": meta.get("title", meeting_sig.get("text", "Untitled Meeting")),
    }


def grade_meeting(
    user_email: str,
    meeting_id: str,
    db_path: str = "",
) -> dict[str, Any] | None:
    """Grade a meeting and return the full report.

    P11: this is the production entry point for meeting grading.
    P13: meeting data is DERIVED from the user's signal history —
    the caller supplies only the meeting_id (which signal to grade).

    Args:
        user_email: the user
        meeting_id: the signal_id of the meeting to grade
        db_path: override the DB path (for tests)

    Returns:
        grade report dict with: grade, effective_grade, score, factors,
        action_items, action_item_completion_rate, follow_ups_pending,
        follow_ups_completed, confidence_label
        OR None if the meeting isn't found.
    """
    if not ENTERPRISE_GRADER_AVAILABLE:
        return None

    signals = _get_signals_for_user(user_email, db_path=db_path)
    if not signals:
        return None

    meeting_data = _derive_meeting_data_from_signals(meeting_id, signals)
    if not meeting_data:
        return None

    grader = MeetingGrader()
    grader.set_meeting_data(
        transcript=meeting_data["transcript"],
        duration_minutes=meeting_data["duration_minutes"],
        talk_ratio_balance=meeting_data["talk_ratio_balance"],
        sentiment_score=meeting_data["sentiment_score"],
        participants=meeting_data["participants"],
    )

    report = grader.grade_meeting(meeting_id=meeting_id)
    result = report.to_dict()
    # Enrich with meeting metadata for the mobile app
    result["meeting_id"] = meeting_id
    result["entity"] = meeting_data["entity"]
    result["title"] = meeting_data["title"]
    return result


def grade_all_meetings(
    user_email: str,
    db_path: str = "",
) -> list[dict[str, Any]]:
    """Grade all meetings for a user.

    Convenience wrapper — finds all meeting signals and grades each.
    Returns a list of grade report dicts, sorted by score (highest first).
    """
    if not ENTERPRISE_GRADER_AVAILABLE:
        return []

    signals = _get_signals_for_user(user_email, db_path=db_path)
    if not signals:
        return []

    # Find all meeting signals
    meeting_ids = [
        s.get("signal_id")
        for s in signals
        if s.get("signal_type") in ("meeting_scheduled", "meeting_context", "pre_call_briefing")
    ]

    results = []
    for mid in meeting_ids:
        report = grade_meeting(user_email, mid, db_path=db_path)
        if report:
            results.append(report)

    # Sort by score descending
    results.sort(key=lambda r: r.get("score", 0), reverse=True)
    return results


def set_user_override(
    user_email: str,
    meeting_id: str,
    grade: str,
    db_path: str = "",
) -> dict[str, Any] | None:
    """Allow the user to override the computed grade for a meeting.

    Args:
        meeting_id: the meeting to override
        grade: the override grade (A, B, C, D, or F)

    Returns the updated grade report with the override applied.
    """
    if not ENTERPRISE_GRADER_AVAILABLE:
        return None

    # Validate grade
    try:
        override_grade = MeetingGrade(grade.upper())
    except ValueError:
        return None

    signals = _get_signals_for_user(user_email, db_path=db_path)
    if not signals:
        return None

    meeting_data = _derive_meeting_data_from_signals(meeting_id, signals)
    if not meeting_data:
        return None

    grader = MeetingGrader()
    grader.set_meeting_data(
        transcript=meeting_data["transcript"],
        duration_minutes=meeting_data["duration_minutes"],
        talk_ratio_balance=meeting_data["talk_ratio_balance"],
        sentiment_score=meeting_data["sentiment_score"],
        participants=meeting_data["participants"],
    )
    grader.set_user_override(override_grade)

    report = grader.grade_meeting(meeting_id=meeting_id)
    result = report.to_dict()
    result["meeting_id"] = meeting_id
    result["entity"] = meeting_data["entity"]
    result["title"] = meeting_data["title"]
    return result
