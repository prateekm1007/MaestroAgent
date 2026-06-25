"""Predictive theories for adaptive multi-agent systems.

Two theories derived from the v2.5–v3.8 experimental program:

1. Temporal Scale Separation (TSS) — confirmed at "Supported" maturity.
2. Dual-Component Interference — the refinement that explains TSS's
   v3.6 held-out failure.

Construct: Adaptive State System (ASS) — a subsystem that (1) stores
persistent parameters, (2) updates them from outcomes, (3) uses them
in future decisions. TSS applies ONLY to ASSs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AdaptiveStateSystem:
    """A subsystem that maintains and updates persistent parameters."""
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
                "stores_persistent_parameters": self.stores_persistent_parameters,
                "updates_parameters_from_outcomes": self.updates_parameters_from_outcomes,
                "parameters_influence_future_decisions": self.parameters_influence_future_decisions}


@dataclass
class Prediction:
    id: str
    statement: str
    derivation: str
    falsification_criterion: str
    prior_evidence: str
    status: str = "untested"
    test_result: str = ""
    experiment: str = ""


@dataclass
class Theory:
    name: str
    formal_statement: str
    intuition: str
    predictions: list[Prediction] = field(default_factory=list)
    alternative_explanations: list[dict[str, str]] = field(default_factory=list)
    status: str = "pending"
    maturity: str = "Proposed"
    evidence_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "formal_statement": self.formal_statement,
                "intuition": self.intuition,
                "predictions": [{"id": p.id, "statement": p.statement,
                                 "status": p.status} for p in self.predictions],
                "alternative_explanations": self.alternative_explanations,
                "status": self.status, "maturity": self.maturity,
                "evidence_summary": self.evidence_summary}


TSS_THEORY = Theory(
    name="Temporal Scale Separation (TSS)",
    formal_statement=(
        "When two Adaptive State Systems (ASSs) operate on the same temporal "
        "scale, they will interfere. Different scales → coexistence.\n\n"
        "TSS applies ONLY to ASSs. Temporal scale is the strongest supported "
        "explanatory variable — not claimed as the unique root cause."
    ),
    intuition="Same-scale ASSs compete for the same signal. Different-scale ASSs don't.",
    predictions=[
        Prediction("TSS-P1", "Regret is monotonic in update frequency", "", "", "v3.2: roughly monotonic", "partially_confirmed"),
        Prediction("TSS-P2", "Effect holds OOD", "", "", "v3.3: CONFIRMED delta=0.0", "confirmed", "v3.3 TSS falsification"),
        Prediction("TSS-P3", "Effect holds cold-start", "", "", "v3.3: CONFIRMED delta=0.0", "confirmed", "v3.3 TSS falsification"),
        Prediction("TSS-P4", "Any same-scale operational ASS interferes", "", "", "v3.4: reflection (not ASS) has no effect", "partially_confirmed"),
    ],
    alternative_explanations=[
        {"explanation": "SAT (shared adaptive target)", "status": "rejected", "evidence": "v3.4 stress test"},
        {"explanation": "Only in-distribution", "status": "rejected", "evidence": "v3.3 OOD confirmed"},
        {"explanation": "Only warm-start", "status": "rejected", "evidence": "v3.3 cold-start confirmed"},
    ],
    status="partially_confirmed", maturity="Supported",
    evidence_summary="95.5% training corpus, 70% held-out. P2/P3 confirmed. SAT rejected.",
)

DUAL_COMPONENT_THEORY = Theory(
    name="Dual-Component Interference",
    formal_statement=(
        "Interference ≈ BehavioralInterference + RepresentationalInterference.\n"
        "Behavioral: changes actions (AIC). Representational: changes beliefs.\n"
        "A subsystem with AIC=0 can still participate in representational interference."
    ),
    intuition="WM has AIC=0 but Belief>0 — operates in belief space, not action space.",
    predictions=[
        Prediction("DC-P1", "Predicts held-out better than TSS", "", "", "v3.8: 90% vs 70%", "confirmed"),
        Prediction("DC-P2", "Components independently manipulable", "", "", "v3.8: inconclusive", "untested"),
        Prediction("DC-P3", "Complexity justified under AIC/BIC/MDL", "", "", "v3.9: pending", "untested"),
    ],
    alternative_explanations=[
        {"explanation": "Overfitting to held-out corpus", "status": "untested", "evidence": "Needs new held-out"},
    ],
    status="partially_confirmed", maturity="Predictive",
    evidence_summary="90% held-out (vs TSS 70%). Three-dimensional measurement revealed WM belief-space influence.",
)

ALL_THEORIES = [TSS_THEORY, DUAL_COMPONENT_THEORY]
