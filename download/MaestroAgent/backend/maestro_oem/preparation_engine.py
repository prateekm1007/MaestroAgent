"""The Preparation Engine — Maestro's Chief of Staff capability.

CEO's vision (2026-07-03): "Every evening Maestro should quietly ask:
What meetings happen tomorrow? What decisions will likely be made?
What objections are likely? What evidence should already be assembled?
Which commitments are at risk? Which people should the user talk to first?

Then, before the user opens their laptop, Maestro has already done the thinking."

The Preparation Engine runs nightly (or on-demand) to prepare for tomorrow.
It gathers customer concerns, previous objections, relevant commitments,
internal experts, draft responses, and competitive comparisons — all
assembled before the user arrives.

This is the difference between an assistant and a Chief of Staff.

Phase 3 (2026-07-03, AUDIT-0644916):
  - Accepts a CalendarSource (dependency injection) instead of synthesizing
    meetings from signals. Calendar is the first trigger source.
  - Filters to consequential conversations via ConsequentialityFilter
    (not all meetings — standups and lunches are filtered out).
  - Flags at_risk meetings when the entity has a broken commitment.
  - Evidence Spine is built from real signals via EvidenceBuilder,
    including objection history in conflicting_evidence.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from maestro_oem.calendar_source import CalendarSource, CalendarEvent, DemoCalendarSource
from maestro_oem.consequentiality_filter import ConsequentialityFilter

logger = logging.getLogger(__name__)


class PreparationEngine:
    """Prepare for tomorrow — the Chief of Staff capability.

    Usage (Phase 3 — with calendar source):
        from maestro_oem.calendar_source import StaticCalendarSource
        cal = StaticCalendarSource(events)
        engine = PreparationEngine(model, signals, calendar_source=cal, now=now)
        brief = engine.prepare_for_tomorrow(org_id="default")

    Usage (backward-compat — no calendar source, uses DemoCalendarSource):
        engine = PreparationEngine(model, signals)
        brief = engine.prepare_for_tomorrow(org_id="default")
    """

    def __init__(
        self,
        model: Any,
        signals: list,
        calendar_source: CalendarSource | None = None,
        now: datetime | None = None,
    ) -> None:
        self.model = model
        self.signals = signals
        # If no calendar source is provided, fall back to the demo source
        # (synthesizes meetings from signals — backward-compatible with
        # the old behavior). In production, inject a real calendar source.
        self.calendar_source = calendar_source or DemoCalendarSource(signals)
        self._now = now or datetime.now(timezone.utc)

    def prepare_for_tomorrow(self, org_id: str = "default", user_email: str = "") -> dict[str, Any]:
        """Generate tomorrow's preparation brief.

        Pipeline:
          1. Get tomorrow's date
          2. Fetch events from calendar_source for that date
          3. Filter to consequential events via ConsequentialityFilter
          4. For each consequential event, build a preparation brief
             with Evidence Spine from real signals
          5. Flag at_risk meetings (entity has broken commitment)
          6. Return the full brief

        Returns:
            {
                "date": "2026-07-04",
                "meetings": [...],
                "decisions_likely": [...],
                "commitments_at_risk": [...],
                "people_to_contact": [...]
            }
        """
        tomorrow_dt = self._now + timedelta(days=1)
        tomorrow_str = tomorrow_dt.strftime("%Y-%m-%d")

        # ── Step 2: Fetch events from calendar source ─────────────────
        try:
            events = self.calendar_source.get_events_for_date(tomorrow_dt)
        except Exception as e:
            logger.warning("PreparationEngine: calendar_source.get_events_for_date failed: %s", e)
            events = []

        # ── Step 3: Filter to consequential events ────────────────────
        filt = ConsequentialityFilter(signals=self.signals, now=self._now)
        consequential_events = filt.filter(events)

        # ── Step 4-5: Prepare each consequential meeting ──────────────
        prepared_meetings = []
        for event in consequential_events:
            prepared = self._prepare_for_event(event, tomorrow_str)
            prepared_meetings.append(prepared)

        # Decisions likely to be made tomorrow
        decisions_likely = self._get_likely_decisions()

        # Commitments at risk (top-level list — backward-compat)
        commitments_at_risk = self._get_commitments_at_risk()

        # People to contact
        people_to_contact = self._get_people_to_contact()

        return {
            "date": tomorrow_str,
            "user": user_email,
            "meetings": prepared_meetings,
            "decisions_likely": decisions_likely,
            "commitments_at_risk": commitments_at_risk,
            "people_to_contact": people_to_contact,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "calendar_source": type(self.calendar_source).__name__,
            "filter_summary": {
                "total_events": len(events),
                "consequential_events": len(consequential_events),
                "filtered_out": len(events) - len(consequential_events),
            },
        }

    def _prepare_for_event(self, event: CalendarEvent, tomorrow_str: str) -> dict[str, Any]:
        """Prepare a single consequential CalendarEvent.

        Builds:
          - preparation dict (concerns, objections, commitments, expert, draft)
          - evidence_spine from real signals via EvidenceBuilder
          - at_risk flag (True if entity has broken commitment)
          - attendees propagated from calendar
          - consequentiality score propagated (proves WHY this was kept)
        """
        from maestro_oem.evidence import EvidenceBuilder, Evidence
        from maestro_oem.signal import SignalType

        # Convert event to the meeting dict shape used by _prepare_for_meeting
        meeting_dict = {
            "title": event.title,
            "time": event.start.strftime("%H:%M"),
            "entity": event.entity,
            "customer": event.entity,
            "attendees": list(event.attendees),
        }

        # Build preparation materials (existing logic)
        prep = self._prepare_for_meeting(meeting_dict)

        # Build Evidence Spine from real signals
        builder = EvidenceBuilder(self.signals)
        entity = event.entity
        if entity:
            # Use commitment_exists builder — it populates observed_facts
            # from commitment signals AND conflicting_evidence from
            # objection signals (Phase 1's EvidenceBuilder already does
            # this — Phase 3 just USES it correctly).
            evidence_obj = builder.build_for_whisper(
                whisper_type="commitment_exists",
                entity=entity,
                topic="",
                raw_evidence={
                    "artifact": "",
                    "timestamp": event.start.isoformat(),
                },
                context="meeting",
            )
        else:
            evidence_obj = Evidence(
                claim=f"Preparation for {event.title}",
                observed_facts=[{
                    "source": "calendar",
                    "date": tomorrow_str,
                    "text": event.title,
                    "people": list(event.attendees),
                }],
                assumptions=["The meeting will proceed as scheduled"],
            )

        # Enrich evidence with calendar-derived artifacts + people
        evidence_dict = evidence_obj.to_dict()
        # Add calendar event as a source artifact
        evidence_dict.setdefault("source_artifacts", []).append({
            "type": "calendar_event",
            "url": "",
            "retrieved_at": tomorrow_str,
            "artifact_id": f"cal:{event.title}",
            "event_time": event.start.isoformat(),
        })
        # Add attendees as people_involved
        for attendee in event.attendees:
            existing_names = {p.get("name", "") for p in evidence_dict.get("people_involved", [])}
            if attendee not in existing_names:
                evidence_dict.setdefault("people_involved", []).append({
                    "name": attendee,
                    "role": "attendee",
                    "why_relevant": f"attending {event.title}",
                })
        # Add timestamps from calendar
        evidence_dict.setdefault("timestamps", {})
        evidence_dict["timestamps"]["meeting_date"] = tomorrow_str
        evidence_dict["timestamps"]["meeting_start"] = event.start.isoformat()

        # Compute at_risk flag — does this entity have a broken commitment?
        at_risk = False
        if entity:
            broken_signals = [
                s for s in self.signals
                if hasattr(s, "metadata") and s.metadata.get("customer") == entity
                and hasattr(s, "type") and s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN
            ]
            at_risk = len(broken_signals) > 0

            # If at_risk, add the broken commitment to evidence
            if at_risk and broken_signals:
                for s in broken_signals[:2]:
                    broken_text = s.metadata.get("commitment", "")
                    if broken_text:
                        evidence_dict.setdefault("observed_facts", []).append({
                            "source": "customer signals",
                            "date": s.timestamp.isoformat()[:10] if hasattr(s.timestamp, "isoformat") else "",
                            "text": f"Commitment broken: {broken_text}",
                            "people": [s.actor] if s.actor else [],
                        })
                evidence_dict.setdefault("conflicting_evidence", []).append({
                    "claim": f"{entity} has a broken commitment — trust may be fragile",
                    "source": "customer signals",
                    "why_conflicts": "A prior commitment was not honored",
                })

        # Compute consequentiality score (for transparency — proves WHY kept)
        filt = ConsequentialityFilter(signals=self.signals, now=self._now)
        score = filt.score(event)

        return {
            "title": event.title,
            "time": event.start.strftime("%H:%M"),
            "entity": event.entity,
            "attendees": list(event.attendees),
            "preparation": prep,
            "evidence_spine": evidence_dict,
            "at_risk": at_risk,
            "consequentiality": score.to_dict(),
            "consequentiality_reason": score.reason(),
        }

    def _prepare_for_meeting(self, meeting: dict[str, Any]) -> dict[str, Any]:
        """Prepare materials for a single meeting.

        Gathers:
        - Customer concerns from signals
        - Previous objections from contradiction log
        - Relevant commitments from commitment tracker
        - Internal experts from knowledge graph
        - Draft email/response
        - Competitive comparison
        """
        from maestro_oem.signal import SignalType

        entity = meeting.get("entity", "")
        customer = meeting.get("customer", "")

        # Customer concerns — what have they raised before?
        customer_concerns = []
        if customer:
            customer_signals = [s for s in self.signals
                               if s.metadata.get("customer") == customer]
            for s in customer_signals:
                if s.type == SignalType.CUSTOMER_OBJECTION:
                    concern = s.metadata.get("objection_type", "")
                    if concern and concern not in customer_concerns:
                        customer_concerns.append(concern)

        # Previous objections
        previous_objections = []
        if customer:
            objection_signals = [s for s in self.signals
                                if s.metadata.get("customer") == customer
                                and s.type == SignalType.CUSTOMER_OBJECTION]
            for s in objection_signals[:3]:
                previous_objections.append({
                    "type": s.metadata.get("objection_type", ""),
                    "date": s.timestamp.isoformat()[:10] if hasattr(s.timestamp, "isoformat") else "",
                    "artifact": s.artifact,
                })

        # Relevant commitments
        relevant_commitments = []
        if customer:
            commitment_signals = [s for s in self.signals
                                 if s.metadata.get("customer") == customer
                                 and s.type == SignalType.CUSTOMER_COMMITMENT_MADE]
            for s in commitment_signals[:3]:
                relevant_commitments.append({
                    "commitment": s.metadata.get("commitment", ""),
                    "date": s.timestamp.isoformat()[:10] if hasattr(s.timestamp, "isoformat") else "",
                })

        # Internal expert — who knows this customer/domain best?
        internal_expert = ""
        if customer:
            person_counts: dict[str, int] = {}
            for s in self.signals:
                if s.metadata.get("customer") == customer and s.actor:
                    person_counts[s.actor] = person_counts.get(s.actor, 0) + 1
            if person_counts:
                internal_expert = max(person_counts, key=person_counts.get)

        # Suggested talking points
        suggested_talking_points = []
        if customer_concerns:
            for concern in customer_concerns[:3]:
                suggested_talking_points.append(f"Address {concern} proactively")
        if relevant_commitments:
            suggested_talking_points.append("Review status of open commitments")
        suggested_talking_points.append("Confirm next steps and timeline")

        # Draft email
        draft_email = ""
        if customer and customer_concerns:
            draft_email = self._generate_draft_email(customer, customer_concerns)

        # Competitive comparison (simplified)
        competitive_comparison = {}
        if customer:
            competitive_comparison = {
                "customer": customer,
                "position": "strong" if len(relevant_commitments) > 0 else "unknown",
                "key_differentiator": "Organizational intelligence platform",
            }

        return {
            "customer_concerns": customer_concerns,
            "previous_objections": previous_objections,
            "relevant_commitments": relevant_commitments,
            "suggested_talking_points": suggested_talking_points,
            "internal_expert": internal_expert,
            "draft_email": draft_email,
            "competitive_comparison": competitive_comparison,
        }

    def _generate_draft_email(self, customer: str, concerns: list[str]) -> str:
        """Generate a draft email addressing the customer's concerns."""
        concern_text = ", ".join(concerns[:3])
        return (
            f"Dear {customer} team,\n\n"
            f"Following up on our recent discussions, I wanted to address "
            f"your concerns about {concern_text}. We take these seriously "
            f"and have prepared the following:\n\n"
            f"1. Detailed response to each concern\n"
            f"2. Evidence from similar engagements\n"
            f"3. Proposed timeline for resolution\n\n"
            f"Looking forward to our conversation.\n\n"
            f"Best regards,\n"
            f"The Maestro Team"
        )

    def _get_likely_decisions(self) -> list[dict[str, Any]]:
        """What decisions will likely be made tomorrow?

        Based on pending recommendations and approaching deadlines.
        """
        decisions = []
        try:
            recs = self.model.decisions.get_recommendations() if hasattr(self.model, "decisions") else []
            for rec in recs[:3]:
                decisions.append({
                    "title": rec.get("title", "") if isinstance(rec, dict) else str(rec),
                    "type": rec.get("type", "recommendation") if isinstance(rec, dict) else "recommendation",
                    "urgency": rec.get("urgency", "medium") if isinstance(rec, dict) else "medium",
                })
        except Exception as e:
            logger.warning("Failed to get recommendations: %s", e)

        if not decisions:
            decisions.append({
                "title": "Q3 budget allocation",
                "type": "financial",
                "urgency": "high",
            })

        return decisions

    def _get_commitments_at_risk(self) -> list[dict[str, Any]]:
        """Which commitments are at risk of being missed?

        Based on broken commitments and approaching deadlines.
        """
        from maestro_oem.signal import SignalType

        at_risk = []
        broken = [s for s in self.signals if s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN]
        for s in broken[:3]:
            at_risk.append({
                "customer": s.metadata.get("customer", ""),
                "commitment": s.metadata.get("commitment", ""),
                "status": "broken",
            })

        return at_risk

    def _get_people_to_contact(self) -> list[dict[str, Any]]:
        """Who should the user talk to first tomorrow?

        Based on bottlenecks, champions gone quiet, and key influencers.
        """
        people = []

        # Bottlenecks
        try:
            bottlenecks = self.model.approvals.get_bottlenecks(min_count=2) if hasattr(self.model, "approvals") else []
            for bn in bottlenecks[:2]:
                people.append({
                    "person": bn["gate"],
                    "reason": f"Gating {bn['items_gated']} items",
                    "priority": "high",
                })
        except Exception:
            pass

        # Champions gone quiet
        from maestro_oem.signal import SignalType
        quiet = [s for s in self.signals if s.type == SignalType.CUSTOMER_CHAMPION_QUIET]
        for s in quiet[:2]:
            people.append({
                "person": s.metadata.get("customer", ""),
                "reason": "Champion has gone quiet",
                "priority": "medium",
            })

        return people

    def _get_tomorrows_meetings(self, date_str: str) -> list[dict[str, Any]]:
        """Get tomorrow's meetings — DEPRECATED in Phase 3.

        Phase 3 replaces this with calendar_source.get_events_for_date().
        Kept for backward-compat with any callers that don't yet pass a
        calendar_source. DemoCalendarSource (the default) reproduces the
        old behavior.
        """
        from maestro_oem.signal import SignalType

        customers = set()
        for s in self.signals:
            if hasattr(s, "metadata") and s.metadata.get("customer"):
                customers.add(s.metadata["customer"])

        meetings = []
        for customer in list(customers)[:3]:
            meetings.append({
                "title": f"{customer} Quarterly Review",
                "time": "10:00",
                "entity": customer,
                "customer": customer,
            })

        if not meetings:
            meetings.append({
                "title": "Team Standup",
                "time": "09:00",
                "entity": "",
                "customer": "",
            })

        return meetings
