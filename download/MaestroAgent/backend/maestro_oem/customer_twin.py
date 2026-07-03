"""
Customer Digital Twin — "What happens if we change the customer relationship?"

The organizational DigitalTwin answers "what if we restructure the org?"
This twin answers "what if we change how we engage this customer?"

Scenarios:
  - pricing:         What if we increase price by X%?
  - pilot:           What if we offer a 90-day pilot?
  - delay:           What if we delay delivery by N weeks?
  - champion_leaves: What if the champion departs?
  - security:        What if a security concern is raised?
  - procurement:     What if procurement delays by N weeks?
  - legal:           What if legal review takes longer?

Each scenario predicts:
  - Expected outcome (renew / churn / delay / expand)
  - Confidence (0..1)
  - Supporting evidence (laws, patterns, past decisions)
  - Counter-evidence (signals that suggest a different outcome)
  - Business impact (ARR delta)
  - Alternative actions

The twin uses the customer's historical decision pattern + drift metrics
to predict. It does NOT modify the real OEM.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from maestro_oem.customer_judgment import CustomerJudgmentEngine
from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
from maestro_oem.learning_object import LearningObjectType


@dataclass
class CustomerImpactReport:
    """Result of a customer-relationship what-if scenario."""
    scenario_id: str
    scenario_type: str
    customer: str
    description: str
    timestamp: str
    expected_outcome: str  # renew | churn | delay | expand
    confidence: float
    supporting_evidence: list[dict[str, Any]] = field(default_factory=list)
    counter_evidence: list[dict[str, Any]] = field(default_factory=list)
    business_impact: dict[str, Any] = field(default_factory=dict)
    alternative_actions: list[dict[str, Any]] = field(default_factory=list)
    risk_level: str = "low"  # low | medium | high | critical

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_type": self.scenario_type,
            "customer": self.customer,
            "description": self.description,
            "timestamp": self.timestamp,
            "expected_outcome": self.expected_outcome,
            "confidence": round(self.confidence, 4),
            "supporting_evidence": self.supporting_evidence,
            "counter_evidence": self.counter_evidence,
            "business_impact": self.business_impact,
            "alternative_actions": self.alternative_actions,
            "risk_level": self.risk_level,
        }


class CustomerScenarioEngine:
    """Applies customer-relationship scenarios and predicts the impact.

    Usage:
        engine = CustomerJudgmentEngine(model, signals, decisions)
        twin = CustomerScenarioEngine(engine)
        report = twin.run_scenario({
            "type": "pricing",
            "customer": "<customer>",
            "increase_pct": 10,
        })
    """

    SCENARIO_TYPES = (
        "pricing", "pilot", "delay", "champion_leaves",
        "security", "procurement", "legal",
    )

    def __init__(self, engine: CustomerJudgmentEngine) -> None:
        self.engine = engine

    def run_scenario(self, scenario: dict[str, Any]) -> CustomerImpactReport:
        """Apply a scenario and return the predicted impact."""
        stype = scenario.get("type", "unknown")
        customer = scenario.get("customer", "")
        scenario_id = f"cscenario-{uuid4().hex[:8]}"

        if stype not in self.SCENARIO_TYPES:
            return CustomerImpactReport(
                scenario_id=scenario_id,
                scenario_type=stype,
                customer=customer,
                description=f"Unknown scenario type: {stype}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                expected_outcome="unknown",
                confidence=0.0,
            )

        # Get baseline state
        drift = self.engine.relationship_drift(customer)
        brief = self.engine.executive_brief(customer)
        arr = brief.get("arr_at_stake", 0)

        # Dispatch
        if stype == "pricing":
            outcome, conf, support, counter, impact, alts, risk = self._scenario_pricing(scenario, customer, drift, arr)
        elif stype == "pilot":
            outcome, conf, support, counter, impact, alts, risk = self._scenario_pilot(scenario, customer, drift, arr)
        elif stype == "delay":
            outcome, conf, support, counter, impact, alts, risk = self._scenario_delay(scenario, customer, drift, arr)
        elif stype == "champion_leaves":
            outcome, conf, support, counter, impact, alts, risk = self._scenario_champion_leaves(scenario, customer, drift, arr)
        elif stype == "security":
            outcome, conf, support, counter, impact, alts, risk = self._scenario_security(scenario, customer, drift, arr)
        elif stype == "procurement":
            outcome, conf, support, counter, impact, alts, risk = self._scenario_procurement(scenario, customer, drift, arr)
        else:  # legal
            outcome, conf, support, counter, impact, alts, risk = self._scenario_legal(scenario, customer, drift, arr)

        description = self._describe(stype, scenario, customer)

        return CustomerImpactReport(
            scenario_id=scenario_id,
            scenario_type=stype,
            customer=customer,
            description=description,
            timestamp=datetime.now(timezone.utc).isoformat(),
            expected_outcome=outcome,
            confidence=conf,
            supporting_evidence=support,
            counter_evidence=counter,
            business_impact=impact,
            alternative_actions=alts,
            risk_level=risk,
        )

    # ─── Scenarios ─────────────────────────────────────────────────────────

    def _scenario_pricing(self, scenario, customer, drift, arr):
        """What if we increase price by X%?"""
        pct = float(scenario.get("increase_pct", 10))
        # If customer has pricing objections in history, confidence of churn rises
        los = self.engine._customer_los(customer)
        has_pricing_objection = any(
            lo.metadata.get("objection_type") == "pricing"
            for lo in los if lo.type == LearningObjectType.CUSTOMER_RISK
        )
        trust = drift["trust"]
        momentum = drift["momentum"]

        if has_pricing_objection or trust < 0.5 or momentum == "negative":
            outcome = "churn"
            conf = 0.7
            risk = "high"
            support = [
                {"type": "objection", "detail": "Customer has previously objected to pricing."},
                {"type": "drift", "detail": f"Momentum is {momentum}, trust is {trust:.2f}."},
            ]
            counter = [
                {"type": "value", "detail": "If the price increase funds new features, value may offset cost."},
            ]
        elif momentum == "positive" and trust > 0.7:
            outcome = "renew"
            conf = 0.75
            risk = "low"
            support = [
                {"type": "momentum", "detail": "Relationship momentum is positive."},
                {"type": "trust", "detail": f"Trust is high ({trust:.2f})."},
            ]
            counter = [
                {"type": "sensitivity", "detail": "Even healthy customers have price ceilings."},
            ]
        else:
            outcome = "delay"
            conf = 0.5
            risk = "medium"
            support = [{"type": "neutral", "detail": "No strong signal either way."}]
            counter = [{"type": "uncertainty", "detail": "Outcome depends on competitor pricing."}]

        impact = {
            "arr_at_stake": arr,
            "price_change_pct": pct,
            "arr_delta_if_renew": arr * pct / 100,
            "arr_delta_if_churn": -arr,
        }
        alts = [
            {"action": "Phase the increase over 2 years", "rationale": "Reduces sticker shock."},
            {"action": "Bundle additional value (features, support tier)", "rationale": "Offsets price perception."},
            {"action": "Negotiate multi-year lock", "rationale": "Trades price for stability."},
        ]
        return outcome, conf, support, counter, impact, alts, risk

    def _scenario_pilot(self, scenario, customer, drift, arr):
        """What if we offer a 90-day pilot?"""
        pilot_days = int(scenario.get("days", 90))
        momentum = drift["momentum"]
        if momentum == "negative":
            outcome = "renew"
            conf = 0.65
            risk = "medium"
            support = [{"type": "drift", "detail": "Pilot can re-engage a drifting champion."}]
        else:
            outcome = "expand"
            conf = 0.6
            risk = "low"
            support = [{"type": "opportunity", "detail": "Pilot opens new use cases."}]
        counter = [{"type": "cost", "detail": "Pilot consumes engineering cycles without guaranteed return."}]
        impact = {
            "arr_at_stake": arr,
            "pilot_days": pilot_days,
            "engineering_cost_estimate": pilot_days * 0.5,  # rough
        }
        alts = [
            {"action": "Time-box the pilot with success criteria", "rationale": "Prevents open-ended commitment."},
            {"action": "Charge a nominal pilot fee", "rationale": "Tests serious intent."},
        ]
        return outcome, conf, support, counter, impact, alts, risk

    def _scenario_delay(self, scenario, customer, drift, arr):
        """What if we delay delivery by N weeks?"""
        weeks = int(scenario.get("weeks", 4))
        trust = drift["trust"]
        if trust < 0.5:
            outcome = "churn"
            conf = 0.7
            risk = "high"
        elif weeks > 8:
            outcome = "churn"
            conf = 0.6
            risk = "high"
        else:
            outcome = "delay"
            conf = 0.55
            risk = "medium"
        support = [
            {"type": "trust", "detail": f"Current trust is {trust:.2f} — delay will erode further."},
        ]
        counter = [{"type": "communication", "detail": "Proactive communication can mitigate trust loss."}]
        impact = {
            "arr_at_stake": arr,
            "delay_weeks": weeks,
            "trust_erosion_estimate": weeks * 0.05,
        }
        alts = [
            {"action": "Deliver partial scope on time", "rationale": "Shows good faith."},
            {"action": "Offer concession for the delay", "rationale": "Compensates trust erosion."},
        ]
        return outcome, conf, support, counter, impact, alts, risk

    def _scenario_champion_leaves(self, scenario, customer, drift, arr):
        """What if the champion departs?"""
        champion_health = drift["champion_health"]
        if champion_health == "quiet":
            outcome = "churn"
            conf = 0.8
            risk = "critical"
        else:
            outcome = "delay"
            conf = 0.65
            risk = "high"
        support = [
            {"type": "champion", "detail": f"Champion health is {champion_health}."},
            {"type": "bus_factor", "detail": "Single-threaded relationships are fragile."},
        ]
        counter = [{"type": "multi_thread", "detail": "If we've built multiple contacts, loss is survivable."}]
        impact = {
            "arr_at_stake": arr,
            "champion_loss_risk": "high",
        }
        alts = [
            {"action": "Immediately expand to 2+ contacts at the customer", "rationale": "Reduces single-thread risk."},
            {"action": "Schedule executive sponsor introduction", "rationale": "Builds redundancy at the top."},
            {"action": "Document the champion's institutional knowledge", "rationale": "Preserves relationship context."},
        ]
        return outcome, conf, support, counter, impact, alts, risk

    def _scenario_security(self, scenario, customer, drift, arr):
        """What if a security concern is raised?"""
        los = self.engine._customer_los(customer)
        has_security_role = any(
            lo.metadata.get("role") == "security"
            for lo in los if lo.type == LearningObjectType.CUSTOMER_COMMITTEE_ROLE
        )
        if has_security_role:
            outcome = "delay"
            conf = 0.7
            risk = "medium"
            support = [{"type": "committee", "detail": "Security role is already engaged — concern will be taken seriously."}]
        else:
            outcome = "delay"
            conf = 0.6
            risk = "high"
            support = [{"type": "committee", "detail": "No security role identified — concern may stall the deal."}]
        counter = [{"type": "remediation", "detail": "If we have a SOC2 report, the concern may resolve quickly."}]
        impact = {
            "arr_at_stake": arr,
            "delay_weeks_estimate": 4,
        }
        alts = [
            {"action": "Proactively share security documentation", "rationale": "Gets ahead of the concern."},
            {"action": "Schedule a security architecture review", "rationale": "Demonstrates seriousness."},
        ]
        return outcome, conf, support, counter, impact, alts, risk

    def _scenario_procurement(self, scenario, customer, drift, arr):
        """What if procurement delays by N weeks?"""
        weeks = int(scenario.get("weeks", 3))
        outcome = "delay"
        conf = 0.65
        risk = "medium"
        support = [{"type": "standard", "detail": "Procurement delays are common in enterprise deals."}]
        counter = [{"type": "lever", "detail": "Executive sponsor can sometimes bypass procurement."}]
        impact = {
            "arr_at_stake": arr,
            "delay_weeks": weeks,
        }
        alts = [
            {"action": "Engage procurement early with paperwork", "rationale": "Front-loads the delay."},
            {"action": "Leverage executive sponsor to expedite", "rationale": "Can shorten procurement cycle."},
        ]
        return outcome, conf, support, counter, impact, alts, risk

    def _scenario_legal(self, scenario, customer, drift, arr):
        """What if legal review takes longer?"""
        weeks = int(scenario.get("weeks", 4))
        outcome = "delay"
        conf = 0.6
        risk = "medium"
        support = [{"type": "standard", "detail": "Legal review is a standard enterprise gate."}]
        counter = [{"type": "template", "detail": "If we have a papered template, review is faster."}]
        impact = {
            "arr_at_stake": arr,
            "delay_weeks": weeks,
        }
        alts = [
            {"action": "Pre-negotiate common redlines", "rationale": "Speeds up legal."},
            {"action": "Offer standard terms with minimal deviation", "rationale": "Reduces review scope."},
        ]
        return outcome, conf, support, counter, impact, alts, risk

    # ─── Helpers ───────────────────────────────────────────────────────────

    def _describe(self, stype: str, scenario: dict, customer: str) -> str:
        if stype == "pricing":
            return f"Pricing scenario for {customer}: +{scenario.get('increase_pct', 10)}% increase."
        if stype == "pilot":
            return f"Pilot scenario for {customer}: {scenario.get('days', 90)}-day pilot."
        if stype == "delay":
            return f"Delay scenario for {customer}: +{scenario.get('weeks', 4)} weeks."
        if stype == "champion_leaves":
            return f"Champion departure scenario for {customer}."
        if stype == "security":
            return f"Security concern scenario for {customer}."
        if stype == "procurement":
            return f"Procurement delay scenario for {customer}: +{scenario.get('weeks', 3)} weeks."
        if stype == "legal":
            return f"Legal review scenario for {customer}: +{scenario.get('weeks', 4)} weeks."
        return f"Scenario for {customer}."
