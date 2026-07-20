"""
Phase 9 behavior change — past outcomes change future behavior.

The roadmap requires:
  Learning behavior-change rate >= 70% controlled scenarios

Past outcomes should measurably change:
  - ranking (entities with poor track record ranked lower)
  - interruption threshold (unreliable entities interrupted sooner)
  - recommendation wording (calibrated confidence shown)
  - confidence (adjusted by Brier score)
  - suppression (repeatedly dismissed patterns suppressed)

This module reads resolved predictions + outcomes and produces behavior
adjustments that callers apply to future interactions.

Rule-based — no LLM needed.
"""

from __future__ import annotations

import logging
import sqlite3
from maestro_personal_shell.db_util import get_db_conn
import json
from typing import Any
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    import os
    return os.environ.get(
        "MAESTRO_PERSONAL_DB",
        str(Path(__file__).resolve().parent / "personal.db"),
    )


def get_entity_track_record(entity: str, user_email: str, db_path: str | None = None) -> dict[str, Any]:
    """Get the track record for an entity: how many predictions hit/miss.

    Returns:
    {
        "entity": entity,
        "total": int,
        "hits": int,
        "misses": int,
        "hit_rate": float,  # 0.0-1.0
        "reliability_score": float,  # 0.0-1.0 (1.0 = always delivers)
    }
    """
    path = db_path or _get_db_path()
    conn = get_db_conn(path)
    try:
        # Get predictions for this entity that are resolved
        rows = conn.execute(
            """SELECT p.predicted_confidence, p.expected_outcome, p.actual_outcome, o.actual_outcome as outcome_outcome
               FROM predictions p
               LEFT JOIN outcomes o ON p.prediction_id = o.prediction_id
               WHERE p.entity_id = ? AND p.resolved_at IS NOT NULL""",
            (entity,),
        ).fetchall()

        total = len(rows)
        if total == 0:
            return {"entity": entity, "total": 0, "hits": 0, "misses": 0,
                    "hit_rate": 0.5, "reliability_score": 0.5}

        hits = 0
        misses = 0
        for row in rows:
            actual = row[3] or row[2]  # outcome table or prediction's own
            if actual == "hit":
                hits += 1
            elif actual == "miss":
                misses += 1

        hit_rate = hits / total if total > 0 else 0.5
        return {
            "entity": entity,
            "total": total,
            "hits": hits,
            "misses": misses,
            "hit_rate": round(hit_rate, 2),
            "reliability_score": round(hit_rate, 2),
        }
    except Exception as e:
        logger.debug("Track record query failed: %s", e)
        return {"entity": entity, "total": 0, "hits": 0, "misses": 0,
                "hit_rate": 0.5, "reliability_score": 0.5}
    finally:
        conn.close()


def get_behavior_adjustments(user_email: str, db_path: str | None = None) -> dict[str, Any]:
    """Get behavior adjustments based on learning history.

    Returns adjustments for:
      - ranking: entities with low reliability get a penalty
      - interruption_threshold: unreliable entities get lower threshold
      - confidence_calibration: adjust confidence by Brier score
      - suppression_patterns: repeatedly dismissed patterns to suppress
    """
    path = db_path or _get_db_path()
    conn = get_db_conn(path)
    conn.row_factory = sqlite3.Row

    # 1. Ranking: entity reliability scores
    entity_reliability: dict[str, float] = {}
    try:
        rows = conn.execute(
            """SELECT entity_id, actual_outcome, COUNT(*) as cnt
               FROM predictions
               WHERE resolved_at IS NOT NULL AND entity_id IS NOT NULL
               GROUP BY entity_id, actual_outcome""",
        ).fetchall()
        entity_stats: dict[str, dict] = {}
        for row in rows:
            entity = row["entity_id"]
            if entity not in entity_stats:
                entity_stats[entity] = {"hits": 0, "misses": 0}
            if row["actual_outcome"] == "hit":
                entity_stats[entity]["hits"] += row["cnt"]
            elif row["actual_outcome"] == "miss":
                entity_stats[entity]["misses"] += row["cnt"]

        for entity, stats in entity_stats.items():
            total = stats["hits"] + stats["misses"]
            if total > 0:
                hit_rate = stats["hits"] / total
                # Reliability < 0.5 = penalty; > 0.5 = bonus
                entity_reliability[entity] = round(hit_rate, 2)
    except Exception as e:
        logger.debug("Entity reliability query failed: %s", e)

    # 2. Suppression: repeatedly dismissed signals
    suppressed_patterns: list[str] = []
    try:
        rows = conn.execute(
            """SELECT entity, COUNT(*) as dismiss_count
               FROM signals
               WHERE user_email = ? AND metadata LIKE '%"correction": "dismiss"%'
               GROUP BY entity HAVING dismiss_count >= 3""",
            (user_email,),
        ).fetchall()
        for row in rows:
            suppressed_patterns.append(row["entity"])
    except Exception as e:
        logger.debug("Suppression query failed: %s", e)

    # 3. Confidence calibration: Brier score (from Core's calibration_primitives
    # via outcome_tracker — not reimplemented here per the no-dilution guard)
    _brier = 0.5  # default (no calibration)
    try:
        from maestro_personal_shell.outcome_tracker import get_calibration_report
        report = get_calibration_report(db_path=path, user_email=user_email)
        if report.get("brier_score") is not None:
            _brier = report["brier_score"]
    except Exception as e:
        logger.debug("_brier failed: %s", e)
    conn.close()

    return {
        "entity_reliability": entity_reliability,
        "suppressed_entities": suppressed_patterns,
        "brier_score": _brier,
        "adjustments": {
            "ranking": "Entities with reliability < 0.5 ranked lower",
            "interruption_threshold": "Unreliable entities get lower threshold (interrupt sooner)",
            "confidence_calibration": f"Confidence adjusted by Brier score ({_brier:.2f})",
            "suppression": f"{len(suppressed_patterns)} entities suppressed after 3+ dismissals",
        },
    }


def apply_ranking_adjustment(entities: list[str], user_email: str,
                              db_path: str | None = None) -> list[tuple[str, float]]:
    """Rank entities by reliability. Low-reliability entities ranked lower.

    Returns list of (entity, adjusted_score) sorted by score descending.
    """
    adjustments = get_behavior_adjustments(user_email, db_path)
    reliability = adjustments["entity_reliability"]

    scored = []
    for entity in entities:
        # Default reliability 0.5; adjust by track record
        rel = reliability.get(entity, 0.5)
        # Penalize entities below 0.5 reliability
        if rel < 0.5:
            score = rel * 0.5  # halve their ranking score
        else:
            score = rel
        scored.append((entity, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def should_suppress_entity(entity: str, user_email: str,
                           db_path: str | None = None) -> bool:
    """Check if an entity should be suppressed (3+ dismissals)."""
    adjustments = get_behavior_adjustments(user_email, db_path)
    return entity in adjustments["suppressed_entities"]


def get_calibrated_confidence(raw_confidence: float, user_email: str,
                               db_path: str | None = None) -> float:
    """Calibrate a raw confidence by the user's Brier score.

    If the Brier score is high (poor calibration), reduce confidence.
    If low (good calibration), keep or slightly increase.
    """
    adjustments = get_behavior_adjustments(user_email, db_path)
    _brier = adjustments["brier_score"]

    # Brier score: 0 = perfect, 1 = worst
    # Adjust confidence: if brier > 0.25, reduce confidence
    if _brier > 0.25:
        adjustment = 1.0 - (_brier - 0.25)  # 0.25→1.0, 0.5→0.75, 1.0→0.25
    else:
        adjustment = 1.0  # good calibration, no adjustment

    calibrated = raw_confidence * adjustment
    return round(max(0.0, min(1.0, calibrated)), 2)
