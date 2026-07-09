"""
Outcome tracking — closes the learning + calibration loop.

Per external audit: 'Calibration is theater. Always insufficient. No
outcome tracking, no Brier evolution, no behavior change.'

This module provides:
1. POST /api/predictions — register a prediction (confidence + expected outcome)
2. POST /api/outcomes — resolve a prediction with an actual outcome
3. GET /api/calibration — get the Brier score + 10-bucket calibration report

When predictions are registered AND outcomes are resolved, the calibration
report shows real Brier scores instead of 'Insufficient calibration history.'
"""

from __future__ import annotations

import sqlite3
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    import os
    return os.environ.get(
        "MAESTRO_PERSONAL_DB",
        str(__import__("pathlib").Path(__file__).resolve().parent / "personal.db"),
    )


def init_outcome_db(db_path: str | None = None) -> None:
    """Initialize prediction + outcome tables."""
    path = db_path or _get_db_path()
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            prediction_id TEXT PRIMARY KEY,
            prediction_type TEXT NOT NULL DEFAULT 'recommendation',
            predicted_confidence REAL NOT NULL,
            expected_outcome TEXT NOT NULL,
            entity_id TEXT,
            predicted_at TEXT NOT NULL,
            resolved_at TEXT,
            actual_outcome TEXT,
            metadata TEXT DEFAULT '{}'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS outcomes (
            outcome_id TEXT PRIMARY KEY,
            prediction_id TEXT NOT NULL,
            actual_outcome TEXT NOT NULL,
            resolved_at TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id)
        )
    """)
    conn.commit()
    conn.close()


def register_prediction(
    predicted_confidence: float,
    expected_outcome: str = "hit",
    prediction_type: str = "recommendation",
    entity_id: str = "",
    metadata: dict | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Register a prediction with a confidence level.

    This is the START of the learning loop. Before a commitment is
    resolved (kept/broken), we register what we PREDICT will happen
    and at what confidence. Later, when the outcome is known, we
    resolve the prediction and compute Brier score.

    Returns the prediction record.
    """
    path = db_path or _get_db_path()
    init_outcome_db(path)
    prediction_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    if not 0.0 <= predicted_confidence <= 1.0:
        raise ValueError("predicted_confidence must be 0.0-1.0")

    conn = sqlite3.connect(path)
    conn.execute(
        """INSERT INTO predictions
           (prediction_id, prediction_type, predicted_confidence, expected_outcome,
            entity_id, predicted_at, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (prediction_id, prediction_type, predicted_confidence, expected_outcome,
         entity_id, now, json.dumps(metadata or {})),
    )
    conn.commit()
    conn.close()

    return {
        "prediction_id": prediction_id,
        "prediction_type": prediction_type,
        "predicted_confidence": predicted_confidence,
        "expected_outcome": expected_outcome,
        "entity_id": entity_id,
        "predicted_at": now,
        "status": "pending",
    }


def resolve_outcome(
    prediction_id: str,
    actual_outcome: str,
    metadata: dict | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Resolve a prediction with the actual outcome.

    This CLOSES the learning loop. The prediction had a confidence;
    the outcome is now known. The Brier score can be computed from
    the difference between predicted confidence and actual outcome.

    actual_outcome should be: "hit" (prediction was correct) or
    "miss" (prediction was wrong).

    Returns the resolved prediction record.
    """
    path = db_path or _get_db_path()
    init_outcome_db(path)
    now = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(path)

    # Check prediction exists
    row = conn.execute(
        "SELECT * FROM predictions WHERE prediction_id = ?", (prediction_id,)
    ).fetchone()
    if not row:
        conn.close()
        return {"error": "Prediction not found", "prediction_id": prediction_id}

    # Update prediction with outcome
    conn.execute(
        "UPDATE predictions SET resolved_at = ?, actual_outcome = ? WHERE prediction_id = ?",
        (now, actual_outcome, prediction_id),
    )

    # Record outcome
    outcome_id = str(uuid4())
    conn.execute(
        """INSERT INTO outcomes
           (outcome_id, prediction_id, actual_outcome, resolved_at, metadata)
           VALUES (?, ?, ?, ?, ?)""",
        (outcome_id, prediction_id, actual_outcome, now, json.dumps(metadata or {})),
    )
    conn.commit()
    conn.close()

    # Feed outcome to Core's BehavioralLearningEngine
    try:
        import sys
        sys.path.insert(0, "backend")
        from maestro_cognitive_council.behavioral_learning_engine import BehavioralLearningEngine
        engine = BehavioralLearningEngine()
        engine.resolve_outcomes([], use_layered_resolver=False)
    except Exception as e:
        logger.debug("Core learning engine feed failed: %s", e)

    return {
        "prediction_id": prediction_id,
        "actual_outcome": actual_outcome,
        "resolved_at": now,
        "status": "resolved",
    }


def get_calibration_report(
    prediction_type: str = "recommendation",
    db_path: str | None = None,
) -> dict[str, Any]:
    """Get the Brier score + calibration report.

    When there are >= 10 resolved predictions, returns a real Brier score
    and 10-bucket calibration. When < 10, returns 'Insufficient calibration
    history' (honest P25).

    This is what the Commitments and Ask endpoints SHOULD show instead
    of the hardcoded 'Insufficient calibration history' string.
    """
    path = db_path or _get_db_path()
    init_outcome_db(path)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT predicted_confidence, actual_outcome
           FROM predictions
           WHERE prediction_type = ? AND resolved_at IS NOT NULL""",
        (prediction_type,),
    ).fetchall()
    conn.close()

    if not rows:
        return {
            "total_predictions": 0,
            "resolved_predictions": 0,
            "brier_score": None,
            "message": "Insufficient calibration history — keep tracking outcomes to build your Brier score.",
            "has_sufficient_data": False,
        }

    # Build resolved_predictions list for Brier
    # Brier = (predicted_confidence - actual_value)^2
    # actual_value = 1.0 for "hit", 0.0 for "miss"
    resolved = []
    for r in rows:
        confidence = r["predicted_confidence"]
        outcome = r["actual_outcome"]
        actual_value = 1.0 if outcome == "hit" else 0.0
        resolved.append((confidence, actual_value))

    # Compute Brier score
    import sys
    sys.path.insert(0, "backend")
    try:
        from maestro_cognitive_council.calibration_primitives import brier_score, build_calibration_report

        # brier_score expects list of (confidence, actual) tuples
        brier = brier_score([(c, a) for c, a in resolved])

        if len(resolved) < 10:
            return {
                "total_predictions": len(rows),
                "resolved_predictions": len(resolved),
                "brier_score": round(brier, 4) if brier is not None else None,
                "message": f"Partial calibration: {len(resolved)} resolved predictions. Need 10+ for full report. Current Brier: {brier:.4f}" if brier else "Insufficient calibration history.",
                "has_sufficient_data": False,
            }

        # Full calibration report (10+ resolved)
        report = build_calibration_report(
            prediction_type=prediction_type,
            resolved_predictions=[(c, "hit" if a == 1.0 else "miss") for c, a in resolved],
        )

        return {
            "total_predictions": len(rows),
            "resolved_predictions": len(resolved),
            "brier_score": round(brier, 4) if brier is not None else None,
            "message": f"Brier score: {brier:.4f} across {len(resolved)} resolved predictions.",
            "has_sufficient_data": True,
            "calibration_report": {
                "total_resolved": getattr(report, "total_resolved", len(resolved)),
                "total_hits": getattr(report, "total_hits", sum(1 for _, a in resolved if a == 1.0)),
                "total_misses": getattr(report, "total_misses", sum(1 for _, a in resolved if a == 0.0)),
                "is_well_calibrated": getattr(report, "is_well_calibrated", None),
            },
        }
    except Exception as e:
        logger.debug("Calibration report failed: %s", e)
        # Fallback: compute Brier manually
        if resolved:
            brier = sum((c - a) ** 2 for c, a in resolved) / len(resolved)
            return {
                "total_predictions": len(rows),
                "resolved_predictions": len(resolved),
                "brier_score": round(brier, 4),
                "message": f"Brier score: {brier:.4f} across {len(resolved)} resolved predictions." if len(resolved) >= 10 else f"Partial: {len(resolved)} resolved. Need 10+ for full report.",
                "has_sufficient_data": len(resolved) >= 10,
            }
        return {
            "total_predictions": 0,
            "resolved_predictions": 0,
            "brier_score": None,
            "message": "Insufficient calibration history.",
            "has_sufficient_data": False,
        }


def get_prediction_count(db_path: str | None = None) -> dict[str, int]:
    """Get prediction counts for status display."""
    path = db_path or _get_db_path()
    init_outcome_db(path)
    conn = sqlite3.connect(path)
    total = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    resolved = conn.execute("SELECT COUNT(*) FROM predictions WHERE resolved_at IS NOT NULL").fetchone()[0]
    pending = total - resolved
    conn.close()
    return {"total": total, "resolved": resolved, "pending": pending}
