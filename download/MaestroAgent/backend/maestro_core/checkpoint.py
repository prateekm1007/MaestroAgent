"""Checkpoint store — per-step persistence for crash recovery and replay.

Every node invocation writes a checkpoint before and after. This makes a
run fully reconstructable from the store alone, enables time-travel
debugging (fork from any past step), and gives us free resume-on-crash.

The default backend is SQLite. The schema is intentionally simple:

    steps(
        run_id, step_id, parent_step_id, revision, iteration,
        node_id, status, state_json, ts
    )

Plus an audit table:

    audit(
        run_id, ts, kind, payload_json, prev_hash, hash
    )

The audit table is hash-chained: each row's `hash` is
sha256(prev_hash || canonical_json(payload)). Tampering with any row
breaks the chain and is detectable by `audit_verify()`.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from maestro_core.state import State


@dataclass
class Step:
    run_id: str
    step_id: str
    parent_step_id: str | None
    revision: int
    iteration: int
    node_id: str | None
    status: str
    state_json: str
    ts: str


class CheckpointStore(ABC):
    """Abstract checkpoint store."""

    @abstractmethod
    async def save(self, state: State, node_id: str | None, status: str) -> None: ...

    @abstractmethod
    async def load(self, run_id: str, step_id: str) -> State | None: ...

    @abstractmethod
    async def latest(self, run_id: str) -> State | None: ...

    @abstractmethod
    async def history(self, run_id: str) -> list[Step]: ...

    @abstractmethod
    async def audit(self, run_id: str, kind: str, payload: dict[str, Any]) -> None: ...

    @abstractmethod
    async def audit_log(self, run_id: str) -> list[dict[str, Any]]: ...


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _chain_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        (prev_hash + _canonical_json(payload)).encode("utf-8")
    ).hexdigest()


class SQLiteCheckpointStore(CheckpointStore):
    """SQLite-backed checkpoint store. Default for v0.1."""

    def __init__(self, db_path: str | Path = "maestro.db") -> None:
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None
        self._init_schema()

    def _conn_get(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_schema(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS steps(
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL PRIMARY KEY,
                    parent_step_id TEXT,
                    revision INTEGER NOT NULL,
                    iteration INTEGER NOT NULL,
                    node_id TEXT,
                    status TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    ts TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_steps_run ON steps(run_id, ts);

                CREATE TABLE IF NOT EXISTS audit(
                    run_id TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    seq INTEGER PRIMARY KEY AUTOINCREMENT
                );
                CREATE INDEX IF NOT EXISTS idx_audit_run ON audit(run_id, ts);

                CREATE TABLE IF NOT EXISTS audit_heads(
                    run_id TEXT PRIMARY KEY,
                    last_hash TEXT NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    async def save(self, state: State, node_id: str | None, status: str) -> None:
        conn = self._conn_get()
        conn.execute(
            "INSERT OR REPLACE INTO steps "
            "(run_id, step_id, parent_step_id, revision, iteration, node_id, status, state_json, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                state.run_id,
                state.step_id,
                state.parent_step_id,
                state.revision,
                state.iteration,
                node_id,
                status,
                state.model_dump_json(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()

    async def load(self, run_id: str, step_id: str) -> State | None:
        conn = self._conn_get()
        row = conn.execute(
            "SELECT state_json FROM steps WHERE run_id = ? AND step_id = ?",
            (run_id, step_id),
        ).fetchone()
        if row is None:
            return None
        return State.model_validate_json(row["state_json"])

    async def latest(self, run_id: str) -> State | None:
        conn = self._conn_get()
        row = conn.execute(
            "SELECT state_json FROM steps WHERE run_id = ? ORDER BY ts DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return State.model_validate_json(row["state_json"])

    async def history(self, run_id: str) -> list[Step]:
        conn = self._conn_get()
        rows = conn.execute(
            "SELECT run_id, step_id, parent_step_id, revision, iteration, "
            "node_id, status, state_json, ts "
            "FROM steps WHERE run_id = ? ORDER BY ts ASC",
            (run_id,),
        ).fetchall()
        return [
            Step(
                run_id=r["run_id"],
                step_id=r["step_id"],
                parent_step_id=r["parent_step_id"],
                revision=r["revision"],
                iteration=r["iteration"],
                node_id=r["node_id"],
                status=r["status"],
                state_json=r["state_json"],
                ts=r["ts"],
            )
            for r in rows
        ]

    async def audit(self, run_id: str, kind: str, payload: dict[str, Any]) -> None:
        conn = self._conn_get()
        head = conn.execute(
            "SELECT last_hash FROM audit_heads WHERE run_id = ?", (run_id,)
        ).fetchone()
        prev_hash = head["last_hash"] if head else "0" * 64
        h = _chain_hash(prev_hash, payload)
        conn.execute(
            "INSERT INTO audit (run_id, ts, kind, payload_json, prev_hash, hash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_id,
                datetime.now(timezone.utc).isoformat(),
                kind,
                _canonical_json(payload),
                prev_hash,
                h,
            ),
        )
        conn.execute(
            "INSERT OR REPLACE INTO audit_heads (run_id, last_hash) VALUES (?, ?)",
            (run_id, h),
        )
        conn.commit()

    async def audit_log(self, run_id: str) -> list[dict[str, Any]]:
        conn = self._conn_get()
        rows = conn.execute(
            "SELECT ts, kind, payload_json, hash FROM audit WHERE run_id = ? ORDER BY seq ASC",
            (run_id,),
        ).fetchall()
        return [
            {
                "ts": r["ts"],
                "kind": r["kind"],
                "payload": json.loads(r["payload_json"]),
                "hash": r["hash"],
            }
            for r in rows
        ]

    def audit_verify(self, run_id: str) -> bool:
        """Verify the audit chain is intact."""
        conn = self._conn_get()
        rows = conn.execute(
            "SELECT prev_hash, payload_json, hash FROM audit WHERE run_id = ? ORDER BY seq ASC",
            (run_id,),
        ).fetchall()
        prev = "0" * 64
        for r in rows:
            if r["prev_hash"] != prev:
                return False
            expected = _chain_hash(prev, json.loads(r["payload_json"]))
            if expected != r["hash"]:
                return False
            prev = r["hash"]
        return True
