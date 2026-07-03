"""
Perspective Engine — same decision, different implications per team.

The same event means different things to different teams. Legal hears
"risk increased." Engineering hears "deployment blocked." Finance hears
"revenue delayed." Maestro should translate.

This is the Hayek realization: knowledge is dispersed. The OEM shouldn't
centralize it — it should translate it. Each team retains ownership of
their knowledge; the OEM makes it actionable across team boundaries.

Perspectives:
  - engineering: What does this mean for code/deployments/architecture?
  - legal: What does this mean for compliance/contracts/risk?
  - finance: What does this mean for revenue/budget/forecast?
  - sales: What does this mean for pipeline/customers/deals?
  - support: What does this mean for customers/tickets/satisfaction?
  - leadership: What does this mean for strategy/priorities/board?

Rule-based, not LLM. Each team has a translation template that maps
signal types to team-specific implications.

Product law: eliminates TRANSLATING (each team sees the same event
in their own language without a meeting).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


PERSPECTIVES = ("engineering", "legal", "finance", "sales", "support", "leadership")


# ─── Translation templates ─────────────────────────────────────────────────
# Each template maps a signal type to a team-specific implication.

_TEMPLATES: dict[str, dict[str, str]] = {
    # Customer commitment broken
    "customer.commitment_broken": {
        "engineering": "Deployment timeline for {customer} may slip — dependency on '{commitment}' is unresolved.",
        "legal": "Contractual obligation to {customer} may be at risk — review SLA terms.",
        "finance": "Revenue recognition for {customer} deal may delay — update forecast.",
        "sales": "Relationship with {customer} is at risk — schedule recovery meeting.",
        "support": "Expect escalated tickets from {customer} — prepare context.",
        "leadership": "Trust deficit with {customer} — may affect renewal. ARR at stake: ${arr:,.0f}.",
    },
    # Customer champion quiet
    "customer.champion_quiet": {
        "engineering": "Technical champion at {customer} is disengaging — may slow technical reviews.",
        "legal": "No immediate legal impact.",
        "finance": "Renewal probability for {customer} is declining — adjust forecast.",
        "sales": "Champion at {customer} went quiet — relationship decay risk. Act now.",
        "support": "Monitor {customer} ticket sentiment — may indicate broader dissatisfaction.",
        "leadership": "Key relationship at {customer} is deteriorating. ARR at stake: ${arr:,.0f}.",
    },
    # Customer contract churned
    "customer.contract_churned": {
        "engineering": "No engineering action needed — but review if technical issues contributed.",
        "legal": "Contract with {customer} terminated — ensure clean offboarding.",
        "finance": "Revenue loss: ${arr:,.0f} ARR. Update Q4 forecast.",
        "sales": "Loss review needed — what could we have done differently with {customer}?",
        "support": "Schedule offboarding for {customer} — data export, access revocation.",
        "leadership": "Customer loss: {customer} (${arr:,.0f} ARR). Root cause analysis required.",
    },
    # Customer objection
    "customer.objection": {
        "engineering": "Technical objection from {customer}: {objection_type}. May need engineering input.",
        "legal": "Review if {objection_type} has legal implications for {customer}.",
        "finance": "Objection from {customer} may delay deal — assess revenue impact.",
        "sales": "Address {objection_type} objection from {customer} before next meeting.",
        "support": "No immediate support action.",
        "leadership": "{customer} raised {objection_type} — monitor for pattern.",
    },
    # Bottleneck detected
    "bottleneck": {
        "engineering": "Approval bottleneck at {gate} is blocking {count} engineering items.",
        "legal": "No direct legal impact unless {gate} is a legal review.",
        "finance": "Bottleneck at {gate} delays revenue-generating work — quantify impact.",
        "sales": "Delays may affect customer commitments — check if {gate} blocks customer-facing work.",
        "support": "Bottleneck at {gate} may delay customer-facing fixes.",
        "leadership": "{gate} is gating {count} items — organizational efficiency risk.",
    },
    # Incident
    "incident": {
        "engineering": "Incident detected — assemble response team. Check similar past incidents.",
        "legal": "Assess if incident has contractual or compliance implications.",
        "finance": "Incident may affect SLA compliance — review penalty clauses.",
        "sales": "Prepare customer communication if incident is customer-visible.",
        "support": " frontline — expect customer tickets. Prepare status updates.",
        "leadership": "Incident active — monitor for escalation. Review postmortem within 48h.",
    },
    # Law strengthened
    "law_strengthened": {
        "engineering": "Pattern validated — engineering can rely on this for planning.",
        "legal": "Organizational precedent strengthened — cite in legal reviews.",
        "finance": "Reliable pattern improves forecast accuracy.",
        "sales": "Pattern helps qualify deals faster — share with sales team.",
        "support": "Use validated pattern to guide support responses.",
        "leadership": "Organizational learning confirmed — pattern is now a reliable law.",
    },
    # Law challenged
    "law_challenged": {
        "engineering": "Previously reliable pattern is failing — review engineering assumptions.",
        "legal": "Organizational precedent is weakening — re-evaluate risk position.",
        "finance": "Forecast reliability decreasing — add uncertainty buffer.",
        "sales": "Pattern that guided deal qualification may no longer hold.",
        "support": "Support guidance based on this pattern may need updating.",
        "leadership": "An organizational assumption is being proven wrong — strategic review needed.",
    },
    # Sprint completed
    "sprint.completed": {
        "engineering": "Sprint completed with velocity {velocity} — assess team capacity.",
        "legal": "No direct legal impact.",
        "finance": "Sprint velocity {velocity} — update delivery forecast.",
        "sales": "Delivery velocity {velocity} — adjust customer timeline expectations.",
        "support": "New features/fixes from sprint — update support docs.",
        "leadership": "Team velocity: {velocity}. Trend indicates {'improving' if velocity > 35 else 'stable' if velocity > 25 else 'declining'}.",
    },
    # P1 risk
    "p1_risk": {
        "engineering": "P1 risk cluster detected — prioritize mitigation.",
        "legal": "P1 risk may have compliance implications — review.",
        "finance": "P1 risk threatens ${arr:,.0f} ARR if it materializes.",
        "sales": "P1 risk may affect customer commitments — prepare contingency.",
        "support": "P1 risk may generate customer incidents — prepare response.",
        "leadership": "P1 risk at {probability} — board-level attention warranted.",
    },
}


class PerspectiveEngine:
    """Translates OEM events into team-specific perspectives.

    Usage:
        engine = PerspectiveEngine()
        perspectives = engine.translate(
            event_type="customer.commitment_broken",
            context={"customer": "<customer>", "commitment": "SSO by Q1", "arr": 3200000},
        )
        # perspectives = {"engineering": "...", "legal": "...", "finance": "...", ...}
    """

    def translate(
        self,
        event_type: str,
        context: dict[str, Any] | None = None,
        perspectives: list[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Translate an event into team-specific perspectives.

        Args:
            event_type: The signal/event type (e.g. "customer.commitment_broken")
            context: Dict with event-specific data (customer, arr, commitment, etc.)
            perspectives: Which perspectives to generate (default: all 6)

        Returns:
            Dict mapping perspective name → {implication, relevance, action}
        """
        context = context or {}
        target_perspectives = perspectives or list(PERSPECTIVES)
        templates = _TEMPLATES.get(event_type, {})
        result = {}

        for perspective in target_perspectives:
            template = templates.get(perspective, "")
            if not template:
                result[perspective] = {
                    "implication": f"No direct {perspective} impact identified for this event.",
                    "relevance": "low",
                    "action": "No action needed at this time.",
                }
            else:
                # Fill in the template with context
                try:
                    implication = template.format(**context)
                except (KeyError, ValueError):
                    implication = template  # Use unfilled template if context is incomplete

                result[perspective] = {
                    "implication": implication,
                    "relevance": "high" if perspective in ("engineering", "sales", "leadership") else "medium",
                    "action": self._recommend_action(event_type, perspective, context),
                }

        return result

    def translate_signal(self, signal: Any, perspectives: list[str] | None = None) -> dict[str, dict[str, Any]]:
        """Translate a specific ExecutionSignal into perspectives."""
        event_type = signal.type.value
        context = {
            "customer": signal.metadata.get("customer", "the customer"),
            "contact": signal.metadata.get("contact", ""),
            "commitment": signal.metadata.get("commitment", "the commitment"),
            "objection_type": signal.metadata.get("objection_type", "unspecified"),
            "arr": float(signal.metadata.get("arr_impact", 0) or 0),
            "gate": signal.metadata.get("gate", ""),
            "count": signal.metadata.get("items_gated", 0),
            "velocity": signal.metadata.get("velocity", 0),
            "probability": signal.metadata.get("probability", 0),
        }
        return self.translate(event_type, context, perspectives)

    def _recommend_action(self, event_type: str, perspective: str, context: dict[str, Any]) -> str:
        """Generate a recommended action for this perspective."""
        actions = {
            ("customer.commitment_broken", "engineering"): "Review dependency chain and adjust timeline.",
            ("customer.commitment_broken", "legal"): "Review SLA terms and prepare remediation plan.",
            ("customer.commitment_broken", "finance"): "Update revenue forecast for potential delay.",
            ("customer.commitment_broken", "sales"): "Schedule recovery meeting with customer within 48h.",
            ("customer.commitment_broken", "leadership"): "Escalate to executive sponsor — trust is at risk.",
            ("customer.champion_quiet", "sales"): "Reach out to champion directly — schedule check-in.",
            ("customer.champion_quiet", "leadership"): "Assign account team to assess relationship health.",
            ("customer.contract_churned", "leadership"): "Commission loss review within 5 business days.",
            ("customer.objection", "sales"): "Prepare evidence packet addressing the specific objection.",
            ("bottleneck", "engineering"): "Redistribute approval authority or streamline the gate.",
            ("bottleneck", "leadership"): "Review whether this gate is VP-level or process-level.",
            ("incident", "engineering"): "Assemble incident response team immediately.",
            ("incident", "leadership"): "Monitor for escalation — prepare board communication if needed.",
            ("law_strengthened", "leadership"): "Consider operationalizing this law into documented process.",
            ("law_challenged", "leadership"): "Strategic review needed — an assumption is being proven wrong.",
        }
        return actions.get((event_type, perspective), "Monitor the situation and assess next steps.")

    def list_perspectives(self) -> list[str]:
        """List all available perspectives."""
        return list(PERSPECTIVES)

    def list_supported_events(self) -> list[str]:
        """List all event types that have translation templates."""
        return list(_TEMPLATES.keys())
