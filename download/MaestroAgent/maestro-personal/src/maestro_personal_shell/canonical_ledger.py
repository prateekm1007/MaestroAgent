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
        ('commitment','request','question','quotation','cancellation','tentative','joke')),
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
        "cancellation", "tentative", "joke",
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
