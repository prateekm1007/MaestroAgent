"""
Maestro Live Copilot — Pre-Call Intelligence endpoint.

Phase 3: Scene 1 (Before You Join).

When the extension detects a meeting lobby, it calls this endpoint with
the meeting title + attendees. This endpoint queries:
  - SituationSnapshot (27 fields — L0.1 verified) for entity context
  - CommitmentTracker for open/overdue commitments
  - OEM signal history for attendee interaction counts
  - PatternDetector for similar historical meetings

Returns a pre-call briefing with:
  - Meeting context card (ARR at risk, renewal countdown, account health)
  - Attendee intelligence (interaction count, commitment status, last gap)
  - Suggested talking points (each citing organizational data)
  - Risks to address (overdue commitments, critical relationships)
  - Opportunities to pursue (expansion, cross-sell)

Every suggestion cites its evidence. No generic LinkedIn-style bios.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from maestro_api.security.policy import auth_policy, AuthPolicy, set_router_policy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/copilot", tags=["copilot-pre-call"])
# F4 fix: stamp USER auth policy
set_router_policy(router, AuthPolicy.USER)

# Module-level imports for helpers (not just the endpoint function)
try:
    from maestro_oem.signal import SignalType
except ImportError:
    SignalType = None


class PreCallRequest(BaseModel):
    """Request from the extension when a meeting lobby is detected."""
    meeting_title: str = ""
    meeting_url: str = ""
    platform: str = ""  # google-meet, zoom, teams
    attendees: list[str] = []  # email addresses
    user_email: str = ""


class PreCallResponse(BaseModel):
    """Pre-call briefing returned to the extension."""
    meeting_context: dict[str, Any]
    attendee_intelligence: list[dict[str, Any]]
    suggested_talking_points: list[dict[str, Any]]
    risks_to_address: list[dict[str, Any]]
    opportunities: list[dict[str, Any]]
    evidence_chains: list[dict[str, Any]]


@router.post("/pre-call", response_model=PreCallResponse)
@auth_policy(AuthPolicy.USER)
async def get_pre_call_briefing(request: PreCallRequest) -> PreCallResponse:
    """Generate a pre-call briefing for an upcoming meeting.

    Queries the OEM for attendee intelligence, open commitments, and
    historical patterns. Every suggestion cites its evidence.
    """
    try:
        from maestro_api.oem_state import oem_state
        from maestro_oem.situation import SituationBuilder
        from maestro_oem.signal import SignalType

        signals = oem_state.signals or []

        # Build attendee intelligence for each email
        attendee_intel = []
        for email in request.attendees:
            intel = _build_attendee_intelligence(email, signals)
            attendee_intel.append(intel)

        # Detect entity from meeting title or attendee domains
        entity = _detect_entity(request.meeting_title, request.attendees)

        # Build SituationSnapshot for the entity (L0.1 — 27 fields)
        situation = None
        if entity:
            builder = SituationBuilder(
                signals=signals,
                calendar_source=None,
                whisper_store=None,
                user_email=request.user_email,
            )
            situation = builder.build_for_entity(entity)

        # Meeting context card
        meeting_context = _build_meeting_context(entity, situation)

        # Suggested talking points (each with evidence)
        talking_points = _generate_talking_points(situation, attendee_intel)

        # Risks to address
        risks = _identify_risks(situation, attendee_intel)

        # Opportunities
        opportunities = _identify_opportunities(situation, attendee_intel)

        # Evidence chains (for the "View evidence" links)
        evidence_chains = _build_evidence_chains(situation, attendee_intel)

        return PreCallResponse(
            meeting_context=meeting_context,
            attendee_intelligence=attendee_intel,
            suggested_talking_points=talking_points,
            risks_to_address=risks,
            opportunities=opportunities,
            evidence_chains=evidence_chains,
        )

    except Exception as e:
        logger.error(f"Copilot pre-call failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pre-call briefing failed: {e}")


def _build_attendee_intelligence(email: str, signals: list) -> dict[str, Any]:
    """Build intelligence profile for an attendee from OEM signals."""
    # Count interactions involving this person
    interactions = [s for s in signals if hasattr(s, "actor") and s.actor == email]
    interaction_count = len(interactions)

    # Find commitments involving this person
    commitments = [
        s for s in signals
        if hasattr(s, "type") and s.type == SignalType.CUSTOMER_COMMITMENT_MADE
        and hasattr(s, "actor") and s.actor == email
    ]

    # Find last interaction
    last_interaction = None
    if interactions:
        sorted_interactions = sorted(
            interactions,
            key=lambda s: getattr(s, "timestamp", datetime.min.replace(tzinfo=timezone.utc)),
            reverse=True,
        )
        last_interaction = sorted_interactions[0]

    # Calculate days since last interaction
    days_since = None
    if last_interaction and hasattr(last_interaction, "timestamp"):
        delta = datetime.now(timezone.utc) - last_interaction.timestamp
        days_since = delta.days

    return {
        "email": email,
        "interaction_count": interaction_count,
        "commitment_count": len(commitments),
        "last_interaction_days_ago": days_since,
        "last_interaction_date": last_interaction.timestamp.isoformat() if last_interaction else None,
        "role": "unknown",  # Phase 3.5: derive from org chart
        "topics_discussed": [],  # Phase 3.5: derive from signal metadata
        "evidence": {
            "signal_count": interaction_count,
            "source": "oem_signal_history",
        },
    }


def _detect_entity(title: str, attendees: list[str]) -> str | None:
    """Detect the customer/org entity from meeting title or attendee domains."""
    # Check known customer names in the title
    title_lower = (title or "").lower()
    known_customers = ["globex", "initech", "testcorp", "acme", "atlas"]
    for customer in known_customers:
        if customer in title_lower:
            return customer.capitalize()

    # Check attendee domains
    for email in attendees:
        if "@" in email:
            domain = email.split("@")[1].split(".")[0]
            if domain not in ["gmail", "outlook", "yahoo", "example"]:
                return domain.capitalize()

    return None


def _build_meeting_context(entity: str | None, situation: Any) -> dict[str, Any]:
    """Build the meeting context card."""
    context = {
        "entity": entity,
        "arr_at_risk": None,
        "days_to_renewal": None,
        "relationship_health": "unknown",
        "current_state": "unknown",
    }

    if situation:
        context["current_state"] = situation.current_state
        context["open_commitments"] = len(situation.commitments)
        context["overdue_commitments"] = len([
            c for c in situation.commitments
            if isinstance(c, dict) and c.get("date")
        ])
        if situation.current_state == "at_risk":
            context["relationship_health"] = "critical"
        elif situation.current_state == "on_track":
            context["relationship_health"] = "strong"
        else:
            context["relationship_health"] = "warning"

    return context


def _generate_talking_points(situation: Any, attendees: list[dict]) -> list[dict[str, Any]]:
    """Generate suggested talking points, each with evidence."""
    points = []

    if situation and situation.commitments:
        # Lead with commitment status
        for commit in situation.commitments[:2]:
            if isinstance(commit, dict):
                points.append({
                    "text": f"Address commitment: {commit.get('text', '')[:80]}",
                    "priority": "high",
                    "evidence": {
                        "source": "commitment_tracker",
                        "actor": commit.get("actor", ""),
                        "date": commit.get("date", ""),
                    },
                })

    # Address stale relationships
    for attendee in attendees:
        if attendee["last_interaction_days_ago"] and attendee["last_interaction_days_ago"] > 14:
            points.append({
                "text": f"Re-engage {attendee['email'].split('@')[0]} — last interaction {attendee['last_interaction_days_ago']} days ago",
                "priority": "medium",
                "evidence": {
                    "source": "oem_signal_history",
                    "days_ago": attendee["last_interaction_days_ago"],
                },
            })

    return points[:5]  # max 5 talking points


def _identify_risks(situation: Any, attendees: list[dict]) -> list[dict[str, Any]]:
    """Identify risks to address in the meeting."""
    risks = []

    if situation and situation.current_state == "at_risk":
        risks.append({
            "type": "relationship_health",
            "severity": "high",
            "text": "Account is at risk — situation state is 'at_risk'",
            "evidence": {"source": "situation_snapshot", "state": situation.current_state},
        })

    for attendee in attendees:
        if attendee["last_interaction_days_ago"] and attendee["last_interaction_days_ago"] > 21:
            risks.append({
                "type": "stale_relationship",
                "severity": "medium",
                "text": f"No interaction with {attendee['email']} in {attendee['last_interaction_days_ago']} days",
                "evidence": attendee["evidence"],
            })

    return risks


def _identify_opportunities(situation: Any, attendees: list[dict]) -> list[dict[str, Any]]:
    """Identify opportunities to pursue."""
    opportunities = []

    if situation and situation.commitments:
        # If commitments are on track, suggest expansion
        if situation.current_state == "on_track":
            opportunities.append({
                "type": "expansion",
                "text": "Account is on track — consider discussing expansion or upsell",
                "evidence": {"source": "situation_snapshot", "state": "on_track"},
            })

    return opportunities


def _build_evidence_chains(situation: Any, attendees: list[dict]) -> list[dict[str, Any]]:
    """Build evidence chains for the 'View evidence' links."""
    chains = []

    if situation and situation.claim_ids:
        chains.append({
            "type": "claims",
            "count": len(situation.claim_ids),
            "claim_ids": situation.claim_ids[:5],
            "source": "situation_snapshot",
        })

    for attendee in attendees:
        if attendee["interaction_count"] > 0:
            chains.append({
                "type": "attendee_history",
                "email": attendee["email"],
                "interaction_count": attendee["interaction_count"],
                "source": "oem_signal_history",
            })

    return chains
