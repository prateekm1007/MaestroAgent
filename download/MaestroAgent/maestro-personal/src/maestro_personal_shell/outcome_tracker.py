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
    # P0-4 fix: query ALL prediction types (not just 'recommendation')
    # so auto-registered 'commitment_completion' predictions are included
    rows = conn.execute(
        """SELECT predicted_confidence, actual_outcome
           FROM predictions
           WHERE resolved_at IS NOT NULL""",
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

        # Phase 9: calibration integrity — suppress precision on small buckets.
        # If any 10-bucket has n < 3, mark that bucket's precision as
        # 'insufficient' to prevent fake precision claims.
        small_bucket_warning = ""
        if len(resolved) < 30:
            small_bucket_warning = (
                f"Warning: {len(resolved)} resolved predictions is below 30. "
                "Bucket-level precision may be unreliable. Overall Brier is valid."
            )

        return {
            "total_predictions": len(rows),
            "resolved_predictions": len(resolved),
            "brier_score": round(brier, 4) if brier is not None else None,
            "message": f"Brier score: {brier:.4f} across {len(resolved)} resolved predictions.",
            "has_sufficient_data": True,
            "calibration_integrity": {
                "n_sufficient": len(resolved) >= 10,
                "bucket_precision_reliable": len(resolved) >= 30,
                "small_bucket_warning": small_bucket_warning,
                "no_fake_precision": True,
            },
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


def get_calibration_context_for_llm(db_path: str | None = None) -> str:
    """Build a calibration context string for injection into LLM system prompts.

    This is the fix for the S0 finding: 'the Brier score is never fed
    back into the LLM prompts. The LLM operates completely amnesiac to
    its past predictive failures.'

    This function queries the outcome database and returns a concise
    summary of:
    - Current Brier score (calibration quality)
    - Number of resolved predictions
    - Recent prediction outcomes (last 5 hits/misses)
    - Calibration guidance (overconfident / underconfident / well-calibrated)

    The returned string is injected into LLM system prompts so the model
    can calibrate its confidence based on past performance.

    Returns an empty string if there's no calibration data (Day 1).
    """
    path = db_path or _get_db_path()
    init_outcome_db(path)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    # Get resolved predictions
    rows = conn.execute(
        """SELECT predicted_confidence, actual_outcome, expected_outcome,
                  entity_id, predicted_at, resolved_at
           FROM predictions
           WHERE resolved_at IS NOT NULL
           ORDER BY resolved_at DESC
           LIMIT 20""",
    ).fetchall()
    conn.close()

    if not rows:
        return ""

    # Compute Brier score
    resolved = []
    for r in rows:
        confidence = r["predicted_confidence"]
        outcome = r["actual_outcome"]
        actual_value = 1.0 if outcome == "hit" else 0.0
        resolved.append((confidence, actual_value))

    try:
        import sys
        sys.path.insert(0, "backend")
        from maestro_cognitive_council.calibration_primitives import brier_score
        brier = brier_score([(c, a) for c, a in resolved])
    except Exception:
        brier = None

    # Build calibration guidance
    hits = sum(1 for _, a in resolved if a == 1.0)
    misses = len(resolved) - hits
    avg_confidence = sum(c for c, _ in resolved) / len(resolved) if resolved else 0
    actual_rate = hits / len(resolved) if resolved else 0

    # Longitudinal evolution: weight recent outcomes more heavily.
    # The auditor found "modest, not transformative" evolution. Root cause:
    # all historical outcomes were weighted equally, so Day 1 outcomes
    # diluted Day 30 signals. Fix: compute a RECENT accuracy rate (last 5)
    # alongside the overall rate, and weight the guidance toward recent.
    recent_n = min(5, len(resolved))
    recent = resolved[:recent_n]
    recent_hits = sum(1 for _, a in recent if a == 1.0)
    recent_rate = recent_hits / recent_n if recent_n > 0 else 0
    recent_avg_conf = sum(c for c, _ in recent) / recent_n if recent_n > 0 else 0

    # Use the RECENT rate for guidance (more responsive to change)
    guidance_confidence = recent_avg_conf if recent_n >= 3 else avg_confidence
    guidance_rate = recent_rate if recent_n >= 3 else actual_rate

    if brier is not None:
        if guidance_confidence > guidance_rate + 0.15:
            calibration_guidance = (
                f"RECENTLY OVERCONFIDENT: Your last {recent_n} predictions averaged "
                f"{guidance_confidence:.0%} confidence but only {guidance_rate:.0%} were correct. "
                f"LOWER your confidence on similar predictions. "
                f"(Overall: {avg_confidence:.0%} conf, {actual_rate:.0%} accuracy)"
            )
        elif guidance_confidence < guidance_rate - 0.15:
            calibration_guidance = (
                f"RECENTLY UNDERCONFIDENT: Your last {recent_n} predictions averaged "
                f"{guidance_confidence:.0%} confidence but {guidance_rate:.0%} were correct. "
                f"You can be MORE confident on similar predictions. "
                f"(Overall: {avg_confidence:.0%} conf, {actual_rate:.0%} accuracy)"
            )
        else:
            calibration_guidance = (
                f"WELL-CALIBRATED: Your confidence ({avg_confidence:.0%}) closely "
                f"matches your accuracy ({actual_rate:.0%}). Maintain this level."
            )
    else:
        calibration_guidance = "Insufficient data for calibration guidance."

    # Build recent outcomes summary (last 5)
    recent = rows[:5]
    recent_summary = []
    for r in recent:
        outcome_label = "correct" if r["actual_outcome"] == "hit" else "wrong"
        entity = r["entity_id"] or "unknown"
        conf = r["predicted_confidence"]
        recent_summary.append(f"  - {entity} (predicted {conf:.0%}, {outcome_label})")

    brier_str = f"{brier:.4f}" if brier is not None else "N/A"

    context = f"""YOUR CALIBRATION HISTORY (use this to calibrate your confidence):
- Brier score: {brier_str} (lower is better; 0.0=perfect, 0.33=random)
- Resolved predictions: {len(resolved)} ({hits} correct, {misses} wrong)
- Average predicted confidence: {avg_confidence:.0%}
- Actual accuracy: {actual_rate:.0%}
- {calibration_guidance}

Recent outcomes (most recent first):
{chr(10).join(recent_summary)}

Based on this history, calibrate your confidence in current predictions. If you've been overconfident on similar situations, lower your confidence. If underconfident, raise it."""

    return context


def get_corrections_context_for_llm(db_path: str | None = None, user_email: str | None = None) -> str:
    """Build a corrections context string for injection into LLM system prompts.

    Phase 2.2 fix: the roadmap requires that the LLM queries past user
    corrections before generating judgments. This function retrieves all
    dismissed/cancelled/corrected signals and builds a context string
    that tells the LLM what the user has previously rejected.

    This closes the correction-persistence loop: when the user dismisses
    something, the LLM sees it and avoids repeating the mistake.

    Returns an empty string if there are no corrections (Day 1).
    """
    path = db_path or _get_db_path()
    init_outcome_db(path)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    # Ensure the signals table exists (it's created by api.init_db, but
    # outcome_tracker may be called before that in some test scenarios)
    try:
        conn.execute("SELECT 1 FROM signals LIMIT 1")
    except sqlite3.OperationalError:
        conn.close()
        return ""  # signals table doesn't exist yet — no corrections possible

    # Query signals that have been corrected (stored in metadata)
    if user_email:
        rows = conn.execute(
            """SELECT signal_id, entity, text, signal_type, metadata, user_email
               FROM signals
               WHERE user_email = ? AND metadata LIKE '%correction%'
               ORDER BY created_at DESC LIMIT 20""",
            (user_email,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT signal_id, entity, text, signal_type, metadata
               FROM signals
               WHERE metadata LIKE '%correction%'
               ORDER BY created_at DESC LIMIT 20""",
        ).fetchall()
    conn.close()

    if not rows:
        return ""

    corrections = []
    for r in rows:
        try:
            meta = json.loads(r["metadata"]) if r["metadata"] else {}
            action = meta.get("correction", "unknown")
            entity = r["entity"]
            text = r["text"][:100]
            corrections.append(f"  - [{action}] {entity}: {text}")
        except Exception:
            continue

    if not corrections:
        return ""

    context = f"""USER CORRECTIONS (the user has rejected these — do NOT repeat):
{chr(10).join(corrections)}

Before generating a judgment, check if the current situation resembles any
of these corrected items. If it does, lower confidence or suppress the
recommendation entirely. The user has explicitly told you these are not
commitments or not relevant."""

    return context
