"""
Cross-feature compounding links — strengthens the 3 weak pairs identified
in the System Integration Review.

1. Deal Health + Commitment Escalation: deal health drops when commitments overdue
2. Sentiment + Cross-Meeting Threads: sentiment trends tracked across meetings
3. Meeting Grade + Email/Slack: grade boosted if follow-up email sent within 24h

These are the integration wires that make 10 features compound into a
single intelligence system, not 10 isolated tools.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class CrossFeatureCompounding:
    """
    Wires the 3 weak compounding pairs identified in the system integration review.

    Usage:
        compounding = CrossFeatureCompounding()

        # Link 1: Deal Health incorporates overdue commitments
        adjusted_score = compounding.adjust_deal_health_for_commitments(
            base_score=75.0, overdue_count=3
        )

        # Link 2: Sentiment trend across meetings
        trend = compounding.compute_sentiment_trend_across_meetings(
            meeting_sentiments=[0.7, 0.5, 0.3, 0.2]
        )

        # Link 3: Meeting grade boosted if follow-up sent
        adjusted_grade = compounding.adjust_meeting_grade_for_followup(
            base_grade_score=72.0, follow_up_sent_within_24h=True
        )
    """

    # Link 1: Deal Health + Commitment Escalation
    OVERDUE_COMMITMENT_PENALTY = 5.0  # points per overdue commitment
    MAX_COMMITMENT_PENALTY = 25.0     # cap to prevent one entity from tanking the score

    def adjust_deal_health_for_commitments(
        self, base_score: float, overdue_count: int
    ) -> float:
        """Link 1: Deal Health drops when commitments are overdue.

        Each overdue commitment reduces the deal health score by 5 points
        (capped at 25 points). This makes Deal Health and Commitment
        Escalation compound — overdue commitments drag down the deal.
        """
        penalty = min(overdue_count * self.OVERDUE_COMMITMENT_PENALTY, self.MAX_COMMITMENT_PENALTY)
        adjusted = max(0.0, base_score - penalty)
        logger.debug(
            "CrossFeatureCompounding: deal health adjusted %+.0f → %.1f (overdue=%d)",
            -penalty, adjusted, overdue_count,
        )
        return adjusted

    # Link 2: Sentiment + Cross-Meeting Threads
    SENTIMENT_DECLINE_THRESHOLD = -0.1  # slope < -0.1 = declining

    def compute_sentiment_trend_across_meetings(
        self, meeting_sentiments: list[float]
    ) -> dict:
        """Link 2: Track sentiment trends across meetings.

        Takes a list of average sentiment scores (one per meeting, chronological)
        and computes the trend. If sentiment is declining, surfaces a warning
        that can be threaded into the cross-meeting narrative.
        """
        if len(meeting_sentiments) < 2:
            return {
                "trend": "insufficient_data",
                "slope": 0.0,
                "warning": None,
                "evidence": {"source": "cross_meeting_sentiment", "meetings": len(meeting_sentiments)},
            }

        # Compute linear regression slope
        n = len(meeting_sentiments)
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(meeting_sentiments) / n
        numerator = sum((x[i] - x_mean) * (meeting_sentiments[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0.0

        if slope < self.SENTIMENT_DECLINE_THRESHOLD:
            trend = "declining"
            warning = f"Sentiment declining across meetings (slope: {slope:.2f}). Recent meetings are more negative."
        elif slope > 0.1:
            trend = "improving"
            warning = f"Sentiment improving across meetings (slope: {slope:.2f}). Recent meetings are more positive."
        else:
            trend = "stable"
            warning = None

        return {
            "trend": trend,
            "slope": round(slope, 3),
            "warning": warning,
            "current_sentiment": meeting_sentiments[-1],
            "previous_sentiment": meeting_sentiments[-2],
            "evidence": {
                "source": "cross_meeting_sentiment",
                "meetings": n,
                "sentiments": meeting_sentiments,
            },
        }

    # Link 3: Meeting Grade + Email/Slack
    FOLLOW_UP_BOOST = 5.0  # points added if follow-up sent within 24h

    def adjust_meeting_grade_for_followup(
        self, base_grade_score: float, follow_up_sent_within_24h: bool
    ) -> float:
        """Link 3: Meeting grade boosted if follow-up email sent within 24h.

        A meeting where action items are followed up promptly is more
        effective than one where they're ignored. This wires Meeting Grade
        to the Workplace Signal Fusion (email/Slack) engine.
        """
        if follow_up_sent_within_24h:
            adjusted = min(100.0, base_grade_score + self.FOLLOW_UP_BOOST)
            logger.debug(
                "CrossFeatureCompounding: meeting grade boosted %+.0f → %.1f (follow-up sent)",
                self.FOLLOW_UP_BOOST, adjusted,
            )
            return adjusted
        return base_grade_score

    def check_follow_up_sent(
        self, meeting_end_time: datetime, signals: list[dict]
    ) -> bool:
        """Check if a follow-up email/Slack was sent within 24h of the meeting.

        Args:
            meeting_end_time: when the meeting ended
            signals: list of workplace signals (from WorkplaceSignalFusion)

        Returns True if any email/Slack was sent within 24h after the meeting.
        """
        cutoff = meeting_end_time + timedelta(hours=24)
        for signal in signals:
            signal_time = signal.get("timestamp")
            if isinstance(signal_time, str):
                try:
                    signal_time = datetime.fromisoformat(signal_time.replace("Z", "+00:00"))
                except ValueError:
                    continue
            if isinstance(signal_time, datetime):
                if meeting_end_time <= signal_time <= cutoff:
                    return True
        return False
