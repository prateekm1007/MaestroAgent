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
    conn = sqlite3.connect(path)
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
) -> None:
    """Log a trace event for the current request.

    Args:
        event_type: 'surface_read', 'whisper_decision', 'mutation', 'llm_call'
        surface: 'ask', 'commitments', 'prepare', 'what_changed', 'the_moment', 'copilot'
        entity: the entity involved (if any)
        action: what was done (e.g., 'query', 'create', 'delete', 'whisper', 'silence')
        details: additional structured data
        latency_ms: time taken for this operation
    """
    import json
    path = db_path or _get_db_path()
    trace_id = get_trace_id()
    user_email = get_user_email() or "unknown"

    try:
        conn = sqlite3.connect(path)
        conn.execute(
            """INSERT INTO trace_events
               (trace_id, user_email, event_type, surface, entity, action, details, latency_ms, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trace_id,
                user_email,
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
    db_path: str | None = None,
) -> None:
    """Log a whisper decision — WHY did the system whisper or stay silent?

    This is the key observability event for Trusted Silence. When a user
    asks 'why didn't Maestro alert me about X?', this log answers the
    question: the materiality score was below threshold, or the transition
    type was routine_activity, or the entity was suppressed.
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


def get_trace(trace_id: str, db_path: str | None = None) -> list[dict[str, Any]]:
    """Get all events for a trace ID.

    Returns a timeline of everything that happened in a single request:
    surface reads, whisper decisions, mutations, LLM calls — all linked
    by the trace ID.
    """
    import json
    path = db_path or _get_db_path()
    init_observability_tables(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
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
    conn = sqlite3.connect(path)
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
    conn = sqlite3.connect(path)
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
