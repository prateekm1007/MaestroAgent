"""
Learning Loop 2.0 — cross-surface auto-outcome tracking + behavior modeling.

CEO Directive 2 (Days 8-15): Evolve the learning loop into a true
compound advantage.

Three new capabilities:

1. CROSS-SURFACE AUTO-OUTCOME TRACKING
   When a commitment is detected, Maestro auto-registers a prediction
   (confidence based on classification + staleness + type). When a
   completion/dismissal is detected, the prediction is auto-resolved.
   No manual /api/predictions needed — the loop is automatic.

2. USER BEHAVIOR MODELING
   Tracks dismissal patterns: which agent suggestions does the user
   dismiss? Which types of commitments do they mark as "not a commitment"?
   These patterns are injected into LLM system prompts so Maestro
   personalizes its behavior over time.

3. BEHAVIOR CONTEXT FOR LLM PROMPTS
   The behavior context is injected alongside calibration context,
   so the LLM knows: "user dismisses 80% of low-urgency suggestions"
   or "user marks 'tentative' signals as commitments 30% of the time."
"""

from __future__ import annotations

import logging
import sqlite3
import json
import os
from typing import Any
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    return os.environ.get(
        "MAESTRO_PERSONAL_DB",
        str(Path(__file__).resolve().parent / "personal.db"),
    )


# ---------------------------------------------------------------------------
# 1. Cross-surface auto-outcome tracking
# ---------------------------------------------------------------------------


def auto_register_prediction(
    signal_id: str,
    commitment_type: str,
    confidence: float,
    entity: str,
    user_email: str = "bootstrap",
    db_path: str | None = None,
) -> str | None:
    """Auto-register a prediction when a commitment is created.

    Directive 2: instead of requiring manual /api/predictions calls,
    the system auto-registers a prediction whenever a commitment is
    detected. The prediction's confidence is derived from the
    commitment classifier's confidence + staleness + type adjustments.

    When the commitment is later completed/dismissed/cancelled, the
    prediction is auto-resolved — closing the loop automatically.
    """
    path = db_path or _get_db_path()

    try:
        from maestro_personal_shell.outcome_tracker import init_outcome_db, register_prediction
        init_outcome_db(path)

        # Adjust confidence based on commitment type
        type_adjustments = {
            "explicit": 1.0,
            "implicit": 0.9,
            "conditional": 0.7,
            "tentative": 0.4,
            "proposal": 0.3,
            "request": 0.2,
        }
        adjusted_confidence = confidence * type_adjustments.get(commitment_type, 0.7)
        adjusted_confidence = max(0.01, min(0.99, adjusted_confidence))

        prediction = register_prediction(
            predicted_confidence=adjusted_confidence,
            expected_outcome="hit",  # we predict the commitment will be kept
            prediction_type="commitment_completion",
            entity_id=f"{entity}:{signal_id}",
            metadata={
                "signal_id": signal_id,
                "commitment_type": commitment_type,
                "auto_registered": True,
                "entity": entity,
            },
            db_path=path,
            user_email=user_email,  # P0 fix: tenant isolation
        )

        logger.debug(
            "Auto-registered prediction for %s (type=%s, conf=%.2f)",
            entity, commitment_type, adjusted_confidence,
        )
        return prediction.get("prediction_id") if prediction else None
    except Exception as e:
        logger.debug("Auto-register prediction failed: %s", e)
        return None


def auto_resolve_prediction(
    signal_id: str,
    outcome: str,
    user_email: str = "bootstrap",
    db_path: str | None = None,
) -> bool:
    """Auto-resolve a prediction when a commitment is completed/dismissed.

    Directive 2: when a user dismisses a commitment ("not a commitment")
    or marks it complete, the auto-registered prediction is resolved.

    outcome:
    - "hit" = commitment was kept (completed)
    - "miss" = commitment was not kept (dismissed/cancelled/forgotten)
    """
    path = db_path or _get_db_path()

    try:
        from maestro_personal_shell.outcome_tracker import init_outcome_db
        init_outcome_db(path)

        conn = sqlite3.connect(path)
        # Find the auto-registered prediction for this signal (P20 fix: scope by user_email)
        rows = conn.execute(
            """SELECT prediction_id, metadata FROM predictions
               WHERE prediction_type = 'commitment_completion'
               AND resolved_at IS NULL
               AND user_email = ?
               AND metadata LIKE ?""",
            (user_email, f'%{signal_id}%'),
        ).fetchall()

        if not rows:
            conn.close()
            return False

        from maestro_personal_shell.outcome_tracker import resolve_outcome
        for row in rows:
            pred_id = row[0]
            try:
                meta = json.loads(row[1]) if row[1] else {}
            except Exception:
                meta = {}

            # Verify this prediction is for the right signal
            if meta.get("signal_id") != signal_id:
                continue

            resolve_outcome(
                prediction_id=pred_id,
                actual_outcome=outcome,
                metadata={
                    "auto_resolved": True,
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                },
                db_path=path,
                user_email=user_email,  # P20 fix: scope resolution by user
            )
            logger.debug("Auto-resolved prediction %s as %s", pred_id, outcome)

        conn.close()
        return True
    except Exception as e:
        logger.debug("Auto-resolve prediction failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# 2. User behavior modeling
# ---------------------------------------------------------------------------


def record_user_behavior(
    behavior_type: str,
    details: dict[str, Any],
    user_email: str = "bootstrap",
    db_path: str | None = None,
) -> None:
    """Record a user behavior event for pattern learning.

    Directive 2: tracks patterns like:
    - "dismissed suggestion from agent X"
    - "marked commitment_type Y as 'not a commitment'"
    - "overrode confidence on entity Z"
    - "ignored stale commitment reminder"

    These patterns are used to personalize Maestro's behavior.
    """
    path = db_path or _get_db_path()
    try:
        conn = sqlite3.connect(path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_behaviors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                behavior_type TEXT NOT NULL,
                details TEXT DEFAULT '{}',
                recorded_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO user_behaviors (user_email, behavior_type, details, recorded_at) VALUES (?, ?, ?, ?)",
            (
                user_email,
                behavior_type,
                json.dumps(details),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug("Record user behavior failed: %s", e)


def get_behavior_patterns(
    user_email: str = "bootstrap",
    db_path: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Analyze user behavior patterns for personalization.

    Returns patterns like:
    {
        "dismissal_rate_by_agent": {"sales": 0.8, "customer_success": 0.2},
        "dismissal_rate_by_type": {"tentative": 0.9, "explicit": 0.1},
        "override_rate": 0.15,
        "total_behaviors": 42,
        "most_dismissed_agent": "sales",
        "most_dismissed_type": "tentative",
    }
    """
    path = db_path or _get_db_path()
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT behavior_type, details FROM user_behaviors WHERE user_email = ? ORDER BY recorded_at DESC LIMIT ?",
            (user_email, limit),
        ).fetchall()
        conn.close()

        if not rows:
            return {"total_behaviors": 0}

        # Analyze patterns
        dismissals_by_agent = Counter()
        dismissals_by_type = Counter()
        total_dismissals = 0
        total_overrides = 0

        for row in rows:
            btype = row["behavior_type"]
            try:
                details = json.loads(row["details"]) if row["details"] else {}
            except Exception:
                details = {}

            if btype == "dismiss_suggestion":
                total_dismissals += 1
                agent = details.get("agent", "unknown")
                dismissals_by_agent[agent] += 1
            elif btype == "correct_commitment":
                ctype = details.get("commitment_type", "unknown")
                dismissals_by_type[ctype] += 1
            elif btype == "override_confidence":
                total_overrides += 1

        total = len(rows)
        dismissal_rate = total_dismissals / total if total > 0 else 0

        return {
            "total_behaviors": total,
            "total_dismissals": total_dismissals,
            "dismissal_rate": round(dismissal_rate, 2),
            "dismissal_rate_by_agent": {
                k: round(v / total_dismissals, 2) if total_dismissals > 0 else 0
                for k, v in dismissals_by_agent.most_common()
            },
            "dismissal_rate_by_type": {
                k: round(v / max(1, sum(dismissals_by_type.values())), 2)
                for k, v in dismissals_by_type.most_common()
            },
            "override_rate": round(total_overrides / total, 2) if total > 0 else 0,
            "most_dismissed_agent": dismissals_by_agent.most_common(1)[0][0] if dismissals_by_agent else None,
            "most_dismissed_type": dismissals_by_type.most_common(1)[0][0] if dismissals_by_type else None,
        }
    except Exception as e:
        logger.debug("Get behavior patterns failed: %s", e)
        return {"total_behaviors": 0}


# ---------------------------------------------------------------------------
# 3. Behavior context for LLM prompts
# ---------------------------------------------------------------------------


def get_behavior_context_for_llm(
    user_email: str = "bootstrap",
    db_path: str | None = None,
) -> str:
    """Build a behavior context string for injection into LLM system prompts.

    Directive 2: alongside calibration context (Brier scores), the LLM
    now receives behavior context that tells it how the user interacts
    with suggestions. This personalizes Maestro over time.

    Example output:
    "USER BEHAVIOR PATTERNS (personalize your suggestions):
    - Total interactions: 42
    - Dismissal rate: 65% (user dismisses most suggestions)
    - Most dismissed agent: sales (80% of sales suggestions dismissed)
    - Most dismissed type: tentative (90% dismissed)
    - Override rate: 15%

    Based on these patterns:
    - REDUCE suggestions from the 'sales' agent (user dismisses 80%)
    - REDUCE 'tentative' classification surfacing (user dismisses 90%)
    - BE MORE CONFIDENT when you do speak (user values quality over quantity)"

    Returns empty string if no behavior data (Day 1).
    """
    patterns = get_behavior_patterns(user_email, db_path)

    if patterns.get("total_behaviors", 0) < 3:
        return ""  # Not enough data for patterns

    parts = []
    parts.append(f"- Total interactions: {patterns['total_behaviors']}")
    parts.append(f"- Dismissal rate: {patterns.get('dismissal_rate', 0):.0%}")

    if patterns.get("most_dismissed_agent"):
        agent_rate = patterns.get("dismissal_rate_by_agent", {}).get(
            patterns["most_dismissed_agent"], 0
        )
        parts.append(
            f"- Most dismissed agent: {patterns['most_dismissed_agent']} "
            f"({agent_rate:.0%} of dismissals)"
        )

    if patterns.get("most_dismissed_type"):
        parts.append(f"- Most dismissed commitment type: {patterns['most_dismissed_type']}")

    parts.append(f"- Override rate: {patterns.get('override_rate', 0):.0%}")

    # Generate personalized guidance
    guidance = []
    if patterns.get("dismissal_rate", 0) > 0.5:
        guidance.append(
            "- BE MORE SELECTIVE: user dismisses >50% of suggestions. "
            "Only surface high-confidence, high-materiality items."
        )

    if patterns.get("most_dismissed_agent"):
        agent_rate = patterns.get("dismissal_rate_by_agent", {}).get(
            patterns["most_dismissed_agent"], 0
        )
        if agent_rate > 0.7:
            guidance.append(
                f"- REDUCE suggestions from '{patterns['most_dismissed_agent']}' agent "
                f"(user dismisses {agent_rate:.0%} of them)"
            )

    if patterns.get("most_dismissed_type"):
        guidance.append(
            f"- REDUCE '{patterns['most_dismissed_type']}' classification surfacing "
            f"(user frequently dismisses this type)"
        )

    context = f"""USER BEHAVIOR PATTERNS (personalize your suggestions):
{chr(10).join(parts)}

Based on these patterns:
{chr(10).join(guidance) if guidance else "- Continue current behavior — no strong patterns yet"}"""

    return context
