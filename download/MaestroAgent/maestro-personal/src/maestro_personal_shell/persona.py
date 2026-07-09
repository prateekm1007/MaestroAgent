"""
Persona system — learns the user's patterns for personalized delivery (v4).

The persona model learns:
  - Response patterns: which whispers get opened vs dismissed
  - Timing patterns: when the user is most active/responsive
  - Salience preferences: which situation types the user engages with
  - Communication style: terse vs detailed (from Ask feedback)

The model is transparent — the user can see what it knows (GET /api/persona)
and the data can be deleted (DELETE /api/account removes all persona data too).

Privacy: persona data never leaves the user's device/db. It is NOT shared
with Enterprise or any third party. It personalizes delivery for THIS user only.
"""

from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timezone
from collections import Counter
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    import os
    return os.environ.get(
        "MAESTRO_PERSONAL_DB",
        str(__import__("pathlib").Path(__file__).resolve().parent / "personal.db"),
    )


def init_persona_db(db_path: str | None = None) -> None:
    """Initialize persona tables."""
    path = db_path or _get_db_path()
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS persona_actions (
            action_id TEXT PRIMARY KEY,
            action_type TEXT NOT NULL,
            surface TEXT NOT NULL,
            entity TEXT,
            timestamp TEXT NOT NULL,
            metadata TEXT DEFAULT '{}'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS persona_model (
            persona_id TEXT PRIMARY KEY DEFAULT 'default',
            created_at TEXT NOT NULL,
            last_updated TEXT NOT NULL,
            model_data TEXT NOT NULL DEFAULT '{}'
        )
    """)
    # Insert default model if not exists
    existing = conn.execute("SELECT persona_id FROM persona_model WHERE persona_id = 'default'").fetchone()
    if not existing:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO persona_model (persona_id, created_at, last_updated, model_data) VALUES ('default', ?, ?, '{}')",
            (now, now),
        )
    conn.commit()
    conn.close()


def record_action(
    action_type: str,
    surface: str,
    entity: str = "",
    timestamp: str = "",
    metadata: dict[str, Any] | None = None,
    db_path: str | None = None,
) -> str:
    """Record a user action for the persona model.

    Args:
        action_type: "open" | "dismiss" | "act" | "snooze"
        surface: "whisper" | "commitment" | "prepare" | "ask"
        entity: the entity involved (e.g., "Alex")
        timestamp: ISO timestamp
        metadata: additional context
    """
    import json
    path = db_path or _get_db_path()
    init_persona_db(path)
    action_id = str(uuid4())
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(path)
    conn.execute(
        """INSERT INTO persona_actions
           (action_id, action_type, surface, entity, timestamp, metadata)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (action_id, action_type, surface, entity, ts, json.dumps(metadata or {})),
    )
    conn.commit()
    conn.close()

    # Update the model (recompute from actions)
    _recompute_model(path)
    return action_id


def get_persona_model(db_path: str | None = None) -> dict[str, Any]:
    """Get the current persona model.

    Returns a dict with:
      - persona_id
      - created_at
      - dimensions: the learned dimensions
      - action_count: total actions recorded
    """
    import json
    path = db_path or _get_db_path()
    init_persona_db(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    # Get model
    model_row = conn.execute(
        "SELECT * FROM persona_model WHERE persona_id = 'default'"
    ).fetchone()

    # Get action count
    action_count = conn.execute("SELECT COUNT(*) FROM persona_actions").fetchone()[0]

    conn.close()

    model_data = json.loads(model_row["model_data"]) if model_row else {}
    return {
        "persona_id": "default",
        "created_at": model_row["created_at"] if model_row else "",
        "dimensions": model_data,
        "action_count": action_count,
    }


def _recompute_model(db_path: str | None = None) -> dict[str, Any]:
    """Recompute the persona model from recorded actions.

    This is called after each action is recorded. In production, this
    could be batched (recompute hourly) for scale, but for v1 dogfood
    with low action volume, per-action is fine.
    """
    import json
    path = db_path or _get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    # Load all actions
    actions = conn.execute("SELECT * FROM persona_actions ORDER BY timestamp").fetchall()

    if not actions:
        model_data = {}
    else:
        # Dimension 1: Response patterns (open vs dismiss by surface)
        opens = Counter()
        dismissals = Counter()
        for a in actions:
            if a["action_type"] == "open":
                opens[a["surface"]] += 1
            elif a["action_type"] == "dismiss":
                dismissals[a["surface"]] += 1

        response_rates = {}
        for surface in set(list(opens.keys()) + list(dismissals.keys())):
            total = opens[surface] + dismissals[surface]
            if total > 0:
                response_rates[surface] = {
                    "open_rate": opens[surface] / total,
                    "total": total,
                }

        # Dimension 2: Timing patterns (hour of day → action count)
        hour_activity = Counter()
        for a in actions:
            try:
                ts = datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00"))
                hour_activity[ts.hour] += 1
            except Exception:
                continue

        # Find peak hours (top 3)
        peak_hours = [h for h, _ in hour_activity.most_common(3)]

        # Dimension 3: Entity engagement (which entities the user acts on)
        entity_engagement = Counter()
        for a in actions:
            if a["entity"] and a["action_type"] == "act":
                entity_engagement[a["entity"]] += 1

        # Dimension 4: Surface preference (which surfaces get most engagement)
        surface_engagement = Counter()
        for a in actions:
            if a["action_type"] == "act":
                surface_engagement[a["surface"]] += 1

        model_data = {
            "response_rates": dict(response_rates),
            "peak_hours": peak_hours,
            "hour_activity": dict(hour_activity),
            "entity_engagement": dict(entity_engagement),
            "surface_engagement": dict(surface_engagement),
            "total_actions": len(actions),
        }

    # Save the model
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE persona_model SET model_data = ?, last_updated = ? WHERE persona_id = 'default'",
        (json.dumps(model_data), now),
    )
    conn.commit()
    conn.close()

    return model_data


def get_delivery_personalization(db_path: str | None = None) -> dict[str, Any]:
    """Get persona-driven delivery personalization.

    Used by push.py and whisper.py to personalize:
      - optimal_push_hour: when to push (based on peak_hours)
      - should_batch: if current hour is low-activity, batch to next peak
      - preferred_entities: entities the user engages with most
    """
    model = get_persona_model(db_path)
    dims = model["dimensions"]

    peak_hours = dims.get("peak_hours", [])
    entity_engagement = dims.get("entity_engagement", {})

    # Default: push at 9am if no data
    optimal_push_hour = peak_hours[0] if peak_hours else 9

    # Current hour
    now = datetime.now(timezone.utc)
    current_hour = now.hour

    # Should we batch? If current hour is not in top 3 peak hours
    should_batch = len(peak_hours) > 0 and current_hour not in peak_hours

    return {
        "optimal_push_hour": optimal_push_hour,
        "peak_hours": peak_hours,
        "should_batch_now": should_batch,
        "preferred_entities": list(entity_engagement.keys())[:5],
        "has_sufficient_data": model["action_count"] >= 10,
    }


def delete_persona_data(db_path: str | None = None) -> int:
    """Delete all persona data (privacy control).

    Called by DELETE /api/account. Returns the number of actions deleted.
    """
    path = db_path or _get_db_path()
    init_persona_db(path)
    conn = sqlite3.connect(path)
    count = conn.execute("SELECT COUNT(*) FROM persona_actions").fetchone()[0]
    conn.execute("DELETE FROM persona_actions")
    conn.execute(
        "UPDATE persona_model SET model_data = '{}', last_updated = ? WHERE persona_id = 'default'",
        (datetime.now(timezone.utc).isoformat(),),
    )
    conn.commit()
    conn.close()
    return count
