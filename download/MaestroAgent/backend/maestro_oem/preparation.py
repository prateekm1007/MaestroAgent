"""
Preparation Engine — transforms Maestro from "recommends" to "already prepared."

The core shift: instead of "You should do X," Maestro says "X is ready. Approve?"

For each recommendation the OEM produces, the PreparationEngine asks:
  "If this recommendation is correct, what work would need to exist?"
Then it assembles that work from existing OEM data — receipts, laws,
patterns, signals. No LLM generation from scratch; the content is
evidence-backed and traceable.

Preparation types:
  - legal_packet: relevant contracts, prior decisions, risk assessment
  - rfc_draft: context, proposed change, alternatives, stakeholders
  - rollback_plan: rollback steps, monitoring thresholds, comms template
  - customer_brief: relationship state, commitments, objections, recommendation
  - incident_response: similar incidents, responders, mitigation steps

Product law: "Every new capability must measurably eliminate searching,
remembering, coordinating, waiting, translating, or preparing."
The Preparation Engine eliminates PREPARING. The CEO's decision changes
from "Think + Research + Prepare" to "Approve."
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class Preparation:
    """A prepared work packet, assembled from OEM data."""

    def __init__(
        self,
        preparation_id: str,
        preparation_type: str,
        title: str,
        recommendation_id: str,
        content: dict[str, Any],
        evidence: list[dict[str, Any]],
        confidence: float,
        status: str = "ready",  # ready | approved | rejected | expired
        created_at: datetime | None = None,
        approved_by: str = "",
        approved_at: datetime | None = None,
        intent_id: str = "",  # Links to the Intent this preparation serves
    ) -> None:
        self.preparation_id = preparation_id
        self.preparation_type = preparation_type
        self.title = title
        self.recommendation_id = recommendation_id
        self.content = content
        self.evidence = evidence
        self.confidence = confidence
        self.status = status
        self.created_at = created_at or datetime.now(timezone.utc)
        self.approved_by = approved_by
        self.approved_at = approved_at
        self.intent_id = intent_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "preparation_id": self.preparation_id,
            "preparation_type": self.preparation_type,
            "title": self.title,
            "recommendation_id": self.recommendation_id,
            "intent_id": self.intent_id,
            "content": self.content,
            "evidence": self.evidence,
            "confidence": round(self.confidence, 4),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
        }


class PreparationEngine:
    """Assembles prepared work packets from OEM data for each recommendation.

    Usage:
        engine = PreparationEngine(model, signals, decisions)
        preparations = engine.prepare_all()
        # preparations = [{type: "rollback_plan", title: "...", content: {...}, ...}]
    """

    def __init__(self, model: Any, signals: list, decisions: Any = None) -> None:
        self.model = model
        self.signals = signals
        self.decisions = decisions
        self._preparations: list[Preparation] = []

    def prepare_all(self) -> list[dict[str, Any]]:
        """Generate preparations for all active recommendations.

        Returns a list of preparation dicts (via to_dict()).
        """
        self._preparations = []
        try:
            if self.decisions:
                recs = self.decisions.get_recommendations()
                for rec in recs:
                    prep = self._prepare_for_recommendation(rec)
                    if prep:
                        self._preparations.append(prep)
        except Exception as e:
            logger.warning("Preparation engine failed: %s", e)

        return [p.to_dict() for p in self._preparations]

    def prepare_for(self, recommendation_id: str) -> Preparation | None:
        """Prepare work for a specific recommendation."""
        try:
            if not self.decisions:
                return None
            recs = self.decisions.get_recommendations()
            rec = next((r for r in recs if r.rec_id == recommendation_id), None)
            if not rec:
                return None
            return self._prepare_for_recommendation(rec)
        except Exception as e:
            logger.warning("Prepare for %s failed: %s", recommendation_id, e)
            return None

    def _prepare_for_recommendation(self, rec: Any) -> Preparation | None:
        """Determine the preparation type and assemble the packet."""
        title = getattr(rec, "title", str(rec))
        recommendation = getattr(rec, "recommendation", title)
        impact = getattr(rec, "impact", "")
        confidence = getattr(rec, "confidence", 0.5)
        linked_laws = getattr(rec, "linked_laws", [])
        # Use the title as a stable identifier — rec_id changes between calls
        # because DecisionEngine generates new UUIDs each time get_recommendations()
        # is called. The title is deterministic and unique per recommendation.
        rec_id = getattr(rec, "rec_id", "")
        stable_id = title  # Stable across calls for auto-linking

        title_lower = title.lower()
        impact_lower = impact.lower()

        # Determine preparation type from the recommendation's content
        if any(kw in title_lower for kw in ["rollback", "deploy", "release", "ship"]):
            return self._prepare_rollback_plan(rec, title, stable_id, confidence, linked_laws)
        elif any(kw in title_lower for kw in ["bottleneck", "approval", "gate"]):
            return self._prepare_rfc_draft(rec, title, stable_id, confidence, linked_laws)
        elif any(kw in title_lower for kw in ["customer", "renewal", "churn", "objection"]):
            return self._prepare_customer_brief(rec, title, stable_id, confidence, linked_laws)
        elif any(kw in title_lower for kw in ["incident", "p1", "outage", "sev"]):
            return self._prepare_incident_response(rec, title, stable_id, confidence, linked_laws)
        elif any(kw in title_lower for kw in ["legal", "compliance", "contract", "policy"]):
            return self._prepare_legal_packet(rec, title, stable_id, confidence, linked_laws)
        else:
            # Default: prepare a general brief
            return self._prepare_general_brief(rec, title, stable_id, confidence, linked_laws)

    def _prepare_rollback_plan(self, rec, title, rec_id, confidence, linked_laws) -> Preparation:
        """Assemble a rollback plan from OEM data."""
        from maestro_oem.signal import SignalType

        # Find relevant deployment/release signals
        deployments = [s for s in self.signals
                      if s.type in (SignalType.DEPLOYMENT, SignalType.RELEASE, SignalType.PR_MERGED)]

        # Find relevant incidents (for rollback context)
        incidents = [s for s in self.signals if s.type == SignalType.INCIDENT]

        # Find relevant laws about deployment
        deploy_laws = [l for l in self.model.laws.values()
                      if "deploy" in l.statement.lower() or "release" in l.statement.lower()]

        evidence = []
        evidence.append({"type": "deployments_found", "count": len(deployments), "detail": f"Found {len(deployments)} deployment signals in OEM history"})
        if incidents:
            evidence.append({"type": "past_incidents", "count": len(incidents), "detail": f"{len(incidents)} past incidents provide rollback context"})
        if deploy_laws:
            evidence.append({"type": "deployment_laws", "codes": [l.code for l in deploy_laws], "detail": "Organizational laws about deployment patterns"})

        content = {
            "rollback_steps": [
                "1. Verify current deployment version and health metrics",
                "2. Identify the last known stable version from deployment history",
                "3. Execute rollback via deployment pipeline",
                "4. Monitor health metrics for 15 minutes post-rollback",
                "5. Notify stakeholders via communication template below",
            ],
            "monitoring_thresholds": {
                "error_rate": "< 1% for 5 consecutive minutes",
                "latency_p99": "< 500ms",
                "availability": "> 99.9%",
            },
            "communication_template": f"Rollback executed for: {title}. Previous version restored. Monitoring in progress. — {datetime.now(timezone.utc).isoformat()}",
            "relevant_history": f"{len(deployments)} past deployments, {len(incidents)} past incidents",
            "applicable_laws": [l.code for l in deploy_laws],
        }

        return Preparation(
            preparation_id=f"prep-{uuid4().hex[:12]}",
            preparation_type="rollback_plan",
            title=f"Rollback plan ready: {title[:60]}",
            recommendation_id=rec_id,
            content=content,
            evidence=evidence,
            confidence=confidence,
        )

    def _prepare_rfc_draft(self, rec, title, rec_id, confidence, linked_laws) -> Preparation:
        """Assemble an RFC draft from OEM data."""
        description = getattr(rec, "description", "")
        decision_question = getattr(rec, "decision_question", "")

        # Find related RFCs
        from maestro_oem.signal import SignalType
        related_rfcs = [s for s in self.signals if s.type == SignalType.RFC_CREATED]

        # Find stakeholders from the knowledge graph
        stakeholders = list(self.model.knowledge.domain_holders.keys())[:5]

        evidence = []
        if related_rfcs:
            evidence.append({"type": "related_rfcs", "count": len(related_rfcs), "detail": f"{len(related_rfcs)} prior RFCs in OEM history"})
        if stakeholders:
            evidence.append({"type": "stakeholders", "count": len(stakeholders), "detail": f"Identified {len(stakeholders)} potential stakeholders from knowledge graph"})

        content = {
            "context": description or f"Addressing: {title}",
            "proposed_change": getattr(rec, "recommendation", title),
            "alternatives": [
                "Status quo (no change)",
                f"Alternative approach based on {decision_question}" if decision_question else "Alternative approach to be defined",
            ],
            "stakeholders": stakeholders,
            "timeline": "2 weeks for review, 1 week for implementation",
            "risk_assessment": f"Confidence: {confidence:.0%}. Linked laws: {linked_laws or 'none'}",
            "decision_question": decision_question or f"Should we proceed with: {title[:60]}?",
        }

        return Preparation(
            preparation_id=f"prep-{uuid4().hex[:12]}",
            preparation_type="rfc_draft",
            title=f"RFC draft ready: {title[:60]}",
            recommendation_id=rec_id,
            content=content,
            evidence=evidence,
            confidence=confidence,
        )

    def _prepare_customer_brief(self, rec, title, rec_id, confidence, linked_laws) -> Preparation:
        """Assemble a customer brief from OEM data."""
        from maestro_oem.signal import SignalType

        # Extract customer name from the recommendation title
        customer_name = ""
        for kw in ["customer", "renewal", "churn"]:
            if kw in title.lower():
                # Try to extract customer name from the title
                parts = title.split()
                for part in parts:
                    if part[0].isupper() and part.lower() not in ["address", "the", "is", "has"]:
                        customer_name = part
                        break

        # Find customer signals
        customer_signals = [s for s in self.signals
                           if s.provider.value == "customer"
                           and (not customer_name or customer_name.lower() in s.metadata.get("customer", "").lower())]

        # Find commitments
        commitments = [s for s in customer_signals if s.type == SignalType.CUSTOMER_COMMITMENT_MADE]
        broken = [s for s in customer_signals if s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN]
        objections = [s for s in customer_signals if s.type == SignalType.CUSTOMER_OBJECTION]
        drift = [s for s in customer_signals if s.type == SignalType.CUSTOMER_CHAMPION_QUIET]

        evidence = []
        if commitments:
            evidence.append({"type": "commitments", "count": len(commitments), "detail": f"{len(commitments)} open commitments tracked"})
        if broken:
            evidence.append({"type": "broken_commitments", "count": len(broken), "detail": f"{len(broken)} broken commitments — trust risk"})
        if objections:
            evidence.append({"type": "objections", "count": len(objections), "detail": f"{len(objections)} objections raised"})
        if drift:
            evidence.append({"type": "drift_signals", "count": len(drift), "detail": f"{len(drift)} drift signals — champion may be disengaging"})

        content = {
            "relationship_state": "at_risk" if (broken or drift) else "healthy" if not objections else "stable",
            "open_commitments": [
                {"commitment": s.metadata.get("commitment", ""), "due_date": s.metadata.get("due_date", "")}
                for s in commitments[:5]
            ],
            "likely_objections": list({s.metadata.get("objection_type", "") for s in objections if s.metadata.get("objection_type")}),
            "recommended_outcome": getattr(rec, "recommendation", title),
            "things_not_to_say": [
                f"Avoid discussing {s.metadata.get('objection_type', 'past objections')} without preparation"
                for s in objections[:2]
            ],
            "arr_impact": max(float(s.metadata.get("arr_impact", 0) or 0) for s in customer_signals) if customer_signals else 0,
        }

        return Preparation(
            preparation_id=f"prep-{uuid4().hex[:12]}",
            preparation_type="customer_brief",
            title=f"Customer brief ready: {title[:60]}",
            recommendation_id=rec_id,
            content=content,
            evidence=evidence,
            confidence=confidence,
        )

    def _prepare_incident_response(self, rec, title, rec_id, confidence, linked_laws) -> Preparation:
        """Assemble an incident response packet from OEM data."""
        from maestro_oem.signal import SignalType

        # Find similar past incidents
        incidents = [s for s in self.signals if s.type == SignalType.INCIDENT]
        p1_issues = [s for s in self.signals
                    if s.type == SignalType.ISSUE_CREATED
                    and s.metadata.get("priority", "").upper() in ("P1", "P0")]

        # Find relevant experts
        experts = []
        try:
            for expert in self.model.knowledge.get_hidden_experts()[:3]:
                experts.append({"email": expert.get("entity", ""), "domains": expert.get("domains", [])})
        except Exception:
            pass

        evidence = []
        if incidents:
            evidence.append({"type": "similar_incidents", "count": len(incidents), "detail": f"{len(incidents)} past incidents for context"})
        if experts:
            evidence.append({"type": "responders", "count": len(experts), "detail": f"{len(experts)} identified experts who can help"})

        content = {
            "similar_incidents": [
                {"artifact": s.artifact, "timestamp": s.timestamp.isoformat()}
                for s in incidents[:5]
            ],
            "responders": experts,
            "communication_draft": f"Incident: {title}. Severity: P1. Response team assembling. Root cause investigation in progress. — {datetime.now(timezone.utc).isoformat()}",
            "mitigation_steps": [
                "1. Acknowledge incident and assign incident commander",
                "2. Gather relevant experts (identified above)",
                "3. Review similar past incidents for patterns",
                "4. Implement immediate mitigation",
                "5. Conduct postmortem within 48 hours",
            ],
            "applicable_laws": linked_laws or [],
        }

        return Preparation(
            preparation_id=f"prep-{uuid4().hex[:12]}",
            preparation_type="incident_response",
            title=f"Incident response ready: {title[:60]}",
            recommendation_id=rec_id,
            content=content,
            evidence=evidence,
            confidence=confidence,
        )

    def _prepare_legal_packet(self, rec, title, rec_id, confidence, linked_laws) -> Preparation:
        """Assemble a legal packet from OEM data."""
        from maestro_oem.signal import SignalType

        # Find contract signals
        contracts = [s for s in self.signals
                    if s.type in (SignalType.CUSTOMER_CONTRACT_SIGNED,
                                  SignalType.CUSTOMER_CONTRACT_RENEWED,
                                  SignalType.CUSTOMER_CONTRACT_CHURNED)]

        # Find relevant laws
        legal_laws = [l for l in self.model.laws.values()
                     if any(kw in l.statement.lower() for kw in ["legal", "compliance", "contract", "risk"])]

        evidence = []
        if contracts:
            evidence.append({"type": "contract_history", "count": len(contracts), "detail": f"{len(contracts)} contract events in OEM history"})
        if legal_laws:
            evidence.append({"type": "legal_laws", "codes": [l.code for l in legal_laws], "detail": f"{len(legal_laws)} organizational laws relevant to legal review"})

        content = {
            "relevant_contracts": [
                {"artifact": s.artifact, "type": s.type.value, "customer": s.metadata.get("customer", "")}
                for s in contracts[:5]
            ],
            "prior_decisions": [l.statement[:80] for l in legal_laws[:3]],
            "risk_assessment": f"Confidence: {confidence:.0%}. Linked laws: {linked_laws or 'none'}",
            "suggested_clauses": [
                "Standard SLA terms apply",
                "Limitation of liability per master agreement",
                "Data processing addendum required for GDPR compliance",
            ],
        }

        return Preparation(
            preparation_id=f"prep-{uuid4().hex[:12]}",
            preparation_type="legal_packet",
            title=f"Legal packet ready: {title[:60]}",
            recommendation_id=rec_id,
            content=content,
            evidence=evidence,
            confidence=confidence,
        )

    def _prepare_general_brief(self, rec, title, rec_id, confidence, linked_laws) -> Preparation:
        """Assemble a general brief from OEM data (fallback)."""
        description = getattr(rec, "description", "")
        impact = getattr(rec, "impact", "")
        urgency = getattr(rec, "urgency", "normal")

        evidence = []
        if linked_laws:
            evidence.append({"type": "linked_laws", "codes": linked_laws, "detail": f"{len(linked_laws)} organizational laws support this recommendation"})

        content = {
            "summary": description or title,
            "expected_impact": impact or "Impact assessment pending",
            "urgency": urgency,
            "linked_laws": linked_laws or [],
            "recommendation": getattr(rec, "recommendation", title),
            "decision_question": getattr(rec, "decision_question", ""),
        }

        return Preparation(
            preparation_id=f"prep-{uuid4().hex[:12]}",
            preparation_type="general_brief",
            title=f"Brief ready: {title[:60]}",
            recommendation_id=rec_id,
            content=content,
            evidence=evidence,
            confidence=confidence,
        )

    def approve(self, preparation_id: str, approved_by: str = "ceo") -> bool:
        """Mark a preparation as approved.

        In production, this would trigger execution (create Jira ticket,
        send Slack message, etc.). For now, it just updates the status.
        """
        for prep in self._preparations:
            if prep.preparation_id == preparation_id:
                prep.status = "approved"
                prep.approved_by = approved_by
                prep.approved_at = datetime.now(timezone.utc)
                logger.info("Preparation %s approved by %s", preparation_id, approved_by)
                return True
        return False

    def reject(self, preparation_id: str, rejected_by: str = "ceo", reason: str = "") -> bool:
        """Mark a preparation as rejected.

        Round 51 H18 fix: the old code had no reject method — the UI faked
        rejection via string conventions (approved_by='ceo-rejected'). Now
        there is a real reject method that sets status='rejected' and records
        the rejector + reason.
        """
        for prep in self._preparations:
            if prep.preparation_id == preparation_id:
                prep.status = "rejected"
                prep.approved_by = rejected_by
                prep.approved_at = datetime.now(timezone.utc)
                prep.metadata["reject_reason"] = reason
                logger.info("Preparation %s rejected by %s: %s", preparation_id, rejected_by, reason)
                return True
        return False

    def get_preparation(self, preparation_id: str) -> dict[str, Any] | None:
        """Get a single preparation by ID."""
        for prep in self._preparations:
            if prep.preparation_id == preparation_id:
                return prep.to_dict()
        return None

    def list_preparations(self, status: str | None = None) -> list[dict[str, Any]]:
        """List all preparations, optionally filtered by status."""
        if status:
            return [p.to_dict() for p in self._preparations if p.status == status]
        return [p.to_dict() for p in self._preparations]
