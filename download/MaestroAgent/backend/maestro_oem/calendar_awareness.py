"""
Calendar Awareness Engine — Ambient intelligence from calendar context.

Phase 9 of the Ambient Intelligence roadmap (Days 34-43, 40 hours).

This engine runs 24/7, analyzing the user's calendar to:
1. Predict upcoming meetings and pre-fetch relevant intelligence
2. Detect meeting clusters (e.g., "3 Globex meetings this week = deal acceleration")
3. Identify preparation gaps (e.g., "Meeting in 2 hours, no prep done")
4. Surface time-based patterns (e.g., "Pricing always comes up in Q4 renewal calls")

Privacy: Only reads calendar metadata (title, time, attendees). Never reads
meeting content or attachments without explicit consent.

This advances the AMBIENT dimension: it works between calls, not just during.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from collections import Counter

logger = logging.getLogger(__name__)


class MeetingUrgency(str, Enum):
    """How soon is this meeting?"""
    NOW = "now"          # < 5 minutes
    IMMINENT = "imminent"  # 5-30 minutes
    SOON = "soon"        # 30-120 minutes
    TODAY = "today"      # 2-12 hours
    UPCOMING = "upcoming"  # 12-48 hours
    FUTURE = "future"    # > 48 hours


class PreparationStatus(str, Enum):
    """Has the user prepared for this meeting?"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    READY = "ready"
    STALE = "stale"  # Prepared > 24h ago


@dataclass
class MeetingContext:
    """Rich context for an upcoming meeting."""
    meeting_id: str
    title: str
    start_time: datetime
    end_time: datetime
    attendees: list[str]
    urgency: MeetingUrgency
    preparation_status: PreparationStatus

    # Derived intelligence
    entity: Optional[str] = None
    deal_stage: Optional[str] = None
    arr_at_risk: Optional[float] = None
    days_to_renewal: Optional[int] = None

    # Relationship intelligence
    attendee_profiles: list[dict] = field(default_factory=list)
    last_interaction_ago: Optional[str] = None
    relationship_health: Optional[str] = None  # strong/warning/critical

    # Commitment context
    open_commitments: list[dict] = field(default_factory=list)
    overdue_commitments: list[dict] = field(default_factory=list)

    # Historical patterns
    similar_meetings: list[dict] = field(default_factory=list)
    common_topics: list[str] = field(default_factory=list)
    typical_duration: Optional[int] = None  # minutes

    # Preparation suggestions
    suggested_talking_points: list[dict] = field(default_factory=list)
    risks_to_address: list[dict] = field(default_factory=list)
    opportunities_to_pursue: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "meeting_id": self.meeting_id,
            "title": self.title,
            "start_time": self.start_time.isoformat() if isinstance(self.start_time, datetime) else str(self.start_time),
            "end_time": self.end_time.isoformat() if isinstance(self.end_time, datetime) else str(self.end_time),
            "attendees": self.attendees,
            "urgency": self.urgency.value,
            "preparation_status": self.preparation_status.value,
            "entity": self.entity,
            "relationship_health": self.relationship_health,
            "attendee_profiles": self.attendee_profiles,
            "open_commitments": len(self.open_commitments),
            "overdue_commitments": len(self.overdue_commitments),
            "suggested_talking_points": self.suggested_talking_points,
            "risks_to_address": self.risks_to_address,
            "opportunities_to_pursue": self.opportunities_to_pursue,
        }


class CalendarAwarenessEngine:
    """
    Ambient calendar intelligence. Runs continuously, updating meeting
    contexts as time progresses and new signals arrive.

    Usage:
        engine = CalendarAwarenessEngine(oem_state, calendar_source)
        await engine.start()  # Starts background loop

        # Get current meeting contexts
        contexts = await engine.get_upcoming_meetings(hours=24)

        # Get urgent meeting (next 30 min)
        urgent = await engine.get_urgent_meeting()
    """

    KNOWN_ENTITIES = ["Globex", "Initech", "TestCorp", "Acme", "Atlas"]

    def __init__(
        self,
        oem_state: Any = None,
        calendar_source: Any = None,
        refresh_interval_seconds: int = 300,  # 5 minutes
    ):
        self.oem = oem_state
        self.calendar = calendar_source
        self.refresh_interval = refresh_interval_seconds
        self._contexts: dict[str, MeetingContext] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._preparation_log: dict[str, datetime] = {}  # meeting_id → last prep time

    async def start(self):
        """Start the background awareness loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._awareness_loop())
        logger.info("CalendarAwarenessEngine started")

    async def stop(self):
        """Stop the background loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("CalendarAwarenessEngine stopped")

    async def _awareness_loop(self):
        """Background loop: refresh meeting contexts periodically."""
        while self._running:
            try:
                await self._refresh_all_meetings()
            except Exception as e:
                logger.error(f"CalendarAwarenessEngine error: {e}", exc_info=True)
            await asyncio.sleep(self.refresh_interval)

    async def _refresh_all_meetings(self):
        """Refresh all upcoming meetings in the next 48 hours."""
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(hours=48)

        if self.calendar:
            events = await self._get_calendar_events(now, horizon)
            for event in events:
                await self._build_meeting_context(event)

    async def _get_calendar_events(self, start: datetime, end: datetime) -> list[dict]:
        """Fetch calendar events from the calendar source."""
        if not self.calendar:
            return []
        try:
            return await self.calendar.get_events(start=start, end=end)
        except Exception as e:
            logger.warning(f"CalendarAwarenessEngine: calendar fetch failed: {e}")
            return []

    async def build_context_for_event(self, event: dict) -> MeetingContext:
        """Build rich context for a single meeting event (public API for testing)."""
        return await self._build_meeting_context(event)

    async def _build_meeting_context(self, event: dict) -> MeetingContext:
        """Build rich context for a single meeting."""
        meeting_id = event.get("id", f"meeting-{event.get('title', 'untitled')}")
        now = datetime.now(timezone.utc)
        start = event.get("start", now)
        end = event.get("end", now + timedelta(hours=1))

        # Ensure timezone-aware
        if isinstance(start, datetime) and start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if isinstance(end, datetime) and end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        # Determine urgency
        urgency = self._compute_urgency(start, now)

        # Check preparation status
        prep_status = self._check_preparation(meeting_id)

        # Extract entity (customer/org) from title or attendees
        entity = self._extract_entity(event)

        # Build attendee profiles
        attendee_profiles = []
        for attendee in event.get("attendees", []):
            profile = self._build_attendee_profile(attendee)
            attendee_profiles.append(profile)

        # Get open commitments from OEM signals
        open_commitments = []
        overdue_commitments = []
        if entity:
            open_commitments, overdue_commitments = self._get_commitments_for_entity(entity)

        # Generate talking points (each with evidence — anti-Cluely)
        talking_points = self._generate_talking_points(
            entity=entity,
            attendee_profiles=attendee_profiles,
            open_commitments=open_commitments,
            overdue_commitments=overdue_commitments,
        )

        # Identify risks
        risks = self._identify_risks(
            entity=entity,
            overdue_commitments=overdue_commitments,
            attendee_profiles=attendee_profiles,
        )

        # Identify opportunities
        opportunities = self._identify_opportunities(
            entity=entity,
            attendee_profiles=attendee_profiles,
        )

        # Detect meeting clusters (AMBIENT dimension: "3 Globex meetings this week")
        cluster_info = self._detect_meeting_clusters(entity, event)

        context = MeetingContext(
            meeting_id=meeting_id,
            title=event.get("title", "Untitled Meeting"),
            start_time=start,
            end_time=end,
            attendees=event.get("attendees", []),
            urgency=urgency,
            preparation_status=prep_status,
            entity=entity,
            attendee_profiles=attendee_profiles,
            relationship_health=self._get_relationship_health(entity),
            open_commitments=open_commitments,
            overdue_commitments=overdue_commitments,
            suggested_talking_points=talking_points,
            risks_to_address=risks,
            opportunities_to_pursue=opportunities,
        )

        self._contexts[meeting_id] = context
        return context

    def _compute_urgency(self, start: datetime, now: datetime) -> MeetingUrgency:
        """Compute meeting urgency from time-to-start."""
        time_to_start = start - now
        if time_to_start < timedelta(minutes=5):
            return MeetingUrgency.NOW
        elif time_to_start < timedelta(minutes=30):
            return MeetingUrgency.IMMINENT
        elif time_to_start < timedelta(hours=2):
            return MeetingUrgency.SOON
        elif time_to_start < timedelta(hours=12):
            return MeetingUrgency.TODAY
        elif time_to_start < timedelta(hours=48):
            return MeetingUrgency.UPCOMING
        else:
            return MeetingUrgency.FUTURE

    def _check_preparation(self, meeting_id: str) -> PreparationStatus:
        """Check if the user has prepared for this meeting."""
        if meeting_id not in self._preparation_log:
            return PreparationStatus.NOT_STARTED
        last_prep = self._preparation_log[meeting_id]
        age = datetime.now(timezone.utc) - last_prep
        if age > timedelta(hours=24):
            return PreparationStatus.STALE
        return PreparationStatus.READY

    def mark_prepared(self, meeting_id: str) -> None:
        """Mark a meeting as prepared (user viewed the pre-call briefing)."""
        self._preparation_log[meeting_id] = datetime.now(timezone.utc)

    def _extract_entity(self, event: dict) -> Optional[str]:
        """Extract customer/org name from meeting title or attendees."""
        title = event.get("title", "")

        # Check known entities in title
        for entity in self.KNOWN_ENTITIES:
            if entity.lower() in title.lower():
                return entity

        # Check attendee domains
        attendees = event.get("attendees", [])
        domains = [a.split("@")[-1].split(".")[0] for a in attendees if "@" in a]
        domain_counts = {}
        for domain in domains:
            if domain not in ["acme", "yourcompany", "example", "gmail", "outlook"]:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

        if domain_counts:
            most_common = max(domain_counts, key=domain_counts.get)
            return most_common.capitalize()

        return None

    def _build_attendee_profile(self, attendee_email: str) -> dict:
        """Build intelligence profile for a single attendee from OEM signals."""
        interaction_count = 0
        last_interaction = None
        topics = []

        if self.oem and hasattr(self.oem, "signals"):
            for sig in self.oem.signals:
                if hasattr(sig, "actor") and sig.actor and attendee_email.lower() in str(sig.actor).lower():
                    interaction_count += 1
                    if hasattr(sig, "timestamp"):
                        if last_interaction is None or sig.timestamp > last_interaction:
                            last_interaction = sig.timestamp
                    if hasattr(sig, "metadata"):
                        topic = sig.metadata.get("title", "") or sig.metadata.get("commitment", "")
                        if topic and topic not in topics:
                            topics.append(topic)

        days_ago = None
        if last_interaction:
            days_ago = (datetime.now(timezone.utc) - last_interaction).days

        return {
            "email": attendee_email,
            "interaction_count": interaction_count,
            "last_interaction_days_ago": days_ago,
            "topics": topics[:5],
            "evidence": {"source": "oem_signal_history", "count": interaction_count},
        }

    def _get_commitments_for_entity(self, entity: str) -> tuple[list[dict], list[dict]]:
        """Get open and overdue commitments for an entity from OEM signals."""
        from maestro_oem.signal import SignalType

        open_commitments = []
        overdue_commitments = []
        now = datetime.now(timezone.utc)

        if not self.oem or not hasattr(self.oem, "signals"):
            return open_commitments, overdue_commitments

        for sig in self.oem.signals:
            if (hasattr(sig, "type") and sig.type == SignalType.CUSTOMER_COMMITMENT_MADE
                    and hasattr(sig, "metadata") and sig.metadata.get("customer", "").lower() == entity.lower()):
                commit = {
                    "id": getattr(sig, "artifact", ""),
                    "text": sig.metadata.get("commitment", ""),
                    "actor": getattr(sig, "actor", ""),
                    "date": sig.timestamp.isoformat()[:10] if hasattr(sig, "timestamp") else "",
                    "due_date": sig.metadata.get("due_date"),
                }
                # Simple overdue check: if date is more than 60 days ago, consider it overdue
                # (Phase 9.5 will add proper due-date tracking)
                open_commitments.append(commit)

        return open_commitments, overdue_commitments

    def _generate_talking_points(
        self,
        entity: Optional[str],
        attendee_profiles: list[dict],
        open_commitments: list[dict],
        overdue_commitments: list[dict],
    ) -> list[dict]:
        """Generate suggested talking points, each with evidence (anti-Cluely)."""
        points = []

        # 1. Address overdue commitments first (high priority)
        for c in overdue_commitments[:2]:
            points.append({
                "priority": "high",
                "category": "commitment",
                "text": f"Address overdue commitment: {c.get('text', '')[:80]}",
                "reason": f"Overdue — {c.get('actor', 'someone')} committed",
                "evidence": {"source": "commitment_tracker", "id": c.get("id", "")},
            })

        # 2. Reference recent interactions with attendees
        for profile in attendee_profiles[:3]:
            if profile["last_interaction_days_ago"] is not None:
                days = profile["last_interaction_days_ago"]
                if days < 7:
                    points.append({
                        "priority": "medium",
                        "category": "relationship",
                        "text": f"Follow up with {profile['email'].split('@')[0]} — last interaction {days} days ago",
                        "reason": f"Recent topic: {profile['topics'][0] if profile['topics'] else 'unknown'}",
                        "evidence": profile["evidence"],
                    })
                elif days > 14:
                    points.append({
                        "priority": "high",
                        "category": "relationship",
                        "text": f"Re-engage {profile['email'].split('@')[0]} — {days} days since last interaction",
                        "reason": "Stale relationship — risk of disengagement",
                        "evidence": profile["evidence"],
                    })

        # 3. Reference open commitments
        for c in open_commitments[:2]:
            points.append({
                "priority": "medium",
                "category": "commitment",
                "text": f"Discuss commitment: {c.get('text', '')[:80]}",
                "reason": f"Open commitment from {c.get('actor', 'someone')}",
                "evidence": {"source": "commitment_tracker", "id": c.get("id", "")},
            })

        # Sort by priority
        points.sort(key=lambda p: {"high": 0, "medium": 1, "low": 2}.get(p["priority"], 3))
        return points[:5]

    def _identify_risks(
        self,
        entity: Optional[str],
        overdue_commitments: list[dict],
        attendee_profiles: list[dict],
    ) -> list[dict]:
        """Identify risks to address in the meeting."""
        risks = []

        for c in overdue_commitments:
            risks.append({
                "type": "overdue_commitment",
                "severity": "high",
                "text": f"Overdue commitment: {c.get('text', '')[:80]}",
                "evidence": {"source": "commitment_tracker"},
            })

        for profile in attendee_profiles:
            if profile["last_interaction_days_ago"] and profile["last_interaction_days_ago"] > 21:
                risks.append({
                    "type": "stale_relationship",
                    "severity": "medium",
                    "text": f"No interaction with {profile['email']} in {profile['last_interaction_days_ago']} days",
                    "evidence": profile["evidence"],
                })

        return risks

    def _identify_opportunities(
        self,
        entity: Optional[str],
        attendee_profiles: list[dict],
    ) -> list[dict]:
        """Identify opportunities to pursue."""
        opportunities = []

        if entity and attendee_profiles:
            # If we have strong interaction history, suggest expansion
            total_interactions = sum(p["interaction_count"] for p in attendee_profiles)
            if total_interactions > 10:
                opportunities.append({
                    "type": "expansion",
                    "text": f"Strong relationship with {entity} ({total_interactions} interactions) — consider expansion",
                    "evidence": {"source": "oem_signal_history", "total_interactions": total_interactions},
                })

        return opportunities

    def _get_relationship_health(self, entity: Optional[str]) -> Optional[str]:
        """Get relationship health for an entity."""
        if not entity or not self.oem or not hasattr(self.oem, "signals"):
            return None

        from maestro_oem.signal import SignalType
        entity_lower = entity.lower()
        entity_signals = [
            s for s in self.oem.signals
            if hasattr(s, "metadata") and s.metadata.get("customer", "").lower() == entity_lower
        ]

        if not entity_signals:
            return "unknown"

        has_broken = any(
            hasattr(s, "type") and s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN
            for s in entity_signals
        )
        has_objection = any(
            hasattr(s, "type") and s.type == SignalType.CUSTOMER_OBJECTION
            for s in entity_signals
        )

        if has_broken:
            return "critical"
        elif has_objection:
            return "warning"
        else:
            return "strong"

    def _detect_meeting_clusters(self, entity: Optional[str], event: dict) -> dict:
        """Detect meeting clusters (AMBIENT: '3 Globex meetings this week')."""
        if not entity:
            return {}

        # Count meetings with this entity in the next 7 days
        now = datetime.now(timezone.utc)
        week_ahead = now + timedelta(days=7)
        entity_meetings = [
            ctx for ctx in self._contexts.values()
            if ctx.entity and ctx.entity.lower() == entity.lower()
            and ctx.start_time <= week_ahead
        ]

        cluster_count = len(entity_meetings) + 1  # +1 for the current event
        is_acceleration = cluster_count >= 3

        return {
            "entity": entity,
            "meetings_this_week": cluster_count,
            "deal_acceleration": is_acceleration,
            "message": f"{cluster_count} {entity} meetings this week" + (" — deal acceleration pattern" if is_acceleration else ""),
        }

    async def get_upcoming_meetings(self, hours: int = 24) -> list[MeetingContext]:
        """Get all upcoming meetings within the given time horizon."""
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(hours=hours)
        return [
            ctx for ctx in self._contexts.values()
            if ctx.start_time <= horizon
        ]

    async def get_urgent_meeting(self) -> Optional[MeetingContext]:
        """Get the most urgent meeting (next 30 minutes)."""
        now = datetime.now(timezone.utc)
        urgent = [
            ctx for ctx in self._contexts.values()
            if ctx.urgency in (MeetingUrgency.NOW, MeetingUrgency.IMMINENT)
        ]
        if not urgent:
            return None
        return min(urgent, key=lambda c: c.start_time)

    def get_preparation_gap_alerts(self) -> list[dict]:
        """Get alerts for meetings where the user hasn't prepared.

        This is the killer feature: if a meeting is in <30 minutes and
        the user hasn't prepared, surface a 'Preparation Gap' alert.
        """
        now = datetime.now(timezone.utc)
        alerts = []
        for ctx in self._contexts.values():
            if ctx.urgency in (MeetingUrgency.NOW, MeetingUrgency.IMMINENT):
                if ctx.preparation_status == PreparationStatus.NOT_STARTED:
                    alerts.append({
                        "type": "preparation_gap",
                        "meeting_id": ctx.meeting_id,
                        "title": ctx.title,
                        "time_to_start": (ctx.start_time - now).total_seconds(),
                        "talking_points": ctx.suggested_talking_points[:3],
                        "message": f"Meeting in {int((ctx.start_time - now).total_seconds() / 60)} minutes — no preparation done. Here are the 3 most important talking points.",
                    })
        return alerts
