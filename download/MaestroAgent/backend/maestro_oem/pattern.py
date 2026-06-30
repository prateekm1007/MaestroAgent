"""
Pattern — a regularity detected across multiple LearningObjects.

Patterns are the intermediate step between raw evidence (LearningObjects)
and organizational laws.

A Pattern says: "We've seen this N times across M teams."
A Law says: "This pattern predicts outcome X with confidence Y."
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class PatternType(str, Enum):
    STRUCTURAL = "structural"  # Duplicate work, parallel implementations
    CAUSAL = "causal"  # X causes Y (e.g., Legal late → ship delay)
    INFLUENCE = "influence"  # Person X influences outcome Y
    TEMPORAL = "temporal"  # Time-based regularity (Friday merges, hiring bursts)
    VELOCITY = "velocity"  # Throughput patterns (P1 → velocity drop)
    KNOWLEDGE = "knowledge"  # Knowledge distribution patterns
    APPROVAL = "approval"  # Approval gate patterns
    CUSTOMER = "customer"  # Customer relationship patterns (drift, committee, commitment health)


class Pattern(BaseModel):
    """
    A detected pattern across multiple LearningObjects.

    strength: fraction of evidence that supports this pattern (0..1)
    coverage: how many distinct entities/teams it spans
    """

    pattern_id: UUID = Field(default_factory=uuid4)
    type: PatternType
    description: str
    learning_object_ids: list[UUID] = Field(default_factory=list)
    strength: float = 0.0  # Computed from evidence
    coverage: int = 0  # Number of distinct teams/entities
    providers: set[str] = Field(default_factory=set)
    first_detected: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_detected: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_learning_object(self, lo_id: UUID, provider: str) -> None:
        if lo_id not in self.learning_object_ids:
            self.learning_object_ids.append(lo_id)
            self.providers.add(provider)
            self.last_detected = datetime.now(timezone.utc)

    @property
    def evidence_count(self) -> int:
        return len(self.learning_object_ids)

    @property
    def is_law_candidate(self) -> bool:
        """A pattern becomes a law candidate when it has enough evidence."""
        return self.evidence_count >= 3 and self.coverage >= 2

    @property
    def is_law_candidate_relaxed(self) -> bool:
        """Relaxed threshold — evidence >= 3 and coverage >= 1 (single-entity patterns)."""
        return self.evidence_count >= 3


class PatternDetector:
    """
    Detects patterns from LearningObjects.

    This is the inference layer — it looks at accumulated evidence and
    identifies regularities. Each detector is specific to a pattern type.
    """

    def __init__(self) -> None:
        self.patterns: list[Pattern] = []

    def detect(
        self,
        learning_objects: list,  # list[LearningObject] — avoid circular import
    ) -> list[Pattern]:
        """Run all detectors and return new/updated patterns."""
        new_patterns: list[Pattern] = []

        # Structural: duplicate work
        new_patterns.extend(self._detect_duplicate_work(learning_objects))

        # Influence: hidden experts
        new_patterns.extend(self._detect_hidden_experts(learning_objects))

        # Causal: bottlenecks and delays
        new_patterns.extend(self._detect_bottlenecks(learning_objects))

        # Temporal: velocity drops after incidents
        new_patterns.extend(self._detect_velocity_patterns(learning_objects))

        # Knowledge: knowledge death at boundaries
        new_patterns.extend(self._detect_knowledge_death(learning_objects))

        # Approval: gate patterns
        new_patterns.extend(self._detect_approval_gates(learning_objects))

        # Customer: relationship drift, committee formation, commitment health
        new_patterns.extend(self._detect_customer_drift(learning_objects))
        new_patterns.extend(self._detect_customer_committee(learning_objects))
        new_patterns.extend(self._detect_customer_commitment_health(learning_objects))
        new_patterns.extend(self._detect_customer_objection_clusters(learning_objects))

        # Merge with existing patterns
        for new_p in new_patterns:
            existing = self._find_matching(new_p)
            if existing:
                existing.add_learning_object(
                    new_p.learning_object_ids[0], list(new_p.providers)[0]
                )
                existing.strength = self._compute_strength(existing)
                existing.coverage = self._compute_coverage(existing, learning_objects)
            else:
                new_p.strength = self._compute_strength(new_p)
                new_p.coverage = self._compute_coverage(new_p, learning_objects)
                self.patterns.append(new_p)

        return [p for p in self.patterns if p.is_law_candidate or p.is_law_candidate_relaxed]

    def _find_matching(self, pattern: Pattern) -> Pattern | None:
        for p in self.patterns:
            if p.type == pattern.type and p.description == pattern.description:
                return p
        return None

    def _compute_strength(self, pattern: Pattern) -> float:
        """Strength = evidence_count / (evidence_count + contradiction_penalty)."""
        base = pattern.evidence_count
        if base == 0:
            return 0.0
        return min(1.0, base / (base + 2))

    def _compute_coverage(
        self, pattern: Pattern, learning_objects: list
    ) -> int:
        """Count distinct teams/entities across the pattern's LOs."""
        entities: set[str] = set()
        lo_map = {lo.lo_id: lo for lo in learning_objects}
        for lo_id in pattern.learning_object_ids:
            lo = lo_map.get(lo_id)
            if lo:
                entities.update(lo.entities)
        return len(entities)

    def _detect_duplicate_work(self, los: list) -> list[Pattern]:
        """Detect same artifact built by different teams."""
        patterns: list[Pattern] = []
        duplicates: dict[str, list] = {}
        for lo in los:
            if lo.type.value == "duplicate_work":
                key = lo.metadata.get("domain", "unknown")
                duplicates.setdefault(key, []).append(lo)
        for domain, group in duplicates.items():
            if len(group) >= 2:
                teams = set()
                providers: set[str] = set()
                lo_ids: list[UUID] = []
                for lo in group:
                    teams.update(lo.entities)
                    providers.update(lo.providers)
                    lo_ids.append(lo.lo_id)
                patterns.append(Pattern(
                    type=PatternType.STRUCTURAL,
                    description=f"Duplicate work detected in {domain} — {len(group)} independent implementations across {len(teams)} teams",
                    learning_object_ids=lo_ids,
                    providers=providers,
                    coverage=len(teams),
                    metadata={"domain": domain, "implementations": len(group)},
                ))
        return patterns

    def _detect_hidden_experts(self, los: list) -> list[Pattern]:
        """Detect undocumented experts — aggregates evidence across LOs for the same entity."""
        patterns: list[Pattern] = []
        # Group hidden_expert LOs by entity
        by_entity: dict[str, list] = {}
        for lo in los:
            if lo.type.value == "hidden_expert":
                for entity in lo.entities:
                    by_entity.setdefault(entity, []).append(lo)

        for entity, entity_los in by_entity.items():
            total_evidence = sum(lo.evidence_count for lo in entity_los)
            if total_evidence >= 3:
                all_providers: set[str] = set()
                lo_ids: list = []
                for lo in entity_los:
                    all_providers.update(lo.providers)
                    lo_ids.append(lo.lo_id)
                patterns.append(Pattern(
                    type=PatternType.INFLUENCE,
                    description=f"{entity} is an undocumented expert — {total_evidence} evidence signals across {len(entity_los)} observations",
                    learning_object_ids=lo_ids,
                    providers=all_providers,
                    coverage=len(entity_los),
                    metadata={"expert": entity, "total_evidence": total_evidence},
                ))
        return patterns

    def _detect_bottlenecks(self, los: list) -> list[Pattern]:
        """Detect process bottlenecks — aggregates evidence across LOs for the same gate."""
        patterns: list[Pattern] = []
        # Group bottleneck LOs by gate entity
        by_gate: dict[str, list] = {}
        for lo in los:
            if lo.type.value == "bottleneck":
                for entity in lo.entities:
                    by_gate.setdefault(entity, []).append(lo)

        for gate, gate_los in by_gate.items():
            total_evidence = sum(lo.evidence_count for lo in gate_los)
            if total_evidence >= 2:
                all_providers: set[str] = set()
                lo_ids: list = []
                for lo in gate_los:
                    all_providers.update(lo.providers)
                    lo_ids.append(lo.lo_id)
                patterns.append(Pattern(
                    type=PatternType.CAUSAL,
                    description=f"{gate} is a bottleneck — {total_evidence} evidence signals across {len(gate_los)} observations",
                    learning_object_ids=lo_ids,
                    providers=all_providers,
                    coverage=len(gate_los),
                    metadata={"gate": gate, "total_evidence": total_evidence},
                ))
        return patterns

    def _detect_velocity_patterns(self, los: list) -> list[Pattern]:
        """Detect velocity drops after incidents — aggregates across LOs."""
        patterns: list[Pattern] = []
        by_type: dict[str, list] = {}
        for lo in los:
            if lo.type.value == "velocity_drop":
                by_type.setdefault("velocity", []).append(lo)

        for key, group_los in by_type.items():
            total_evidence = sum(lo.evidence_count for lo in group_los)
            if total_evidence >= 3:
                all_providers: set[str] = set()
                lo_ids: list = []
                for lo in group_los:
                    all_providers.update(lo.providers)
                    lo_ids.append(lo.lo_id)
                patterns.append(Pattern(
                    type=PatternType.VELOCITY,
                    description=f"Velocity drop pattern — {total_evidence} evidence signals across {len(group_los)} observations",
                    learning_object_ids=lo_ids,
                    providers=all_providers,
                    coverage=len(group_los),
                    metadata={"total_evidence": total_evidence},
                ))
        return patterns

    def _detect_knowledge_death(self, los: list) -> list[Pattern]:
        """Detect knowledge that doesn't transfer — aggregates across LOs."""
        patterns: list[Pattern] = []
        by_boundary: dict[str, list] = {}
        for lo in los:
            if lo.type.value == "knowledge_death":
                boundary = lo.metadata.get("boundary", "unknown")
                by_boundary.setdefault(boundary, []).append(lo)

        for boundary, group_los in by_boundary.items():
            total_evidence = sum(lo.evidence_count for lo in group_los)
            if total_evidence >= 2:
                all_providers: set[str] = set()
                lo_ids: list = []
                for lo in group_los:
                    all_providers.update(lo.providers)
                    lo_ids.append(lo.lo_id)
                patterns.append(Pattern(
                    type=PatternType.KNOWLEDGE,
                    description=f"Knowledge death at {boundary} — {total_evidence} evidence signals across {len(group_los)} observations",
                    learning_object_ids=lo_ids,
                    providers=all_providers,
                    coverage=len(group_los),
                    metadata={"boundary": boundary, "total_evidence": total_evidence},
                ))
        return patterns

    def _detect_approval_gates(self, los: list) -> list[Pattern]:
        """Detect approval gate patterns — aggregates across LOs."""
        patterns: list[Pattern] = []
        by_gate: dict[str, list] = {}
        for lo in los:
            if lo.type.value == "approval_gate":
                gate = lo.entities[0] if lo.entities else "unknown"
                by_gate.setdefault(gate, []).append(lo)

        for gate, gate_los in by_gate.items():
            total_evidence = sum(lo.evidence_count for lo in gate_los)
            if total_evidence >= 3:
                all_providers: set[str] = set()
                lo_ids: list = []
                for lo in gate_los:
                    all_providers.update(lo.providers)
                    lo_ids.append(lo.lo_id)
                patterns.append(Pattern(
                    type=PatternType.APPROVAL,
                    description=f"{gate} gates {total_evidence} items across {len(gate_los)} observations",
                    learning_object_ids=lo_ids,
                    providers=all_providers,
                    coverage=len(gate_los),
                    metadata={"gate": gate, "total_evidence": total_evidence},
                ))
        return patterns

    # ─── Customer relationship patterns ──────────────────────────────────

    def _detect_customer_drift(self, los: list) -> list[Pattern]:
        """Detect relationship drift — aggregates CUSTOMER_DRIFT LOs per customer.

        A pattern is promoted when a customer accumulates >= 2 drift signals
        (champion quiet, engagement waning). This becomes a law candidate
        like "Globex champion engagement is decaying — predict renewal risk."
        """
        patterns: list[Pattern] = []
        by_customer: dict[str, list] = {}
        for lo in los:
            if lo.type.value == "customer_drift":
                customer = lo.metadata.get("customer", "unknown")
                by_customer.setdefault(customer, []).append(lo)

        for customer, cust_los in by_customer.items():
            total_evidence = sum(lo.evidence_count for lo in cust_los)
            if total_evidence >= 2:
                all_providers: set[str] = set()
                lo_ids: list = []
                arr = 0.0
                for lo in cust_los:
                    all_providers.update(lo.providers)
                    lo_ids.append(lo.lo_id)
                    arr += float(lo.metadata.get("arr_impact", 0) or 0)
                patterns.append(Pattern(
                    type=PatternType.CUSTOMER,
                    description=f"{customer} relationship drifting — {total_evidence} drift signals across {len(cust_los)} observations",
                    learning_object_ids=lo_ids,
                    providers=all_providers,
                    coverage=len(cust_los),
                    metadata={
                        "customer": customer,
                        "total_evidence": total_evidence,
                        "arr_at_stake": arr,
                        "drift_type": "relationship_decay",
                    },
                ))
        return patterns

    def _detect_customer_committee(self, los: list) -> list[Pattern]:
        """Detect buying-committee formation — aggregates COMMITTEE_ROLE LOs.

        A pattern is promoted when a customer has >= 3 distinct role signals,
        indicating the buying committee is taking shape. The law candidate
        becomes "Globex buying committee: champion=Raj, economic_buyer=Sam..."
        """
        patterns: list[Pattern] = []
        by_customer: dict[str, list] = {}
        for lo in los:
            if lo.type.value == "customer_committee_role":
                customer = lo.metadata.get("customer", "unknown")
                by_customer.setdefault(customer, []).append(lo)

        for customer, cust_los in by_customer.items():
            total_evidence = sum(lo.evidence_count for lo in cust_los)
            if total_evidence >= 3:
                all_providers: set[str] = set()
                lo_ids: list = []
                roles_seen: dict[str, str] = {}
                for lo in cust_los:
                    all_providers.update(lo.providers)
                    lo_ids.append(lo.lo_id)
                    role = lo.metadata.get("role", "")
                    contact = lo.metadata.get("contact", "")
                    if role and contact:
                        roles_seen[role] = contact
                patterns.append(Pattern(
                    type=PatternType.CUSTOMER,
                    description=f"{customer} buying committee active — {len(roles_seen)} roles identified across {total_evidence} signals",
                    learning_object_ids=lo_ids,
                    providers=all_providers,
                    coverage=len(roles_seen),
                    metadata={
                        "customer": customer,
                        "roles": roles_seen,
                        "total_evidence": total_evidence,
                    },
                ))
        return patterns

    def _detect_customer_commitment_health(self, los: list) -> list[Pattern]:
        """Detect commitment-health patterns per customer.

        When a customer accumulates >= 2 commitment LOs, we promote a pattern
        showing the kept/broken ratio. A high broken ratio becomes a law
        candidate like "Acme has a pattern of broken commitments — trust
        deficit predicts renewal failure."
        """
        patterns: list[Pattern] = []
        by_customer: dict[str, list] = {}
        for lo in los:
            if lo.type.value == "customer_commitment":
                customer = lo.metadata.get("customer", "unknown")
                by_customer.setdefault(customer, []).append(lo)

        for customer, cust_los in by_customer.items():
            total_evidence = sum(lo.evidence_count for lo in cust_los)
            if total_evidence >= 2:
                all_providers: set[str] = set()
                lo_ids: list = []
                kept = 0
                broken = 0
                open_count = 0
                for lo in cust_los:
                    all_providers.update(lo.providers)
                    lo_ids.append(lo.lo_id)
                    status = lo.metadata.get("status", "open")
                    if status == "kept":
                        kept += 1
                    elif status == "broken":
                        broken += 1
                    else:
                        open_count += 1
                health_ratio = kept / max(kept + broken, 1)
                patterns.append(Pattern(
                    type=PatternType.CUSTOMER,
                    description=f"{customer} commitment health — {kept} kept, {broken} broken, {open_count} open across {total_evidence} signals",
                    learning_object_ids=lo_ids,
                    providers=all_providers,
                    coverage=len(cust_los),
                    metadata={
                        "customer": customer,
                        "kept": kept,
                        "broken": broken,
                        "open": open_count,
                        "health_ratio": round(health_ratio, 3),
                    },
                ))
        return patterns

    def _detect_customer_objection_clusters(self, los: list) -> list[Pattern]:
        """Detect clusters of objections on the same customer.

        When a customer accumulates >= 2 objection LOs, we promote a pattern.
        The law candidate becomes "Globex objects to security concerns —
        repeated pattern indicates unresolved review-blocker."
        """
        patterns: list[Pattern] = []
        by_customer: dict[str, list] = {}
        for lo in los:
            if lo.type.value == "customer_risk":
                customer = lo.metadata.get("customer", "unknown")
                by_customer.setdefault(customer, []).append(lo)

        for customer, cust_los in by_customer.items():
            total_evidence = sum(lo.evidence_count for lo in cust_los)
            if total_evidence >= 2:
                all_providers: set[str] = set()
                lo_ids: list = []
                arr = 0.0
                objection_types: list[str] = []
                for lo in cust_los:
                    all_providers.update(lo.providers)
                    lo_ids.append(lo.lo_id)
                    arr += float(lo.metadata.get("arr_impact", 0) or 0)
                    ot = lo.metadata.get("objection_type", "")
                    if ot:
                        objection_types.append(ot)
                patterns.append(Pattern(
                    type=PatternType.CUSTOMER,
                    description=f"{customer} risk cluster — {total_evidence} risk signals across {len(cust_los)} observations",
                    learning_object_ids=lo_ids,
                    providers=all_providers,
                    coverage=len(cust_los),
                    metadata={
                        "customer": customer,
                        "total_evidence": total_evidence,
                        "arr_at_stake": arr,
                        "objection_types": objection_types,
                    },
                ))
        return patterns
