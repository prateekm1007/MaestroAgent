"""Dual-Component Interference Theory v1.

Immutable theory snapshot. The refinement that explains TSS's v3.6
held-out failure.

Maturity: Predictive
  - Makes falsifiable predictions
  - 1/3 predictions confirmed (DC-P1: 90% held-out vs TSS 70%)
  - 2/3 untested (DC-P2: isolation, DC-P3: formal model selection)
  - Not yet stress-tested

Evidence chain:
  DC-P1 (held-out better than TSS) → v3.8 model comparison → 9/10 (90%) → CONFIRMED
  DC-P2 (components independently manipulable) → v3.8 isolation → inconclusive → UNTESTED
  DC-P3 (complexity justified under AIC/BIC) → pending → UNTESTED
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from research.findings.TSS.theory_v1 import VersionedTheory, VersionedPrediction, EvidenceLevel


DUAL_COMPONENT_V1 = VersionedTheory(
    name="Dual-Component Interference",
    version="v1",
    formal_statement=(
        "Interference ≈ BehavioralInterference + RepresentationalInterference\n\n"
        "1. Behavioral interference: changes actions. Proportional to both "
        "   subsystems' policy influence (AIC) and temporal overlap.\n"
        "2. Representational interference: changes internal state (estimates). "
        "   Proportional to both subsystems' belief influence and temporal overlap.\n\n"
        "A subsystem with AIC=0 can still participate in representational "
        "interference if it shares an adaptive target with another learner "
        "on the same temporal scale."
    ),
    intuition=(
        "The World Model has AIC=0 (doesn't change which approach is selected) "
        "but high belief influence (changes estimate quality). It operates in "
        "BELIEF space, not ACTION space. This is why AIC alone couldn't detect "
        "its interference with the Planner."
    ),
    predictions=[
        VersionedPrediction(
            id="DC-P1",
            statement="Dual-component model predicts held-out corpus better than TSS alone",
            derivation="TSS misses experiments where AIC=0 subsystems don't interfere; dual-component correctly identifies them via belief influence",
            falsification_criterion="If dual-component accuracy <= TSS accuracy on held-out",
            status="confirmed",
            evidence=[
                EvidenceLevel("prediction", "Derived from dual-component formal statement"),
                EvidenceLevel("held_out", "v3.8 model comparison on held-out corpus", "EXP-v3.8-model", "90% vs TSS 70%, +2 predictions for +2 assumptions"),
            ],
        ),
        VersionedPrediction(
            id="DC-P2",
            statement="Behavioral and representational interference are independently manipulable",
            derivation="If they're distinct mechanisms, isolating one should produce a different outcome signature",
            falsification_criterion="If behavioral-only and representational-only produce identical outcomes",
            status="untested",
            evidence=[
                EvidenceLevel("experiment", "v3.8 isolation experiment", "EXP-v3.8-iso", "inconclusive — B=C because planner reads both fields"),
            ],
        ),
        VersionedPrediction(
            id="DC-P3",
            statement="Complexity (5 vs 3 assumptions) is justified under formal model selection",
            derivation="If AIC/BIC/MDL prefer the dual-component model, the complexity is warranted",
            falsification_criterion="If AIC/BIC/MDL prefer the simpler TSS model",
            status="untested",
            evidence=[],
        ),
    ],
    alternative_explanations=[
        {"explanation": "The dual-component model is overfitting to the held-out corpus",
         "status": "untested", "evidence": "Needs a new held-out corpus to test"},
    ],
    maturity="Predictive",
    evidence_summary=(
        "Dual-component v1 achieved 90% on v3.6 held-out corpus (vs TSS 70%). "
        "The three-dimensional measurement (v3.8) revealed WM operates in belief "
        "space (AIC=0, Belief>0). Formal model selection (AIC/BIC/MDL) pending. "
        "Isolation experiment inconclusive — needs identifiable benchmark."
    ),
)
