"""
Deal Health Engine — Live deal scoring during calls.

Phase 11 of the Ambient Intelligence roadmap (Days 54-63, 40 hours).

Computes a live deal health score (0-100%) during calls based on:
  - Commitment health (open, overdue, kept)
  - Sentiment trends (from Phase 10's SentimentPatternEngine)
  - Relationship dynamics (interaction frequency, engagement)
  - Historical patterns (similar deals, win/loss rates)

The score updates in real time as new signals arrive during the call.
Risk factors and momentum indicators are surfaced alongside the score.

P25: the score always carries its denominator (number of data points
calibrating the model). If < 10 deals in the cohort, the display says
"insufficient calibration history" — never bare precision.

DEEPER dimension: multi-layer intelligence (commitment + sentiment +
relationship + historical → single score).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class DealHealthStatus(str, Enum):
    """Overall deal health status."""
    STRONG = "strong"        # score >= 75
    ON_TRACK = "on_track"    # score 50-74
    AT_RISK = "at_risk"      # score 25-49
    CRITICAL = "critical"    # score < 25


class Momentum(str, Enum):
    """Deal momentum direction."""
    ACCELERATING = "accelerating"  # score increasing
    STABLE = "stable"              # score flat
    DECELERATING = "decelerating"  # score decreasing


@dataclass
class RiskFactor:
    """A factor that negatively impacts deal health."""
    factor_type: str      # "overdue_commitment", "stale_relationship", "sentiment_decline", etc.
    severity: str         # "high", "medium", "low"
    description: str
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "factor_type": self.factor_type,
            "severity": self.severity,
            "description": self.description,
            "evidence": self.evidence,
        }


@dataclass
class DealHealthScore:
    """Live deal health score with context."""
    entity: str
    score: float                    # 0.0 - 100.0
    status: DealHealthStatus
    momentum: Momentum
    risk_factors: list[RiskFactor] = field(default_factory=list)
    positive_indicators: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # P25: denominator = number of historical deals calibrating the model
    calibration_denominator: int = 0
    score_history: list[float] = field(default_factory=list)

    @property
    def confidence_label(self) -> str:
        """P25: display the denominator. <10 = 'insufficient calibration'."""
        if self.calibration_denominator < 10:
            return "insufficient calibration history"
        return f"{self.score:.0f}% ({self.calibration_denominator} deals in cohort)"

    def to_dict(self) -> dict:
        return {
            "entity": self.entity,
            "score": round(self.score, 1),
            "status": self.status.value,
            "momentum": self.momentum.value,
            "confidence_label": self.confidence_label,
            "calibration_denominator": self.calibration_denominator,
            "risk_factors": [rf.to_dict() for rf in self.risk_factors],
            "positive_indicators": self.positive_indicators,
            "timestamp": self.timestamp.isoformat(),
            "score_history": self.score_history[-5:],  # last 5 scores
        }


class DealHealthEngine:
    """
    Computes live deal health scores during calls.

    Usage:
        engine = DealHealthEngine(oem_state)
        score = engine.compute_score(entity="Globex")
        print(f"Deal health: {score.score}% ({score.status.value})")
        print(f"Risk factors: {[rf.description for rf in score.risk_factors]}")
    """

    # Score component weights (sum to 1.0)
    WEIGHT_COMMITMENT = 0.35
    WEIGHT_SENTIMENT = 0.25
    WEIGHT_RELATIONSHIP = 0.20
    WEIGHT_HISTORICAL = 0.20

    def __init__(self, oem_state: Any = None):
        self.oem = oem_state
        # Score history per entity (for momentum calculation)
        self._score_history: dict[str, list[float]] = {}
        # Historical deal outcomes per entity (for calibration)
        self._deal_outcomes: dict[str, list[str]] = {}  # entity → ["won", "lost", "won", ...]

    def compute_score(self, entity: str) -> DealHealthScore:
        """Compute the current deal health score for an entity.

        The score is a weighted combination of:
          - Commitment health (35%): open vs overdue vs kept
          - Sentiment trends (25%): from recent sentiment patterns
          - Relationship dynamics (20%): interaction frequency + engagement
          - Historical patterns (20%): win/loss rate for similar deals
        """
        # Compute each component (0.0 - 1.0)
        commitment_score = self._compute_commitment_score(entity)
        sentiment_score = self._compute_sentiment_score(entity)
        relationship_score = self._compute_relationship_score(entity)
        historical_score = self._compute_historical_score(entity)

        # Weighted combination
        raw_score = (
            commitment_score * self.WEIGHT_COMMITMENT
            + sentiment_score * self.WEIGHT_SENTIMENT
            + relationship_score * self.WEIGHT_RELATIONSHIP
            + historical_score * self.WEIGHT_HISTORICAL
        )

        # Convert to 0-100 scale
        score = raw_score * 100

        # Determine status
        if score >= 75:
            status = DealHealthStatus.STRONG
        elif score >= 50:
            status = DealHealthStatus.ON_TRACK
        elif score >= 25:
            status = DealHealthStatus.AT_RISK
        else:
            status = DealHealthStatus.CRITICAL

        # Determine momentum (compare to history)
        momentum = self._compute_momentum(entity, score)

        # Collect risk factors
        risk_factors = self._collect_risk_factors(entity, commitment_score, sentiment_score, relationship_score, historical_score)

        # Collect positive indicators
        positive_indicators = self._collect_positive_indicators(
            entity, commitment_score, sentiment_score, relationship_score
        )

        # Calibration denominator (P25)
        calibration = len(self._deal_outcomes.get(entity, []))

        # Update score history
        if entity not in self._score_history:
            self._score_history[entity] = []
        self._score_history[entity].append(score)
        if len(self._score_history[entity]) > 20:
            self._score_history[entity] = self._score_history[entity][-20:]

        return DealHealthScore(
            entity=entity,
            score=score,
            status=status,
            momentum=momentum,
            risk_factors=risk_factors,
            positive_indicators=positive_indicators,
            calibration_denominator=calibration,
            score_history=self._score_history[entity],
        )

    def record_deal_outcome(self, entity: str, outcome: str) -> None:
        """Record a historical deal outcome for calibration.

        outcome: "won" or "lost"
        """
        if entity not in self._deal_outcomes:
            self._deal_outcomes[entity] = []
        self._deal_outcomes[entity].append(outcome)

    def _compute_commitment_score(self, entity: str) -> float:
        """Score based on commitment health (0.0-1.0).

        - Kept commitments: +positive
        - Open commitments: neutral
        - Overdue/broken commitments: -negative
        """
        if not self.oem or not hasattr(self.oem, "signals"):
            return 0.5  # neutral when no data

        from maestro_oem.signal import SignalType
        entity_lower = entity.lower()

        kept = 0
        open_count = 0
        broken = 0

        for sig in self.oem.signals:
            if not hasattr(sig, "metadata"):
                continue
            if sig.metadata.get("customer", "").lower() != entity_lower:
                continue
            if sig.type == SignalType.CUSTOMER_COMMITMENT_KEPT:
                kept += 1
            elif sig.type == SignalType.CUSTOMER_COMMITMENT_MADE:
                open_count += 1
            elif sig.type == SignalType.CUSTOMER_COMMITMENT_BROKEN:
                broken += 1

        total = kept + open_count + broken
        if total == 0:
            return 0.5  # neutral when no commitments

        # Score: kept commitments boost, broken commitments penalize
        score = 0.5 + (kept * 0.15) - (broken * 0.25)
        return max(0.0, min(1.0, score))

    def _compute_sentiment_score(self, entity: str) -> float:
        """Score based on recent sentiment patterns (0.0-1.0).

        Uses SENTIMENT_PATTERN signals from Phase 10:
        - sudden_positivity: +boost
        - escalating_frustration: -penalty
        - stress_spike: -penalty
        - emotional_fatigue: -small penalty
        - sentiment_divergence: -small penalty
        """
        if not self.oem or not hasattr(self.oem, "signals"):
            return 0.5

        from maestro_oem.signal import SignalType
        entity_lower = entity.lower()

        positive_patterns = 0
        negative_patterns = 0

        for sig in self.oem.signals:
            if not hasattr(sig, "type") or sig.type != SignalType.SENTIMENT_PATTERN:
                continue
            if not hasattr(sig, "metadata"):
                continue
            # Check if the pattern relates to this entity
            # (sentiment signals may not have entity metadata, so we count all recent ones)
            pattern_type = sig.metadata.get("pattern_type", "")
            if pattern_type == "sudden_positivity":
                positive_patterns += 1
            elif pattern_type in ("escalating_frustration", "stress_spike"):
                negative_patterns += 1
            elif pattern_type in ("emotional_fatigue", "sentiment_divergence"):
                negative_patterns += 0.5

        if positive_patterns + negative_patterns == 0:
            return 0.5  # neutral

        score = 0.5 + (positive_patterns * 0.1) - (negative_patterns * 0.15)
        return max(0.0, min(1.0, score))

    def _compute_relationship_score(self, entity: str) -> float:
        """Score based on relationship dynamics (0.0-1.0).

        - Interaction frequency: more = better
        - Recent engagement: < 14 days = good
        - Stale relationship: > 21 days = penalty
        """
        if not self.oem or not hasattr(self.oem, "signals"):
            return 0.5

        entity_lower = entity.lower()
        now = datetime.now(timezone.utc)

        interaction_count = 0
        last_interaction = None

        for sig in self.oem.signals:
            if not hasattr(sig, "metadata"):
                continue
            if sig.metadata.get("customer", "").lower() == entity_lower:
                interaction_count += 1
                if hasattr(sig, "timestamp"):
                    if last_interaction is None or sig.timestamp > last_interaction:
                        last_interaction = sig.timestamp

        if interaction_count == 0:
            return 0.3  # low score for no relationship

        # Base score from interaction volume
        score = min(0.8, 0.3 + (interaction_count * 0.03))

        # Adjust for recency
        if last_interaction:
            days_ago = (now - last_interaction).days
            if days_ago < 7:
                score += 0.15  # recent engagement
            elif days_ago < 14:
                score += 0.05
            elif days_ago > 21:
                score -= 0.20  # stale relationship
            elif days_ago > 30:
                score -= 0.30  # very stale

        return max(0.0, min(1.0, score))

    def _compute_historical_score(self, entity: str) -> float:
        """Score based on historical deal outcomes (0.0-1.0).

        Win rate from past deals with this entity.
        P25: if < 10 deals, the score is less reliable (denominator tracked).
        """
        outcomes = self._deal_outcomes.get(entity, [])
        if not outcomes:
            return 0.5  # neutral when no history

        wins = sum(1 for o in outcomes if o == "won")
        win_rate = wins / len(outcomes)
        return win_rate

    def _compute_momentum(self, entity: str, current_score: float) -> Momentum:
        """Compute momentum from score history."""
        history = self._score_history.get(entity, [])
        if len(history) < 2:
            return Momentum.STABLE

        # Compare current to previous
        previous = history[-1] if history else current_score
        delta = current_score - previous

        if delta > 5:  # > 5 points increase
            return Momentum.ACCELERATING
        elif delta < -5:  # > 5 points decrease
            return Momentum.DECELERATING
        return Momentum.STABLE

    def _collect_risk_factors(
        self,
        entity: str,
        commitment_score: float,
        sentiment_score: float,
        relationship_score: float,
        historical_score: float = 0.5,
    ) -> list[RiskFactor]:
        """Collect risk factors that negatively impact the deal."""
        risks = []

        if commitment_score < 0.4:
            risks.append(RiskFactor(
                factor_type="commitment_health",
                severity="high" if commitment_score < 0.2 else "medium",
                description=f"Poor commitment health (score: {commitment_score:.0%}) — overdue or broken commitments",
                evidence={"source": "commitment_tracker", "score": commitment_score},
            ))

        if sentiment_score < 0.4:
            risks.append(RiskFactor(
                factor_type="sentiment_decline",
                severity="high" if sentiment_score < 0.2 else "medium",
                description=f"Negative sentiment trends detected (score: {sentiment_score:.0%})",
                evidence={"source": "sentiment_engine", "score": sentiment_score},
            ))

        if relationship_score < 0.4:
            risks.append(RiskFactor(
                factor_type="stale_relationship",
                severity="medium",
                description=f"Relationship engagement is low (score: {relationship_score:.0%})",
                evidence={"source": "oem_signal_history", "score": relationship_score},
            ))

        if historical_score < 0.4:
            risks.append(RiskFactor(
                factor_type="poor_history",
                severity="high" if historical_score < 0.2 else "medium",
                description=f"Poor historical deal outcomes (win rate: {historical_score:.0%})",
                evidence={"source": "deal_outcome_history", "score": historical_score},
            ))

        return risks

    def _collect_positive_indicators(
        self,
        entity: str,
        commitment_score: float,
        sentiment_score: float,
        relationship_score: float,
    ) -> list[str]:
        """Collect positive indicators for the deal."""
        indicators = []

        if commitment_score > 0.7:
            indicators.append("Strong commitment health — commitments being kept")
        if sentiment_score > 0.7:
            indicators.append("Positive sentiment trends detected")
        if relationship_score > 0.7:
            indicators.append("High engagement — recent interactions are frequent")

        return indicators
