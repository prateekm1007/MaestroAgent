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
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


class PreparationEngine:
    """Prepare for tomorrow — the Chief of Staff capability.

    Usage:
        engine = PreparationEngine(model, signals)
        brief = engine.prepare_for_tomorrow(org_id="default", user_email="ceo@acme.com")
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def prepare_for_tomorrow(self, org_id: str = "default", user_email: str = "") -> dict[str, Any]:
        """Generate tomorrow's preparation brief.

        Returns:
        {
            "date": "2026-07-04",
            "meetings": [...],
            "decisions_likely": [...],
            "commitments_at_risk": [...],
            "people_to_contact": [...]
        }
        """
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

        # Get tomorrow's meetings (from demo seed calendar or real calendar)
        meetings = self._get_tomorrows_meetings(tomorrow)

        # For each meeting, prepare materials
        prepared_meetings = []
        for meeting in meetings:
            prep = self._prepare_for_meeting(meeting)
            # Phase 1: Build Evidence Spine for this meeting from actual signals
            from maestro_oem.evidence import EvidenceBuilder
            builder = EvidenceBuilder(self.signals)
            entity = meeting.get("entity", "") or meeting.get("customer", "")
            if entity:
                evidence_obj = builder.build_for_whisper(
                    whisper_type="commitment_exists",
                    entity=entity,
                    topic="",
                    raw_evidence={},
                    context="meeting",
                )
            else:
                from maestro_oem.evidence import Evidence
                evidence_obj = Evidence(
                    claim=f"Preparation for {meeting.get('title', 'meeting')}",
                    observed_facts=[{"source": "calendar", "date": tomorrow, "text": meeting.get("title", ""), "people": []}],
                    assumptions=["The meeting will proceed as scheduled"],
                )
            prepared_meetings.append({
                "title": meeting["title"],
                "time": meeting["time"],
                "entity": meeting.get("entity", ""),
                "preparation": prep,
                "evidence_spine": evidence_obj.to_dict(),
            })

        # Decisions likely to be made tomorrow
        decisions_likely = self._get_likely_decisions()

        # Commitments at risk
        commitments_at_risk = self._get_commitments_at_risk()

        # People to contact
        people_to_contact = self._get_people_to_contact()

        return {
            "date": tomorrow,
            "user": user_email,
            "meetings": prepared_meetings,
            "decisions_likely": decisions_likely,
            "commitments_at_risk": commitments_at_risk,
            "people_to_contact": people_to_contact,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _get_tomorrows_meetings(self, date_str: str) -> list[dict[str, Any]]:
        """Get tomorrow's meetings from demo seed or real calendar.

        In demo mode, returns a synthetic meeting based on the customer signals.
        In production, this would query the calendar API.
        """
        from maestro_oem.signal import SignalType

        # Find customers with recent signals (likely to have meetings)
        customers = set()
        for s in self.signals:
            if hasattr(s, "metadata") and s.metadata.get("customer"):
                customers.add(s.metadata["customer"])

        meetings = []
        for customer in list(customers)[:3]:  # Max 3 meetings
            meetings.append({
                "title": f"{customer} Quarterly Review",
                "time": "10:00",
                "entity": customer,
                "customer": customer,
            })

        # If no customers found, add a default meeting
        if not meetings:
            meetings.append({
                "title": "Team Standup",
                "time": "09:00",
                "entity": "",
                "customer": "",
            })

        return meetings

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
            # Find the person with the most signals about this customer
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
            import logging
            logging.getLogger(__name__).warning("Failed to get recommendations: %s", e)

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
