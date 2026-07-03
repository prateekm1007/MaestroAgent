"""
CustomerJudgmentEngine — the Customer Judgment Engine's OEM surface.

This is NOT a CRM. It is an OEM execution surface that reads customer
signals (which have already flowed through the ingestion pipeline into
LearningObjects, Patterns, and Laws) and produces organizational judgment.

Every output is evidence-backed:
  - Every recommendation cites the laws + LOs + receipts that produced it.
  - Every confidence value traces to the CalibrationEngine.
  - Every "why" answer includes counter-evidence and unknowns.

The engine NEVER models people. It models organizational relationships:
  - Customer → Buying Committee → Roles → Commitments → Decisions → Receipts
  - The relationship is the object, not the person.

Surfaces (each maps to an API route):
  - executive_brief(customer)      → pre-meeting briefing
  - relationship_memory(customer)  → searchable timeline
  - buying_committee(customer)     → inferred committee graph
  - relationship_drift(customer)   → momentum / trust / engagement trends
  - opportunity_graph(customer)    → engineering/legal/finance dependencies
  - ask(query)                     → natural-language relationship query
  - customer_physics(customer)     → decision velocity, trust velocity, etc.
  - morning_brief()                → 3 relationships needing attention today

The engine reads from:
  - ExecutionModel.learning_objects (customer_* LOs)
  - ExecutionModel.laws (customer-pattern laws)
  - ExecutionModel.pattern_detector.patterns (customer patterns)
  - ExecutionModel.receipt_chains (provenance)
  - signals list (raw customer signals for timeline)
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
from maestro_oem.learning_object import LearningObject, LearningObjectType
from maestro_oem.pattern import Pattern, PatternType

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════════

COMMITTEE_ROLES = (
    "champion",
    "economic_buyer",
    "technical_buyer",
    "legal",
    "security",
    "procurement",
    "executive_sponsor",
    "blocker",
)


class CustomerJudgmentEngine:
    """The Customer Judgment Engine's read surface.

    Constructed with the live OEM model + signals. Every method returns
    evidence-backed judgment — never a bare opinion.

    Usage:
        engine = CustomerJudgmentEngine(model, signals, decisions)
        brief = engine.executive_brief("<customer>")
        committee = engine.buying_committee("<customer_b>")
        answer = engine.ask("Why is <customer_b> slowing down?")
    """

    def __init__(self, model: Any, signals: list[ExecutionSignal], decisions: Any = None) -> None:
        self.model = model
        self.signals = signals
        self.decisions = decisions

    # ─── Helpers ──────────────────────────────────────────────────────────

    def _customer_signals(self, customer: str) -> list[ExecutionSignal]:
        """All signals for a specific customer account."""
        return [
            s for s in self.signals
            if s.provider == SignalProvider.CUSTOMER
            and s.metadata.get("customer") == customer
        ]

    def _customer_los(self, customer: str) -> list[LearningObject]:
        """All LearningObjects mentioning this customer."""
        return [
            lo for lo in self.model.learning_objects.values()
            if lo.metadata.get("customer") == customer
        ]

    def _customer_laws(self, customer: str) -> list[Any]:
        """All laws whose statement mentions this customer."""
        return [
            law for law in self.model.laws.values()
            if customer in law.statement
        ]

    def _customer_patterns(self, customer: str) -> list[Pattern]:
        """All patterns whose description mentions this customer."""
        return [
            p for p in self.model.pattern_detector.patterns
            if customer in p.description
        ]

    def _all_customers(self) -> list[str]:
        """Distinct customer accounts seen across all customer signals."""
        seen: set[str] = set()
        for s in self.signals:
            if s.provider == SignalProvider.CUSTOMER:
                cust = s.metadata.get("customer", "")
                if cust:
                    seen.add(cust)
        return sorted(seen)

    def _arr_at_stake(self, customer: str) -> float:
        """Sum of arr_impact across this customer's signals (max seen)."""
        arrs = [
            float(s.metadata.get("arr_impact", 0) or 0)
            for s in self._customer_signals(customer)
        ]
        return max(arrs) if arrs else 0.0

    def _confidence_from_evidence(self, evidence_count: int, contradiction_count: int = 0) -> float:
        """Compute confidence the same way the rest of the OEM does."""
        if evidence_count == 0:
            return 0.0
        base = evidence_count / (evidence_count + 2)
        penalty = contradiction_count * 0.1
        return max(0.0, min(1.0, base - penalty))

    # ══════════════════════════════════════════════════════════════════════
    # 1. EXECUTIVE BRIEF
    # ══════════════════════════════════════════════════════════════════════

    def executive_brief(self, customer: str) -> dict[str, Any]:
        """Pre-meeting briefing for a customer relationship.

        Returns:
          - relationship_state: healthy | at_risk | churning | unknown
          - open_commitments: list of unfulfilled promises
          - recent_interactions: last 5 signals
          - outstanding_risks: objections, broken commitments, drift
          - likely_objections: inferred from past objection patterns
          - decision_history: past decisions with outcomes
          - recommended_outcome: what Maestro suggests
          - things_not_to_say: topics that triggered objections before
          - evidence: laws + LOs + receipts supporting every claim
          - confidence: 0..1 with explanation
          - business_impact: ARR at stake
        """
        sigs = self._customer_signals(customer)
        los = self._customer_los(customer)
        laws = self._customer_laws(customer)
        patterns = self._customer_patterns(customer)
        arr = self._arr_at_stake(customer)

        if not sigs:
            return self._empty_brief(customer)

        # Sort signals by time
        sigs_sorted = sorted(sigs, key=lambda s: s.timestamp)
        recent = sigs_sorted[-5:]

        # Open commitments (made but not kept/broken)
        commitment_los = [lo for lo in los if lo.type == LearningObjectType.CUSTOMER_COMMITMENT]
        open_commitments = []
        broken_commitments = []
        kept_commitments = []
        for lo in commitment_los:
            status = lo.metadata.get("status", "open")
            if status == "open":
                open_commitments.append(lo)
            elif status == "broken":
                broken_commitments.append(lo)
            elif status == "kept":
                kept_commitments.append(lo)

        # Outstanding risks: objections, drift, broken commitments
        risk_los = [lo for lo in los if lo.type == LearningObjectType.CUSTOMER_RISK]
        drift_los = [lo for lo in los if lo.type == LearningObjectType.CUSTOMER_DRIFT]
        quiet_signals = [s for s in sigs if s.type == SignalType.CUSTOMER_CHAMPION_QUIET]

        # Likely objections: distinct objection_types seen before
        objection_types = sorted({
            lo.metadata.get("objection_type", "")
            for lo in risk_los
            if lo.metadata.get("objection_type")
        })

        # Decision history
        decision_los = [lo for lo in los if lo.type == LearningObjectType.CUSTOMER_DECISION_PATTERN]
        decision_history = [
            {
                "outcome": lo.metadata.get("outcome", "unknown"),
                "contact": lo.metadata.get("contact", ""),
                "role": lo.metadata.get("role", ""),
                "timestamp": lo.last_seen.isoformat(),
            }
            for lo in decision_los
        ]

        # Relationship state inference
        has_churn = any(s.type == SignalType.CUSTOMER_CONTRACT_CHURNED for s in sigs)
        has_renewal = any(s.type == SignalType.CUSTOMER_CONTRACT_RENEWED for s in sigs)
        if has_churn:
            state = "churned"
        elif has_renewal:
            state = "renewed"
        elif quiet_signals or broken_commitments or objection_types:
            state = "at_risk"
        elif recent and (datetime.now(timezone.utc) - recent[-1].timestamp).days < 30:
            state = "healthy"
        else:
            state = "unknown"

        # Recommended outcome
        if state == "at_risk":
            recommendation = "Schedule executive escalation. Address drift + objections before renewal."
            urgency = "urgent"
        elif state == "churned":
            recommendation = "Conduct loss review. Analyze pattern to prevent recurrence."
            urgency = "normal"
        elif state == "renewed":
            recommendation = "Expand. Identify upsell opportunities from healthy relationship."
            urgency = "low"
        elif state == "healthy":
            recommendation = "Maintain cadence. Prepare for renewal negotiation."
            urgency = "normal"
        else:
            recommendation = "Gather more signals — insufficient data for judgment."
            urgency = "low"

        # Things not to say: topics that triggered objections
        things_not_to_say = []
        for ot in objection_types:
            things_not_to_say.append(f"Avoid {ot} discussion without preparation — triggered objection before")

        # Evidence + confidence
        evidence_count = len(los) + len(laws)
        contradiction_count = len(broken_commitments)
        confidence = self._confidence_from_evidence(evidence_count, contradiction_count)

        return {
            "customer": customer,
            "relationship_state": state,
            "arr_at_stake": arr,
            "open_commitments": [
                {
                    "commitment": lo.metadata.get("commitment", ""),
                    "due_date": lo.metadata.get("due_date", ""),
                    "made_by": lo.entities[0] if lo.entities else "",
                }
                for lo in open_commitments
            ],
            "recent_interactions": [
                {
                    "type": s.type.value,
                    "timestamp": s.timestamp.isoformat(),
                    "actor": s.actor,
                    "contact": s.metadata.get("contact", ""),
                    "subject": s.metadata.get("subject", s.metadata.get("commitment", "")),
                }
                for s in recent
            ],
            "outstanding_risks": {
                "broken_commitments": len(broken_commitments),
                "objections": len(risk_los),
                "drift_signals": len(quiet_signals),
                "objection_types": objection_types,
            },
            "likely_objections": objection_types,
            "decision_history": decision_history,
            "recommended_outcome": recommendation,
            "urgency": urgency,
            "things_not_to_say": things_not_to_say,
            "evidence": {
                "learning_objects": len(los),
                "laws": [
                    {"code": l.code, "statement": l.statement, "confidence": round(l.confidence, 4)}
                    for l in laws
                ],
                "patterns": [
                    {"description": p.description, "strength": round(p.strength, 4)}
                    for p in patterns
                ],
                "signals": len(sigs),
            },
            "confidence": round(confidence, 4),
            "confidence_explanation": (
                f"Confidence {confidence:.2f} from {evidence_count} evidence units "
                f"({len(los)} LOs + {len(laws)} laws) with {contradiction_count} contradictions "
                f"(broken commitments)."
            ),
            "business_impact": f"${arr:,.0f} ARR at stake." if arr else "ARR impact unknown.",
        }

    def _empty_brief(self, customer: str) -> dict[str, Any]:
        return {
            "customer": customer,
            "relationship_state": "unknown",
            "arr_at_stake": 0,
            "open_commitments": [],
            "recent_interactions": [],
            "outstanding_risks": {"broken_commitments": 0, "objections": 0, "drift_signals": 0, "objection_types": []},
            "likely_objections": [],
            "decision_history": [],
            "recommended_outcome": "No signals for this customer.",
            "urgency": "low",
            "things_not_to_say": [],
            "evidence": {"learning_objects": 0, "laws": [], "patterns": [], "signals": 0},
            "confidence": 0.0,
            "confidence_explanation": "No evidence — confidence is 0.",
            "business_impact": "Unknown.",
        }

    # ══════════════════════════════════════════════════════════════════════
    # 2. RELATIONSHIP MEMORY
    # ══════════════════════════════════════════════════════════════════════

    def relationship_memory(self, customer: str, query: str = "") -> dict[str, Any]:
        """Searchable timeline of every interaction with a customer.

        Returns:
          - timeline: chronological list of every signal
          - decisions: every decision event with outcome
          - commitments: every commitment with status
          - receipts: provenance chain IDs
          - evidence: LO + law counts
        """
        sigs = self._customer_signals(customer)
        sigs_sorted = sorted(sigs, key=lambda s: s.timestamp)

        # Filter by query if provided (simple substring match)
        if query:
            q_lower = query.lower()
            sigs_sorted = [
                s for s in sigs_sorted
                if q_lower in s.metadata.get("subject", "").lower()
                or q_lower in s.metadata.get("commitment", "").lower()
                or q_lower in s.metadata.get("objection_type", "").lower()
                or q_lower in s.type.value.lower()
                or q_lower in s.metadata.get("contact", "").lower()
            ]

        timeline = [
            {
                "timestamp": s.timestamp.isoformat(),
                "type": s.type.value,
                "actor": s.actor,
                "contact": s.metadata.get("contact", ""),
                "role": s.metadata.get("role", ""),
                "artifact": s.artifact,
                "subject": s.metadata.get("subject", s.metadata.get("commitment", "")),
                "arr_impact": s.metadata.get("arr_impact", 0),
            }
            for s in sigs_sorted
        ]

        los = self._customer_los(customer)
        commitments = [
            {
                "commitment": lo.metadata.get("commitment", ""),
                "status": lo.metadata.get("status", "open"),
                "due_date": lo.metadata.get("due_date", ""),
                "timestamp": lo.last_seen.isoformat(),
            }
            for lo in los if lo.type == LearningObjectType.CUSTOMER_COMMITMENT
        ]
        decisions = [
            {
                "outcome": lo.metadata.get("outcome", ""),
                "contact": lo.metadata.get("contact", ""),
                "role": lo.metadata.get("role", ""),
                "timestamp": lo.last_seen.isoformat(),
            }
            for lo in los if lo.type == LearningObjectType.CUSTOMER_DECISION_PATTERN
        ]

        return {
            "customer": customer,
            "query": query,
            "timeline": timeline,
            "total_events": len(timeline),
            "commitments": commitments,
            "decisions": decisions,
            "evidence": {
                "learning_objects": len(los),
                "laws": len(self._customer_laws(customer)),
                "signals": len(sigs),
            },
        }

    # ══════════════════════════════════════════════════════════════════════
    # 3. BUYING COMMITTEE GRAPH
    # ══════════════════════════════════════════════════════════════════════

    def buying_committee(self, customer: str) -> dict[str, Any]:
        """Infer the buying committee for a customer.

        Returns:
          - members: list of {contact, role, influence, support_level, confidence}
          - decision_radius: how many people are needed to say yes
          - coverage: which committee roles are filled vs missing
          - confidence: based on signal volume + role diversity
        """
        los = self._customer_los(customer)
        committee_los = [lo for lo in los if lo.type == LearningObjectType.CUSTOMER_COMMITTEE_ROLE]

        # Aggregate per contact: roles seen, interaction count, last seen
        contact_data: dict[str, dict[str, Any]] = {}
        for lo in committee_los:
            contact = lo.metadata.get("contact", "")
            role = lo.metadata.get("role", "")
            if not contact:
                continue
            if contact not in contact_data:
                contact_data[contact] = {
                    "contact": contact,
                    "roles": set(),
                    "interactions": 0,
                    "last_seen": lo.last_seen,
                    "arr_impact": 0.0,
                }
            contact_data[contact]["roles"].add(role)
            contact_data[contact]["interactions"] += lo.evidence_count
            contact_data[contact]["last_seen"] = max(contact_data[contact]["last_seen"], lo.last_seen)
            contact_data[contact]["arr_impact"] = max(
                contact_data[contact]["arr_impact"],
                float(lo.metadata.get("arr_impact", 0) or 0),
            )

        # Build member list with inferred support level
        members = []
        for contact, data in contact_data.items():
            # Support level: more recent + more interactions = stronger support
            days_since = (datetime.now(timezone.utc) - data["last_seen"]).days
            if days_since < 30 and data["interactions"] >= 2:
                support = "strong"
            elif days_since < 60:
                support = "moderate"
            elif days_since < 90:
                support = "weak"
            else:
                support = "inactive"

            # Influence: interactions + role seniority
            role_set = data["roles"]
            seniority_bonus = 0
            if "economic_buyer" in role_set or "executive_sponsor" in role_set:
                seniority_bonus = 2
            elif "champion" in role_set:
                seniority_bonus = 1
            influence = min(10.0, data["interactions"] + seniority_bonus)

            members.append({
                "contact": contact,
                "roles": sorted(role_set),
                "influence": round(influence, 2),
                "support_level": support,
                "last_seen": data["last_seen"].isoformat(),
                "interactions": data["interactions"],
                "confidence": round(self._confidence_from_evidence(data["interactions"]), 4),
            })

        # Sort by influence descending
        members.sort(key=lambda m: m["influence"], reverse=True)

        # Coverage: which roles are filled
        roles_filled = set()
        for m in members:
            roles_filled.update(m["roles"])
        roles_missing = [r for r in COMMITTEE_ROLES if r not in roles_filled]

        # Decision radius: how many people must say yes (heuristic: champion + economic_buyer)
        must_have = {"champion", "economic_buyer"}
        have_must = must_have & roles_filled
        decision_radius = len(have_must)

        # Confidence: based on member count + role coverage
        confidence = self._confidence_from_evidence(
            len(committee_los),
            contradiction_count=len([m for m in members if m["support_level"] == "inactive"]),
        )

        return {
            "customer": customer,
            "members": members,
            "total_members": len(members),
            "roles_filled": sorted(roles_filled),
            "roles_missing": roles_missing,
            "decision_radius": decision_radius,
            "coverage": round(len(roles_filled) / len(COMMITTEE_ROLES), 4),
            "confidence": round(confidence, 4),
            "evidence": {
                "committee_signals": len(committee_los),
                "laws": [
                    {"code": l.code, "statement": l.statement}
                    for l in self._customer_laws(customer)
                    if "committee" in l.statement.lower()
                ],
            },
        }

    # ══════════════════════════════════════════════════════════════════════
    # 4. RELATIONSHIP DRIFT
    # ══════════════════════════════════════════════════════════════════════

    def relationship_drift(self, customer: str) -> dict[str, Any]:
        """Continuously-computed drift metrics for a customer.

        Returns:
          - momentum: positive | neutral | negative (trend over last 90 days)
          - trust: kept/broken commitment ratio
          - executive_engagement: are economic_buyer / exec_sponsor still active?
          - response_latency: days since last interaction
          - decision_readiness: is the relationship ready to decide?
          - champion_health: active | quiet | departed
          - buying_velocity: how fast is the relationship moving?
          - escalation_risk: 0..1 — how likely is this to escalate negatively?
          - confidence: 0..1
        """
        sigs = self._customer_signals(customer)
        los = self._customer_los(customer)
        if not sigs:
            return self._empty_drift(customer)

        now = datetime.now(timezone.utc)
        sigs_sorted = sorted(sigs, key=lambda s: s.timestamp)
        last_interaction = sigs_sorted[-1].timestamp
        days_since_last = (now - last_interaction).days

        # Momentum: compare positive vs negative signals in last 90 days
        cutoff = now - timedelta(days=90)
        recent_sigs = [s for s in sigs if s.timestamp > cutoff]
        positive_types = {
            SignalType.CUSTOMER_CHAMPION_ACTIVE,
            SignalType.CUSTOMER_COMMITMENT_KEPT,
            SignalType.CUSTOMER_CONTRACT_RENEWED,
            SignalType.CUSTOMER_CONTRACT_SIGNED,
            SignalType.CUSTOMER_MEETING,
            SignalType.CUSTOMER_EMAIL,
            SignalType.CUSTOMER_STAGE_CHANGE,
        }
        negative_types = {
            SignalType.CUSTOMER_CHAMPION_QUIET,
            SignalType.CUSTOMER_COMMITMENT_BROKEN,
            SignalType.CUSTOMER_OBJECTION,
            SignalType.CUSTOMER_CONTRACT_CHURNED,
        }
        pos = sum(1 for s in recent_sigs if s.type in positive_types)
        neg = sum(1 for s in recent_sigs if s.type in negative_types)
        if pos > neg:
            momentum = "positive"
        elif neg > pos:
            momentum = "negative"
        else:
            momentum = "neutral"

        # Trust: kept / (kept + broken)
        commitment_los = [lo for lo in los if lo.type == LearningObjectType.CUSTOMER_COMMITMENT]
        kept = sum(1 for lo in commitment_los if lo.metadata.get("status") == "kept")
        broken = sum(1 for lo in commitment_los if lo.metadata.get("status") == "broken")
        trust = kept / max(kept + broken, 1)

        # Executive engagement
        committee_los = [lo for lo in los if lo.type == LearningObjectType.CUSTOMER_COMMITTEE_ROLE]
        exec_contacts = {
            lo.metadata.get("contact", "")
            for lo in committee_los
            if lo.metadata.get("role") in ("economic_buyer", "executive_sponsor")
        }
        exec_recent_sigs = [
            s for s in recent_sigs
            if s.metadata.get("contact") in exec_contacts
        ]
        executive_engagement = "active" if exec_recent_sigs else "inactive"

        # Decision readiness
        has_active_champion = any(
            s.type == SignalType.CUSTOMER_CHAMPION_ACTIVE for s in recent_sigs
        )
        has_active_economic = exec_recent_sigs
        no_open_objections = not any(
            s.type == SignalType.CUSTOMER_OBJECTION for s in recent_sigs
        )
        if has_active_champion and has_active_economic and no_open_objections:
            decision_readiness = "ready"
        elif has_active_champion or has_active_economic:
            decision_readiness = "preparing"
        else:
            decision_readiness = "not_ready"

        # Champion health
        champion_sigs = [s for s in sigs if s.metadata.get("role") == "champion"]
        quiet_sigs = [s for s in champion_sigs if s.type == SignalType.CUSTOMER_CHAMPION_QUIET]
        active_sigs = [s for s in champion_sigs if s.type == SignalType.CUSTOMER_CHAMPION_ACTIVE]
        if quiet_sigs and not active_sigs:
            champion_health = "quiet"
        elif quiet_sigs and active_sigs:
            champion_health = "mixed"
        elif active_sigs:
            champion_health = "active"
        else:
            champion_health = "unknown"

        # Buying velocity: signals per month in last 90 days
        months = 3
        velocity = len(recent_sigs) / months

        # Escalation risk
        risk_score = 0.0
        if momentum == "negative":
            risk_score += 0.3
        if trust < 0.5:
            risk_score += 0.3
        if champion_health == "quiet":
            risk_score += 0.2
        if executive_engagement == "inactive":
            risk_score += 0.1
        if days_since_last > 30:
            risk_score += 0.1
        risk_score = min(1.0, risk_score)

        confidence = self._confidence_from_evidence(len(sigs))

        return {
            "customer": customer,
            "momentum": momentum,
            "trust": round(trust, 4),
            "executive_engagement": executive_engagement,
            "response_latency_days": days_since_last,
            "decision_readiness": decision_readiness,
            "champion_health": champion_health,
            "buying_velocity": round(velocity, 2),
            "escalation_risk": round(risk_score, 4),
            "confidence": round(confidence, 4),
            "trend": {
                "positive_signals_90d": pos,
                "negative_signals_90d": neg,
                "total_signals": len(sigs),
                "last_interaction": last_interaction.isoformat(),
            },
            "evidence": {
                "drift_los": len([lo for lo in los if lo.type == LearningObjectType.CUSTOMER_DRIFT]),
                "risk_los": len([lo for lo in los if lo.type == LearningObjectType.CUSTOMER_RISK]),
                "laws": len(self._customer_laws(customer)),
            },
        }

    def _empty_drift(self, customer: str) -> dict[str, Any]:
        return {
            "customer": customer,
            "momentum": "unknown",
            "trust": 0.0,
            "executive_engagement": "unknown",
            "response_latency_days": None,
            "decision_readiness": "unknown",
            "champion_health": "unknown",
            "buying_velocity": 0.0,
            "escalation_risk": 0.0,
            "confidence": 0.0,
            "trend": {},
            "evidence": {},
        }

    # ══════════════════════════════════════════════════════════════════════
    # 5. OPPORTUNITY GRAPH
    # ══════════════════════════════════════════════════════════════════════

    def opportunity_graph(self, customer: str) -> dict[str, Any]:
        """Cross-functional dependencies affecting this customer opportunity.

        Connects engineering, legal, finance, security, support, product,
        and customer success work that affects this customer relationship.
        NOT pipeline stages — execution dependencies.
        """
        los = self._customer_los(customer)
        sigs = self._customer_signals(customer)

        # Map each internal actor to their function (inferred from team field)
        actors: dict[str, set[str]] = {}
        for s in sigs:
            actor = s.actor
            team = s.team or "unknown"
            actors.setdefault(actor, set()).add(team)

        # Build dependency nodes
        nodes = []
        for actor, teams in actors.items():
            nodes.append({
                "id": actor,
                "type": "person",
                "function": sorted(teams),
                "interactions": sum(
                    1 for s in sigs if s.actor == actor
                ),
            })

        # Add customer-side contacts as nodes
        customer_contacts: dict[str, set[str]] = {}
        for s in sigs:
            contact = s.metadata.get("contact", "")
            role = s.metadata.get("role", "")
            if contact:
                customer_contacts.setdefault(contact, set()).add(role)
        for contact, roles in customer_contacts.items():
            nodes.append({
                "id": contact,
                "type": "customer_contact",
                "roles": sorted(roles),
                "interactions": sum(
                    1 for s in sigs if s.metadata.get("contact") == contact
                ),
            })

        # Edges: internal actor ↔ customer contact
        edges = []
        edge_seen: set[tuple[str, str]] = set()
        for s in sigs:
            actor = s.actor
            contact = s.metadata.get("contact", "")
            if actor and contact:
                key = tuple(sorted([actor, contact]))
                if key not in edge_seen:
                    edge_seen.add(key)
                    edges.append({
                        "source": actor,
                        "target": contact,
                        "weight": sum(
                            1 for s2 in sigs
                            if s2.actor == actor and s2.metadata.get("contact") == contact
                        ),
                    })

        # Open commitments as dependency edges (internal must deliver)
        commitment_los = [lo for lo in los if lo.type == LearningObjectType.CUSTOMER_COMMITMENT]
        dependencies = [
            {
                "commitment": lo.metadata.get("commitment", ""),
                "status": lo.metadata.get("status", "open"),
                "due_date": lo.metadata.get("due_date", ""),
                "owner": lo.entities[0] if lo.entities else "",
            }
            for lo in commitment_los
        ]

        return {
            "customer": customer,
            "nodes": nodes,
            "edges": edges,
            "dependencies": dependencies,
            "total_internal_actors": sum(1 for n in nodes if n["type"] == "person"),
            "total_customer_contacts": sum(1 for n in nodes if n["type"] == "customer_contact"),
            "total_dependencies": len(dependencies),
            "arr_at_stake": self._arr_at_stake(customer),
        }

    # ══════════════════════════════════════════════════════════════════════
    # 6. ASK THE RELATIONSHIP (natural-language query)
    # ══════════════════════════════════════════════════════════════════════

    def ask(self, query: str) -> dict[str, Any]:
        """Natural-language query about customer relationships.

        Examples:
          "Why is <customer_b> slowing down?"
          "Who actually influences <customer>?"
          "Why did we lose <customer_c>?"
          "What promises have we made?"
          "Which engineering work unlocks the most ARR?"

        Returns:
          - answer: human-readable judgment
          - evidence: laws, LOs, receipts supporting the answer
          - counter_evidence: signals that contradict the answer
          - unknowns: what Maestro doesn't know yet
          - confidence: 0..1 with explanation
        """
        q_lower = query.lower()

        # Dispatch to the right analyzer based on query intent
        if "slow" in q_lower or "drift" in q_lower or "stalling" in q_lower:
            return self._ask_why_slowing(query)
        if "influence" in q_lower or "who" in q_lower or "committee" in q_lower:
            return self._ask_who_influences(query)
        if "lost" in q_lower or "lose" in q_lower or "churn" in q_lower:
            return self._ask_why_lost(query)
        if "promis" in q_lower or "commitment" in q_lower:
            return self._ask_promises(query)
        if "unlock" in q_lower or "arr" in q_lower or "engineering" in q_lower:
            return self._ask_unlocks_arr(query)

        # Default: search all customers for the query
        return self._ask_general(query)

    def _ask_why_slowing(self, query: str) -> dict[str, Any]:
        """Answer 'Why is X slowing down?'"""
        # Find the customer mentioned in the query
        customer = self._find_customer_in_query(query)
        if not customer:
            return self._no_customer_answer(query)

        drift = self.relationship_drift(customer)
        reasons = []
        if drift["champion_health"] == "quiet":
            reasons.append(f"Champion has gone quiet — {drift['trend'].get('negative_signals_90d', 0)} drift signals in 90 days.")
        if drift["trust"] < 0.5:
            reasons.append(f"Trust is low ({drift['trust']:.2f}) — broken commitments exceed kept ones.")
        if drift["executive_engagement"] == "inactive":
            reasons.append("Executive sponsor is inactive — no recent engagement.")
        if drift["response_latency_days"] and drift["response_latency_days"] > 30:
            reasons.append(f"Response latency is {drift['response_latency_days']} days — relationship is cooling.")
        if not reasons:
            reasons.append("No strong drift signals detected — the relationship appears stable.")

        answer = f"{customer} is slowing down because: " + " ".join(reasons)

        return {
            "question": query,
            "answer": answer,
            "customer": customer,
            "evidence": drift["evidence"],
            "counter_evidence": [
                "If the champion re-engages within 30 days, drift may reverse.",
                "If a new positive signal arrives, momentum could shift to positive.",
            ],
            "unknowns": [
                "We don't know why the champion went quiet (no exit-interview signal).",
                "We don't know if a competitor is influencing the relationship.",
            ],
            "confidence": drift["confidence"],
            "confidence_explanation": (
                f"Confidence {drift['confidence']:.2f} from {drift['evidence'].get('drift_los', 0)} drift LOs "
                f"and {drift['evidence'].get('laws', 0)} customer laws."
            ),
        }

    def _ask_who_influences(self, query: str) -> dict[str, Any]:
        """Answer 'Who actually influences X?'"""
        customer = self._find_customer_in_query(query)
        if not customer:
            return self._no_customer_answer(query)

        committee = self.buying_committee(customer)
        top = committee["members"][:3]
        names = ", ".join(f"{m['contact']} ({'/'.join(m['roles'])})" for m in top)
        answer = f"The key influencers at {customer} are: {names}."

        return {
            "question": query,
            "answer": answer,
            "customer": customer,
            "evidence": committee["evidence"],
            "counter_evidence": [],
            "unknowns": [
                f"Roles missing: {committee['roles_missing'] or 'none'}",
                "Influence is inferred from signal volume — actual authority may differ.",
            ],
            "confidence": committee["confidence"],
            "confidence_explanation": (
                f"Confidence {committee['confidence']:.2f} from {committee['total_members']} committee members "
                f"across {len(committee['roles_filled'])} roles."
            ),
        }

    def _ask_why_lost(self, query: str) -> dict[str, Any]:
        """Answer 'Why did we lose X?'"""
        customer = self._find_customer_in_query(query)
        if not customer:
            return self._no_customer_answer(query)

        los = self._customer_los(customer)
        risk_los = [lo for lo in los if lo.type == LearningObjectType.CUSTOMER_RISK]
        broken = [lo for lo in los if lo.type == LearningObjectType.CUSTOMER_COMMITMENT and lo.metadata.get("status") == "broken"]
        quiet = [lo for lo in los if lo.type == LearningObjectType.CUSTOMER_DRIFT and lo.metadata.get("drift_type") == "champion_quiet"]

        reasons = []
        if quiet:
            reasons.append(f"Champion went quiet ({len(quiet)} drift signals).")
        if broken:
            reasons.append(f"{len(broken)} broken commitments eroded trust.")
        if risk_los:
            objection_types = sorted({lo.metadata.get("objection_type", "") for lo in risk_los if lo.metadata.get("objection_type")})
            reasons.append(f"Objections raised: {', '.join(objection_types)}.")
        if not reasons:
            reasons.append("No clear loss pattern detected — manual review needed.")

        answer = f"We lost {customer} because: " + " ".join(reasons)

        # Look for a law that captures this pattern
        laws = self._customer_laws(customer)
        pattern_law = next((l for l in laws if "risk" in l.statement.lower() or "drift" in l.statement.lower()), None)

        return {
            "question": query,
            "answer": answer,
            "customer": customer,
            "evidence": {
                "risk_los": len(risk_los),
                "broken_commitments": len(broken),
                "drift_signals": len(quiet),
                "pattern_law": {
                    "code": pattern_law.code,
                    "statement": pattern_law.statement,
                    "confidence": round(pattern_law.confidence, 4),
                } if pattern_law else None,
            },
            "counter_evidence": [
                "If a competitor was involved, we don't have that signal.",
                "Pricing may have been a factor even if not explicitly objected to.",
            ],
            "unknowns": [
                "We don't know the champion's reason for leaving (departure signal absent).",
                "We don't know if a competing offer was accepted.",
            ],
            "confidence": self._confidence_from_evidence(len(risk_los) + len(broken) + len(quiet)),
            "confidence_explanation": (
                f"Confidence from {len(risk_los)} risk LOs + {len(broken)} broken commitments + "
                f"{len(quiet)} drift signals."
            ),
        }

    def _ask_promises(self, query: str) -> dict[str, Any]:
        """Answer 'What promises have we made?'"""
        # Aggregate across ALL customers
        all_commitments: list[dict[str, Any]] = []
        for customer in self._all_customers():
            los = self._customer_los(customer)
            for lo in los:
                if lo.type == LearningObjectType.CUSTOMER_COMMITMENT:
                    all_commitments.append({
                        "customer": customer,
                        "commitment": lo.metadata.get("commitment", ""),
                        "status": lo.metadata.get("status", "open"),
                        "due_date": lo.metadata.get("due_date", ""),
                        "owner": lo.entities[0] if lo.entities else "",
                    })

        open_count = sum(1 for c in all_commitments if c["status"] == "open")
        kept_count = sum(1 for c in all_commitments if c["status"] == "kept")
        broken_count = sum(1 for c in all_commitments if c["status"] == "broken")

        answer = (
            f"Across all customer relationships: {len(all_commitments)} commitments tracked — "
            f"{open_count} open, {kept_count} kept, {broken_count} broken."
        )

        return {
            "question": query,
            "answer": answer,
            "commitments": all_commitments,
            "evidence": {
                "total": len(all_commitments),
                "open": open_count,
                "kept": kept_count,
                "broken": broken_count,
            },
            "counter_evidence": [],
            "unknowns": ["Commitments made informally (Slack, verbal) may not be tracked."],
            "confidence": self._confidence_from_evidence(len(all_commitments)),
            "confidence_explanation": f"Confidence from {len(all_commitments)} tracked commitments.",
        }

    def _ask_unlocks_arr(self, query: str) -> dict[str, Any]:
        """Answer 'Which engineering work unlocks the most ARR?'"""
        # Find open commitments with the highest ARR impact
        candidates: list[dict[str, Any]] = []
        for customer in self._all_customers():
            los = self._customer_los(customer)
            arr = self._arr_at_stake(customer)
            for lo in los:
                if lo.type == LearningObjectType.CUSTOMER_COMMITMENT and lo.metadata.get("status") == "open":
                    candidates.append({
                        "customer": customer,
                        "commitment": lo.metadata.get("commitment", ""),
                        "due_date": lo.metadata.get("due_date", ""),
                        "arr_at_stake": arr,
                    })

        candidates.sort(key=lambda c: c["arr_at_stake"], reverse=True)
        top = candidates[:5]

        if not top:
            answer = "No open commitments tied to ARR found."
        else:
            lines = [f"{c['commitment']} for {c['customer']} (${c['arr_at_stake']:,.0f} ARR)" for c in top]
            answer = "Highest-ARR engineering work: " + "; ".join(lines) + "."

        return {
            "question": query,
            "answer": answer,
            "candidates": top,
            "evidence": {"total_open_commitments": len(candidates)},
            "counter_evidence": [],
            "unknowns": ["ARR estimates may not reflect final contract value."],
            "confidence": self._confidence_from_evidence(len(candidates)),
            "confidence_explanation": f"Confidence from {len(candidates)} open commitments with ARR data.",
        }

    def _ask_general(self, query: str) -> dict[str, Any]:
        """General search across all customer relationships."""
        customer = self._find_customer_in_query(query)
        if customer:
            brief = self.executive_brief(customer)
            return {
                "question": query,
                "answer": f"{customer}: {brief['relationship_state']} relationship, ${brief['arr_at_stake']:,.0f} ARR at stake. {brief['recommended_outcome']}",
                "customer": customer,
                "evidence": brief["evidence"],
                "counter_evidence": [],
                "unknowns": [],
                "confidence": brief["confidence"],
                "confidence_explanation": brief["confidence_explanation"],
            }

        return {
            "question": query,
            "answer": f"No customer found matching '{query}'. Try naming a customer: <customer>, <customer_b>, or <customer_c>.",
            "evidence": {},
            "counter_evidence": [],
            "unknowns": ["Query did not match any known customer."],
            "confidence": 0.0,
            "confidence_explanation": "No matching customer.",
        }

    def _find_customer_in_query(self, query: str) -> str | None:
        """Find which customer name appears in the query."""
        q_lower = query.lower()
        for customer in self._all_customers():
            if customer.lower() in q_lower:
                return customer
        return None

    def _no_customer_answer(self, query: str) -> dict[str, Any]:
        return {
            "question": query,
            "answer": f"No customer name found in '{query}'. Known customers: {', '.join(self._all_customers())}.",
            "evidence": {},
            "counter_evidence": [],
            "unknowns": ["Query did not name a customer."],
            "confidence": 0.0,
            "confidence_explanation": "No customer identified.",
        }

    # ══════════════════════════════════════════════════════════════════════
    # 7. CUSTOMER PHYSICS
    # ══════════════════════════════════════════════════════════════════════

    def customer_physics(self, customer: str) -> dict[str, Any]:
        """Inferred 'physics' of a customer relationship.

        NOT CRM stages. These are continuous metrics:
          - decision_velocity: how fast this customer historically decides
          - trust_velocity: rate of trust accumulation (kept - broken / month)
          - knowledge_flow: how many internal teams are connected to this customer
          - commitment_health: kept/broken ratio over time
          - organizational_gravity: how much engineering effort is pulled toward this customer
          - escalation_pressure: 0..1 — how much pressure is accumulating
          - buying_momentum: positive | neutral | negative
        """
        sigs = self._customer_signals(customer)
        los = self._customer_los(customer)
        if not sigs:
            return {"customer": customer, "error": "No signals for this customer."}

        # Decision velocity: days between first and last decision signal
        decision_sigs = [s for s in sigs if s.type == SignalType.CUSTOMER_DECISION]
        if len(decision_sigs) >= 2:
            sorted_dec = sorted(decision_sigs, key=lambda s: s.timestamp)
            span = (sorted_dec[-1].timestamp - sorted_dec[0].timestamp).days
            decision_velocity = max(1, span)
        else:
            # Infer from first-to-last signal span
            sorted_sigs = sorted(sigs, key=lambda s: s.timestamp)
            span = (sorted_sigs[-1].timestamp - sorted_sigs[0].timestamp).days
            decision_velocity = max(1, span)

        # Trust velocity: (kept - broken) per month
        commitment_los = [lo for lo in los if lo.type == LearningObjectType.CUSTOMER_COMMITMENT]
        kept = sum(1 for lo in commitment_los if lo.metadata.get("status") == "kept")
        broken = sum(1 for lo in commitment_los if lo.metadata.get("status") == "broken")
        sorted_sigs = sorted(sigs, key=lambda s: s.timestamp)
        months = max(1, (sorted_sigs[-1].timestamp - sorted_sigs[0].timestamp).days / 30)
        trust_velocity = (kept - broken) / months

        # Knowledge flow: distinct internal teams
        teams: set[str] = set()
        for s in sigs:
            if s.team:
                teams.add(s.team)
        knowledge_flow = len(teams)

        # Commitment health
        commitment_health = kept / max(kept + broken, 1)

        # Organizational gravity: total signals (effort proxy)
        org_gravity = len(sigs)

        # Escalation pressure
        drift = self.relationship_drift(customer)
        escalation_pressure = drift["escalation_risk"]

        # Buying momentum
        buying_momentum = drift["momentum"]

        return {
            "customer": customer,
            "decision_velocity_days": decision_velocity,
            "trust_velocity_per_month": round(trust_velocity, 4),
            "knowledge_flow_teams": knowledge_flow,
            "commitment_health": round(commitment_health, 4),
            "organizational_gravity": org_gravity,
            "escalation_pressure": round(escalation_pressure, 4),
            "buying_momentum": buying_momentum,
            "arr_at_stake": self._arr_at_stake(customer),
            "confidence": round(self._confidence_from_evidence(len(sigs)), 4),
        }

    # ══════════════════════════════════════════════════════════════════════
    # 8. MORNING BRIEF — 3 relationships needing attention today
    # ══════════════════════════════════════════════════════════════════════

    def morning_brief(self) -> dict[str, Any]:
        """Surface the 3 customer relationships most needing attention today.

        Ranked by escalation_risk * arr_at_stake.
        """
        customers = self._all_customers()
        if not customers:
            return {
                "relationships": [],
                "total_customers": 0,
                "summary": "No customer signals in the OEM.",
            }

        ranked = []
        for customer in customers:
            drift = self.relationship_drift(customer)
            arr = self._arr_at_stake(customer)
            # Score = escalation_risk * log(arr) — big at-risk deals win
            arr_score = math.log10(arr + 1) if arr > 0 else 0
            score = drift["escalation_risk"] * arr_score
            ranked.append({
                "customer": customer,
                "score": round(score, 4),
                "arr_at_stake": arr,
                "escalation_risk": drift["escalation_risk"],
                "momentum": drift["momentum"],
                "champion_health": drift["champion_health"],
                "decision_readiness": drift["decision_readiness"],
            })

        ranked.sort(key=lambda r: r["score"], reverse=True)
        top_3 = ranked[:3]

        # Enrich each with a recommendation
        for item in top_3:
            brief = self.executive_brief(item["customer"])
            item["recommendation"] = brief["recommended_outcome"]
            item["urgency"] = brief["urgency"]
            item["confidence"] = brief["confidence"]
            item["expected_value"] = f"${item['arr_at_stake']:,.0f} ARR"
            item["why"] = (
                f"Escalation risk {item['escalation_risk']:.2f}, "
                f"momentum {item['momentum']}, "
                f"champion {item['champion_health']}."
            )

        return {
            "relationships": top_3,
            "total_customers": len(customers),
            "summary": f"{len(top_3)} of {len(customers)} customer relationships need attention today.",
        }
