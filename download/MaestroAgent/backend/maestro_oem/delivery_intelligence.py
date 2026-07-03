"""Loop 1 — Delivery Intelligence (minimal, deterministic).

External auditor correction #3 (2026-07-03):
> Delivery Intelligence should have started already. For each Whisper,
> record: recipient, reason_recipient_chosen, timing_reason, depth,
> materially_changed_since_last_shown. Deterministic rules, not
> learning. But the data model from day one.

This module implements the deterministic rules. No learning. No ML.
Just explicit rules that say: for this Whisper, given this meeting
and these attendees, who should receive it, when, and how deeply?

The 5 fields:

1. recipient (str) — email address of the person who should see this
   Whisper. Deterministic rule: the internal attendee of the upcoming
   meeting (the executive who has the meeting). If the meeting has
   multiple internal attendees, pick the one with the most signals
   for this entity (the "internal expert").

2. reason_recipient_chosen (str) — one sentence explaining WHY this
   person was chosen. e.g., "Jane is the internal expert on Globex
   (3 signals) and is attending tomorrow's meeting."

3. timing_reason (str) — one sentence explaining WHY this Whisper is
   firing now. e.g., "Globex Quarterly Review is tomorrow at 10:00 —
   22 hours lead time."

4. depth (str) — how deeply to deliver. Values: "headline" (1 sentence),
   "brief" (3-5 sentences), "full" (full Evidence Spine). Deterministic
   rule: "full" if the entity has a broken commitment or objection
   (high stakes); "brief" if active signals only; "headline" otherwise.

5. materially_changed_since_last_shown (bool) — True if new signals
   have arrived since the Whisper was last shown. Deterministic rule:
   compare the Whisper's last_shown timestamp to the latest signal
   timestamp for this entity. If any signal is newer, True.

This is NOT learning. This is deterministic Delivery Intelligence —
the data model from day one. Phase 5 (full Delivery Intelligence)
will add learning on top of this data model.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class DeliveryIntelligence:
    """Deterministic Delivery Intelligence for a Whisper.

    Usage:
        di = DeliveryIntelligence(signals=signals, now=now)
        delivery = di.compute(
            entity="Globex",
            meeting=event,
            whisper_last_shown=last_shown_iso,
            whisper_type="commitment_exists",
        )
        # delivery = {recipient, reason_recipient_chosen, timing_reason, depth, materially_changed_since_last_shown}
    """

    def __init__(self, signals: list, now: datetime | None = None) -> None:
        self._signals = signals or []
        self._now = now or datetime.now(timezone.utc)

    def compute(
        self,
        entity: str,
        meeting: Any | None = None,
        whisper_last_shown: str | None = None,
        whisper_type: str = "",
    ) -> dict[str, Any]:
        """Compute the 5 Delivery Intelligence fields for a Whisper.

        Args:
            entity: The customer/org this Whisper is about
            meeting: The upcoming CalendarEvent (optional — if None,
                     timing_reason will say "no upcoming meeting")
            whisper_last_shown: ISO timestamp of when this Whisper was
                                 last shown (None = never shown)
            whisper_type: The whisper type (commitment_exists, etc.)

        Returns:
            dict with recipient, reason_recipient_chosen, timing_reason,
            depth, materially_changed_since_last_shown
        """
        recipient, reason = self._choose_recipient(entity, meeting)
        timing_reason = self._compute_timing_reason(meeting)
        depth = self._compute_depth(entity)
        materially_changed = self._compute_materially_changed(
            entity, whisper_last_shown
        )

        return {
            "recipient": recipient,
            "reason_recipient_chosen": reason,
            "timing_reason": timing_reason,
            "depth": depth,
            "materially_changed_since_last_shown": materially_changed,
        }

    def _choose_recipient(self, entity: str, meeting: Any | None) -> tuple[str, str]:
        """Choose the recipient — the internal attendee with the most
        signals for this entity (the internal expert).

        Returns (recipient, reason).
        """
        # Get internal attendees from the meeting
        internal_attendees: list[str] = []
        if meeting is not None and hasattr(meeting, "attendees"):
            for email in meeting.attendees:
                # Heuristic: internal = acme.com domain (demo org)
                # In production, this would be configurable per org.
                if "@" in email and email.split("@", 1)[1].lower() == "acme.com":
                    internal_attendees.append(email)

        if not internal_attendees:
            # No internal attendees — fall back to the internal expert
            # from signals (the person with the most signals for this entity)
            expert = self._internal_expert(entity)
            if expert:
                return expert, f"{expert} is the internal expert on {entity} (no internal attendees on the meeting)."
            return "unknown", "No internal attendee or signal-derived expert could be identified."

        if len(internal_attendees) == 1:
            return internal_attendees[0], f"{internal_attendees[0]} is attending the {entity} meeting."

        # Multiple internal attendees — pick the one with the most signals
        # for this entity (the internal expert among the attendees)
        signal_counts: dict[str, int] = {}
        for s in self._signals:
            try:
                sig_customer = s.metadata.get("customer", "") if hasattr(s, "metadata") else ""
                if sig_customer != entity:
                    continue
                if s.actor and s.actor in internal_attendees:
                    signal_counts[s.actor] = signal_counts.get(s.actor, 0) + 1
            except Exception:
                continue

        if signal_counts:
            best = max(signal_counts, key=signal_counts.get)
            count = signal_counts[best]
            return best, f"{best} is the internal expert on {entity} ({count} signal(s)) and is attending tomorrow's meeting."

        # No signal data to differentiate — pick the first internal attendee
        return internal_attendees[0], f"{internal_attendees[0]} is attending the {entity} meeting (no signal data to differentiate internal attendees)."

    def _internal_expert(self, entity: str) -> str:
        """Find the person with the most signals for this entity."""
        if not entity:
            return ""
        counts: dict[str, int] = {}
        for s in self._signals:
            try:
                sig_customer = s.metadata.get("customer", "") if hasattr(s, "metadata") else ""
                if sig_customer != entity:
                    continue
                if s.actor:
                    counts[s.actor] = counts.get(s.actor, 0) + 1
            except Exception:
                continue
        if counts:
            return max(counts, key=counts.get)
        return ""

    def _compute_timing_reason(self, meeting: Any | None) -> str:
        """Compute why this Whisper is firing now."""
        if meeting is None or not hasattr(meeting, "start"):
            return "No upcoming meeting — Whisper fired on signal-driven trigger."

        meeting_start = meeting.start
        if meeting_start.tzinfo is None:
            meeting_start = meeting_start.replace(tzinfo=timezone.utc)

        hours_until = (meeting_start - self._now).total_seconds() / 3600.0

        if hours_until < 0:
            return f"The {meeting.title} has already passed — Whisper fired for retrospective review."
        if hours_until < 1:
            return f"{meeting.title} starts in {int(hours_until * 60)} minutes — Whisper fired for immediate preparation."
        if hours_until < 24:
            return f"{meeting.title} is tomorrow at {meeting_start.strftime('%H:%M')} — {int(hours_until)} hours lead time for preparation."
        return f"{meeting.title} is in {int(hours_until / 24)} days — Whisper fired for early preparation."

    def _compute_depth(self, entity: str) -> str:
        """Compute how deeply to deliver.

        - "full" if entity has a broken commitment or objection (high stakes)
        - "brief" if entity has active signals only
        - "headline" otherwise
        """
        from maestro_oem.signal import SignalType

        if not entity:
            return "headline"

        has_broken = False
        has_objection = False
        has_active_signal = False
        cutoff = self._now - __import__("datetime").timedelta(days=30)

        for s in self._signals:
            try:
                sig_customer = s.metadata.get("customer", "") if hasattr(s, "metadata") else ""
                if sig_customer != entity:
                    continue
                if s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN:
                    has_broken = True
                if s.type == SignalType.CUSTOMER_OBJECTION:
                    has_objection = True
                if hasattr(s, "timestamp") and s.timestamp and s.timestamp >= cutoff:
                    has_active_signal = True
            except Exception:
                continue

        if has_broken or has_objection:
            return "full"
        if has_active_signal:
            return "brief"
        return "headline"

    def _compute_materially_changed(
        self, entity: str, whisper_last_shown: str | None
    ) -> bool:
        """True if new signals have arrived since the Whisper was last shown."""
        if not whisper_last_shown or not entity:
            # Never shown — everything is "new"
            return True

        try:
            if whisper_last_shown.endswith("Z"):
                whisper_last_shown = whisper_last_shown[:-1] + "+00:00"
            last_shown_dt = datetime.fromisoformat(whisper_last_shown)
            if last_shown_dt.tzinfo is None:
                last_shown_dt = last_shown_dt.replace(tzinfo=timezone.utc)
        except Exception:
            return True

        for s in self._signals:
            try:
                sig_customer = s.metadata.get("customer", "") if hasattr(s, "metadata") else ""
                if sig_customer != entity:
                    continue
                if hasattr(s, "timestamp") and s.timestamp and s.timestamp > last_shown_dt:
                    return True
            except Exception:
                continue
        return False
