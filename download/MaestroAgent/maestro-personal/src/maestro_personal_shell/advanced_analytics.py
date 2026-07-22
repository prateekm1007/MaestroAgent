"""Personal-shell wrapper for the AdvancedAnalyticsEngine."""
from __future__ import annotations

import logging
import os
import sys as _sys
from datetime import datetime, timezone, timedelta
from pathlib import Path as _Path
from typing import Any

logger = logging.getLogger(__name__)

# Add backend/ to sys.path so we can import the enterprise module.
_BACKEND_ROOT = _Path(__file__).resolve().parent.parent.parent.parent / "backend"
if str(_BACKEND_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_BACKEND_ROOT))

try:
    from maestro_oem.advanced_analytics import (  # type: ignore[import]
        AdvancedAnalyticsEngine,
        OrgLearningReport,
        TrendMetric,
        TrendDirection,
        TeamPerformanceMetric,
    )
    ENTERPRISE_ANALYTICS_AVAILABLE = True
except ImportError as e:
    logger.warning(
        "Enterprise AdvancedAnalyticsEngine not available — analytics disabled. "
        "Import error: %s", e
    )
    ENTERPRISE_ANALYTICS_AVAILABLE = False


def _resolve_db_path() -> str:
    """Resolve the DB path using the SAME logic as api.py."""
    env = os.environ.get("MAESTRO_PERSONAL_DB")
    if env:
        return env
    from pathlib import Path
    return str(Path(__file__).resolve().parent / "personal.db")


def _get_signals_for_user(user_email: str, db_path: str = "") -> list[dict]:
    """Fetch all signals for a user from the personal shell's SQLite DB.

    P13: inputs are DERIVED from stored evidence, not caller-supplied.
    """
    from maestro_personal_shell.db_util import get_db_conn
    import json as _json
    path = db_path or _resolve_db_path()
    db = get_db_conn(path)
    try:
        rows = db.execute(
            "SELECT signal_id, entity, text, signal_type, timestamp, metadata "
            "FROM signals WHERE user_email = ? ORDER BY timestamp ASC",
            (user_email,),
        ).fetchall()
        return [
            {
                "signal_id": r[0],
                "entity": r[1],
                "text": r[2],
                "signal_type": r[3],
                "timestamp": r[4],
                "metadata": _json.loads(r[5]) if r[5] else {},
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("Failed to fetch signals for %s: %s", user_email, e)
        return []
    finally:
        db.close()


def _derive_analytics_from_signals(
    signals: list[dict],
) -> dict[str, Any] | None:
    """P13: DERIVE analytics data points from the user's signal history.

    Inspects signals to extract:
      - Commitments (kept vs broken) → commitment_kept_rate / broken_rate
      - Meeting signals → meeting grades (via simple heuristic)
      - Deal cycle times (from metadata.cycle_time_days)
      - Patterns + laws (from signal metadata)
      - Data points for trend analysis (grouped by period)

    Returns a dict of derived data, or None if no signals.
    """
    if not signals:
        return None

    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)

    # Counters
    commitments_kept = 0
    commitments_broken = 0
    commitments_made = 0
    meeting_grades: list[str] = []
    deal_cycle_times: list[float] = []
    patterns_detected = 0
    laws_validated = 0
    laws_candidate = 0

    # Period buckets for trend analysis
    current_period_signals = 0
    previous_period_signals = 0

    for sig in signals:
        sig_type = sig.get("signal_type", "")
        meta = sig.get("metadata", {}) or {}

        # Parse timestamp
        ts_str = sig.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            ts = now

        # Period bucketing
        if ts >= thirty_days_ago:
            current_period_signals += 1
        elif ts >= sixty_days_ago:
            previous_period_signals += 1

        # Commitments
        if sig_type == "commitment_made":
            commitments_made += 1
        elif sig_type == "commitment_kept" or sig_type == "commitment_completed":
            commitments_kept += 1
        elif sig_type == "commitment_broken":
            commitments_broken += 1

        # Meeting grades (derive a simple grade from meeting signals)
        if sig_type in ("meeting_scheduled", "meeting_context", "meeting_completed"):
            # Simple heuristic: meetings with action items get higher grades
            text = sig.get("text", "").lower()
            has_action = any(
                kw in text for kw in ("i will", "i'll", "follow up", "send", "review")
            )
            has_decision = any(
                kw in text for kw in ("decided", "agreed", "confirmed", "approved")
            )
            if has_action and has_decision:
                meeting_grades.append("A")
            elif has_action or has_decision:
                meeting_grades.append("B")
            else:
                meeting_grades.append("C")

        # Deal cycle times
        cycle_time = meta.get("cycle_time_days") or meta.get("deal_cycle_time_days")
        if cycle_time:
            try:
                deal_cycle_times.append(float(cycle_time))
            except (ValueError, TypeError) as e:
                logger.debug("append failed: %s", e)
        # Patterns + laws
        if sig_type == "pattern_detected" or meta.get("pattern"):
            patterns_detected += 1
        if meta.get("law_status") == "validated":
            laws_validated += 1
        elif meta.get("law_status") == "candidate":
            laws_candidate += 1

    return {
        "commitments_kept": commitments_kept,
        "commitments_broken": commitments_broken,
        "commitments_made": commitments_made,
        "meeting_grades": meeting_grades,
        "deal_cycle_times": deal_cycle_times,
        "patterns_detected": patterns_detected,
        "laws_validated": laws_validated,
        "laws_candidate": laws_candidate,
        "current_period_signals": current_period_signals,
        "previous_period_signals": previous_period_signals,
    }


def get_analytics_report(
    user_email: str,
    db_path: str = "",
) -> dict[str, Any] | None:
    """Get the organizational learning report for a user.

    P11: this is the production entry point for advanced analytics.
    P13: the report is DERIVED from the user's signal history — the
    caller supplies nothing but the auth token.

    Args:
        user_email: the user
        db_path: override the DB path (for tests)

    Returns:
        org learning report dict with: trends, team_performance,
        laws_validated, laws_candidate, patterns_detected, brier_score,
        commitment_kept_rate, commitment_broken_rate,
        meeting_grade_average, deal_cycle_time_days, flywheel_summary
        OR None if no signals.
    """
    if not ENTERPRISE_ANALYTICS_AVAILABLE:
        return None

    signals = _get_signals_for_user(user_email, db_path=db_path)
    if not signals:
        return None

    derived = _derive_analytics_from_signals(signals)
    if not derived:
        return None

    # Build the engine + feed it derived data
    engine = AdvancedAnalyticsEngine()

    # Commitments
    for _ in range(derived["commitments_kept"]):
        engine.record_commitment(kept=True)
    for _ in range(derived["commitments_broken"]):
        engine.record_commitment(kept=False)

    # Meeting grades
    for grade in derived["meeting_grades"]:
        engine.record_meeting_grade(grade)

    # Deal cycle times
    for days in derived["deal_cycle_times"]:
        engine.record_deal_cycle_time(days)

    # Patterns + laws
    for _ in range(derived["patterns_detected"]):
        engine.record_pattern()
    for _ in range(derived["laws_validated"]):
        engine.record_law(validated=True)
    for _ in range(derived["laws_candidate"]):
        engine.record_law(validated=False)

    # Trend data points — signal volume over time
    engine.record_data_point(
        "signal_volume",
        float(derived["current_period_signals"]),
        period="current",
    )
    engine.record_data_point(
        "signal_volume",
        float(derived["previous_period_signals"]),
        period="previous",
    )

    # Record calibration count for P25
    for _ in range(len(signals)):
        engine.record_calibration()

    report = engine.generate_report()
    result = report.to_dict()
    # Enrich with the flywheel summary
    result["flywheel_summary"] = engine.get_flywheel_summary()
    return result


def get_flywheel_summary(
    user_email: str,
    db_path: str = "",
) -> str:
    """Get a one-line flywheel summary for the user.

    Convenience wrapper — useful for dashboards + mobile UI.
    """
    if not ENTERPRISE_ANALYTICS_AVAILABLE:
        return "Analytics unavailable"

    report = get_analytics_report(user_email, db_path=db_path)
    if not report:
        return "No data yet — sync connectors to start the flywheel"
    return report.get("flywheel_summary", "Flywheel status unknown")
