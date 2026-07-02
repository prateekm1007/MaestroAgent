"""
SQLite-backed CheckpointStore for resumable historical imports.

Design goals:
  - Survives process restart (persisted to disk)
  - Per-job, per-provider, per-resource checkpoints
  - Atomic writes (single-statement SQL transactions)
  - Idempotent (re-saving the same checkpoint is safe)
  - Queryable (list active jobs, history, etc.)

Schema:
  import_jobs          — top-level import job (one per "start_import" call)
  import_checkpoints   — per-provider, per-resource progress within a job
  oauth_credentials    — encrypted OAuth tokens per provider
"""

from __future__ import annotations

import json
import logging
from maestro_db import sqlite_compat as sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

logger = logging.getLogger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS import_jobs (
    job_id              TEXT PRIMARY KEY,
    org_id              TEXT NOT NULL DEFAULT 'default',
    status              TEXT NOT NULL,
    providers           TEXT NOT NULL,
    since               TEXT,
    started_at          TEXT NOT NULL,
    completed_at        TEXT,
    total_signals       INTEGER NOT NULL DEFAULT 0,
    error               TEXT
);

CREATE TABLE IF NOT EXISTS import_checkpoints (
    checkpoint_id       TEXT PRIMARY KEY,
    job_id              TEXT NOT NULL,
    provider            TEXT NOT NULL,
    resource_type       TEXT NOT NULL,
    sync_mode           TEXT NOT NULL,
    last_page           INTEGER NOT NULL DEFAULT 0,
    last_cursor         TEXT NOT NULL DEFAULT '',
    last_timestamp      TEXT,
    total_pages_estimated INTEGER NOT NULL DEFAULT 0,
    pages_completed     INTEGER NOT NULL DEFAULT 0,
    signals_produced    INTEGER NOT NULL DEFAULT 0,
    errors              INTEGER NOT NULL DEFAULT 0,
    started_at          TEXT NOT NULL,
    last_updated        TEXT NOT NULL,
    completed           INTEGER NOT NULL DEFAULT 0,
    UNIQUE (job_id, provider, resource_type),
    FOREIGN KEY (job_id) REFERENCES import_jobs(job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_job ON import_checkpoints(job_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_provider ON import_checkpoints(provider);
CREATE INDEX IF NOT EXISTS idx_import_jobs_org ON import_jobs(org_id);

CREATE TABLE IF NOT EXISTS oauth_credentials (
    provider            TEXT NOT NULL,
    org_id              TEXT NOT NULL DEFAULT 'default',
    access_token        TEXT NOT NULL,
    refresh_token       TEXT,
    token_type          TEXT NOT NULL DEFAULT 'Bearer',
    expires_at          TEXT,
    scopes              TEXT,
    metadata            TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    PRIMARY KEY (provider, org_id)
);

CREATE INDEX IF NOT EXISTS idx_oauth_org ON oauth_credentials(org_id);

CREATE TABLE IF NOT EXISTS provider_connections (
    provider            TEXT NOT NULL,
    org_id              TEXT NOT NULL DEFAULT 'default',
    connected           INTEGER NOT NULL DEFAULT 0,
    connected_at        TEXT,
    metadata            TEXT,
    PRIMARY KEY (provider, org_id)
);

CREATE INDEX IF NOT EXISTS idx_connections_org ON provider_connections(org_id);
"""


class CheckpointStore:
    """
    Persistent store for import jobs, checkpoints, and OAuth credentials.

    Thread-safe via a single re-entrant lock around the connection (SQLite
    serializes writes anyway; we just need to avoid cursor reuse races).
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._connect()

    # ─── Connection management ───

    def _connect(self) -> None:
        uri = self.db_path == ":memory:"
        self._conn = sqlite3.connect(
            self.db_path if not uri else "file::memory:?cache=shared",
            uri=uri,
            check_same_thread=False,
            isolation_level=None,  # autocommit; we manage txns explicitly
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        assert self._conn is not None
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute("BEGIN")
                yield cur
                cur.execute("COMMIT")
            except Exception:
                cur.execute("ROLLBACK")
                raise

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ─── Job lifecycle ───

    def create_job(
        self,
        job_id: str | None = None,
        providers: list[str] | None = None,
        since: str | None = None,
        org_id: str = "default",
    ) -> str:
        """Create a new import job. Returns the job_id."""
        job_id = job_id or str(uuid4())
        providers = providers or []
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO import_jobs
                   (job_id, org_id, status, providers, since, started_at, total_signals)
                   VALUES (?, ?, 'pending', ?, ?, ?, 0)""",
                (job_id, org_id, json.dumps(providers), since,
                 datetime.now(timezone.utc).isoformat()),
            )
        logger.info("Created import job %s for providers=%s", job_id, providers)
        return job_id

    def update_job_status(
        self,
        job_id: str,
        status: str,
        error: str | None = None,
        total_signals: int | None = None,
    ) -> None:
        sets = ["status = ?"]
        args: list[Any] = [status]
        if error is not None:
            sets.append("error = ?")
            args.append(error)
        if total_signals is not None:
            sets.append("total_signals = ?")
            args.append(total_signals)
        if status in ("completed", "failed", "cancelled"):
            sets.append("completed_at = ?")
            args.append(datetime.now(timezone.utc).isoformat())
        args.append(job_id)
        with self._cursor() as cur:
            cur.execute(
                f"UPDATE import_jobs SET {', '.join(sets)} WHERE job_id = ?",
                args,
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM import_jobs WHERE job_id = ?", (job_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    def list_jobs(self, limit: int = 50, org_id: str = "default") -> list[dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM import_jobs WHERE org_id = ? ORDER BY started_at DESC LIMIT ?",
                (org_id, limit),
            )
            return [self._row_to_job(r) for r in cur.fetchall()]

    # ─── Checkpoint CRUD ───

    def save_checkpoint(self, cp: dict[str, Any]) -> None:
        """Upsert a checkpoint. Idempotent."""
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO import_checkpoints
                   (checkpoint_id, job_id, provider, resource_type, sync_mode,
                    last_page, last_cursor, last_timestamp, total_pages_estimated,
                    pages_completed, signals_produced, errors, started_at,
                    last_updated, completed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(job_id, provider, resource_type) DO UPDATE SET
                    last_page = excluded.last_page,
                    last_cursor = excluded.last_cursor,
                    last_timestamp = excluded.last_timestamp,
                    total_pages_estimated = excluded.total_pages_estimated,
                    pages_completed = excluded.pages_completed,
                    signals_produced = excluded.signals_produced,
                    errors = excluded.errors,
                    last_updated = excluded.last_updated,
                    completed = excluded.completed
                   """,
                (
                    cp.get("checkpoint_id", str(uuid4())),
                    cp["job_id"],
                    cp["provider"],
                    cp["resource_type"],
                    cp.get("sync_mode", "full"),
                    cp.get("last_page", 0),
                    cp.get("last_cursor", ""),
                    cp.get("last_timestamp"),
                    cp.get("total_pages_estimated", 0),
                    cp.get("pages_completed", 0),
                    cp.get("signals_produced", 0),
                    cp.get("errors", 0),
                    cp.get("started_at", datetime.now(timezone.utc).isoformat()),
                    cp.get("last_updated", datetime.now(timezone.utc).isoformat()),
                    1 if cp.get("completed", False) else 0,
                ),
            )

    def load_checkpoint(
        self, job_id: str, provider: str, resource_type: str = "all"
    ) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(
                """SELECT * FROM import_checkpoints
                   WHERE job_id = ? AND provider = ? AND resource_type = ?""",
                (job_id, provider, resource_type),
            )
            row = cur.fetchone()
            return self._row_to_checkpoint(row) if row else None

    def list_checkpoints(self, job_id: str) -> list[dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM import_checkpoints WHERE job_id = ?",
                (job_id,),
            )
            return [self._row_to_checkpoint(r) for r in cur.fetchall()]

    def list_incomplete_checkpoints(self, job_id: str) -> list[dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(
                """SELECT * FROM import_checkpoints
                   WHERE job_id = ? AND completed = 0
                   ORDER BY provider""",
                (job_id,),
            )
            return [self._row_to_checkpoint(r) for r in cur.fetchall()]

    # ─── OAuth credentials ───

    def save_credentials(
        self,
        provider: str,
        access_token: str,
        refresh_token: str | None = None,
        token_type: str = "Bearer",
        expires_at: str | None = None,
        scopes: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        org_id: str = "default",
    ) -> None:
        # Round 49 C2 fix: encrypt OAuth tokens at rest.
        # Round 52 Fix 4: scope by org_id for multi-tenant isolation.
        from maestro_auth.security import EncryptionManager
        enc = EncryptionManager()
        encrypted_access = enc.encrypt(access_token)
        encrypted_refresh = enc.encrypt(refresh_token) if refresh_token else None

        now = datetime.now(timezone.utc).isoformat()
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO oauth_credentials
                   (provider, org_id, access_token, refresh_token, token_type, expires_at,
                    scopes, metadata, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(provider, org_id) DO UPDATE SET
                    access_token = excluded.access_token,
                    refresh_token = excluded.refresh_token,
                    token_type = excluded.token_type,
                    expires_at = excluded.expires_at,
                    scopes = excluded.scopes,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
                   """,
                (
                    provider, org_id, encrypted_access, encrypted_refresh, token_type, expires_at,
                    json.dumps(scopes or []), json.dumps(metadata or {}), now, now,
                ),
            )

    def load_credentials(self, provider: str, org_id: str = "default") -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM oauth_credentials WHERE provider = ? AND org_id = ?",
                (provider, org_id),
            )
            row = cur.fetchone()
            if not row:
                return None
            # Round 49 C2 fix: decrypt OAuth tokens on read.
            from maestro_auth.security import EncryptionManager
            enc = EncryptionManager()
            try:
                access_token = enc.decrypt(row["access_token"])
            except Exception:
                # If decryption fails, the token may be legacy plaintext
                # (stored before the encryption fix). Return None to force
                # re-authentication rather than returning plaintext.
                access_token = None
            try:
                refresh_token = enc.decrypt(row["refresh_token"]) if row["refresh_token"] else None
            except Exception:
                refresh_token = None
            return {
                "provider": row["provider"],
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": row["token_type"],
                "expires_at": row["expires_at"],
                "scopes": json.loads(row["scopes"] or "[]"),
                "metadata": json.loads(row["metadata"] or "{}"),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

    def delete_credentials(self, provider: str, org_id: str = "default") -> None:
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM oauth_credentials WHERE provider = ? AND org_id = ?",
                (provider, org_id),
            )

    def list_credentials(self) -> list[dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM oauth_credentials ORDER BY provider")
            return [dict(r) for r in cur.fetchall()]

    # ─── Connection state ───

    def set_connection(
        self,
        provider: str,
        connected: bool,
        org_id: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO provider_connections
                   (provider, org_id, connected, connected_at, metadata)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(provider, org_id) DO UPDATE SET
                    connected = excluded.connected,
                    connected_at = excluded.connected_at,
                    metadata = excluded.metadata
                   """,
                (
                    provider, org_id, 1 if connected else 0,
                    now if connected else None,
                    json.dumps(metadata or {}),
                ),
            )

    def get_connection(self, provider: str, org_id: str = "default") -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM provider_connections WHERE provider = ? AND org_id = ?",
                (provider, org_id),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "provider": row["provider"],
                "connected": bool(row["connected"]),
                "connected_at": row["connected_at"],
                "org_id": row["org_id"],
                "metadata": json.loads(row["metadata"] or "{}"),
            }

    def list_connections(self, org_id: str = "default") -> list[dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM provider_connections WHERE org_id = ? ORDER BY provider", (org_id,))
            return [
                {
                    "provider": r["provider"],
                    "connected": bool(r["connected"]),
                    "connected_at": r["connected_at"],
                    "org_id": r["org_id"],
                    "metadata": json.loads(r["metadata"] or "{}"),
                }
                for r in cur.fetchall()
            ]

    # ─── Helpers ───

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_id": row["job_id"],
            "status": row["status"],
            "providers": json.loads(row["providers"]),
            "since": row["since"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "total_signals": row["total_signals"],
            "error": row["error"],
        }

    @staticmethod
    def _row_to_checkpoint(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "checkpoint_id": row["checkpoint_id"],
            "job_id": row["job_id"],
            "provider": row["provider"],
            "resource_type": row["resource_type"],
            "sync_mode": row["sync_mode"],
            "last_page": row["last_page"],
            "last_cursor": row["last_cursor"],
            "last_timestamp": row["last_timestamp"],
            "total_pages_estimated": row["total_pages_estimated"],
            "pages_completed": row["pages_completed"],
            "signals_produced": row["signals_produced"],
            "errors": row["errors"],
            "started_at": row["started_at"],
            "last_updated": row["last_updated"],
            "completed": bool(row["completed"]),
            "progress_pct": round(
                row["pages_completed"] / max(1, row["total_pages_estimated"]) * 100, 1
            ),
        }
