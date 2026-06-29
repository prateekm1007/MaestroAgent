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

        return [p for p in self.patterns if p.is_law_candidate]

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
        """Detect undocumented experts."""
        patterns: list[Pattern] = []
        for lo in los:
            if lo.type.value == "hidden_expert" and lo.evidence_count >= 3:
                expert = lo.entities[0] if lo.entities else "unknown"
                patterns.append(Pattern(
                    type=PatternType.INFLUENCE,
                    description=f"{expert} is an undocumented expert — touches {lo.metadata.get('touch_rate', 'high')}% of successful outcomes",
                    learning_object_ids=[lo.lo_id],
                    providers=lo.providers,
                    coverage=len(lo.entities),
                    metadata={"expert": expert},
                ))
        return patterns

    def _detect_bottlenecks(self, los: list) -> list[Pattern]:
        """Detect process bottlenecks."""
        patterns: list[Pattern] = []
        for lo in los:
            if lo.type.value == "bottleneck" and lo.evidence_count >= 2:
                gate = lo.entities[0] if lo.entities else "unknown"
                patterns.append(Pattern(
                    type=PatternType.CAUSAL,
                    description=f"{gate} is a bottleneck — {lo.metadata.get('delay_days', 0)} day median delay across {lo.evidence_count} projects",
                    learning_object_ids=[lo.lo_id],
                    providers=lo.providers,
                    coverage=len(lo.entities),
                    metadata={"gate": gate},
                ))
        return patterns

    def _detect_velocity_patterns(self, los: list) -> list[Pattern]:
        """Detect velocity drops after incidents."""
        patterns: list[Pattern] = []
        for lo in los:
            if lo.type.value == "velocity_drop" and lo.evidence_count >= 3:
                patterns.append(Pattern(
                    type=PatternType.VELOCITY,
                    description=f"Velocity drops {lo.metadata.get('drop_pct', 0)}% after {lo.metadata.get('incident_threshold', 3)}+ P1 incidents",
                    learning_object_ids=[lo.lo_id],
                    providers=lo.providers,
                    coverage=len(lo.entities),
                    metadata={"drop_pct": lo.metadata.get("drop_pct", 0)},
                ))
        return patterns

    def _detect_knowledge_death(self, los: list) -> list[Pattern]:
        """Detect knowledge that doesn't transfer."""
        patterns: list[Pattern] = []
        for lo in los:
            if lo.type.value == "knowledge_death" and lo.evidence_count >= 2:
                boundary = lo.metadata.get("boundary", "unknown")
                patterns.append(Pattern(
                    type=PatternType.KNOWLEDGE,
                    description=f"Knowledge dies at {boundary} boundary — {lo.metadata.get('rework_rate', 0)}% rework rate",
                    learning_object_ids=[lo.lo_id],
                    providers=lo.providers,
                    coverage=len(lo.entities),
                    metadata={"boundary": boundary},
                ))
        return patterns

    def _detect_approval_gates(self, los: list) -> list[Pattern]:
        """Detect approval gate patterns."""
        patterns: list[Pattern] = []
        for lo in los:
            if lo.type.value == "approval_gate" and lo.evidence_count >= 3:
                gate = lo.entities[0] if lo.entities else "unknown"
                patterns.append(Pattern(
                    type=PatternType.APPROVAL,
                    description=f"{gate} gates {lo.metadata.get('gate_pct', 0)}% of projects — entering late causes {lo.metadata.get('delay_multiplier', 0)}× delay",
                    learning_object_ids=[lo.lo_id],
                    providers=lo.providers,
                    coverage=len(lo.entities),
                    metadata={"gate": gate},
                ))
        return patterns
