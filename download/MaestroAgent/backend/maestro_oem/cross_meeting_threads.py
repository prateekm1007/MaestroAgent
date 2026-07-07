"""
Cross-Meeting Thread Builder — conversation continuity across meetings.

Phase 14 of the Ambient Intelligence roadmap (Days 84-93, 40 hours).

REALITY CHECK CAVEAT: Topic tracking is 70-80% accurate (not 100%).
This module requires user confirmation for low-confidence links (<70%).
Allow manual threading. Show topic hierarchies, not just flat topics.

What it does:
  1. Links meetings by entity + topic: "This continues the Q3 renewal
     discussion from Oct 15"
  2. Tracks decisions across meetings: "Decided to offer phased rollout
     (Oct 22); confirmed in Nov 5 call"
  3. Topic evolution: "Pricing → Volume discounts → 500+ seats"
  4. Confidence scoring: high-confidence links auto-thread; low-confidence
     links require user confirmation

Privacy: processes transcripts locally. No data leaves the user's device
without consent.

RICHER dimension: connects meetings into a coherent narrative, not
isolated events.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ThreadConfidence(str, Enum):
    """Confidence level for a meeting link."""
    HIGH = "high"        # >= 70% — auto-thread
    MEDIUM = "medium"    # 50-69% — suggest, user confirms
    LOW = "low"          # < 50% — don't link


@dataclass
class MeetingSummary:
    """Summary of a single meeting for threading purposes."""
    meeting_id: str
    title: str
    entity: Optional[str]
    start_time: datetime
    attendees: list[str]
    topics: list[str]
    decisions: list[str]
    commitments: list[str]
    transcript_text: str = ""
    # Link 2 compounding: optional per-meeting sentiment score (0.0-1.0).
    # When provided, CrossMeetingThreadBuilder enriches each thread with a
    # sentiment trend via CrossFeatureCompounding.compute_sentiment_trend_across_meetings().
    sentiment: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "meeting_id": self.meeting_id,
            "title": self.title,
            "entity": self.entity,
            "start_time": self.start_time.isoformat() if isinstance(self.start_time, datetime) else str(self.start_time),
            "attendees": self.attendees,
            "topics": self.topics,
            "decisions": self.decisions,
            "commitments": self.commitments,
            "sentiment": self.sentiment,
        }


@dataclass
class MeetingThread:
    """A thread linking related meetings."""
    thread_id: str
    entity: str
    topic: str
    meetings: list[MeetingSummary] = field(default_factory=list)
    confidence: float = 0.0
    confidence_level: ThreadConfidence = ThreadConfidence.LOW
    requires_confirmation: bool = False
    topic_evolution: list[str] = field(default_factory=list)
    decision_chain: list[dict] = field(default_factory=list)
    # Link 2 compounding: sentiment trend across the thread's meetings.
    # Populated by CrossFeatureCompounding.compute_sentiment_trend_across_meetings()
    # when meetings have sentiment data. None when insufficient data.
    sentiment_trend: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "thread_id": self.thread_id,
            "entity": self.entity,
            "topic": self.topic,
            "meeting_count": len(self.meetings),
            "meetings": [m.to_dict() for m in self.meetings],
            "confidence": round(self.confidence, 2),
            "confidence_level": self.confidence_level.value,
            "requires_confirmation": self.requires_confirmation,
            "topic_evolution": self.topic_evolution,
            "decision_chain": self.decision_chain,
            "sentiment_trend": self.sentiment_trend,
        }


class CrossMeetingThreadBuilder:
    """
    Builds threads linking related meetings by entity + topic.

    REALITY CHECK: 70-80% accuracy. Low-confidence links (<70%) require
    user confirmation. Allow manual threading.

    Usage:
        builder = CrossMeetingThreadBuilder()
        builder.add_meeting(meeting_summary)
        threads = builder.build_threads()
        for thread in threads:
            if thread.requires_confirmation:
                print(f"SUGGEST: Are these {len(thread.meetings)} meetings related? [Yes/No]")
            else:
                print(f"LINKED: {thread.topic} ({len(thread.meetings)} meetings)")
    """

    # Topic keywords for matching
    TOPIC_KEYWORDS = {
        "pricing": ["pricing", "price", "cost", "budget", "discount", "quote"],
        "sso": ["sso", "single sign-on", "authentication", "identity"],
        "renewal": ["renewal", "renew", "contract", "term"],
        "integration": ["integration", "integrate", "api", "connector"],
        "security": ["security", "compliance", "audit", "soc2"],
        "deployment": ["deploy", "deployment", "rollout", "launch"],
        "roadmap": ["roadmap", "timeline", "milestone", "deliverable"],
    }

    CONFIRMATION_THRESHOLD = 0.70  # < 70% requires user confirmation

    def __init__(self):
        self._meetings: list[MeetingSummary] = []
        self._confirmed_threads: set[str] = set()  # user-confirmed thread IDs
        self._rejected_threads: set[str] = set()  # user-rejected thread IDs

    def add_meeting(self, meeting: MeetingSummary) -> None:
        """Add a meeting to the thread builder."""
        self._meetings.append(meeting)

    def add_meeting_from_dict(self, data: dict) -> None:
        """Add a meeting from a dict (as received from the post-call summary)."""
        start = data.get("start_time")
        if isinstance(start, str):
            try:
                start = datetime.fromisoformat(start.replace("Z", "+00:00"))
            except ValueError:
                start = datetime.now(timezone.utc)
        elif not isinstance(start, datetime):
            start = datetime.now(timezone.utc)

        meeting = MeetingSummary(
            meeting_id=data.get("meeting_id", f"meeting-{len(self._meetings)}"),
            title=data.get("title", "Untitled"),
            entity=data.get("entity"),
            start_time=start,
            attendees=data.get("attendees", []),
            topics=data.get("topics", []),
            decisions=data.get("decisions", []),
            commitments=data.get("commitments", []),
            transcript_text=data.get("transcript_text", ""),
        )
        self.add_meeting(meeting)

    def build_threads(self) -> list[MeetingThread]:
        """Build threads linking related meetings.

        Returns threads sorted by confidence (highest first).
        Low-confidence threads (<70%) are marked requires_confirmation.
        """
        threads: list[MeetingThread] = []

        # Group meetings by entity
        entity_groups: dict[str, list[MeetingSummary]] = {}
        for meeting in self._meetings:
            entity = meeting.entity or "unknown"
            if entity not in entity_groups:
                entity_groups[entity] = []
            entity_groups[entity].append(meeting)

        # For each entity, find topic-linked meetings
        for entity, meetings in entity_groups.items():
            if len(meetings) < 2:
                continue  # need at least 2 meetings for a thread

            # Sort by start time
            meetings.sort(key=lambda m: m.start_time if isinstance(m.start_time, datetime) else datetime.min)

            # Find topic overlaps
            for i, m1 in enumerate(meetings):
                for m2 in meetings[i + 1:]:
                    topics_overlap, matched_topics, confidence = self._compute_topic_overlap(m1, m2)

                    if topics_overlap and confidence > 0.3:  # minimum threshold
                        # Check if already in a thread
                        thread = self._find_or_create_thread(threads, entity, matched_topics[0])

                        if m1 not in thread.meetings:
                            thread.meetings.append(m1)
                        if m2 not in thread.meetings:
                            thread.meetings.append(m2)

                        # Update confidence (max of existing + new)
                        thread.confidence = max(thread.confidence, confidence)
                        thread.confidence_level = self._confidence_level(thread.confidence)
                        thread.requires_confirmation = thread.confidence < self.CONFIRMATION_THRESHOLD

                        # Build topic evolution
                        self._update_topic_evolution(thread, m1, m2)

                        # Build decision chain
                        self._update_decision_chain(thread, m1, m2)

        # Filter out rejected threads
        threads = [t for t in threads if t.thread_id not in self._rejected_threads]

        # ── Cross-feature compounding (Link 2): Sentiment + Threads ──────
        # Wire CrossFeatureCompounding.compute_sentiment_trend_across_meetings()
        # into the production call path. Each thread's meetings are enriched
        # with a sentiment trend so the user sees "sentiment is declining
        # across this conversation thread" — not just isolated per-meeting
        # sentiment. This makes Sentiment and Cross-Meeting Threads compound.
        from maestro_oem.cross_feature_compounding import CrossFeatureCompounding
        compounding = CrossFeatureCompounding()
        for thread in threads:
            # Sort meetings chronologically for trend computation
            sorted_meetings = sorted(
                thread.meetings,
                key=lambda m: m.start_time if isinstance(m.start_time, datetime) else datetime.min,
            )
            sentiments = [
                m.sentiment for m in sorted_meetings
                if m.sentiment is not None
            ]
            if len(sentiments) >= 2:
                thread.sentiment_trend = compounding.compute_sentiment_trend_across_meetings(
                    meeting_sentiments=sentiments
                )

        # Sort by confidence (highest first)
        threads.sort(key=lambda t: t.confidence, reverse=True)

        return threads

    def _compute_topic_overlap(
        self, m1: MeetingSummary, m2: MeetingSummary
    ) -> tuple[bool, list[str], float]:
        """Compute topic overlap between two meetings.

        Returns (has_overlap, matched_topics, confidence).
        Confidence is based on:
          - Number of overlapping topics (40%)
          - Attendee overlap (30%)
          - Time proximity (30%)
        """
        # Topic matching
        m1_topics = set(t.lower() for t in m1.topics)
        m2_topics = set(t.lower() for t in m2.topics)
        direct_overlap = m1_topics & m2_topics

        # Keyword-based topic matching (for topics phrased differently)
        keyword_matches = set()
        for topic_category, keywords in self.TOPIC_KEYWORDS.items():
            m1_has = any(kw in " ".join(m1.topics).lower() for kw in keywords)
            m2_has = any(kw in " ".join(m2.topics).lower() for kw in keywords)
            if m1_has and m2_has:
                keyword_matches.add(topic_category)

        all_matches = direct_overlap | keyword_matches
        if not all_matches:
            return False, [], 0.0

        # Topic confidence: more matches = higher confidence
        topic_confidence = min(0.4, len(all_matches) * 0.15)

        # Attendee overlap
        m1_attendees = set(a.lower() for a in m1.attendees)
        m2_attendees = set(a.lower() for a in m2.attendees)
        attendee_overlap = len(m1_attendees & m2_attendees)
        attendee_confidence = min(0.3, attendee_overlap * 0.1)

        # Time proximity (closer meetings = more likely related)
        if isinstance(m1.start_time, datetime) and isinstance(m2.start_time, datetime):
            time_delta = abs((m1.start_time - m2.start_time).days)
            if time_delta <= 7:
                time_confidence = 0.3
            elif time_delta <= 30:
                time_confidence = 0.2
            elif time_delta <= 90:
                time_confidence = 0.1
            else:
                time_confidence = 0.0
        else:
            time_confidence = 0.0

        total_confidence = topic_confidence + attendee_confidence + time_confidence
        return True, list(all_matches), total_confidence

    def _confidence_level(self, confidence: float) -> ThreadConfidence:
        """Map confidence score to level."""
        if confidence >= 0.70:
            return ThreadConfidence.HIGH
        elif confidence >= 0.50:
            return ThreadConfidence.MEDIUM
        return ThreadConfidence.LOW

    def _find_or_create_thread(
        self, threads: list[MeetingThread], entity: str, topic: str
    ) -> MeetingThread:
        """Find an existing thread for this entity+topic, or create a new one."""
        for thread in threads:
            if thread.entity == entity and topic.lower() in thread.topic.lower():
                return thread

        thread = MeetingThread(
            thread_id=f"thread-{entity}-{topic}-{len(threads)}",
            entity=entity,
            topic=topic,
        )
        threads.append(thread)
        return thread

    def _update_topic_evolution(
        self, thread: MeetingThread, m1: MeetingSummary, m2: MeetingSummary
    ) -> None:
        """Track how topics evolved across meetings."""
        for topic in m2.topics:
            if topic not in thread.topic_evolution:
                thread.topic_evolution.append(topic)

    def _update_decision_chain(
        self, thread: MeetingThread, m1: MeetingSummary, m2: MeetingSummary
    ) -> None:
        """Track decisions across meetings."""
        for decision in m1.decisions:
            entry = {
                "meeting_id": m1.meeting_id,
                "decision": decision,
                "date": m1.start_time.isoformat() if isinstance(m1.start_time, datetime) else "",
            }
            if entry not in thread.decision_chain:
                thread.decision_chain.append(entry)
        for decision in m2.decisions:
            entry = {
                "meeting_id": m2.meeting_id,
                "decision": decision,
                "date": m2.start_time.isoformat() if isinstance(m2.start_time, datetime) else "",
            }
            if entry not in thread.decision_chain:
                thread.decision_chain.append(entry)

    def confirm_thread(self, thread_id: str) -> None:
        """User confirms a low-confidence thread (manual correction)."""
        self._confirmed_threads.add(thread_id)

    def reject_thread(self, thread_id: str) -> None:
        """User rejects a suggested thread (manual correction)."""
        self._rejected_threads.add(thread_id)

    def get_threads_for_entity(self, entity: str) -> list[MeetingThread]:
        """Get all threads for a specific entity."""
        threads = self.build_threads()
        return [t for t in threads if t.entity == entity]

    def get_decision_history(self, entity: str) -> list[dict]:
        """Get the decision chain for an entity across all meetings."""
        threads = self.get_threads_for_entity(entity)
        decisions = []
        for thread in threads:
            decisions.extend(thread.decision_chain)
        decisions.sort(key=lambda d: d.get("date", ""))
        return decisions
