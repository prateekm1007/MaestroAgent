"""
Meeting Grader - meeting effectiveness score, action items, follow-up tracking.

Phase 16 of the Ambient Intelligence roadmap (Days 104-113, 40 hours).

REALITY CHECK VERDICT: REALISTIC - build, but keep grading simple and
transparent. Meeting grade is subjective; action items are objective.
Use multi-factor grade: 30% action items, 30% sentiment, 20% participation,
20% duration. Allow user override.

What it does:
  1. Meeting effectiveness score (A-F) from 4 factors
  2. Action item extraction + completion tracking
  3. Follow-up tracking across meetings (did committed actions get done?)
  4. User override (allow salesperson to adjust grade based on intuition)

Ethical guard: the grade is a decision support tool, not a judgment of
the person. Transparent scoring (show contributing factors). Allow override.
The constitution: "The organization becomes more capable, not more dependent."

DEEPER dimension: multi-layer intelligence (action items + sentiment +
participation + duration -> single grade with transparent factors).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class MeetingGrade(str, Enum):
    """Letter grade for meeting effectiveness."""
    A = "A"  # 90-100
    B = "B"  # 80-89
    C = "C"  # 70-79
    D = "D"  # 60-69
    F = "F"  # < 60


@dataclass
class ActionItem:
    """An action item extracted from the meeting."""
    text: str
    owner: str = ""
    due_date: Optional[str] = None  # ISO date string
    completed: bool = False
    completed_at: Optional[datetime] = None
    source: str = ""  # which meeting produced this action item

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "owner": self.owner,
            "due_date": self.due_date,
            "completed": self.completed,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "source": self.source,
        }


@dataclass
class MeetingGradeReport:
    """Full meeting grade report with transparent factors."""
    grade: MeetingGrade
    score: float  # 0-100
    factors: dict  # transparent breakdown
    action_items: list[ActionItem] = field(default_factory=list)
    action_item_completion_rate: float = 0.0  # 0-100
    follow_ups_pending: int = 0
    follow_ups_completed: int = 0
    user_override: Optional[MeetingGrade] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    calibration_denominator: int = 0  # P25

    @property
    def confidence_label(self) -> str:
        """P25: confidence display gate."""
        if self.calibration_denominator < 10:
            return "insufficient calibration history"
        return f"calibrated from {self.calibration_denominator} meetings"

    @property
    def effective_grade(self) -> MeetingGrade:
        """The grade after user override (if any)."""
        return self.user_override if self.user_override else self.grade

    def to_dict(self) -> dict:
        return {
            "grade": self.grade.value,
            "effective_grade": self.effective_grade.value,
            "score": round(self.score, 1),
            "factors": self.factors,
            "action_items": [a.to_dict() for a in self.action_items],
            "action_item_completion_rate": round(self.action_item_completion_rate, 1),
            "follow_ups_pending": self.follow_ups_pending,
            "follow_ups_completed": self.follow_ups_completed,
            "user_override": self.user_override.value if self.user_override else None,
            "confidence_label": self.confidence_label,
            "calibration_denominator": self.calibration_denominator,
            "timestamp": self.timestamp.isoformat(),
        }


class MeetingGrader:
    """
    Grades meeting effectiveness with transparent, multi-factor scoring.

    Usage:
        grader = MeetingGrader()
        grader.set_meeting_data(
            transcript="We decided to ship SSO by Friday. Sam will send pricing.",
            duration_minutes=34,
            talk_ratio_balance=0.55,  # 55% you, 45% them (good balance)
            sentiment_score=0.7,  # from Phase 10
            participants=4,
        )
        report = grader.grade_meeting()
        print(f"Grade: {report.grade.value} ({report.score:.0f}/100)")
        print(f"Action items: {len(report.action_items)}")
        print(f"Factors: {report.factors}")
    """

    # Grade weights (sum to 1.0)
    WEIGHT_ACTION_ITEMS = 0.30
    WEIGHT_SENTIMENT = 0.30
    WEIGHT_PARTICIPATION = 0.20
    WEIGHT_DURATION = 0.20

    # Action item patterns
    ACTION_ITEM_PATTERNS = [
        re.compile(r"\b(?:I\s+will|I'?ll|we\s+will|we'?ll|Sam\s+will|he\s+will|she\s+will|they\s+will|\w+\s+will)\s+(?:send|deliver|ship|prepare|share|follow\s+up|schedule|review|check|confirm)\b", re.IGNORECASE),
        re.compile(r"\b(?:action\s+item|next\s+step|to-?do|follow\s+up)\b", re.IGNORECASE),
        re.compile(r"\b(?:by\s+(?:next|this|end\s+of)\s+(?:week|friday|monday|month))\b", re.IGNORECASE),
    ]

    # Owner extraction patterns
    OWNER_PATTERN = re.compile(r"\b(?:I\s+will|I'?ll)\b", re.IGNORECASE)
    THIRD_PARTY_OWNER_PATTERN = re.compile(r"\b(\w+)\s+will\s+(?:send|deliver|ship|prepare|share|follow\s+up|schedule|review|check|confirm)\b", re.IGNORECASE)

    def __init__(self):
        self._transcript = ""
        self._duration_minutes = 0
        self._talk_ratio_balance = 0.5
        self._sentiment_score = 0.5
        self._participants = 2
        self._action_items: list[ActionItem] = []
        self._follow_ups: dict[str, list[ActionItem]] = {}  # meeting_id -> action items
        self._calibration_meetings: int = 0
        self._user_override: Optional[MeetingGrade] = None

    def set_meeting_data(
        self,
        transcript: str = "",
        duration_minutes: float = 0,
        talk_ratio_balance: float = 0.5,
        sentiment_score: float = 0.5,
        participants: int = 2,
    ) -> None:
        """Set the meeting data for grading."""
        self._transcript = transcript
        self._duration_minutes = duration_minutes
        self._talk_ratio_balance = talk_ratio_balance
        self._sentiment_score = sentiment_score
        self._participants = participants

    def set_user_override(self, grade: MeetingGrade) -> None:
        """Allow user to override the computed grade (transparent, auditable)."""
        self._user_override = grade

    def record_meeting_for_calibration(self) -> None:
        """Record this meeting for calibration (P25 denominator)."""
        self._calibration_meetings += 1

    def grade_meeting(self, meeting_id: str = "") -> MeetingGradeReport:
        """Grade the meeting and return the full report."""
        # 1. Extract action items
        action_items = self._extract_action_items(transcript=self._transcript, source=meeting_id)
        self._action_items = action_items

        # 2. Compute factor scores (each 0-100)
        action_item_score = self._compute_action_item_score(action_items)
        sentiment_factor_score = self._sentiment_score * 100
        participation_score = self._compute_participation_score()
        duration_score = self._compute_duration_score()

        # 3. Weighted combination
        score = (
            action_item_score * self.WEIGHT_ACTION_ITEMS
            + sentiment_factor_score * self.WEIGHT_SENTIMENT
            + participation_score * self.WEIGHT_PARTICIPATION
            + duration_score * self.WEIGHT_DURATION
        )

        # 4. Determine grade
        grade = self._score_to_grade(score)

        # 5. Track follow-ups
        if meeting_id:
            self._follow_ups[meeting_id] = action_items

        follow_ups_pending = sum(1 for items in self._follow_ups.values() for a in items if not a.completed)
        follow_ups_completed = sum(1 for items in self._follow_ups.values() for a in items if a.completed)

        # 6. Action item completion rate
        total_items = len(action_items)
        completed_items = sum(1 for a in action_items if a.completed)
        completion_rate = (completed_items / total_items * 100) if total_items > 0 else 0

        factors = {
            "action_items": {
                "score": round(action_item_score, 1),
                "weight": self.WEIGHT_ACTION_ITEMS,
                "count": len(action_items),
                "note": "More clear action items = higher score",
            },
            "sentiment": {
                "score": round(sentiment_factor_score, 1),
                "weight": self.WEIGHT_SENTIMENT,
                "note": "From Phase 10 sentiment engine",
            },
            "participation": {
                "score": round(participation_score, 1),
                "weight": self.WEIGHT_PARTICIPATION,
                "talk_ratio_balance": round(self._talk_ratio_balance, 2),
                "participants": self._participants,
                "note": "Balanced participation = higher score",
            },
            "duration": {
                "score": round(duration_score, 1),
                "weight": self.WEIGHT_DURATION,
                "duration_minutes": round(self._duration_minutes, 1),
                "note": "30-60 min = ideal; too long = fatigue",
            },
        }

        return MeetingGradeReport(
            grade=grade,
            score=score,
            factors=factors,
            action_items=action_items,
            action_item_completion_rate=completion_rate,
            follow_ups_pending=follow_ups_pending,
            follow_ups_completed=follow_ups_completed,
            user_override=self._user_override,
            calibration_denominator=self._calibration_meetings,
        )

    def mark_action_item_completed(self, meeting_id: str, action_text: str) -> None:
        """Mark an action item as completed (follow-up tracking)."""
        if meeting_id in self._follow_ups:
            for item in self._follow_ups[meeting_id]:
                if action_text.lower() in item.text.lower():
                    item.completed = True
                    item.completed_at = datetime.now(timezone.utc)
                    break

    def get_follow_up_status(self) -> list[dict]:
        """Get follow-up status across all meetings."""
        status = []
        for meeting_id, items in self._follow_ups.items():
            for item in items:
                status.append({
                    "meeting_id": meeting_id,
                    "text": item.text,
                    "owner": item.owner,
                    "completed": item.completed,
                    "completed_at": item.completed_at.isoformat() if item.completed_at else None,
                })
        return status

    def _extract_action_items(self, transcript: str, source: str = "") -> list[ActionItem]:
        """Extract action items from the transcript.

        Uses pattern matching to find commitments and next steps.
        """
        if not transcript:
            return []

        items = []
        sentences = re.split(r"[.!?]+", transcript)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            for pattern in self.ACTION_ITEM_PATTERNS:
                if pattern.search(sentence):
                    # Determine owner
                    if self.OWNER_PATTERN.search(sentence):
                        owner = "you"
                    else:
                        # Try to extract third-party owner name
                        third_party = self.THIRD_PARTY_OWNER_PATTERN.search(sentence)
                        if third_party:
                            owner = third_party.group(1).lower()
                        else:
                            owner = "unassigned"

                    # Try to extract due date
                    due_date = None
                    due_match = re.search(
                        r"by\s+(next|this|end\s+of)\s+(week|friday|monday|month)",
                        sentence, re.IGNORECASE,
                    )
                    if due_match:
                        due_date = due_match.group(0)

                    items.append(ActionItem(
                        text=sentence[:200],
                        owner=owner,
                        due_date=due_date,
                        source=source,
                    ))
                    break  # one pattern per sentence

        return items

    def _compute_action_item_score(self, items: list[ActionItem]) -> float:
        """Score based on action item quality (0-100).

        - Having action items at all is good (meetings without action items
          are often wasted time)
        - Clear ownership ("I will") is better than vague ("someone should")
        - Due dates are better than no due dates
        """
        if not items:
            return 40.0  # meetings with no action items are low-scoring

        score = 50.0  # base for having items
        for item in items:
            if item.owner:
                score += 5  # clear ownership
            if item.due_date:
                score += 5  # clear deadline

        # Cap at 100
        return min(100.0, score)

    def _compute_participation_score(self) -> float:
        """Score based on participation balance (0-100).

        - 40-60% talk ratio balance = ideal (100)
        - <30% or >70% = poor (40)
        - More participants = better engagement
        """
        balance = self._talk_ratio_balance
        if 0.4 <= balance <= 0.6:
            balance_score = 100.0
        elif 0.3 <= balance <= 0.7:
            balance_score = 70.0
        else:
            balance_score = 40.0

        # Participant bonus
        participant_bonus = min(20, (self._participants - 2) * 5)

        return min(100.0, balance_score + participant_bonus)

    def _compute_duration_score(self) -> float:
        """Score based on meeting duration (0-100).

        - 30-60 min = ideal (100)
        - 15-30 or 60-90 = good (80)
        - <15 or >90 = poor (50)
        """
        d = self._duration_minutes
        if 30 <= d <= 60:
            return 100.0
        elif 15 <= d < 30 or 60 < d <= 90:
            return 80.0
        elif d > 0:
            return 50.0
        return 50.0

    def _score_to_grade(self, score: float) -> MeetingGrade:
        """Convert numeric score to letter grade."""
        if score >= 90:
            return MeetingGrade.A
        elif score >= 80:
            return MeetingGrade.B
        elif score >= 70:
            return MeetingGrade.C
        elif score >= 60:
            return MeetingGrade.D
        return MeetingGrade.F
