"""
Role-adaptive UX — 4 roles with different default views + salience (v3.2).

Per CEO's product strategy:
  - Intern: "what should I do today?" task list view
  - IC: "what's blocked?" focus view
  - Manager: "who's stuck?" team view (if team tier)
  - Executive: current briefing view (default)

Each role = a different default screen + different salience weighting.
The Situation substrate is the same; only the delivery/view changes.
"""

from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    import os
    return os.environ.get(
        "MAESTRO_PERSONAL_DB",
        str(__import__("pathlib").Path(__file__).resolve().parent / "personal.db"),
    )


def init_roles_db(db_path: str | None = None) -> None:
    """Initialize roles table."""
    path = db_path or _get_db_path()
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY DEFAULT 'default',
            role TEXT NOT NULL DEFAULT 'executive',
            updated_at TEXT NOT NULL
        )
    """)
    existing = conn.execute("SELECT user_id FROM user_settings WHERE user_id = 'default'").fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO user_settings (user_id, role, updated_at) VALUES ('default', 'executive', ?)",
            (datetime.now(timezone.utc).isoformat(),),
        )
    conn.commit()
    conn.close()


ROLE_CONFIGS = {
    "intern": {
        "default_view": "today_tasks",
        "description": "What should I do today?",
        "salience_priority": [
            "commitment_made",        # prioritize commitments due today
            "deadline.approaching",   # prioritize approaching deadlines
            "follow_up.required",     # prioritize follow-ups
        ],
        "salience_deprioritize": [
            "reported_statement",
            "observed_fact",
        ],
        "ui_density": "high",         # show more items (task list)
        "whisper_aggressiveness": "high",  # whisper more (interns need nudges)
    },
    "ic": {
        "default_view": "blocked_focus",
        "description": "What's blocked?",
        "salience_priority": [
            "stale_commitment",       # prioritize blocked commitments
            "follow_up.required",     # prioritize awaiting replies
            "deadline.approaching",
        ],
        "salience_deprioritize": [
            "meeting.scheduled",      # ICs know their meetings
        ],
        "ui_density": "medium",
        "whisper_aggressiveness": "medium",
    },
    "manager": {
        "default_view": "team_status",
        "description": "Who's stuck?",
        "salience_priority": [
            "stale_commitment",       # team members with stale commitments
            "meeting.scheduled",      # 1:1s with stuck team members
            "follow_up.required",
        ],
        "salience_deprioritize": [
            "personal.promise",       # manager's own promises less critical
        ],
        "ui_density": "medium",
        "whisper_aggressiveness": "medium",
        "requires_team_tier": True,
    },
    "executive": {
        "default_view": "briefing",
        "description": "Current briefing",
        "salience_priority": [
            "decision.proposed",      # prioritize decision boundaries
            "org.reorganization",     # prioritize org changes
            "stale_commitment",       # high-stakes stale commitments
        ],
        "salience_deprioritize": [
            "follow_up.required",     # execs have staff for follow-ups
        ],
        "ui_density": "low",          # show fewer, higher-signal items
        "whisper_aggressiveness": "low",  # execs hate notifications
    },
}


def get_role(db_path: str | None = None) -> str:
    """Get the user's current role."""
    path = db_path or _get_db_path()
    init_roles_db(path)
    conn = sqlite3.connect(path)
    row = conn.execute(
        "SELECT role FROM user_settings WHERE user_id = 'default'"
    ).fetchone()
    conn.close()
    return row[0] if row else "executive"


def set_role(role: str, db_path: str | None = None) -> None:
    """Set the user's role."""
    if role not in ROLE_CONFIGS:
        raise ValueError(f"Invalid role: {role}. Must be one of {list(ROLE_CONFIGS.keys())}")
    path = db_path or _get_db_path()
    init_roles_db(path)
    conn = sqlite3.connect(path)
    conn.execute(
        "UPDATE user_settings SET role = ?, updated_at = ? WHERE user_id = 'default'",
        (role, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def get_role_config(role: str) -> dict[str, Any]:
    """Get the configuration for a role."""
    return ROLE_CONFIGS.get(role, ROLE_CONFIGS["executive"])


def apply_role_to_salience(
    signals: list[Any],
    role: str | None = None,
) -> list[Any]:
    """Reorder signals based on role's salience priority.

    This does NOT change the Core's salience — it reorders the display
    so the role's priority types appear first. The Core's salience is
    the source of truth; the role just changes what the user sees first.
    """
    r = role or get_role()
    config = get_role_config(r)
    priority_types = config["salience_priority"]
    deprioritize_types = config.get("salience_deprioritize", [])

    def _get_sig_type(sig: Any) -> str:
        return str(
            getattr(sig, "signal_type", "") or
            getattr(getattr(sig, "type", ""), "value", "")
        ).lower()

    # Sort: priority types first, then neutral, then deprioritized
    def _sort_key(sig: Any) -> tuple[int, str]:
        sig_type = _get_sig_type(sig)
        if sig_type in priority_types:
            return (0, sig_type)
        elif sig_type in deprioritize_types:
            return (2, sig_type)
        else:
            return (1, sig_type)

    return sorted(signals, key=_sort_key)


def get_whisper_aggressiveness(role: str | None = None) -> str:
    """Get how aggressive Whisper should be for this role.

    - high: whisper for medium AND high priority
    - medium: whisper for high priority only (default)
    - low: whisper only for critical (high priority + stale 7+ days)
    """
    r = role or get_role()
    config = get_role_config(r)
    return config.get("whisper_aggressiveness", "medium")
