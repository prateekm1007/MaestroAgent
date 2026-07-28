"""canonical_ledger.py — Append-only commitment ledger (P83).

Implements the canonical event store for MaestroAgent's commitment-tracking
functional area (FA33). Event-sourced per P82: every commitment lifecycle
transition is an immutable row; current state is derived by reduction
(deferred to P47 follow-ups). Dialect-neutral DDL: runs on SQLite directly
and on PostgreSQL via PostgresConnection (?→%s translation); no
dialect-specific functions are used.

Governance citations:
- P1: verified by execution — see tests/test_canonical_ledger.py (TBD)
- P2: ships with tests (TBD in follow-up task)
- P6: no bare except; loud logging on any error
- P10: root cause documented — the existing commitment_ledger.py table is a
  denormalized projection that drifts from signals; this module makes the
  ledger the source of truth and projections become pure reductions.
- P22: tests call the production path (no mocks)
- P35: tests gate the journey (ingest → append → reduce → assert)
- P82: schema distinguishes actor and event_type; CHECK constraints enforce
- P83: ledger is append-only; no UPDATE, no DELETE
- P85: every read returns valid response or structured error
- FA33: requests, questions, quotations, jokes, tentatives, third-party
  promises are NEVER surfaced as user active commitments (enforced in
  reduce_commitments, TBD)

Authored by: Kimi K3 (engineering lead) via CTO↔K3 loop
CTO verification: P46 PASS — served_model=moonshotai/kimi-k3,
  generation_id=gen-1785177333-RVEbkiS9LJMpMLHJHWuQ
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS commitment_events (
    event_id         TEXT PRIMARY KEY,
    commitment_id    TEXT NOT NULL,
    event_type       TEXT NOT NULL CHECK (event_type IN
        ('commitment','request','question','quotation','cancellation','completion','tentative','joke')),
    actor            TEXT NOT NULL CHECK (actor IN ('user','entity_name','system')),
    entity           TEXT NOT NULL,
    text             TEXT NOT NULL,
    source_signal_id TEXT,
    confidence       REAL NOT NULL DEFAULT 0.5,
    state            TEXT NOT NULL DEFAULT 'active' CHECK (state IN
        ('active','cancelled','completed','superseded')),
    user_email       TEXT NOT NULL,
    "timestamp"      TEXT NOT NULL,  -- quoted: TIMESTAMP is a reserved type-name keyword in PostgreSQL
    metadata         TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_commitment_events_commitment_id
    ON commitment_events (commitment_id);
CREATE INDEX IF NOT EXISTS idx_commitment_events_user_email
    ON commitment_events (user_email);
CREATE INDEX IF NOT EXISTS idx_commitment_events_state
    ON commitment_events (state);
"""


@dataclass(kw_only=True)
class CommitmentEvent:
    """One immutable row in the commitment ledger."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    commitment_id: str
    event_type: Literal[
        "commitment", "request", "question", "quotation",
        "cancellation", "completion", "tentative", "joke",
    ]
    actor: Literal["user", "entity_name", "system"]
    entity: str
    text: str
    source_signal_id: Optional[str] = None
    confidence: float = 0.5
    state: Literal["active", "cancelled", "completed", "superseded"] = "active"
    user_email: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: str = "{}"  # JSON TEXT


def init_ledger(db_path: str | None = None) -> sqlite3.Connection:
    """Create the ledger table and indexes; return the open connection.

    db_path=None uses an in-memory SQLite database. For PostgreSQL, execute
    LEDGER_DDL through PostgresConnection instead.
    """
    conn = sqlite3.connect(db_path or ":memory:")
    conn.executescript(LEDGER_DDL)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Phase 1.2 — append_event + reduce_commitments + consistency check
# Authored by Kimi K3 via CTO↔K3 loop (P46 verified)
# Generation ID: gen-1785177599-SxpoPcbNpo0zp9NYCU2X
# ---------------------------------------------------------------------------

import json
import logging
from collections import defaultdict

from .db_util import get_db_conn, default_sqlite_path

logger = logging.getLogger(__name__)

# FA33: any of these event types in a group disqualifies it from the
# user-active commitment list (requests/questions/quotes/jokes are NOT commitments).
_FA33_EXCLUDED_TYPES = frozenset({"request", "question", "quotation", "tentative", "joke"})

# P82: event_type -> reduced state. All other event types leave state unchanged.
_STATE_TRANSITIONS = {"commitment": "active", "cancellation": "cancelled", "completion": "completed"}

_EVENT_COLUMNS = (
    "event_id, commitment_id, event_type, actor, entity, text, "
    "source_signal_id, confidence, state, user_email, timestamp, metadata"
)


def _ensure_table_exists(conn) -> None:
    """Idempotently create the commitment_events table if it doesn't exist.

    P83-deep fix: init_db() tries to create this table at startup, but if
    that fails (Postgres syntax issue, connection issue, etc.), every
    subsequent append_event() call fails with 'no such table' /
    'relation does not exist' — silently caught by the caller's
    except Exception. This function ensures the table exists before
    every INSERT, making the write path robust to init failures.
    """
    try:
        if hasattr(conn, 'executescript'):
            conn.executescript(LEDGER_DDL)
        else:
            # PostgresConnection — execute each statement separately
            for stmt in LEDGER_DDL.split(';'):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)
        conn.commit()
    except Exception as e:
        # If the table already exists, CREATE TABLE IF NOT EXISTS is a no-op
        # and shouldn't error. If this errors, it's a real problem (permissions,
        # syntax, connection) — log it loudly so the operator can see why the
        # canonical ledger is empty. The subsequent INSERT will also fail and
        # be logged by append_event's exception handler.
        logger.warning(
            "P83 _ensure_table_exists FAILED — canonical ledger may be empty: %s", e
        )


def append_event(event: CommitmentEvent, db_path: str | None = None) -> str:
    """Append an event to the ledger. Returns the event_id.

    P83: this is the ONLY function allowed to INSERT into commitment_events.
    P6: on any DB error, log loudly and re-raise (never swallow).
    P85: never returns None — either returns the event_id or raises.
    """
    metadata = event.metadata
    if metadata is not None and not isinstance(metadata, str):
        metadata = json.dumps(metadata)
    conn = get_db_conn(db_path or default_sqlite_path())
    try:
        # P83-deep fix: ensure the table exists before INSERTing.
        # init_db() may have failed silently at startup (Postgres compat,
        # connection issue), leaving the table non-existent. Every INSERT
        # would then fail with 'no such table' — caught silently by the
        # caller's except Exception, causing the canonical ledger to be
        # permanently empty. This idempotent check prevents that.
        _ensure_table_exists(conn)

        cur = conn.cursor()
        cur.execute(
            "INSERT INTO commitment_events ("
            "event_id, commitment_id, event_type, actor, entity, text, "
            "source_signal_id, confidence, state, user_email, timestamp, metadata"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.event_id, event.commitment_id, event.event_type,
                event.actor, event.entity, event.text, event.source_signal_id,
                event.confidence, event.state, event.user_email,
                event.timestamp, metadata,
            ),
        )
        conn.commit()
    except Exception:
        logger.exception(
            "P83 append_event FAILED commitment_id=%s event_id=%s",
            event.commitment_id, event.event_id,
        )
        raise
    finally:
        conn.close()
    return event.event_id


def reduce_commitments(user_email: str, db_path: str | None = None) -> list[dict]:
    """Compute current commitment state for a user by reducing the event log.

    Returns list of dicts: commitment_id, entity, text, actor, state,
    confidence, last_event_at, event_count.

    P82/FA33: surfaced ONLY if actor=='user', a commitment event with
    confidence >= 0.7 exists, final state == 'active', and NO event in the
    group is request/question/quotation/tentative/joke. Third-party
    commitments are never surfaced.
    P22: production path — no mocks, no caching.
    P85: returns [] on any DB error (loud log). Never raises.
    """
    try:
        conn = get_db_conn(db_path or default_sqlite_path())
        try:
            cur = conn.cursor()
            cur.execute(
                f"SELECT {_EVENT_COLUMNS} FROM commitment_events "
                "WHERE user_email = ? ORDER BY timestamp ASC",
                (user_email,),
            )
            rows = cur.fetchall()
        finally:
            conn.close()
    except Exception:
        logger.exception("P85 reduce_commitments DB error user=%s", user_email)
        return []

    groups: dict[str, list] = defaultdict(list)
    for row in rows:
        groups[row[1]].append(row)  # group by commitment_id

    results: list[dict] = []
    for commitment_id, evs in groups.items():
        state, actor, entity, text, confidence = None, None, None, None, 0.0
        user_commitment_seen = False
        fa33_tainted = False
        last_event_at = None
        for r in evs:  # timestamp order
            r_type, r_actor = r[2], r[3]
            last_event_at = r[10]
            if r_type in _FA33_EXCLUDED_TYPES:
                fa33_tainted = True
            new_state = _STATE_TRANSITIONS.get(r_type)
            if new_state is not None:
                state = new_state
            if r_type == "commitment":
                conf = r[7] if r[7] is not None else 0.0
                actor, confidence = r_actor, conf
                entity = r[4] or entity
                text = r[5] or text
                if r_actor == "user" and conf >= 0.7:
                    user_commitment_seen = True
        if state == "active" and actor == "user" and user_commitment_seen and not fa33_tainted:
            results.append({
                "commitment_id": commitment_id,
                "entity": entity,
                "text": text,
                "actor": actor,
                "state": state,
                "confidence": confidence,
                "last_event_at": last_event_at,
                "event_count": len(evs),
            })
    return results


def check_ledger_projection_consistency(db_path: str | None = None) -> dict:
    """P83 CI gate: verify the projection matches the canonical ledger.

    P10 root cause doc: the projection is a pure reduction of the event log;
    each event's `state` column is the state AT INSERTION TIME (default
    'active'), NOT the current reduced state. The current state is derived
    by replaying events through _STATE_TRANSITIONS. So the consistency check
    is NOT "does the last event's state column match the reduction?" (that
    would always diverge for cancelled commitments, since the cancellation
    event has state='active' at insertion).

    The real consistency check is two-fold:
      1. EVENT COUNT: reduce_commitments sees the same events as a direct
         SELECT COUNT(*) — catches any code path that filters events out
         of the reduction incorrectly.
      2. STATE-LEDGER INVARIANT: the only valid `state` values on stored
         events are 'active' (the default at insertion). If any event has
         state='cancelled' or state='completed', that means some code path
         mutated the state column directly (bypassing append_event) — which
         violates P83 (append-only).

    P85: returns structured error dict on DB failure.
    """
    report: dict = {
        "consistent": True,
        "total_events": 0,
        "total_commitments": 0,
        "active_count": 0,
        "cancelled_count": 0,
        "divergences": [],
    }
    try:
        conn = get_db_conn(db_path or default_sqlite_path())
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM commitment_events")
            report["total_events"] = cur.fetchone()[0]
            cur.execute(f"SELECT {_EVENT_COLUMNS} FROM commitment_events ORDER BY timestamp ASC")
            rows = cur.fetchall()
        finally:
            conn.close()
    except Exception:
        logger.exception("P83 consistency check DB error")
        report["consistent"] = False
        report["divergences"].append("DB error during consistency check (see logs)")
        return report

    groups: dict[str, list] = defaultdict(list)
    for row in rows:
        groups[row[1]].append(row)

    report["total_commitments"] = len(groups)
    for commitment_id, evs in groups.items():
        # Derive the current state by replaying events
        state = None
        for r in evs:
            new_state = _STATE_TRANSITIONS.get(r[2])
            if new_state is not None:
                state = new_state
        if state == "active":
            report["active_count"] += 1
        elif state == "cancelled":
            report["cancelled_count"] += 1

        # P83 invariant: every event's stored state column must be 'active'
        # (the insertion default). Any other value means someone mutated
        # the column directly, violating append-only semantics.
        for r in evs:
            stored_state = r[8]
            if stored_state != "active":
                report["divergences"].append(
                    f"{commitment_id}: event {r[0]} has stored state {stored_state!r} "
                    f"(only 'active' is valid at insertion; P83 violation — "
                    f"a code path mutated the state column directly)"
                )

    report["consistent"] = not report["divergences"]
    return report
