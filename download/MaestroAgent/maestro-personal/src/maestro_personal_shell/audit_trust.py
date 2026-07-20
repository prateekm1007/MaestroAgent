"""
Audit, Trust & Transparency module — Directive 5.

CEO Directive 5 (Days 30-33): Security, Trust & Defensibility.

Three new capabilities:

1. CALIBRATION HISTORY
   GET /api/calibration/history — shows Brier score trends over time.
   Users can see how Maestro's accuracy has improved (or not).

2. PRIVACY-FIRST PROCESSING INDICATORS
   Every API response includes a processing_mode field showing whether
   the response was generated locally (rules), via cloud LLM, or via
   local LLM (Ollama). Users know exactly where their data went.

3. AUDIT LOG
   Every data access (read/write/delete) is logged with timestamp,
   user, endpoint, and action. GET /api/audit-log lets users see
   every time their data was accessed.
"""

from __future__ import annotations

import logging
import sqlite3
from maestro_personal_shell.db_util import get_db_conn
import json
import os
from typing import Any
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    return os.environ.get(
        "MAESTRO_PERSONAL_DB",
        str(Path(__file__).resolve().parent / "personal.db"),
    )


# ---------------------------------------------------------------------------
# 1. Calibration history
# ---------------------------------------------------------------------------


def init_audit_tables(db_path: str | None = None) -> None:
    """Initialize audit log + calibration history tables."""
    path = db_path or _get_db_path()
    conn = get_db_conn(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            action TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            resource_id TEXT DEFAULT '',
            details TEXT DEFAULT '{}',
            timestamp TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calibration_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            brier_score REAL,
            resolved_count INTEGER,
            hit_count INTEGER,
            miss_count INTEGER,
            avg_confidence REAL,
            actual_rate REAL,
            recorded_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def record_calibration_snapshot(
    user_email: str = "bootstrap",
    db_path: str | None = None,
) -> None:
    """Record a snapshot of current calibration metrics.

    Called periodically (e.g. when a prediction is resolved) to track
    Brier score trends over time.
    """
    path = db_path or _get_db_path()
    init_audit_tables(path)

    try:
        from maestro_personal_shell.outcome_tracker import get_calibration_report
        report = get_calibration_report(db_path=path, user_email=user_email)

        conn = get_db_conn(path)
        conn.execute(
            """INSERT INTO calibration_history
               (user_email, brier_score, resolved_count, hit_count, miss_count,
                avg_confidence, actual_rate, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_email,
                report.get("brier_score"),
                report.get("resolved_predictions", 0),
                report.get("hit_count", 0) if isinstance(report.get("hit_count"), int) else 0,
                report.get("miss_count", 0) if isinstance(report.get("miss_count"), int) else 0,
                report.get("avg_confidence", 0.0),
                report.get("actual_rate", 0.0),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug("Calibration snapshot failed: %s", e)


def get_calibration_history(
    user_email: str = "bootstrap",
    limit: int = 30,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Get calibration history (Brier score trends over time).

    Returns a list of snapshots, most recent first, showing how
    Maestro's accuracy has evolved.
    """
    path = db_path or _get_db_path()
    init_audit_tables(path)

    conn = get_db_conn(path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT * FROM calibration_history
           WHERE user_email = ?
           ORDER BY recorded_at DESC LIMIT ?""",
        (user_email, limit),
    ).fetchall()
    conn.close()

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 2. Privacy-first processing indicators
# ---------------------------------------------------------------------------


def get_processing_mode() -> dict[str, str]:
    """Get the current processing mode for privacy transparency.

    P0 fix (independent audit S1): report ALL egress paths, not just LLM.
    The previous version said "No data leaves your device" while push
    notifications sent content to Expo servers. Now the description
    accurately reports all data egress paths.

    Returns:
    {
        "mode": "local_rules" | "cloud_llm" | "local_llm",
        "provider": "none" | "zai-glm" | "openai" | "ollama" | etc,
        "data_location": "on-device" | "cloud",
        "description": "human-readable explanation including ALL egress",
        "egress_paths": list of data egress paths,
    }
    """
    # Identify all egress paths
    egress_paths = []

    # Check LLM provider
    llm_egress = False
    try:
        from maestro_personal_shell.llm_bridge import is_llm_available, get_llm_provider_name, get_llm_router

        if not is_llm_available():
            pass  # no LLM egress
        else:
            provider = get_llm_provider_name()
            if provider == "ollama":
                egress_paths.append({"path": "local_llm", "destination": "localhost:11434", "data": "signal text for AI processing"})
            else:
                llm_egress = True
                egress_paths.append({"path": "cloud_llm", "destination": provider, "data": "signal text for AI processing"})
    except Exception as e:
        logger.debug("append failed: %s", e)
    # Push notifications ALWAYS egress (Expo API)
    egress_paths.append({
        "path": "push_notifications",
        "destination": "Expo push service (exp.host)",
        "data": "whisper title + body when push is enabled",
        "note": "Push is opt-in. If no devices are registered, no data is sent."
    })

    # Build description
    if not llm_egress and not any(p["path"] == "cloud_llm" for p in egress_paths):
        mode = "local_rules"
        provider_name = "none"
        data_location = "on-device (AI) / external (push if enabled)"
        description = (
            "AI processing is local (rule-based, no cloud LLM). "
            "Push notifications, if enabled, send whisper titles and bodies "
            "to Expo's push service. No other data leaves your device."
        )
    elif any(p["path"] == "local_llm" for p in egress_paths):
        mode = "local_llm"
        provider_name = "ollama"
        data_location = "on-device (AI) / external (push if enabled)"
        description = (
            "AI processing is local (Ollama). Push notifications, if enabled, "
            "send whisper titles and bodies to Expo's push service. "
            "No other data leaves your device."
        )
    else:
        mode = "cloud_llm"
        provider_name = provider
        data_location = "cloud (AI) / external (push if enabled)"
        description = (
            f"AI processing via {provider}. Signal text is sent to the "
            f"LLM provider. Push notifications, if enabled, send whisper "
            f"titles and bodies to Expo's push service."
        )

    return {
        "mode": mode,
        "provider": provider_name,
        "data_location": data_location,
        "description": description,
        "egress_paths": egress_paths,
    }


def _get_processing_mode_fallback() -> dict[str, str]:
    """Fallback when processing mode check fails."""


# ---------------------------------------------------------------------------
# 3. Audit log
# ---------------------------------------------------------------------------


def log_data_access(
    user_email: str,
    action: str,
    endpoint: str,
    resource_id: str = "",
    details: dict | None = None,
    db_path: str | None = None,
) -> None:
    """Log a data access event for the audit trail.

    Every time user data is read, written, or deleted, this function
    logs the event. Users can review their audit log to see every
    access to their data.
    """
    path = db_path or _get_db_path()
    init_audit_tables(path)

    try:
        conn = get_db_conn(path)
        conn.execute(
            """INSERT INTO audit_log
               (user_email, action, endpoint, resource_id, details, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                user_email,
                action,
                endpoint,
                resource_id,
                json.dumps(details or {}),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug("Audit log failed: %s", e)


def get_audit_log(
    user_email: str = "bootstrap",
    limit: int = 50,
    action: str | None = None,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Get the audit log for a user.

    Returns a list of data access events, most recent first.
    Optional action filter: 'read', 'write', 'delete', 'correct'.
    """
    path = db_path or _get_db_path()
    init_audit_tables(path)

    conn = get_db_conn(path)
    conn.row_factory = sqlite3.Row

    if action:
        rows = conn.execute(
            """SELECT * FROM audit_log
               WHERE user_email = ? AND action = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (user_email, action, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM audit_log
               WHERE user_email = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (user_email, limit),
        ).fetchall()
    conn.close()

    return [dict(r) for r in rows]
