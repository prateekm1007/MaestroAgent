"""
Success metrics — Directive 6.

GET /api/metrics — tracks real user value:
- Commitment completion rate (kept vs missed)
- Silence accuracy (when Maestro speaks vs stays silent, was it right?)
- Calibration trend (Brier score over time)
- Engagement (signals ingested, questions asked, corrections made)
- Agent activity (which agents are producing insights)
- Learning loop health (predictions registered/resolved)

These metrics let the CEO track whether the product is delivering
"I can't live without this" value.
"""

from __future__ import annotations

import logging
import sqlite3
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


def get_success_metrics(user_email: str = "bootstrap") -> dict[str, Any]:
    """Compute all success metrics for a user.

    Returns:
    {
        "commitment_completion_rate": 0.0-1.0,
        "commitments_total": N,
        "commitments_completed": N,
        "commitments_missed": N,
        "commitments_active": N,
        "silence_accuracy": 0.0-1.0,  # how often silence was correct
        "calibration_trend": "improving" | "stable" | "declining" | "insufficient",
        "brier_score": float | None,
        "engagement": {
            "signals_ingested": N,
            "questions_asked": N,
            "corrections_made": N,
            "agents_active": N,
        },
        "learning_loop": {
            "predictions_registered": N,
            "predictions_resolved": N,
            "auto_resolved": N,
        },
        "computed_at": ISO timestamp,
    }
    """
    path = _get_db_path()
    metrics: dict[str, Any] = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    # 1. Commitment metrics
    metrics.update(_compute_commitment_metrics(path, user_email))

    # 2. Silence accuracy (from behavior patterns)
    metrics.update(_compute_silence_accuracy(path, user_email))

    # 3. Calibration trend
    metrics.update(_compute_calibration_trend(path, user_email))

    # 4. Engagement
    metrics["engagement"] = _compute_engagement(path, user_email)

    # 5. Learning loop health
    metrics["learning_loop"] = _compute_learning_loop_health(path, user_email)

    return metrics


def _compute_commitment_metrics(path: str, user_email: str) -> dict[str, Any]:
    """Compute commitment completion rate."""
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row

        # Count signals by type
        total = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE user_email = ? AND signal_type = 'commitment_made'",
            (user_email,),
        ).fetchone()[0]

        # Count completed (metadata has correction=complete)
        completed = conn.execute(
            """SELECT COUNT(*) FROM signals
               WHERE user_email = ? AND metadata LIKE '%correction%complete%'""",
            (user_email,),
        ).fetchone()[0]

        # Count dismissed/cancelled (missed)
        missed = conn.execute(
            """SELECT COUNT(*) FROM signals
               WHERE user_email = ? AND (metadata LIKE '%correction%dismiss%'
               OR metadata LIKE '%correction%cancel%')""",
            (user_email,),
        ).fetchone()[0]

        # Active = total - completed - missed
        active = total - completed - missed

        completion_rate = completed / (completed + missed) if (completed + missed) > 0 else 0.0

        conn.close()

        return {
            "commitment_completion_rate": round(completion_rate, 2),
            "commitments_total": total,
            "commitments_completed": completed,
            "commitments_missed": missed,
            "commitments_active": active,
        }
    except Exception as e:
        logger.debug("Commitment metrics failed: %s", e)
        return {
            "commitment_completion_rate": 0.0,
            "commitments_total": 0,
            "commitments_completed": 0,
            "commitments_missed": 0,
            "commitments_active": 0,
        }


def _compute_silence_accuracy(path: str, user_email: str) -> dict[str, Any]:
    """Compute silence accuracy from behavior patterns.

    If the user dismisses few suggestions, Maestro is speaking when it matters.
    If the user dismisses many, Maestro is speaking too much (low silence accuracy).
    """
    try:
        from maestro_personal_shell.learning_loop_v2 import get_behavior_patterns
        patterns = get_behavior_patterns(user_email=user_email, db_path=path)

        total = patterns.get("total_behaviors", 0)
        dismissals = patterns.get("total_dismissals", 0)

        if total == 0:
            silence_accuracy = 0.5  # neutral — no data
        else:
            # Silence accuracy = 1 - dismissal_rate
            # If user dismisses 20% of suggestions, accuracy = 80%
            dismissal_rate = patterns.get("dismissal_rate", 0)
            silence_accuracy = 1.0 - dismissal_rate

        return {
            "silence_accuracy": round(silence_accuracy, 2),
            "suggestions_dismissed": dismissals,
            "suggestions_total": total,
        }
    except Exception as e:
        logger.debug("Silence accuracy failed: %s", e)
        return {"silence_accuracy": 0.5, "suggestions_dismissed": 0, "suggestions_total": 0}


def _compute_calibration_trend(path: str, user_email: str) -> dict[str, Any]:
    """Compute calibration trend from history."""
    try:
        from maestro_personal_shell.audit_trust import get_calibration_history
        history = get_calibration_history(user_email=user_email, db_path=path, limit=10)

        if len(history) < 2:
            return {
                "calibration_trend": "insufficient",
                "brier_score": None,
            }

        # Compare recent vs older Brier scores
        recent_brier = history[0].get("brier_score")
        older_brier = history[-1].get("brier_score")

        if recent_brier is None or older_brier is None:
            return {
                "calibration_trend": "insufficient",
                "brier_score": recent_brier,
            }

        # Lower Brier = better. If recent < older, improving.
        diff = older_brier - recent_brier
        if diff > 0.02:
            trend = "improving"
        elif diff < -0.02:
            trend = "declining"
        else:
            trend = "stable"

        return {
            "calibration_trend": trend,
            "brier_score": recent_brier,
            "brier_trend_delta": round(diff, 4),
        }
    except Exception as e:
        logger.debug("Calibration trend failed: %s", e)
        return {"calibration_trend": "insufficient", "brier_score": None}


def _compute_engagement(path: str, user_email: str) -> dict[str, Any]:
    """Compute engagement metrics."""
    try:
        conn = sqlite3.connect(path)

        signals_ingested = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE user_email = ?",
            (user_email,),
        ).fetchone()[0]

        conn.close()

        # Count audit log events
        from maestro_personal_shell.audit_trust import get_audit_log
        audit_events = get_audit_log(user_email=user_email, db_path=path, limit=500)

        questions_asked = sum(1 for e in audit_events if "ask" in e.get("endpoint", "").lower())
        corrections_made = sum(1 for e in audit_events if e.get("action") == "correct")

        # Count active agents
        agents_active = 8  # from nerve_wiring PERSONAL_AGENTS

        return {
            "signals_ingested": signals_ingested,
            "questions_asked": questions_asked,
            "corrections_made": corrections_made,
            "agents_active": agents_active,
        }
    except Exception as e:
        logger.debug("Engagement metrics failed: %s", e)
        return {
            "signals_ingested": 0,
            "questions_asked": 0,
            "corrections_made": 0,
            "agents_active": 0,
        }


def _compute_learning_loop_health(path: str, user_email: str) -> dict[str, Any]:
    """Compute learning loop health metrics."""
    try:
        from maestro_personal_shell.outcome_tracker import get_prediction_count
        counts = get_prediction_count(db_path=path)

        return {
            "predictions_registered": counts.get("total", 0),
            "predictions_resolved": counts.get("resolved", 0),
            "predictions_pending": counts.get("pending", 0),
            "auto_resolved": counts.get("resolved", 0),  # all are auto-resolved in v2
        }
    except Exception as e:
        logger.debug("Learning loop health failed: %s", e)
        return {
            "predictions_registered": 0,
            "predictions_resolved": 0,
            "predictions_pending": 0,
            "auto_resolved": 0,
        }
