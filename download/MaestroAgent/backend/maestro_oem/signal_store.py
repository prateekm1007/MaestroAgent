"""P0 fix: SignalStore — SQLite-backed persistence for OEM signals.

Uploaded audit finding (C-01):
> The core OEM cognitive state — the ExecutionModel — is entirely in-memory.
> On server restart, all organizational knowledge is lost.

The fix: persist the SIGNALS (the source data) to SQLite. The ExecutionModel
is a derivative of the signals — it's rebuilt by re-ingesting them. We don't
serialize the model itself; we persist the signals and re-ingest on startup.

Architecture:
  - Signals are the primary data (facts)
  - The model is derived (patterns, laws, learning objects)
  - On startup: load signals → re-ingest → model is restored

Usage:
    store = SignalStore("signals.db")
    store.save_signal(signal)
    signals = store.load_all_signals()
    store.close()
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    signal_type TEXT NOT NULL,
    provider TEXT NOT NULL,
    actor TEXT,
    artifact TEXT,
    timestamp TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_signals_provider ON signals(provider);
"""


class SignalStore:
    """SQLite-backed store for ExecutionSignal objects.

    Signals are serialized as JSON (via Pydantic model_dump_json).
    On load, they're deserialized via model_validate_json.

    Usage:
        store = SignalStore("signals.db")
        store.save_signal(signal)
        signals = store.load_all_signals()
        store.close()
    """

    def __init__(self, db_path: str | Path = "") -> None:
        self._db_path = str(db_path) if db_path else ":memory:"
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._connect()

    def _connect(self) -> None:
        try:
            from maestro_db import sqlite_compat as sqlite3_compat
            self._conn = sqlite3_compat.connect(self._db_path, isolation_level=None)
            self._conn.row_factory = sqlite3_compat.Row
        except Exception:
            self._conn = sqlite3.connect(self._db_path, isolation_level=None)
            self._conn.row_factory = sqlite3.Row

        try:
            cursor = self._conn.cursor()
            for stmt in _SCHEMA.strip().split(';'):
                stmt = stmt.strip()
                if stmt:
                    cursor.execute(stmt)
        except Exception as e:
            logger.warning("SignalStore schema init: %s", e)

    def save_signal(self, signal: Any) -> None:
        """Persist a signal to SQLite. Upsert by signal_id."""
        from maestro_oem.signal import ExecutionSignal

        with self._lock:
            assert self._conn is not None
            sig_json = signal.model_dump_json()
            sig_id = str(signal.signal_id)
            sig_type = signal.type.value if hasattr(signal.type, 'value') else str(signal.type)
            provider = signal.provider.value if hasattr(signal.provider, 'value') else str(signal.provider)
            actor = signal.actor or ""
            artifact = signal.artifact or ""
            timestamp = signal.timestamp.isoformat() if hasattr(signal.timestamp, 'isoformat') else str(signal.timestamp)

            self._conn.execute(
                """INSERT OR REPLACE INTO signals
                   (signal_id, signal_type, provider, actor, artifact, timestamp, data)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (sig_id, sig_type, provider, actor, artifact, timestamp, sig_json),
            )

    def load_all_signals(self) -> list:
        """Load all signals from SQLite. Returns list of ExecutionSignal."""
        from maestro_oem.signal import ExecutionSignal

        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute("SELECT data FROM signals ORDER BY timestamp")
            rows = cur.fetchall()
            signals = []
            for row in rows:
                try:
                    data_str = row["data"] if isinstance(row, dict) else row[0]
                    sig = ExecutionSignal.model_validate_json(data_str)
                    signals.append(sig)
                except Exception as e:
                    logger.warning("SignalStore: failed to deserialize signal: %s", e)
                    continue
            return signals

    def load_signals_by_provider(self, provider: str) -> list:
        """Load signals from a specific provider."""
        from maestro_oem.signal import ExecutionSignal

        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute("SELECT data FROM signals WHERE provider = ? ORDER BY timestamp", (provider,))
            rows = cur.fetchall()
            signals = []
            for row in rows:
                try:
                    data_str = row["data"] if isinstance(row, dict) else row[0]
                    sig = ExecutionSignal.model_validate_json(data_str)
                    signals.append(sig)
                except Exception:
                    continue
            return signals

    def signal_count(self) -> int:
        """Count of persisted signals."""
        with self._lock:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute("SELECT COUNT(*) FROM signals")
            row = cur.fetchone()
            if row is None:
                return 0
            if isinstance(row, dict):
                return list(row.values())[0]
            try:
                return row[0]
            except (KeyError, IndexError):
                return 0

    def clear(self) -> None:
        """Clear all signals (for testing)."""
        with self._lock:
            assert self._conn is not None
            self._conn.execute("DELETE FROM signals")

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
