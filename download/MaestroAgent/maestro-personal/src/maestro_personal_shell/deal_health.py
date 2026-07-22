"""Personal-shell wrapper for the DealHealthEngine."""
from __future__ import annotations

import logging
import os
import sys as _sys
from datetime import datetime, timezone
from pathlib import Path as _Path
from typing import Any

logger = logging.getLogger(__name__)

# Add backend/ to sys.path so we can import the enterprise module.
_BACKEND_ROOT = _Path(__file__).resolve().parent.parent.parent.parent / "backend"
if str(_BACKEND_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_BACKEND_ROOT))

try:
    from maestro_oem.deal_health import (  # type: ignore[import]
        DealHealthEngine,
        DealHealthScore,
        DealHealthStatus,
        Momentum,
        RiskFactor,
    )
    from maestro_oem.signal import SignalType  # type: ignore[import]
    ENTERPRISE_DEAL_HEALTH_AVAILABLE = True
except ImportError as e:
    logger.warning(
        "Enterprise DealHealthEngine not available — deal health disabled. "
        "Import error: %s", e
    )
    ENTERPRISE_DEAL_HEALTH_AVAILABLE = False


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


# ---------------------------------------------------------------------------
# Signal shim — converts personal-shell signal dicts to OEM signal objects
# ---------------------------------------------------------------------------


class _SignalShim:
    """Shim that mimics the OEM Signal object the enterprise engine expects.

    The enterprise DealHealthEngine reads:
      - sig.type (a SignalType enum value)
      - sig.metadata (a dict with "customer", "sentiment", etc.)
      - sig.timestamp (a datetime)
      - sig.entity (a string)

    We map the personal shell's signal_type strings to SignalType enums.
    """

    def __init__(self, sig_dict: dict):
        self._dict = sig_dict
        self.metadata = sig_dict.get("metadata", {}) or {}
        self.entity = sig_dict.get("entity", "")
        self.text = sig_dict.get("text", "")
        self.signal_id = sig_dict.get("signal_id", "")

        # Map personal-shell signal_type → OEM SignalType enum
        self.type = self._map_signal_type(sig_dict.get("signal_type", ""))

        # Parse timestamp
        ts_str = sig_dict.get("timestamp", "")
        try:
            self.timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if self.timestamp.tzinfo is None:
                self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)
        except Exception:
            self.timestamp = datetime.now(timezone.utc)

        # Ensure metadata has "customer" set (the engine reads metadata.customer)
        if "customer" not in self.metadata:
            self.metadata["customer"] = self.entity

    @staticmethod
    def _map_signal_type(signal_type: str) -> Any:
        """Map personal-shell signal_type strings to OEM SignalType enums.

        The personal shell uses string signal_types like:
          - commitment_made, commitment_kept, commitment_broken
          - meeting_scheduled, meeting_context
        The OEM engine expects SignalType enum values.
        """
        if not ENTERPRISE_DEAL_HEALTH_AVAILABLE:
            return None
        st_lower = signal_type.lower()
        mapping = {
            "commitment_made": SignalType.CUSTOMER_COMMITMENT_MADE,
            "commitment_kept": SignalType.CUSTOMER_COMMITMENT_KEPT,
            "commitment_broken": SignalType.CUSTOMER_COMMITMENT_BROKEN,
            "commitment_completed": SignalType.CUSTOMER_COMMITMENT_KEPT,
            "meeting_scheduled": SignalType.MEETING_SCHEDULED,
            "meeting_context": SignalType.CUSTOMER_MEETING,
            "pre_call_briefing": SignalType.CUSTOMER_MEETING,
            "meeting_completed": SignalType.MEETING_COMPLETED,
            "decision": SignalType.CUSTOMER_DECISION,
            "decision_signal": SignalType.DECISION_SIGNAL,
            "objection": SignalType.CUSTOMER_OBJECTION,
            "stage_change": SignalType.CUSTOMER_STAGE_CHANGE,
        }
        # Default to CUSTOMER_MEETING for unknown types — most personal-shell
        # signals are meeting-adjacent, and the engine treats unknown signal
        # types as neutral context.
        return mapping.get(st_lower, SignalType.CUSTOMER_MEETING)


class _OemStateShim:
    """Shim that mimics the OEM state object the enterprise engine expects.

    The enterprise DealHealthEngine reads self.oem.signals (a list of
    signal objects with .type, .metadata, .timestamp, .entity).
    """

    def __init__(self, signals: list[dict]):
        self.signals = [_SignalShim(s) for s in signals]


# ---------------------------------------------------------------------------
# Production entry points
# ---------------------------------------------------------------------------


def get_deal_health(
    user_email: str,
    entity: str,
    db_path: str = "",
) -> dict[str, Any] | None:
    """Get the deal health score for an entity.

    P11: this is the production entry point for deal health scoring.
    P13: the score is DERIVED from the user's signal history — the
    caller supplies only the entity name.

    Args:
        user_email: the user
        entity: the entity (customer/org) to score
        db_path: override the DB path (for tests)

    Returns:
        deal health dict with: entity, score, status, momentum,
        confidence_label, calibration_denominator, risk_factors,
        positive_indicators, score_history, compounding_adjustments
        OR None if the entity has no signals.
    """
    if not ENTERPRISE_DEAL_HEALTH_AVAILABLE:
        return None

    signals = _get_signals_for_user(user_email, db_path=db_path)
    if not signals:
        return None

    # Filter to signals for this entity (P13: derived from evidence)
    entity_lower = entity.lower()
    entity_signals = [
        s for s in signals
        if s.get("entity", "").lower() == entity_lower
    ]
    if not entity_signals:
        return None

    # Build the OEM state shim + engine
    oem_shim = _OemStateShim(entity_signals)
    engine = DealHealthEngine(oem_state=oem_shim)

    score = engine.compute_score(entity=entity)
    return score.to_dict()


def get_deal_health_for_all_entities(
    user_email: str,
    db_path: str = "",
) -> list[dict[str, Any]]:
    """Get deal health scores for all entities the user has signals for.

    Convenience wrapper — finds all distinct entities and scores each.
    Returns a list sorted by score (highest first).
    """
    if not ENTERPRISE_DEAL_HEALTH_AVAILABLE:
        return []

    signals = _get_signals_for_user(user_email, db_path=db_path)
    if not signals:
        return []

    # Find all distinct entities
    entities = list({s.get("entity", "") for s in signals if s.get("entity")})

    results = []
    for entity in entities:
        score = get_deal_health(user_email, entity, db_path=db_path)
        if score:
            results.append(score)

    # Sort by score descending
    results.sort(key=lambda r: r.get("score", 0), reverse=True)
    return results
