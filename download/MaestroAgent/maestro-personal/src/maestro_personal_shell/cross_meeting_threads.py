"""
Personal-shell wrapper for the CrossMeetingThreadBuilder (Phase 14).

P11 fix (wiring): the enterprise CrossMeetingThreadBuilder was built +
tested (13 tests pass) but never wired into the personal shell — the
actual product the mobile app uses. The personal shell had no
cross-meeting threading: meetings were stored as isolated signals with
no way to link "this continues the Q3 renewal discussion from Oct 15".

This is the "institutional memory" moat — the thing Cluely can't do.
It connects meetings into a coherent narrative by entity + topic,
tracks decisions across meetings, and surfaces topic evolution.

This module DERIVES meeting summaries from the user's stored evidence
(signal history) — per P13, the caller does NOT supply the meetings.
The builder inspects meeting_scheduled / meeting_context signals +
their related commitment_made / decision signals, then groups them
into threads by entity + topic overlap.
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
    from maestro_oem.cross_meeting_threads import (  # type: ignore[import]
        CrossMeetingThreadBuilder,
        MeetingSummary,
        MeetingThread,
        ThreadConfidence,
    )
    ENTERPRISE_THREAD_BUILDER_AVAILABLE = True
except ImportError as e:
    logger.warning(
        "Enterprise CrossMeetingThreadBuilder not available — cross-meeting "
        "threading disabled. Import error: %s", e
    )
    ENTERPRISE_THREAD_BUILDER_AVAILABLE = False


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


def _derive_meeting_summaries_from_signals(
    signals: list[dict],
) -> list[dict]:
    """P13: DERIVE meeting summaries from the user's signal history.

    The enterprise CrossMeetingThreadBuilder.add_meeting_from_dict() expects
    dicts with: meeting_id, title, entity, start_time, attendees, topics,
    decisions, commitments, transcript_text.

    We DERIVE these from the personal shell's signals:
      - meeting_scheduled / meeting_context signals → meeting summaries
      - commitment_made signals (same entity, nearby time) → commitments
      - decision signals (signal_type contains 'decision') → decisions
      - topics extracted from the signal text via simple keyword extraction
    """
    # First pass: collect meeting signals
    meetings: list[dict] = []
    meeting_signals = [
        s for s in signals
        if s.get("signal_type") in ("meeting_scheduled", "meeting_context", "pre_call_briefing")
    ]

    for sig in meeting_signals:
        meta = sig.get("metadata", {}) or {}
        start_str = meta.get("start_time") or meta.get("meeting_time") or sig.get("timestamp", "")
        try:
            start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
        except Exception:
            try:
                start_time = datetime.fromisoformat(sig.get("timestamp", "").replace("Z", "+00:00"))
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=timezone.utc)
            except Exception:
                start_time = datetime.now(timezone.utc)

        # DERIVE topics from the signal text + title — simple keyword extraction.
        # The enterprise builder uses topic overlap to link meetings.
        title = meta.get("title") or sig.get("text", "Untitled Meeting")
        text = sig.get("text", "")
        topics = _extract_topics(title + " " + text)

        meetings.append({
            "meeting_id": sig.get("signal_id", f"meeting-{len(meetings)}"),
            "title": title,
            "entity": sig.get("entity"),
            "start_time": start_time.isoformat(),
            "attendees": meta.get("attendees", []),
            "topics": topics,
            "decisions": [],  # populated in second pass
            "commitments": [],  # populated in second pass
            "transcript_text": text,
        })

    # Second pass: attach commitments + decisions to nearby meetings (same entity)
    for meeting in meetings:
        entity = meeting.get("entity")
        if not entity:
            continue
        entity_lower = entity.lower()
        try:
            meeting_time = datetime.fromisoformat(meeting["start_time"].replace("Z", "+00:00"))
        except Exception:
            continue

        # Find commitments for this entity within ±7 days of the meeting
        for sig in signals:
            if sig.get("entity", "").lower() != entity_lower:
                continue
            sig_type = sig.get("signal_type", "")
            try:
                sig_time = datetime.fromisoformat(sig.get("timestamp", "").replace("Z", "+00:00"))
                if sig_time.tzinfo is None:
                    sig_time = sig_time.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            days_apart = abs((sig_time - meeting_time).total_seconds()) / 86400
            if days_apart > 7:
                continue

            if sig_type == "commitment_made":
                meeting["commitments"].append(sig.get("text", ""))
            elif "decision" in sig_type.lower():
                meeting["decisions"].append(sig.get("text", ""))

    return meetings


def _extract_topics(text: str) -> list[str]:
    """Extract topics from text via simple keyword extraction.

    The enterprise builder uses topic overlap to link meetings, so we need
    consistent topic labels. We extract nouns/keywords from the text.

    This is a simplified version — the enterprise module has more
    sophisticated topic extraction. For the personal shell, we extract:
      - Words longer than 4 chars (likely meaningful)
      - Filter out common stop words
      - Deduplicate
    """
    stop_words = {
        "about", "after", "again", "before", "between", "during",
        "meeting", "call", "sync", "discussion", "follow", "update",
        "review", "should", "would", "could", "their", "there", "these",
        "those", "where", "which", "while", "with", "from", "have",
        "they", "will", "been", "more", "than", "into", "them", "what",
        "this", "that", "will", "your", "have",
    }
    # Simple word extraction — split on non-alphanumeric, lowercase, filter
    words = []
    current = ""
    for char in text.lower():
        if char.isalnum():
            current += char
        else:
            if current and len(current) > 4 and current not in stop_words:
                words.append(current)
            current = ""
    if current and len(current) > 4 and current not in stop_words:
        words.append(current)

    # Deduplicate while preserving order, cap at 5 topics
    seen = set()
    topics = []
    for w in words:
        if w not in seen:
            seen.add(w)
            topics.append(w)
        if len(topics) >= 5:
            break
    return topics


def get_cross_meeting_threads(
    user_email: str,
    entity_filter: str = "",
    db_path: str = "",
) -> list[dict[str, Any]]:
    """Get cross-meeting threads for the user.

    P11: this is the production entry point for cross-meeting threading.
    P13: meeting summaries are DERIVED from the user's signal history —
    the caller supplies only the user_email (+ optional entity filter).

    Args:
        user_email: the user to fetch threads for
        entity_filter: if set, only return threads for this entity
        db_path: override the DB path (for tests)

    Returns:
        list of thread dicts, each with:
          thread_id, entity, topic, meeting_count, meetings,
          confidence, confidence_level, requires_confirmation,
          topic_evolution, decision_chain
    """
    if not ENTERPRISE_THREAD_BUILDER_AVAILABLE:
        return []

    signals = _get_signals_for_user(user_email, db_path=db_path)
    if not signals:
        return []

    # DERIVE meeting summaries from signals (P13)
    meeting_summaries = _derive_meeting_summaries_from_signals(signals)
    if len(meeting_summaries) < 2:
        # Need at least 2 meetings to build a thread
        return []

    # Build the threads using the enterprise builder
    builder = CrossMeetingThreadBuilder()
    for meeting_dict in meeting_summaries:
        builder.add_meeting_from_dict(meeting_dict)

    threads = builder.build_threads()

    # Apply entity filter if specified
    if entity_filter:
        entity_lower = entity_filter.lower()
        threads = [t for t in threads if t.entity.lower() == entity_lower]

    return [t.to_dict() for t in threads]


def get_decision_history(
    user_email: str,
    entity: str,
    db_path: str = "",
) -> list[dict[str, Any]]:
    """Get the decision history for an entity across meetings.

    P11: this surfaces the "Decided to offer phased rollout (Oct 22);
    confirmed in Nov 5 call" capability — decisions tracked across
    meetings as a chain.

    Args:
        user_email: the user
        entity: the entity to get decision history for

    Returns:
        list of decision dicts: {meeting_id, date, decision, confirmed_in}
    """
    if not ENTERPRISE_THREAD_BUILDER_AVAILABLE:
        return []

    signals = _get_signals_for_user(user_email, db_path=db_path)
    if not signals:
        return []

    meeting_summaries = _derive_meeting_summaries_from_signals(signals)
    if not meeting_summaries:
        return []

    builder = CrossMeetingThreadBuilder()
    for meeting_dict in meeting_summaries:
        builder.add_meeting_from_dict(meeting_dict)

    return builder.get_decision_history(entity)


def get_threads_for_entity(
    user_email: str,
    entity: str,
    db_path: str = "",
) -> list[dict[str, Any]]:
    """Get all threads for a specific entity.

    Convenience wrapper around get_cross_meeting_threads with an entity filter.
    Useful for /api/ask — when the user asks about an entity, surface the
    cross-meeting thread for context.
    """
    return get_cross_meeting_threads(user_email, entity_filter=entity, db_path=db_path)
