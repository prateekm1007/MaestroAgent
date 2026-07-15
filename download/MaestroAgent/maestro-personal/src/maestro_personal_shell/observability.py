"""
Phase 11 Observability — trace IDs, whisper decision logging, full audit events.

The roadmap requires:
  - Full audit events (not just mutations — surface reads too)
  - Trace IDs (request tracing across surfaces)
  - Whisper decision logging (why did the system whisper or stay silent?)

This module provides:
  1. Trace ID generation + middleware — every request gets a trace ID
     (from X-Request-ID header or auto-generated). The trace ID is
     propagated to all audit log entries and surface interactions.

  2. Whisper decision log — records WHY the system whispered or stayed
     silent: materiality score, transition type, threshold, entity,
     surface, and the reasoning.

  3. Surface interaction log — records every surface read (Ask,
     Commitments, Prepare, What Changed, The Moment, Copilot) with
     the trace ID, surface name, entity, latency, and result summary.

  4. /api/observability/trace — query all events for a given trace ID.

All logging is rule-based — no LLM needed.
"""

from __future__ import annotations

import logging
import sqlite3
from maestro_personal_shell.db_util import get_db_conn
import uuid
import time
from typing import Any
from datetime import datetime, timezone
from pathlib import Path
from contextvars import ContextVar

logger = logging.getLogger(__name__)

# Context variable for the current request's trace ID.
# Set by middleware, read by all surfaces.
_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_user_email_ctx: ContextVar[str] = ContextVar("user_email_ctx", default="")


def _get_db_path() -> str:
    import os
    return os.environ.get(
        "MAESTRO_PERSONAL_DB",
        str(Path(__file__).resolve().parent / "personal.db"),
    )


def init_observability_tables(db_path: str | None = None) -> None:
    """Create observability tables if they don't exist."""
    path = db_path or _get_db_path()
    conn = get_db_conn(path)
    try:
        # Trace events — every surface interaction + whisper decision
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trace_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                user_email TEXT NOT NULL,
                event_type TEXT NOT NULL,
                surface TEXT NOT NULL DEFAULT '',
                entity TEXT DEFAULT '',
                action TEXT DEFAULT '',
                details TEXT DEFAULT '{}',
                latency_ms REAL DEFAULT 0,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_trace_events_trace ON trace_events(trace_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_trace_events_user ON trace_events(user_email, timestamp)"
        )
        conn.commit()
    finally:
        conn.close()


def get_trace_id() -> str:
    """Get the current request's trace ID (from context variable)."""
    tid = _trace_id.get()
    if not tid:
        tid = generate_trace_id()
        _trace_id.set(tid)
    return tid


def generate_trace_id() -> str:
    """Generate a new trace ID."""
    return f"trace-{uuid.uuid4().hex[:12]}"


def set_trace_id(trace_id: str) -> None:
    """Set the trace ID for the current request."""
    _trace_id.set(trace_id)


def set_user_email(user_email: str) -> None:
    """Set the user email for the current request context."""
    _user_email_ctx.set(user_email)


def get_user_email() -> str:
    """Get the user email from the current request context."""
    return _user_email_ctx.get()


def log_trace_event(
    event_type: str,
    surface: str = "",
    entity: str = "",
    action: str = "",
    details: dict[str, Any] | None = None,
    latency_ms: float = 0,
    db_path: str | None = None,
    user_email: str | None = None,
) -> None:
    """Log a trace event for the current request.

    Args:
        event_type: 'surface_read', 'whisper_decision', 'mutation', 'llm_call'
        surface: 'ask', 'commitments', 'prepare', 'what_changed', 'the_moment', 'copilot'
        entity: the entity involved (if any)
        action: what was done (e.g., 'query', 'create', 'delete', 'whisper', 'silence')
        details: additional structured data
        latency_ms: time taken for this operation
        user_email: override the context user_email (for middleware use)
    """
    import json
    path = db_path or _get_db_path()
    trace_id = get_trace_id()
    ue = user_email or get_user_email() or "unknown"

    try:
        conn = get_db_conn(path)
        conn.execute(
            """INSERT INTO trace_events
               (trace_id, user_email, event_type, surface, entity, action, details, latency_ms, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trace_id,
                ue,
                event_type,
                surface,
                entity,
                action,
                json.dumps(details or {}),
                latency_ms,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug("Trace event log failed: %s", e)


def log_whisper_decision(
    surface: str,
    entity: str,
    should_whisper: bool,
    materiality_score: float,
    transition_type: str = "",
    threshold: float = 0.0,
    reasoning: str = "",
    evidence_available: list[dict] | None = None,
    candidate_output: str = "",
    db_path: str | None = None,
) -> None:
    """Log a whisper decision — WHY did the system whisper or stay silent?

    Per auditor deep analysis (AUDIT-CORE-DEEP-ANALYSIS):
    - evidence_available: what signals were available at decision time
      (without this, can't distinguish 'no evidence' from 'gate suppressed')
    - candidate_output: what the system WOULD have said if it whispered
      (the counterfactual — essential for 'why didn't Maestro alert me?')

    This is the key observability event for Trusted Silence.
    """
    log_trace_event(
        event_type="whisper_decision",
        surface=surface,
        entity=entity,
        action="whisper" if should_whisper else "silence",
        details={
            "should_whisper": should_whisper,
            "materiality_score": materiality_score,
            "transition_type": transition_type,
            "threshold": threshold,
            "reasoning": reasoning,
            "evidence_available": evidence_available or [],
            "candidate_output": candidate_output,
        },
        db_path=db_path,
    )


def log_surface_read(
    surface: str,
    entity: str = "",
    action: str = "read",
    result_summary: dict[str, Any] | None = None,
    latency_ms: float = 0,
    db_path: str | None = None,
) -> None:
    """Log a surface read (Ask, Commitments, Prepare, etc.).

    This provides full audit coverage — not just mutations but every
    surface interaction is logged with the trace ID.
    """
    log_trace_event(
        event_type="surface_read",
        surface=surface,
        entity=entity,
        action=action,
        details=result_summary or {},
        latency_ms=latency_ms,
        db_path=db_path,
    )


def get_trace(trace_id: str, db_path: str | None = None, user_email: str | None = None) -> list[dict[str, Any]]:
    """Get all events for a trace ID.

    P0 fix (independent audit S3): scope by user_email. Without this,
    Bob can retrieve Alice's trace by guessing/knowing her trace ID —
    including her email, entity, signal text, and candidate output.

    Returns a timeline of everything that happened in a single request:
    surface reads, whisper decisions, mutations, LLM calls — all linked
    by the trace ID.
    """
    import json
    path = db_path or _get_db_path()
    init_observability_tables(path)
    conn = get_db_conn(path)
    conn.row_factory = sqlite3.Row
    try:
        if user_email:
            rows = conn.execute(
                """SELECT * FROM trace_events WHERE trace_id = ? AND user_email = ? ORDER BY id ASC""",
                (trace_id, user_email),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM trace_events WHERE trace_id = ? ORDER BY id ASC""",
                (trace_id,),
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["details"] = json.loads(d.get("details", "{}"))
            result.append(d)
        return result
    finally:
        conn.close()


def get_user_traces(user_email: str, limit: int = 50, db_path: str | None = None) -> list[dict[str, Any]]:
    """Get recent traces for a user."""
    import json
    path = db_path or _get_db_path()
    init_observability_tables(path)
    conn = get_db_conn(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT trace_id, COUNT(*) as event_count, MIN(timestamp) as started_at,
               MAX(timestamp) as ended_at, GROUP_CONCAT(DISTINCT surface) as surfaces
               FROM trace_events WHERE user_email = ?
               GROUP BY trace_id ORDER BY started_at DESC LIMIT ?""",
            (user_email, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_whisper_decisions(user_email: str, limit: int = 50, db_path: str | None = None) -> list[dict[str, Any]]:
    """Get recent whisper decisions for a user.

    This is the 'why didn't Maestro alert me?' log. Shows every whisper
    decision with the materiality score, transition type, and reasoning.
    """
    import json
    path = db_path or _get_db_path()
    init_observability_tables(path)
    conn = get_db_conn(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT * FROM trace_events
               WHERE user_email = ? AND event_type = 'whisper_decision'
               ORDER BY timestamp DESC LIMIT ?""",
            (user_email, limit),
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["details"] = json.loads(d.get("details", "{}"))
            result.append(d)
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Selection-reason lookup table + over-suppression detection
# (per auditor: Core's reasoning_trace.py has a 14-entry lookup table)
# ---------------------------------------------------------------------------

SELECTION_REASON_LOOKUP: dict[tuple[str, str], str] = {
    ("active", "whisper"): "Active commitment + in meeting — whisper the commitment",
    ("active", "silence"): "Active commitment but not in meeting — no whisper needed",
    ("at_risk", "whisper"): "At-risk commitment + context — whisper urgently",
    ("at_risk", "silence"): "At-risk commitment but low materiality — suppressed",
    ("completed", "silence"): "Completed commitment — correctly suppressed",
    ("completed", "whisper"): "Completed commitment surfaced — possible stale filter",
    ("cancelled", "silence"): "Cancelled commitment — correctly suppressed",
    ("cancelled", "whisper"): "Cancelled commitment surfaced — possible filter bypass",
    ("disputed", "whisper"): "Disputed commitment — whisper the dispute",
    ("disputed", "silence"): "Disputed commitment suppressed — possible over-suppression",
    ("stale", "whisper"): "Stale commitment + context — whisper to follow up",
    ("stale", "silence"): "Stale commitment but not in meeting — deferred to summary",
    ("routine", "silence"): "Routine activity — correctly silenced",
    ("routine", "whisper"): "Routine activity surfaced — possible threshold too low",
}


def get_selection_reason(situation_state: str, action: str) -> str:
    """Get a human-readable explanation for a whisper/silence decision."""
    return SELECTION_REASON_LOOKUP.get(
        (situation_state, action),
        f"State={situation_state}, action={action} — no specific rule matched",
    )


def detect_over_suppression(
    situation_state: str,
    should_whisper: bool,
    has_evidence: bool,
    in_meeting_context: bool = False,
) -> str | None:
    """Detect over-suppression: silence when evidence + context warrant a whisper.

    Per auditor: the Core detects 'auto-disagreement collapse'. The Personal
    equivalent is 'materiality gate over-suppression'.
    """
    if should_whisper:
        return None
    if not has_evidence:
        return None
    if situation_state in ("stale", "at_risk", "disputed") and in_meeting_context:
        return (
            f"OVER-SUPPRESSION WARNING: {situation_state} commitment with evidence "
            "available and in-meeting context, but materiality gate suppressed the whisper."
        )
    if situation_state == "disputed" and has_evidence:
        return (
            "OVER-SUPPRESSION WARNING: disputed commitment with evidence available, "
            "but materiality gate suppressed the whisper. Disputes should generally be surfaced."
        )
    return None
