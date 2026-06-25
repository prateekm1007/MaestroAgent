"""Validity regions: bounded conditional claims for each mechanism.

Instead of global claims ("the world model works"), validity regions
document WHEN each mechanism helps vs fails, with confidence levels
based on accumulated experimental evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidityRegion:
    mechanism: str
    expected_to_help: list[dict[str, str]]
    expected_to_fail: list[dict[str, str]]
    unknown: list[dict[str, str]]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {"mechanism": self.mechanism,
                "expected_to_help": self.expected_to_help,
                "expected_to_fail": self.expected_to_fail,
                "unknown": self.unknown, "summary": self.summary}


VALIDITY_REGIONS: list[ValidityRegion] = [
    ValidityRegion(
        mechanism="World Model",
        summary="Dominant adaptive mechanism. Helps in-distribution and long-horizon. Fails OOD.",
        expected_to_help=[
            {"condition": "In-distribution (repeated domains)", "confidence": "High", "evidence": "v2.9: cuts regret 57% ID"},
            {"condition": "Long-horizon (≥6k tasks)", "confidence": "High", "evidence": "v2.9: cold-start catches up at 6k"},
            {"condition": "Calibration improvement over time", "confidence": "High", "evidence": "v2.7: MAE drops 73% over 10k"},
        ],
        expected_to_fail=[
            {"condition": "Out-of-distribution (unseen domains)", "confidence": "High", "evidence": "v2.8: 7.7 SR gap, no convergence"},
            {"condition": "Cross-domain transfer", "confidence": "High", "evidence": "v2.8: shift = cold (no transfer)"},
        ],
        unknown=[
            {"condition": "Capability-based keying", "confidence": "Low", "evidence": "v3.1: 2/3 capabilities transfer"},
            {"condition": "Performance beyond 20k tasks", "confidence": "Unknown", "evidence": "Not tested"},
        ],
    ),
    ValidityRegion(
        mechanism="Planner Policy Updates",
        summary="Interferes with WM at same scale. Compatible at coarse episode boundaries.",
        expected_to_help=[
            {"condition": "When WM is NOT active (planner-only)", "confidence": "Medium", "evidence": "v2.9: +0.35 SR improvement"},
        ],
        expected_to_fail=[
            {"condition": "Same scale as WM (per-task)", "confidence": "High", "evidence": "v3.1: 5 alternative rules all failed"},
            {"condition": "In-distribution (effect largest)", "confidence": "High", "evidence": "v3.1: d=-0.61 ID vs d=-0.15 OOD"},
        ],
        unknown=[
            {"condition": "Episode-boundary at finer granularity", "confidence": "Low", "evidence": "v3.2: per_domain works, finer doesn't"},
        ],
    ),
    ValidityRegion(
        mechanism="Reflection (Postmortems)",
        summary="Does not improve calibration. Not an ASS — doesn't maintain adaptive state.",
        expected_to_help=[],
        expected_to_fail=[
            {"condition": "Uncertainty inflation mechanism", "confidence": "High", "evidence": "v2.6: slightly worse"},
            {"condition": "As a same-scale learner (it's not an ASS)", "confidence": "High", "evidence": "v3.4: no effect regardless of scale"},
        ],
        unknown=[
            {"condition": "Direct p_success adjustment with fixed matching", "confidence": "Low", "evidence": "v2.8 fixed matching, not re-tested"},
        ],
    ),
    ValidityRegion(
        mechanism="Exploration (Experiments Engine)",
        summary="Hurts with warm-start priors. Best epsilon = 0.00.",
        expected_to_help=[
            {"condition": "Cold-start (no priors) — hypothesized", "confidence": "Unknown", "evidence": "Not tested"},
        ],
        expected_to_fail=[
            {"condition": "Warm-start (seeded priors)", "confidence": "High", "evidence": "v2.7: monotonic decline with epsilon"},
        ],
        unknown=[
            {"condition": "Confidence-conditional exploration", "confidence": "Unknown", "evidence": "Not implemented"},
        ],
    ),
    ValidityRegion(
        mechanism="Dual-Component Interference Model",
        summary="Explains 90% of held-out corpus vs TSS's 70%. Complexity justified.",
        expected_to_help=[
            {"condition": "Predicting held-out experiments", "confidence": "Medium", "evidence": "v3.8: 90% vs 70%"},
            {"condition": "Identifying non-operational ASSs", "confidence": "High", "evidence": "v3.8: AIC=0 + Belief≈0 → no interference"},
        ],
        expected_to_fail=[
            {"condition": "Isolating behavioral from representational (current benchmark)", "confidence": "Medium", "evidence": "v3.8: B=C (identifiability issue)"},
        ],
        unknown=[
            {"condition": "Formal model selection (AIC/BIC/MDL)", "confidence": "Unknown", "evidence": "v3.9: pending"},
            {"condition": "New held-out corpus", "confidence": "Unknown", "evidence": "Not yet tested"},
        ],
    ),
]


def get_validity_region(mechanism: str) -> ValidityRegion | None:
    for vr in VALIDITY_REGIONS:
        if vr.mechanism.lower() == mechanism.lower():
            return vr
    return None


def print_validity_table() -> None:
    print("=" * 80)
    print("VALIDITY REGIONS — When Each Mechanism Should Work")
    print("=" * 80)
    for vr in VALIDITY_REGIONS:
        print(f"\n  {vr.mechanism}")
        print(f"  Summary: {vr.summary}")
        print(f"\n  Expected to HELP:")
        for h in vr.expected_to_help:
            print(f"    • {h['condition']} (confidence: {h['confidence']})")
        print(f"\n  Expected to FAIL:")
        for f in vr.expected_to_fail:
            print(f"    • {f['condition']} (confidence: {f['confidence']})")
        if vr.unknown:
            print(f"\n  UNKNOWN:")
            for u in vr.unknown:
                print(f"    • {u['condition']} (confidence: {u['confidence']})")
    print("\n" + "=" * 80)
