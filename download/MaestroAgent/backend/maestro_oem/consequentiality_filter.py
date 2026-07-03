"""Phase 3: ConsequentialityFilter — filter calendar to consequential meetings.

Director directive (AUDIT-0644916):
> Filter to consequential conversations (not all meetings).

Not every calendar event deserves a preparation brief. A standup with
the team does not need 5 minutes of evidence assembly. A customer
quarterly review where the customer has a broken commitment DOES.

This filter scores each CalendarEvent on 4 consequentiality dimensions:

  1. Has an entity (customer/org) attached — events with empty entity
     are trivial (standups, lunches) and filtered out.
  2. Has active signals in the last 30 days — the entity is "live"
     (not a stale relationship).
  3. Has a high-stakes signal type — commitment, objection, broken
     commitment, churn, or decision. These are the signals that mean
     "this meeting matters."
  4. Has external attendees — non-internal email addresses suggest
     this is an external conversation.

A meeting passes the filter if it has an entity AND at least one of:
  - Active signals in the last 30 days
  - A high-stakes signal type
  - External attendees (non-internal domain)

This is the difference between "prepare for every meeting" (old) and
"prepare for meetings that matter" (Phase 3).
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from maestro_oem.calendar_source import CalendarEvent

logger = logging.getLogger(__name__)


# Signal types that mean "this meeting matters" — high stakes
HIGH_STAKES_SIGNAL_TYPES = {
    "customer.commitment_made",
    "customer.commitment_broken",
    "customer.commitment_kept",
    "customer.objection",
    "customer.decision",
    "customer.contract_signed",
    "customer.contract_renewed",
    "customer.contract_churned",
    "customer.champion_quiet",
}


class ConsequentialityFilter:
    """Filter calendar events to consequential conversations.

    Usage:
        filt = ConsequentialityFilter(signals, now=datetime.now(timezone.utc))
        consequential = filt.filter(events)
    """

    # How recent a signal must be to count as "active relationship"
    ACTIVE_SIGNAL_WINDOW_DAYS = 30

    def __init__(
        self,
        signals: list,
        now: datetime | None = None,
    ) -> None:
        self._signals = signals or []
        self._now = now or datetime.now(timezone.utc)

    def filter(self, events: list[CalendarEvent]) -> list[CalendarEvent]:
        """Return only the consequential events from the input list.

        Args:
            events: List of CalendarEvent objects to filter.

        Returns:
            List of CalendarEvent objects that passed the
            consequentiality filter. Order is preserved.
        """
        result: list[CalendarEvent] = []
        for event in events:
            score = self.score(event)
            if score.is_consequential:
                result.append(event)
        return result

    def score(self, event: CalendarEvent) -> "ConsequentialityScore":
        """Score a single event's consequentiality.

        Returns a ConsequentialityScore with the 4 boolean dimensions
        plus an is_consequential verdict.
        """
        # 1. Has entity
        has_entity = bool(event.entity and event.entity.strip())

        # 2. Has active signals (last 30 days) for this entity
        active_signals = self._active_signals_for_entity(event.entity)
        has_active_signals = len(active_signals) > 0

        # 3. Has high-stakes signal type for this entity
        high_stakes_signals = self._high_stakes_signals_for_entity(event.entity)
        has_high_stakes = len(high_stakes_signals) > 0

        # 4. Has external attendees (non-internal email domain)
        has_external_attendees = self._has_external_attendees(event.attendees)

        # Consequential if has entity AND at least one of:
        # active signals, high-stakes signals, external attendees
        is_consequential = has_entity and (
            has_active_signals or has_high_stakes or has_external_attendees
        )

        return ConsequentialityScore(
            has_entity=has_entity,
            has_active_signals=has_active_signals,
            has_high_stakes=has_high_stakes,
            has_external_attendees=has_external_attendees,
            is_consequential=is_consequential,
            active_signal_count=len(active_signals),
            high_stakes_signal_count=len(high_stakes_signals),
        )

    def _active_signals_for_entity(self, entity: str) -> list[Any]:
        """Find signals for this entity within the active window."""
        if not entity:
            return []
        cutoff = self._now - timedelta(days=self.ACTIVE_SIGNAL_WINDOW_DAYS)
        result = []
        for s in self._signals:
            try:
                sig_customer = ""
                if hasattr(s, "metadata"):
                    sig_customer = s.metadata.get("customer", "")
                if sig_customer != entity:
                    continue
                sig_ts = s.timestamp if hasattr(s, "timestamp") else None
                if sig_ts is None:
                    continue
                if sig_ts >= cutoff:
                    result.append(s)
            except Exception:
                continue
        return result

    def _high_stakes_signals_for_entity(self, entity: str) -> list[Any]:
        """Find high-stakes signals (commitments, objections, etc.) for entity."""
        if not entity:
            return []
        result = []
        for s in self._signals:
            try:
                sig_customer = ""
                if hasattr(s, "metadata"):
                    sig_customer = s.metadata.get("customer", "")
                if sig_customer != entity:
                    continue
                # Check signal type against high-stakes set
                sig_type_str = ""
                if hasattr(s, "type"):
                    sig_type_str = str(s.type).lower()
                    # Normalize: "SignalType.CUSTOMER_COMMITMENT_MADE" → "customer.commitment_made"
                    if "." in sig_type_str and "signaltype" in sig_type_str:
                        # Strip the "SignalType." prefix
                        sig_type_str = sig_type_str.split(".")[-1]
                        sig_type_str = sig_type_str.lower().replace("_", ".")
                if sig_type_str in HIGH_STAKES_SIGNAL_TYPES:
                    result.append(s)
            except Exception:
                continue
        return result

    def _has_external_attendees(self, attendees: list[str]) -> bool:
        """Check if any attendee has a non-internal email domain.

        Heuristic: an email is "external" if its domain is not the
        organization's internal domain. Since we don't know the org
        domain in this context, we use a simpler heuristic: the email
        domain is not the configured org domain (MAESTRO_ORG_DOMAIN). In production, this
        would be configurable.

        A more sophisticated implementation would compare against the
        actual org's email domain (from auth settings).
        """
        if not attendees:
            return False
        org_domain = os.environ.get("MAESTRO_ORG_DOMAIN", "").lower().strip()
        for email in attendees:
            try:
                if "@" not in email:
                    continue
                domain = email.split("@", 1)[1].lower()
                if org_domain and domain != org_domain:
                    return True
            except Exception:
                continue
        return False


class ConsequentialityScore:
    """The consequentiality score for a single CalendarEvent.

    All four dimensions are recorded so the PreparationEngine can
    include them in the evidence_spine (proving WHY this meeting was
    deemed consequential).
    """

    def __init__(
        self,
        has_entity: bool,
        has_active_signals: bool,
        has_high_stakes: bool,
        has_external_attendees: bool,
        is_consequential: bool,
        active_signal_count: int = 0,
        high_stakes_signal_count: int = 0,
    ) -> None:
        self.has_entity = has_entity
        self.has_active_signals = has_active_signals
        self.has_high_stakes = has_high_stakes
        self.has_external_attendees = has_external_attendees
        self.is_consequential = is_consequential
        self.active_signal_count = active_signal_count
        self.high_stakes_signal_count = high_stakes_signal_count

    def to_dict(self) -> dict:
        return {
            "has_entity": self.has_entity,
            "has_active_signals": self.has_active_signals,
            "has_high_stakes": self.has_high_stakes,
            "has_external_attendees": self.has_external_attendees,
            "is_consequential": self.is_consequential,
            "active_signal_count": self.active_signal_count,
            "high_stakes_signal_count": self.high_stakes_signal_count,
        }

    def reason(self) -> str:
        """Human-readable reason this meeting is (or isn't) consequential."""
        if not self.is_consequential:
            reasons = []
            if not self.has_entity:
                reasons.append("no customer entity")
            elif not (self.has_active_signals or self.has_high_stakes or self.has_external_attendees):
                reasons.append("no active signals, no high-stakes signals, no external attendees")
            return "Filtered: " + "; ".join(reasons)

        reasons = []
        if self.has_high_stakes:
            reasons.append(f"{self.high_stakes_signal_count} high-stakes signal(s)")
        if self.has_active_signals:
            reasons.append(f"{self.active_signal_count} active signal(s) in last 30 days")
        if self.has_external_attendees:
            reasons.append("external attendees")
        return "Consequential: " + "; ".join(reasons)
