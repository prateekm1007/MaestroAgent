"""
Round 47 — Block 5: Pilot Metrics (privacy-preserving).

Collects ONLY usage counts — NOT content. The metrics measure
engagement-shaped signals (usage) but NOT engagement-manipulating
signals (dwell time, return frequency). The metrics answer "is the
flywheel accelerating?" not "how do we make users stay longer?"

This is the constitutional distinction from Round 43: we measure
whether the product compounds capability, not whether it manipulates
attention.

Allowed metrics:
  - daily_active_users
  - cards_swiped_per_session
  - actions_taken_per_session
  - filter_usage (All/Work/Personal split)
  - feature_usage (which surfaces are opened)
  - brier_score_trend

FORBIDDEN metrics (never collected):
  - message text / decision content / personal data
  - dwell time / time-on-page
  - return frequency / session length
  - scroll depth
  - click positions
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# The ONLY allowed metric fields. Any field not in this set is a violation.
ALLOWED_METRICS = {
    "daily_active_users",
    "cards_swiped",
    "actions_taken",
    "filter_all_count",
    "filter_work_count",
    "filter_personal_count",
    "surface_opens",
    "brier_score",
}

# Explicitly forbidden patterns — if any of these appear in the metrics
# payload, the collection is rejected.
FORBIDDEN_METRIC_PATTERNS = {
    "dwell_time", "dwellTime", "time_on_page", "timeOnPage",
    "return_frequency", "returnFrequency", "session_length", "sessionLength",
    "scroll_depth", "scrollDepth", "click_position", "clickPosition",
    "message_text", "messageText", "decision_content", "decisionContent",
    "personal_data", "personalData",
}


class PilotMetrics:
    """Privacy-preserving pilot metrics. Usage counts only, never content."""

    _metrics: dict[str, Any] = defaultdict(int)
    _surface_opens: dict[str, int] = defaultdict(int)
    _daily_users: set[str] = set()
    _brier_scores: list[float] = []
    _initialized: bool = False

    @classmethod
    def _ensure_init(cls) -> None:
        if not cls._initialized:
            cls._metrics = defaultdict(int)
            cls._surface_opens = defaultdict(int)
            cls._daily_users = set()
            cls._brier_scores = []
            cls._initialized = True

    @classmethod
    def record_card_swipe(cls, direction: str = "right") -> None:
        """Record a card swipe. Only the count + direction, never the card content."""
        cls._ensure_init()
        cls._metrics["cards_swiped"] += 1

    @classmethod
    def record_action(cls) -> None:
        """Record an action taken (writeback, task complete, etc.). Never the action content."""
        cls._ensure_init()
        cls._metrics["actions_taken"] += 1

    @classmethod
    def record_filter_usage(cls, filter_value: str) -> None:
        """Record which filter was used (all/work/personal). Never the card content shown."""
        cls._ensure_init()
        if filter_value == "all":
            cls._metrics["filter_all_count"] += 1
        elif filter_value == "work":
            cls._metrics["filter_work_count"] += 1
        elif filter_value == "personal":
            cls._metrics["filter_personal_count"] += 1

    @classmethod
    def record_surface_open(cls, surface: str) -> None:
        """Record which surface was opened. Only the surface name, never the content viewed."""
        cls._ensure_init()
        cls._surface_opens[surface] += 1

    @classmethod
    def record_daily_active_user(cls, user_id: str) -> None:
        """Record a daily active user. Only a hash of the user ID, never the user's data."""
        cls._ensure_init()
        # Store only a hash, not the raw ID (privacy)
        import hashlib
        hashed = hashlib.sha256(user_id.encode()).hexdigest()[:16]
        cls._daily_users.add(hashed)

    @classmethod
    def record_brier_score(cls, score: float) -> None:
        """Record a Brier score for the calibration trend."""
        cls._ensure_init()
        cls._brier_scores.append(score)

    @classmethod
    def get_metrics(cls) -> dict[str, Any]:
        """Get the aggregated metrics. Only returns allowed fields."""
        cls._ensure_init()
        # Build the response with ONLY allowed fields
        metrics: dict[str, Any] = {
            "daily_active_users": len(cls._daily_users),
            "cards_swiped": cls._metrics.get("cards_swiped", 0),
            "actions_taken": cls._metrics.get("actions_taken", 0),
            "filter_usage": {
                "all": cls._metrics.get("filter_all_count", 0),
                "work": cls._metrics.get("filter_work_count", 0),
                "personal": cls._metrics.get("filter_personal_count", 0),
            },
            "feature_usage": dict(cls._surface_opens),
            "brier_score_trend": list(cls._brier_scores[-10:]) if cls._brier_scores else [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Defense in depth — verify no forbidden patterns leaked
        metrics_str = str(metrics).lower()
        for pattern in FORBIDDEN_METRIC_PATTERNS:
            if pattern.lower() in metrics_str:
                logger.error("Forbidden metric pattern detected: %s", pattern)
                # Return empty metrics rather than ship a violation
                return {"error": "Forbidden metric pattern detected. Metrics suppressed."}

        return metrics

    @classmethod
    def clear(cls) -> None:
        """Clear all metrics (for testing)."""
        cls._metrics = defaultdict(int)
        cls._surface_opens = defaultdict(int)
        cls._daily_users = set()
        cls._brier_scores = []
        cls._initialized = False

    @classmethod
    def verify_no_forbidden_metrics(cls, payload: dict[str, Any]) -> bool:
        """Verify a metrics payload contains no forbidden patterns.

        This is the constitutional guard. The pilot metrics endpoint
        calls this before returning data. If any forbidden pattern is
        found, the endpoint returns an error instead of the data.
        """
        payload_str = str(payload).lower()
        for pattern in FORBIDDEN_METRIC_PATTERNS:
            if pattern.lower() in payload_str:
                return False
        return True
