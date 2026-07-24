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
from maestro_personal_shell.db_util import get_db_conn
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
        conn = get_db_conn(path)
        conn.row_factory = sqlite3.Row

        # Count signals by type. Total = all commitment-related signals.
        # Auditor (2026-07-24) [CMPL] gap: previously only `commitment_made`
        # was counted as total, so a `commitment_completed` signal was neither
        # in total NOR counted as completed (the metadata-correction check
        # doesn't match the lifecycle fixture's metadata). Result: a tenant
        # with a real completed commitment (Alex Chen) showed
        # commitments_completed=0 — a false-zero that hid a real lifecycle
        # event. Fix: count ALL commitment_* signal types as total, and
        # count `commitment_completed` as completed.
        total = conn.execute(
            """SELECT COUNT(*) FROM signals
               WHERE user_email = ?
               AND signal_type IN
                   ('commitment_made','commitment_updated','commitment_completed','commitment_broken')""",
            (user_email,),
        ).fetchone()[0]

        # Count completed (auditor [CMPL] fix):
        #   (a) signals with signal_type = 'commitment_completed' (lifecycle
        #       fixture path — Alex Chen-style "I already reviewed it")
        #   (b) signals whose metadata records a correction=complete event
        #       (user-marked-via-UI path)
        completed = conn.execute(
            """SELECT COUNT(*) FROM signals
               WHERE user_email = ?
               AND (
                   signal_type = 'commitment_completed'
                   OR metadata LIKE '%correction%complete%'
                   OR metadata LIKE '%commitment_state%completed%'
               )""",
            (user_email,),
        ).fetchone()[0]

        # Count dismissed/cancelled (missed)
        missed = conn.execute(
            """SELECT COUNT(*) FROM signals
               WHERE user_email = ?
               AND (
                   signal_type = 'commitment_broken'
                   OR metadata LIKE '%correction%dismiss%'
                   OR metadata LIKE '%correction%cancel%'
                   OR metadata LIKE '%commitment_state%cancelled%'
               )""",
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
    """Compute silence accuracy from behavior patterns."""
    try:
        from maestro_personal_shell.learning_loop_v2 import get_behavior_patterns
        patterns = get_behavior_patterns(user_email=user_email, db_path=path)

        total = patterns.get("total_behaviors", 0)
        dismissals = patterns.get("total_dismissals", 0)
        dismissal_rate = patterns.get("dismissal_rate", 0)

        # P1-Audit-F6: silence_accuracy is None (not 0.5) when no data.
        # When data exists, report the dismissal_rate honestly — do NOT
        # call it "accuracy" because 1-dismissal_rate is not silence quality.
        if total == 0:
            silence_accuracy = None  # insufficient data
            silence_quality = None   # requires labeled benchmark
        else:
            # Keep the old field for backward compat, but mark it honestly
            silence_accuracy = round(1.0 - dismissal_rate, 2)
            silence_quality = None  # not measurable from behaviors alone

        return {
            "silence_accuracy": silence_accuracy,
            "silence_quality": silence_quality,  # P1-Audit-F6: None until benchmark run
            "dismissal_rate": round(dismissal_rate, 2),
            "suggestions_dismissed": dismissals,
            "suggestions_total": total,
            "note": (
                "silence_accuracy is 1-dismissal_rate (retention rate, not silence quality). "
                "silence_quality requires a labeled critical-event benchmark."
                if total > 0
                else "Insufficient data — no suggestion interactions recorded yet."
            ),
        }
    except Exception as e:
        logger.debug("Silence accuracy failed: %s", e)
        return {
            "silence_accuracy": None,
            "silence_quality": None,
            "dismissal_rate": None,
            "suggestions_dismissed": 0,
            "suggestions_total": 0,
            "note": "Error computing metrics.",
        }


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
        conn = get_db_conn(path)

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
        counts = get_prediction_count(db_path=path, user_email=user_email)

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
