"""
Advanced Analytics Engine - trend analysis, team performance, org learning.

Phase 20 of the Ambient Intelligence roadmap (Days 144-153, 40 hours).

REALITY CHECK VERDICT: REALISTIC - build. Trend analysis is simple
arithmetic. Team performance is aggregate (never individual surveillance).
Org learning metrics tie to OutcomeLedger + law promotion.

This is the MASTER GATE phase. It proves the flywheel is compounding:
  - Brier score improvement (predictions getting more accurate)
  - Law promotion rate (patterns becoming validated laws)
  - Pattern validation rate (candidate patterns getting validated)
  - Deal cycle time trends (getting faster or slower)
  - Meeting effectiveness trends (grades improving or declining)
  - Commitment kept/broken ratio (improving or declining)

AMBIENT dimension: the dashboard shows the organization getting smarter
over time. This is the moat: Cluely has GPT. Maestro has your
organization's entire history, learning from every interaction.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TrendDirection(str, Enum):
    """Direction of a trend."""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"


@dataclass
class TrendMetric:
    """A single trend metric."""
    name: str
    current_value: float
    previous_value: float
    direction: TrendDirection
    change_percentage: float
    period: str  # "30d", "90d", "365d"
    description: str = ""
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "current_value": round(self.current_value, 2),
            "previous_value": round(self.previous_value, 2),
            "direction": self.direction.value,
            "change_percentage": round(self.change_percentage, 1),
            "period": self.period,
            "description": self.description,
            "evidence": self.evidence,
        }


@dataclass
class TeamPerformanceMetric:
    """Aggregate team performance metric (never individual surveillance)."""
    metric_name: str
    team_average: float
    team_count: int  # number of team members in the aggregate
    period: str
    description: str = ""
    # P25: denominator = number of data points
    calibration_denominator: int = 0

    @property
    def confidence_label(self) -> str:
        """P25: confidence display gate."""
        if self.calibration_denominator < 10:
            return "insufficient calibration history"
        return f"calibrated from {self.calibration_denominator} data points"

    def to_dict(self) -> dict:
        return {
            "metric_name": self.metric_name,
            "team_average": round(self.team_average, 2),
            "team_count": self.team_count,
            "period": self.period,
            "description": self.description,
            "confidence_label": self.confidence_label,
            "calibration_denominator": self.calibration_denominator,
        }


@dataclass
class OrgLearningReport:
    """Full organizational learning report - the master gate deliverable."""
    trends: list[TrendMetric] = field(default_factory=list)
    team_performance: list[TeamPerformanceMetric] = field(default_factory=list)
    laws_validated: int = 0
    laws_candidate: int = 0
    patterns_detected: int = 0
    brier_score: Optional[float] = None
    brier_score_previous: Optional[float] = None
    brier_trend: Optional[TrendDirection] = None
    commitment_kept_rate: float = 0.0
    commitment_broken_rate: float = 0.0
    meeting_grade_average: float = 0.0
    deal_cycle_time_days: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "trends": [t.to_dict() for t in self.trends],
            "team_performance": [tp.to_dict() for tp in self.team_performance],
            "laws_validated": self.laws_validated,
            "laws_candidate": self.laws_candidate,
            "patterns_detected": self.patterns_detected,
            "brier_score": round(self.brier_score, 4) if self.brier_score else None,
            "brier_score_previous": round(self.brier_score_previous, 4) if self.brier_score_previous else None,
            "brier_trend": self.brier_trend.value if self.brier_trend else None,
            "commitment_kept_rate": round(self.commitment_kept_rate, 2),
            "commitment_broken_rate": round(self.commitment_broken_rate, 2),
            "meeting_grade_average": round(self.meeting_grade_average, 1),
            "deal_cycle_time_days": round(self.deal_cycle_time_days, 1),
            "timestamp": self.timestamp.isoformat(),
        }


class AdvancedAnalyticsEngine:
    """
    Advanced analytics: trends, team performance, organizational learning.

    This is the master gate engine. It proves the flywheel is compounding
    by showing trends over time. Team performance is AGGREGATE only —
    no individual surveillance (privacy safeguard).

    Usage:
        engine = AdvancedAnalyticsEngine()
        engine.record_data_point("commitment_kept_rate", 0.72, period="30d")
        engine.record_data_point("commitment_kept_rate", 0.85, period="current")
        report = engine.generate_report()
        print(f"Brier: {report.brier_score}")
        print(f"Commitment kept rate: {report.commitment_kept_rate}")
    """

    def __init__(self):
        self._data_points: dict[str, list[tuple[str, float]]] = {}  # metric -> [(period, value)]
        self._brier_scores: list[tuple[datetime, float]] = []
        self._meeting_grades: list[str] = []  # letter grades
        self._deal_cycle_times: list[float] = []  # days
        self._commitments: dict[str, int] = {"kept": 0, "broken": 0}
        self._laws: dict[str, int] = {"validated": 0, "candidate": 0}
        self._patterns_detected: int = 0
        self._team_data: dict[str, list[float]] = {}  # metric -> [values per team member]
        self._calibration_count: int = 0

    def record_data_point(self, metric: str, value: float, period: str = "current") -> None:
        """Record a data point for trend analysis."""
        if metric not in self._data_points:
            self._data_points[metric] = []
        self._data_points[metric].append((period, value))

    def record_brier_score(self, score: float, timestamp: Optional[datetime] = None) -> None:
        """Record a Brier score measurement (prediction calibration)."""
        self._brier_scores.append((timestamp or datetime.now(timezone.utc), score))

    def record_meeting_grade(self, grade: str) -> None:
        """Record a meeting grade for average calculation."""
        self._meeting_grades.append(grade)

    def record_deal_cycle_time(self, days: float) -> None:
        """Record a deal cycle time (from first contact to close)."""
        self._deal_cycle_times.append(days)

    def record_commitment(self, kept: bool) -> None:
        """Record a commitment outcome (kept or broken)."""
        if kept:
            self._commitments["kept"] += 1
        else:
            self._commitments["broken"] += 1

    def record_law(self, validated: bool) -> None:
        """Record a law status (validated or candidate)."""
        if validated:
            self._laws["validated"] += 1
        else:
            self._laws["candidate"] += 1

    def record_pattern(self) -> None:
        """Record a pattern detection."""
        self._patterns_detected += 1

    def record_team_metric(self, metric: str, value: float) -> None:
        """Record a team metric (aggregate, never individual).

        Privacy: team performance is aggregate only. No individual PII.
        """
        if metric not in self._team_data:
            self._team_data[metric] = []
        self._team_data[metric].append(value)

    def record_calibration(self) -> None:
        """Record a calibration data point (P25)."""
        self._calibration_count += 1

    def generate_report(self) -> OrgLearningReport:
        """Generate the full organizational learning report.

        This is the master gate deliverable. It proves the flywheel
        is compounding by showing trends, team performance, and
        organizational learning metrics.
        """
        trends = self._compute_trends()
        team_performance = self._compute_team_performance()

        # Brier score trend
        brier_current = self._brier_scores[-1][1] if self._brier_scores else None
        brier_previous = self._brier_scores[-2][1] if len(self._brier_scores) >= 2 else None
        brier_trend = None
        if brier_current is not None and brier_previous is not None:
            if brier_current < brier_previous:
                brier_trend = TrendDirection.IMPROVING  # lower Brier = better
            elif brier_current > brier_previous:
                brier_trend = TrendDirection.DECLINING
            else:
                brier_trend = TrendDirection.STABLE

        # Commitment rates
        total_commitments = self._commitments["kept"] + self._commitments["broken"]
        kept_rate = (self._commitments["kept"] / total_commitments * 100) if total_commitments > 0 else 0
        broken_rate = (self._commitments["broken"] / total_commitments * 100) if total_commitments > 0 else 0

        # Meeting grade average (convert letters to numbers)
        grade_map = {"A": 90, "B": 80, "C": 70, "D": 60, "F": 50}
        grade_scores = [grade_map.get(g, 50) for g in self._meeting_grades]
        grade_avg = sum(grade_scores) / len(grade_scores) if grade_scores else 0

        # Deal cycle time average
        cycle_avg = sum(self._deal_cycle_times) / len(self._deal_cycle_times) if self._deal_cycle_times else 0

        return OrgLearningReport(
            trends=trends,
            team_performance=team_performance,
            laws_validated=self._laws["validated"],
            laws_candidate=self._laws["candidate"],
            patterns_detected=self._patterns_detected,
            brier_score=brier_current,
            brier_score_previous=brier_previous,
            brier_trend=brier_trend,
            commitment_kept_rate=kept_rate,
            commitment_broken_rate=broken_rate,
            meeting_grade_average=grade_avg,
            deal_cycle_time_days=cycle_avg,
        )

    def _compute_trends(self) -> list[TrendMetric]:
        """Compute trend metrics from recorded data points."""
        trends = []

        for metric_name, data_points in self._data_points.items():
            if len(data_points) < 2:
                continue

            current = data_points[-1][1]
            previous = data_points[-2][1]

            if previous == 0:
                change_pct = 100.0 if current > 0 else 0.0
            else:
                change_pct = ((current - previous) / previous) * 100

            # Determine direction (metric-specific: some improve when increasing,
            # others when decreasing)
            if "broken" in metric_name.lower() or "brier" in metric_name.lower():
                # Lower is better
                if change_pct < -5:
                    direction = TrendDirection.IMPROVING
                elif change_pct > 5:
                    direction = TrendDirection.DECLINING
                else:
                    direction = TrendDirection.STABLE
            else:
                # Higher is better
                if change_pct > 5:
                    direction = TrendDirection.IMPROVING
                elif change_pct < -5:
                    direction = TrendDirection.DECLINING
                else:
                    direction = TrendDirection.STABLE

            trends.append(TrendMetric(
                name=metric_name,
                current_value=current,
                previous_value=previous,
                direction=direction,
                change_percentage=change_pct,
                period=data_points[-1][0],
                description=self._metric_description(metric_name),
                evidence={"source": "advanced_analytics", "data_points": len(data_points)},
            ))

        return trends

    def _compute_team_performance(self) -> list[TeamPerformanceMetric]:
        """Compute aggregate team performance metrics.

        Privacy: AGGREGATE ONLY. No individual surveillance.
        """
        metrics = []
        for metric_name, values in self._team_data.items():
            if not values:
                continue
            metrics.append(TeamPerformanceMetric(
                metric_name=metric_name,
                team_average=sum(values) / len(values),
                team_count=len(values),
                period="30d",
                description=self._metric_description(metric_name),
                calibration_denominator=self._calibration_count,
            ))
        return metrics

    def _metric_description(self, metric_name: str) -> str:
        """Get a human-readable description for a metric."""
        descriptions = {
            "commitment_kept_rate": "Percentage of commitments that were kept",
            "commitment_broken_rate": "Percentage of commitments that were broken",
            "deal_cycle_time": "Average days from first contact to deal close",
            "meeting_grade": "Average meeting effectiveness grade (0-100)",
            "brier_score": "Prediction calibration score (lower = better)",
            "talk_ratio_balance": "Average talk ratio balance across team meetings",
            "sentiment_score": "Average sentiment score across meetings",
            "pattern_detection_rate": "Rate of new organizational patterns detected",
        }
        return descriptions.get(metric_name, metric_name.replace("_", " ").title())

    def get_flywheel_summary(self) -> str:
        """Get a summary of whether the flywheel is compounding.

        This is the moat: if trends are improving, the organization is
        getting smarter. If stable, it's maintaining. If declining, the
        system is not compounding.
        """
        report = self.generate_report()
        improving = sum(1 for t in report.trends if t.direction == TrendDirection.IMPROVING)
        declining = sum(1 for t in report.trends if t.direction == TrendDirection.DECLINING)

        if report.brier_trend == TrendDirection.IMPROVING:
            brier_note = f"Brier score improving ({report.brier_score:.4f} from {report.brier_score_previous:.4f}) — predictions getting more accurate."
        elif report.brier_trend == TrendDirection.DECLINING:
            brier_note = f"Brier score declining ({report.brier_score:.4f} from {report.brier_score_previous:.4f}) — predictions getting less accurate."
        else:
            brier_note = f"Brier score stable at {report.brier_score:.4f}" if report.brier_score else "No Brier score data yet."

        return (
            f"Flywheel status: {improving} improving, {declining} declining. "
            f"{brier_note} "
            f"Laws: {report.laws_validated} validated, {report.laws_candidate} candidate. "
            f"Commitments: {report.commitment_kept_rate:.0f}% kept, {report.commitment_broken_rate:.0f}% broken. "
            f"Meeting grades: {report.meeting_grade_average:.0f}/100 average. "
            f"Deal cycle: {report.deal_cycle_time_days:.0f} days average."
        )
