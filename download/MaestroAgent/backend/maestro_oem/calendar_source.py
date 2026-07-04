"""Phase 3: CalendarSource — abstract calendar integration for Preparation.

Director directive (AUDIT-0644916):
> Calendar integration is the first trigger source. Filter to
> consequential conversations (not all meetings).

This module provides:
  - CalendarEvent: a dataclass representing a single calendar event
  - CalendarSource: an abstract interface (subclass + implement
    get_events_for_date)
  - DemoCalendarSource: returns synthetic events from signal data
    (used in dev/test when no real calendar is connected)
  - StaticCalendarSource: takes a pre-built list of events (used in
    tests + by injection in production when calendar API is wired)

Production wiring (Phase 3.5, future): GoogleCalendarSource and
OutlookCalendarSource will subclass CalendarSource and call the real
calendar APIs. The PreparationEngine does not change — only the source
injected into it changes. This is dependency injection, not a mock.

Design notes:
  - CalendarEvent has an `entity` field — the customer/org the meeting
    is with. The ConsequentialityFilter uses this to decide whether
    to prepare for the meeting. Events with empty entity are trivial
    (standups, lunches) and get filtered out.
  - CalendarEvent has `attendees` — list of email addresses. Used to
    populate the evidence_spine.people_involved field (Phase 2's
    enrichment goal extended to Phase 3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    """A single calendar event.

    Attributes:
        title: Event title (e.g., "<customer> Quarterly Review")
        start: Start time (timezone-aware datetime)
        end: End time (timezone-aware datetime)
        entity: The customer/org this meeting is with. Empty for
                internal/trivial events (standups, lunches).
        attendees: List of email addresses
        location: Optional location string
        description: Optional description / agenda
        metadata: Optional dict for source-specific fields
    """
    title: str
    start: datetime
    end: datetime
    entity: str = ""
    attendees: list[str] = field(default_factory=list)
    location: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class CalendarSource:
    """Abstract calendar source — subclass + implement get_events_for_date.

    The PreparationEngine accepts any CalendarSource instance. In dev/test,
    inject StaticCalendarSource with pre-built events. In production,
    inject GoogleCalendarSource or OutlookCalendarSource (future).
    """

    def get_events_for_date(self, date: datetime) -> list[CalendarEvent]:
        """Return all events on the given date.

        Args:
            date: The date to query (timezone-aware). Only the date
                  portion matters; time is ignored.

        Returns:
            List of CalendarEvent objects. Empty list if no events.
        """
        raise NotImplementedError(
            "CalendarSource subclasses must implement get_events_for_date()"
        )


class StaticCalendarSource(CalendarSource):
    """A calendar source with a pre-built list of events.

    Used in tests (deterministic) and in production when a real
    calendar source is not yet wired. Pass in the exact events you
    want returned.
    """

    def __init__(self, events: list[CalendarEvent]) -> None:
        self._events = events

    def get_events_for_date(self, date: datetime) -> list[CalendarEvent]:
        # Filter by date — only the date portion matters
        target_date = date.date() if hasattr(date, "date") else date
        result = []
        for event in self._events:
            event_date = event.start.date() if hasattr(event.start, "date") else event.start
            if event_date == target_date:
                result.append(event)
        return result


class DemoCalendarSource(CalendarSource):
    """Demo calendar source — synthesizes events from signal data.

    Used as the default when no real calendar is connected. Synthesizes
    "{customer} Quarterly Review" events for each customer with recent
    signals. This is the BEHAVIORAL EQUIVALENT of the old
    PreparationEngine._get_tomorrows_meetings() — preserved for
    backward compatibility and demo mode.

    In production, replace this with GoogleCalendarSource or
    OutlookCalendarSource (Phase 3.5, future).
    """

    def __init__(self, signals: list) -> None:
        self._signals = signals or []

    def get_events_for_date(self, date: datetime) -> list[CalendarEvent]:
        # Find unique customers from signals
        customers: list[str] = []
        seen: set[str] = set()
        for s in self._signals:
            try:
                customer = s.metadata.get("customer", "") if hasattr(s, "metadata") else ""
                if customer and customer not in seen:
                    seen.add(customer)
                    customers.append(customer)
            except Exception:
                continue

        events: list[CalendarEvent] = []
        # Synthesize up to 3 customer meetings at 10:00, 14:00, 16:00
        times = [10, 14, 16]
        for i, customer in enumerate(customers[:3]):
            hour = times[i] if i < len(times) else 10
            events.append(CalendarEvent(
                title=f"{customer} Quarterly Review",
                start=date.replace(hour=hour, minute=0, second=0, microsecond=0),
                end=date.replace(hour=hour + 1, minute=0, second=0, microsecond=0),
                entity=customer,
                attendees=[],
            ))

        # If no customers, add a default standup so the prep isn't empty
        if not events:
            events.append(CalendarEvent(
                title="Team Standup",
                start=date.replace(hour=9, minute=0, second=0, microsecond=0),
                end=date.replace(hour=9, minute=15, second=0, microsecond=0),
                entity="",
                attendees=[],
            ))

        return events


class MeetingStoreCalendarSource(CalendarSource):
    """Phase 2 hardening: CalendarSource backed by MeetingStore.

    This adapter connects the Loop 2 meeting lifecycle (prepare → occur →
    observe_outcome → record_learning) into the daily brief. Before this
    adapter, PreparationEngine used DemoCalendarSource which synthesized
    fake meetings from signals. Real meetings stored in MeetingStore
    (via /loop2/meeting endpoints) were invisible to /preparation/tomorrow.

    P11 fix: the MeetingStore existed, the PreparationEngine existed, but
    they were never connected. This adapter is the wiring.
    """

    def __init__(self, meeting_store: Any) -> None:
        self._store = meeting_store

    def get_events_for_date(self, date: datetime) -> list[CalendarEvent]:
        if not self._store:
            return []
        try:
            meetings = self._store.get_all()
        except Exception as e:
            logger.warning("MeetingStoreCalendarSource: get_all failed: %s", e)
            return []

        events: list[CalendarEvent] = []
        for m in meetings:
            # Filter to meetings on the requested date
            if hasattr(m, "start") and m.start:
                try:
                    meeting_date = m.start
                    if hasattr(meeting_date, "date"):
                        if meeting_date.date() != date.date():
                            continue
                    elif hasattr(meeting_date, "replace"):
                        # datetime or string — try to parse
                        pass
                    else:
                        continue
                except Exception:
                    continue

            events.append(CalendarEvent(
                title=getattr(m, "title", "Meeting"),
                start=getattr(m, "start", date.replace(hour=10, minute=0)),
                end=getattr(m, "end", date.replace(hour=11, minute=0)),
                entity=getattr(m, "entity", ""),
                attendees=getattr(m, "attendees", []),
            ))

        return events
