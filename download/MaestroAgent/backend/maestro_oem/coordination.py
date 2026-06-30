"""
Coordination Engine — quietly coordinate teams without scheduling meetings.

When a decision is detected (e.g., CEO says "standardize OAuth"), the
engine:
  1. Identifies affected teams (from the OEM's knowledge graph)
  2. For each team, identifies the right person to ask (from influence + expertise)
  3. Sends a targeted question to each person
  4. Collects responses
  5. Synthesizes a single answer with all perspectives

"CEO says standardize OAuth → Maestro asks Security, Platform, Legal,
DevRel → returns one multi-perspective answer."

The CEO didn't have to schedule a single meeting.

Product law: eliminates COORDINATING (no meetings needed to get
multi-team input) and WAITING (responses are collected asynchronously
and synthesized when ready).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class CoordinationRequest:
    """A coordination request for a decision."""

    def __init__(
        self,
        request_id: str,
        decision: str,  # "Standardize OAuth across all services"
        initiated_by: str = "",
        teams: list[str] | None = None,
        contacts: list[dict[str, Any]] | None = None,
        status: str = "initiated",  # initiated | collecting | synthesized | closed
        created_at: datetime | None = None,
        responses: list[dict[str, Any]] | None = None,
        synthesis: str = "",
    ) -> None:
        self.request_id = request_id
        self.decision = decision
        self.initiated_by = initiated_by
        self.teams = teams or []
        self.contacts = contacts or []
        self.status = status
        self.created_at = created_at or datetime.now(timezone.utc)
        self.responses = responses or []
        self.synthesis = synthesis

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "decision": self.decision,
            "initiated_by": self.initiated_by,
            "teams": self.teams,
            "contacts": self.contacts,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "responses": self.responses,
            "synthesis": self.synthesis,
            "response_count": len(self.responses),
            "total_contacts": len(self.contacts),
        }


class CoordinationEngine:
    """Coordinates multi-team input for decisions.

    Usage:
        engine = CoordinationEngine(model, signals)
        request = engine.initiate("Standardize OAuth", initiated_by="ceo@acme.com")
        engine.add_response(request["request_id"], "security@acme.com", "Security", "We need to review the threat model first.")
        synthesis = engine.synthesize(request["request_id"])
    """

    # Team → domain mapping for identifying affected teams
    TEAM_DOMAINS = {
        "engineering": ["payments", "auth", "platform", "frontend", "backend", "mobile", "infrastructure"],
        "security": ["auth", "security", "compliance"],
        "legal": ["compliance", "contract", "policy", "regulation"],
        "finance": ["billing", "invoice", "budget"],
        "product": ["product", "roadmap", "feature"],
        "support": ["support", "customer"],
    }

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals
        self._requests: dict[str, CoordinationRequest] = {}

    def initiate(
        self,
        decision: str,
        initiated_by: str = "",
        intent_id: str = "",
    ) -> dict[str, Any]:
        """Initiate a coordination request for a decision.

        Automatically identifies affected teams and contacts from the OEM.
        """
        request_id = f"coord-{uuid4().hex[:12]}"

        # Identify affected teams from the decision text
        teams = self._identify_teams(decision)

        # Identify contacts for each team from the knowledge graph
        contacts = self._identify_contacts(teams)

        # Also look at the knowledge graph for domain experts
        try:
            for expert in self.model.knowledge.get_hidden_experts()[:5]:
                domain = expert.get("domains", ["unknown"])[0] if expert.get("domains") else "unknown"
                contacts.append({
                    "email": expert.get("entity", ""),
                    "team": self._domain_to_team(domain),
                    "domain": domain,
                    "reason": f"Hidden expert in {domain}",
                    "responded": False,
                })
        except Exception:
            pass

        # Deduplicate contacts by email
        seen_emails = set()
        unique_contacts = []
        for c in contacts:
            if c.get("email") and c["email"] not in seen_emails:
                seen_emails.add(c["email"])
                unique_contacts.append(c)

        request = CoordinationRequest(
            request_id=request_id,
            decision=decision,
            initiated_by=initiated_by,
            teams=teams,
            contacts=unique_contacts,
        )
        self._requests[request_id] = request

        logger.info("Coordination initiated: %s — '%s' (teams: %s, contacts: %d)",
                     request_id, decision[:40], teams, len(unique_contacts))

        return request.to_dict()

    def add_response(
        self,
        request_id: str,
        responder: str,
        team: str,
        response: str,
        stance: str = "neutral",  # support | oppose | neutral | conditional
    ) -> bool:
        """Add a response from a team contact."""
        request = self._requests.get(request_id)
        if not request:
            return False

        request.responses.append({
            "responder": responder,
            "team": team,
            "response": response,
            "stance": stance,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Update contact status
        for contact in request.contacts:
            if contact.get("email") == responder:
                contact["responded"] = True
                contact["stance"] = stance
                break

        # Update status
        if len(request.responses) >= len(request.contacts):
            request.status = "collecting"
        elif len(request.responses) > 0:
            request.status = "collecting"

        return True

    def synthesize(self, request_id: str) -> dict[str, Any] | None:
        """Synthesize a single multi-perspective answer from all responses.

        In production, this would use an LLM. For now, it's rule-based:
        group by stance, summarize each team's position.
        """
        request = self._requests.get(request_id)
        if not request:
            return None

        if not request.responses:
            request.status = "synthesized"
            request.synthesis = "No responses received yet."
            return request.to_dict()

        # Group by stance
        by_stance: dict[str, list[dict[str, Any]]] = {}
        for r in request.responses:
            by_stance.setdefault(r["stance"], []).append(r)

        # Build synthesis
        parts = []
        if "support" in by_stance:
            teams = [r["team"] for r in by_stance["support"]]
            parts.append(f"Supported by: {', '.join(teams)}")
        if "conditional" in by_stance:
            teams = [r["team"] for r in by_stance["conditional"]]
            conditions = [r["response"][:60] for r in by_stance["conditional"]]
            parts.append(f"Conditional support from: {', '.join(teams)} — {conditions}")
        if "oppose" in by_stance:
            teams = [r["team"] for r in by_stance["oppose"]]
            parts.append(f"Opposed by: {', '.join(teams)}")
        if "neutral" in by_stance:
            teams = [r["team"] for r in by_stance["neutral"]]
            parts.append(f"Neutral from: {', '.join(teams)}")

        parts.append(f"\nSummary: {len(request.responses)}/{len(request.contacts)} teams responded.")

        # Per-team positions
        parts.append("\nPer-team positions:")
        for r in request.responses:
            parts.append(f"  {r['team']} ({r['stance']}): {r['response'][:80]}")

        request.synthesis = "\n".join(parts)
        request.status = "synthesized"

        return request.to_dict()

    def get(self, request_id: str) -> dict[str, Any] | None:
        request = self._requests.get(request_id)
        return request.to_dict() if request else None

    def list_requests(self, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            return [r.to_dict() for r in self._requests.values() if r.status == status]
        return [r.to_dict() for r in self._requests.values()]

    def _identify_teams(self, decision: str) -> list[str]:
        """Identify affected teams from the decision text."""
        decision_lower = decision.lower()
        teams = set()

        for team, domains in self.TEAM_DOMAINS.items():
            for domain in domains:
                if domain in decision_lower:
                    teams.add(team)
                    break

        # Always include engineering and leadership for cross-cutting decisions
        if not teams:
            teams = {"engineering", "leadership"}

        # Add legal for anything mentioning compliance/contract
        if any(kw in decision_lower for kw in ["compliance", "contract", "legal", "gdpr", "policy"]):
            teams.add("legal")

        # Add security for anything mentioning auth/security
        if any(kw in decision_lower for kw in ["auth", "oauth", "saml", "security", "password"]):
            teams.add("security")

        return sorted(teams)

    def _identify_contacts(self, teams: list[str]) -> list[dict[str, Any]]:
        """Identify the right person to ask for each team."""
        contacts = []

        # Map teams to people from the signal history
        team_people: dict[str, set[str]] = {}
        for s in self.signals:
            actor = s.actor
            if not actor or actor == "unknown":
                continue
            domain = s.metadata.get("domain", "")
            team = self._domain_to_team(domain)
            if team in teams:
                team_people.setdefault(team, set()).add(actor)

        # Pick the most active person per team (most signals)
        for team in teams:
            people = team_people.get(team, set())
            if people:
                # Count signals per person for this team
                counts = {p: sum(1 for s in self.signals if s.actor == p) for p in people}
                best = max(counts, key=counts.get)
                contacts.append({
                    "email": best,
                    "team": team,
                    "reason": f"Most active in {team} ({counts[best]} signals)",
                    "responded": False,
                })

        # If no team people found, use knowledge graph experts
        if not contacts:
            try:
                for expert in self.model.knowledge.get_hidden_experts()[:3]:
                    contacts.append({
                        "email": expert.get("entity", ""),
                        "team": "engineering",
                        "reason": f"Identified expert ({expert.get('influence', 0):.0f} influence)",
                        "responded": False,
                    })
            except Exception:
                pass

        return contacts

    def _domain_to_team(self, domain: str) -> str:
        """Map a domain to a team."""
        domain_lower = domain.lower()
        for team, domains in self.TEAM_DOMAINS.items():
            if domain_lower in domains:
                return team
        return "engineering"
