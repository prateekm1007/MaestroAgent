"""TSS Theory v1 — Temporal Scale Separation.

Immutable theory snapshot. Future revisions will be theory_v2.py, etc.

Maturity: Supported
  - ≥2 successful novel predictions (P2, P3 confirmed)
  - Pre-registered
  - Survived ≥1 stress test (shared-target, v3.4)
  - Out-of-sample: 70% (v3.6 held-out corpus)

Evidence chain:
  P2 (OOD) → v3.3 pre-registered experiment → 3 seeds → delta=0.0 → CONFIRMED
  P3 (cold-start) → v3.3 pre-registered experiment → 3 seeds → delta=0.0 → CONFIRMED
  SAT alternative → v3.4 stress test → rejected (same-scale-diff-target interferes)
  Held-out corpus → v3.6 → 7/10 (70%) → partially confirmed (construct issue identified)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvidenceLevel:
    """Hierarchy of evidence strength."""
    level: str  # "prediction" | "experiment" | "replication" | "stress_test" | "held_out" | "external"
    description: str
    experiment_id: str = ""
    result: str = ""


@dataclass
class VersionedPrediction:
    id: str
    statement: str
    derivation: str
    falsification_criterion: str
    status: str = "untested"  # untested → confirmed → falsified → partially_confirmed
    evidence: list[EvidenceLevel] = field(default_factory=list)


@dataclass
class VersionedTheory:
    name: str
    version: str  # "v1"
    formal_statement: str
    intuition: str
    predictions: list[VersionedPrediction]
    alternative_explanations: list[dict[str, str]]
    maturity: str  # "Proposed" | "Predictive" | "Supported" | "Robust" | "General"
    evidence_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "version": self.version,
            "formal_statement": self.formal_statement, "intuition": self.intuition,
            "predictions": [{"id": p.id, "statement": p.statement, "status": p.status,
                             "evidence": [{"level": e.level, "result": e.result} for e in p.evidence]}
                            for p in self.predictions],
            "alternative_explanations": self.alternative_explanations,
            "maturity": self.maturity, "evidence_summary": self.evidence_summary,
        }


# ---------------------------------------------------------------------------
# Adaptive State System (ASS) construct.
# ---------------------------------------------------------------------------

@dataclass
class AdaptiveStateSystem:
    """A subsystem that (1) stores persistent parameters, (2) updates them
    from outcomes, (3) uses them in future decisions.

    ASS membership is OPERATIONAL — a subsystem that satisfies the definition
    but doesn't measurably change decisions (AIC=0) may not function as an
    ASS in a given implementation.
    """
    name: str
    stores_persistent_parameters: bool
    updates_parameters_from_outcomes: bool
    parameters_influence_future_decisions: bool

    @property
    def is_ass(self) -> bool:
        return (self.stores_persistent_parameters and
                self.updates_parameters_from_outcomes and
                self.parameters_influence_future_decisions)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "is_ass": self.is_ass,
                "stores": self.stores_persistent_parameters,
                "updates": self.updates_parameters_from_outcomes,
                "uses": self.parameters_influence_future_decisions}


# ---------------------------------------------------------------------------
# TSS Theory v1.
# ---------------------------------------------------------------------------

TSS_V1 = VersionedTheory(
    name="Temporal Scale Separation (TSS)",
    version="v1",
    formal_statement=(
        "When two Adaptive State Systems (ASSs) operate on the same temporal "
        "scale, they will interfere. Different scales → coexistence.\n\n"
        "TSS applies ONLY to ASSs. Temporal scale is the strongest supported "
        "explanatory variable — not claimed as the unique root cause."
    ),
    intuition="Same-scale ASSs compete for the same signal. Different-scale ASSs don't.",
    predictions=[
        VersionedPrediction(
            id="TSS-P1",
            statement="Regret is monotonic in update frequency",
            derivation="More frequent updates → more same-scale overlap → more interference",
            falsification_criterion="If any intermediate frequency achieves regret within 10% of best",
            status="partially_confirmed",
            evidence=[EvidenceLevel("experiment", "v3.2 episode learning", "EXP-v3.2-ep", "roughly monotonic but per_workflow_20 borderline")],
        ),
        VersionedPrediction(
            id="TSS-P2",
            statement="Effect holds out-of-distribution",
            derivation="Temporal scale is about update frequency, not domain knowledge",
            falsification_criterion="If per_domain doesn't match disabled OOD (regret diff > 20%)",
            status="confirmed",
            evidence=[
                EvidenceLevel("prediction", "Derived from TSS formal statement"),
                EvidenceLevel("experiment", "v3.3 TSS falsification (pre-registered)", "EXP-v3.3-tss", "delta=0.0 on shift domains, 3 seeds"),
                EvidenceLevel("replication", "All 3 seeds consistent", "EXP-v3.3-tss", "std < 15 across seeds"),
            ],
        ),
        VersionedPrediction(
            id="TSS-P3",
            statement="Effect holds under cold-start (no seeded priors)",
            derivation="Cold-start changes starting point but not update frequency",
            falsification_criterion="If per_domain under cold-start has regret > 20% worse than disabled",
            status="confirmed",
            evidence=[
                EvidenceLevel("prediction", "Derived from TSS formal statement"),
                EvidenceLevel("experiment", "v3.3 TSS falsification (pre-registered)", "EXP-v3.3-tss", "delta=0.0 cold-start, 3 seeds"),
            ],
        ),
        VersionedPrediction(
            id="TSS-P4",
            statement="Any same-scale operational ASS interferes (not just planner)",
            derivation="TSS is about temporal scale, not specific mechanisms",
            falsification_criterion="If a same-scale ASS doesn't interfere with WM",
            status="partially_confirmed",
            evidence=[
                EvidenceLevel("experiment", "v3.4 three-learner test", "EXP-v3.4-3learn", "reflection (NOT an ASS) has no effect — boundary condition found"),
            ],
        ),
    ],
    alternative_explanations=[
        {"explanation": "SAT (shared adaptive target)", "status": "rejected",
         "evidence": "v3.4 stress test: same-scale-diff-target interferes (139.0), diff-scale-same-target doesn't (68.4)"},
        {"explanation": "Only in-distribution", "status": "rejected",
         "evidence": "v3.3: per_domain = disabled exactly on shift domains"},
        {"explanation": "Only warm-start", "status": "rejected",
         "evidence": "v3.3: per_domain = disabled exactly cold-start"},
    ],
    maturity="Supported",
    evidence_summary=(
        "TSS v1 is at 'Supported' maturity. P2 and P3 confirmed via pre-registered "
        "falsification (v3.3). SAT alternative rejected (v3.4). Explains 95.5% "
        "of training corpus (21/22) but only 70% of held-out corpus (7/10). "
        "The held-out failure led to the dual-component refinement (see DualComponent/theory_v1.py)."
    ),
)
