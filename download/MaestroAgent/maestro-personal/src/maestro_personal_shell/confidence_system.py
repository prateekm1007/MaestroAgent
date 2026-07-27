"""Multi-factor confidence computation and ledger variance stats (P77).

P10 root cause: legacy confidence was uniform (0.85-0.9) because every
value came from a single rule-based classifier pattern with no evidence
weighting. This module derives confidence from five independent factors
so the value tracks actual evidence quality.

P77 gate: std_dev(confidence) > 0.15 across the production ledger.
P22: reads the canonical ledger (reduce_commitments), no mocks.
P85: public functions never raise; they return safe defaults on error.

Authored by: Kimi K3 (helpers) + CTO (public API completion)
  Kimi K3 generation_id: gen-1785183089-yLbYAWTGx4WErQWbXJkn (P46 verified)
  CTO completed compute_confidence + compute_ledger_confidence_stats +
  flag_low_confidence_for_review after K3 output was truncated.
"""

from __future__ import annotations

import json
import logging
import re
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

MAX_CONFIDENCE = 0.95  # never 1.0 — absolute certainty is dishonest
LOW_CONFIDENCE_THRESHOLD = 0.5
HIGH_CONFIDENCE_THRESHOLD = 0.8
VARIANCE_GATE_STD_DEV = 0.15  # P77

_SOURCE_RELIABILITY = {
    "personal_email": 0.20,
    "email": 0.20,
    "slack": 0.15,
    "newsletter": 0.05,
    "notification": 0.02,
    "self_generated": 0.0,
    "self": 0.0,
}
_UNKNOWN_SOURCE_RELIABILITY = 0.05

_COMMITMENT_RE = re.compile(
    r"\b(i\s+will|i'll|i\s+shall|i'm\s+going\s+to|i\s+am\s+going\s+to)\b",
    re.IGNORECASE,
)
_DEADLINE_RE = re.compile(
    r"(\bby\s+(eod|eow|tomorrow|tonight|today|monday|tuesday|wednesday|"
    r"thursday|friday|saturday|sunday|\d)"
    r"|\bbefore\b|\bdue\b|\bno later than\b|\bdeadline\b"
    r"|\btomorrow\b|\btonight\b|\bend of (day|week)\b|\beod\b|\beow\b"
    r"|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}(/\d{2,4})?\b"
    r"|\b(next|this)\s+(week|monday|tuesday|wednesday|thursday|friday))\b",
    re.IGNORECASE,
)
_HEDGED_RE = re.compile(
    r"\b(might|maybe|perhaps|probably|possibly|try\s+to|i'll\s+try|"
    r"hope\s+to|should\s+be\s+able|not\s+sure|tentative)\b",
    re.IGNORECASE,
)

_TEXT_KEYS = ("text", "content", "body", "snippet", "commitment_text",
              "description", "subject", "title")
_TS_KEYS = ("timestamp", "created_at", "detected_at", "received_at", "date", "ts")
_ENTITY_KEYS = ("entity", "entity_name", "counterparty", "person")
_SOURCE_KEYS = ("source", "source_type", "channel")


# ---------------------------------------------------------------------------
# Factor helpers (authored by Kimi K3)
# ---------------------------------------------------------------------------

def _first_key(signal: dict, keys: tuple) -> Any:
    for k in keys:
        v = signal.get(k)
        if v not in (None, ""):
            return v
    return None


def _signal_text(signal: dict) -> str:
    parts = [str(signal[k]) for k in _TEXT_KEYS if signal.get(k)]
    return " ".join(parts)


def _signal_entity(signal: Any) -> str | None:
    if not isinstance(signal, dict):
        return None
    v = _first_key(signal, _ENTITY_KEYS)
    if isinstance(v, (list, tuple)):
        v = v[0] if v else None
    return str(v).strip() if v else None


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            v = float(value)
            if v > 1e12:  # epoch millis
                v /= 1000.0
            return datetime.fromtimestamp(v, tz=timezone.utc)
        if isinstance(value, str):
            s = value.strip()
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"):
                    try:
                        return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
    except Exception as exc:  # P6: log loudly, no bare except
        logger.warning("confidence: unparseable timestamp %r: %s", value, exc)
    return None


def _freshness_score(signal: dict) -> float:
    ts = _parse_timestamp(_first_key(signal, _TS_KEYS))
    if ts is None:
        return 0.05
    age = datetime.now(timezone.utc) - ts
    if age <= timedelta(hours=24):
        return 0.20
    if age <= timedelta(days=7):
        return 0.15
    if age <= timedelta(days=30):
        return 0.10
    return 0.05


def _source_score(signal: dict) -> float:
    raw = _first_key(signal, _SOURCE_KEYS)
    if raw is None:
        return _UNKNOWN_SOURCE_RELIABILITY
    key = re.sub(r"[\s\-]+", "_", str(raw).strip().lower())
    return _SOURCE_RELIABILITY.get(key, _UNKNOWN_SOURCE_RELIABILITY)


def _clarity_score(signal: dict) -> float:
    text = _signal_text(signal)
    if not text:
        return 0.03
    hedged = bool(_HEDGED_RE.search(text))
    committed = bool(_COMMITMENT_RE.search(text))
    if committed and _DEADLINE_RE.search(text) and not hedged:
        return 0.15
    if hedged or committed:
        return 0.08
    return 0.03


def _partial_entity_match(a: str, b: str) -> bool:
    a, b = a.lower(), b.lower()
    if a in b or b in a:
        return True
    return bool(set(a.split()) & set(b.split()))


def _entity_match_score(signal: dict, ctx: dict | None) -> float:
    entity = _signal_entity(signal)
    if not entity:
        return 0.0
    target = None
    if isinstance(ctx, dict):
        target = (ctx.get("entity_name") or ctx.get("canonical_entity")
                  or ctx.get("entity"))
    if not target:
        return 0.08  # entity present but nothing to verify against
    target = str(target).strip()
    if entity.lower() == target.lower():
        return 0.15
    return 0.08 if _partial_entity_match(entity, target) else 0.0


def _corroboration_score(signal: dict, ctx: dict | None) -> float:
    count = 0
    if isinstance(ctx, dict):
        if ctx.get("corroborating_count") is not None:
            try:
                count = max(0, int(ctx["corroborating_count"]))
            except (TypeError, ValueError) as exc:
                logger.warning("confidence: bad corroborating_count: %s", exc)
                count = 0
        else:
            related = (ctx.get("related_signals")
                       or ctx.get("corroborating_signals") or [])
            entity = _signal_entity(signal)
            if entity:
                count = sum(
                    1 for r in related
                    if _signal_entity(r)
                    and _partial_entity_match(entity, _signal_entity(r))
                )
            else:
                count = len(related)
    if count <= 0:
        return 0.1
    if count <= 2:
        return 0.2
    return 0.3


# ---------------------------------------------------------------------------
# Public API (compute_confidence completed by CTO after K3 truncation)
# ---------------------------------------------------------------------------

def compute_confidence(signal: dict, evidence_context: dict | None = None) -> float:
    """Multi-factor confidence in [0.0, 0.95]. Never raises (P85).

    Factors:
      - Corroborating signals (0.3 max): how many other signals reference the same entity
      - Source reliability (0.2 max): personal_email > slack > newsletter > notification
      - Temporal freshness (0.2 max): within 24h > 7d > 30d > older
      - Entity match quality (0.15 max): exact > partial > none
      - Content clarity (0.15 max): explicit + deadline > hedged > ambiguous
    """
    try:
        if not isinstance(signal, dict):
            logger.warning("confidence: non-dict signal %r", type(signal))
            return 0.3

        score = (
            _corroboration_score(signal, evidence_context)   # max 0.30
            + _source_score(signal)                           # max 0.20
            + _freshness_score(signal)                        # max 0.20
            + _entity_match_score(signal, evidence_context)   # max 0.15
            + _clarity_score(signal)                          # max 0.15
        )
        # Clamp to [0.0, MAX_CONFIDENCE] — never 1.0
        return round(min(max(score, 0.0), MAX_CONFIDENCE), 3)
    except Exception as exc:
        logger.exception("compute_confidence failed: %s", exc)
        return 0.3  # safe default


def compute_ledger_confidence_stats(user_email: str, db_path: str | None = None) -> dict:
    """Compute confidence statistics for a user's ledger (P77).

    Returns:
      {count, mean, std_dev, min, max, variance_healthy, low_confidence_count,
       high_confidence_count}

    P77 gate: variance_healthy is True if std_dev > 0.15.
    P85: never raises — returns safe defaults on any error.
    P22: reads from the canonical ledger directly (ALL events, not just
         the user-active projection — reduce_commitments filters by
         confidence >= 0.7, which would hide the low-confidence signals
         that P77 needs to measure).
    """
    try:
        from maestro_personal_shell.canonical_ledger import _EVENT_COLUMNS
        from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path

        conn = get_db_conn(db_path or default_sqlite_path())
        try:
            rows = conn.execute(
                f"SELECT {_EVENT_COLUMNS} FROM commitment_events "
                "WHERE user_email = ? ORDER BY timestamp ASC",
                (user_email,),
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return {
                "count": 0,
                "mean": 0.0,
                "std_dev": 0.0,
                "min": 0.0,
                "max": 0.0,
                "variance_healthy": True,  # empty ledger is trivially healthy
                "low_confidence_count": 0,
                "high_confidence_count": 0,
            }

        # Extract confidence (column index 7 in _EVENT_COLUMNS)
        confidences = []
        for row in rows:
            conf = row[7] if isinstance(row, (tuple, list)) else row.get("confidence", 0.5)
            if conf is not None:
                confidences.append(float(conf))

        if not confidences:
            return {
                "count": 0, "mean": 0.0, "std_dev": 0.0, "min": 0.0, "max": 0.0,
                "variance_healthy": True, "low_confidence_count": 0, "high_confidence_count": 0,
            }

        count = len(confidences)
        mean = sum(confidences) / count
        std_dev = statistics.pstdev(confidences) if count > 1 else 0.0

        return {
            "count": count,
            "mean": round(mean, 4),
            "std_dev": round(std_dev, 4),
            "min": round(min(confidences), 4),
            "max": round(max(confidences), 4),
            "variance_healthy": std_dev > VARIANCE_GATE_STD_DEV,
            "low_confidence_count": sum(1 for c in confidences if c < LOW_CONFIDENCE_THRESHOLD),
            "high_confidence_count": sum(1 for c in confidences if c >= HIGH_CONFIDENCE_THRESHOLD),
        }
    except Exception as exc:
        logger.exception("compute_ledger_confidence_stats failed for user=%s: %s", user_email, exc)
        return {
            "count": 0, "mean": 0.0, "std_dev": 0.0, "min": 0.0, "max": 0.0,
            "variance_healthy": False, "low_confidence_count": 0, "high_confidence_count": 0,
        }


def flag_low_confidence_for_review(user_email: str, db_path: str | None = None) -> list[dict]:
    """Return signals with confidence < 0.5, sorted by confidence ascending (P77).

    These should be flagged for user review, not surfaced as facts.
    P85: never raises — returns [] on any error.
    """
    try:
        from maestro_personal_shell.canonical_ledger import _EVENT_COLUMNS
        from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path

        conn = get_db_conn(db_path or default_sqlite_path())
        try:
            rows = conn.execute(
                f"SELECT {_EVENT_COLUMNS} FROM commitment_events "
                "WHERE user_email = ? AND confidence < ? "
                "ORDER BY confidence ASC",
                (user_email, LOW_CONFIDENCE_THRESHOLD),
            ).fetchall()
        finally:
            conn.close()

        results = []
        for row in rows:
            results.append({
                "event_id": row[0],
                "commitment_id": row[1],
                "event_type": row[2],
                "actor": row[3],
                "entity": row[4],
                "text": row[5],
                "confidence": row[7],
                "timestamp": row[10],
            })
        return results
    except Exception as exc:
        logger.exception("flag_low_confidence_for_review failed for user=%s: %s", user_email, exc)
        return []
