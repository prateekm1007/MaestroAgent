"""Uncertainty quantification for three-dimensional influence measurements.

Measures Policy influence (AIC), Belief influence (calibration shift),
and Outcome influence (regret delta) with bootstrap confidence intervals.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Sequence
from evaluation.statistics import bootstrap_ci


@dataclass
class InfluenceWithUncertainty:
    subsystem: str
    policy_estimate: float; policy_ci: tuple[float, float]
    belief_estimate: float; belief_ci: tuple[float, float]
    outcome_estimate: float; outcome_ci: tuple[float, float]
    n_seeds: int; profile: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "subsystem": self.subsystem,
            "policy": {"estimate": round(self.policy_estimate, 4), "ci_95": [round(self.policy_ci[0], 4), round(self.policy_ci[1], 4)]},
            "belief": {"estimate": round(self.belief_estimate, 4), "ci_95": [round(self.belief_ci[0], 4), round(self.belief_ci[1], 4)]},
            "outcome": {"estimate": round(self.outcome_estimate, 2), "ci_95": [round(self.outcome_ci[0], 2), round(self.outcome_ci[1], 2)]},
            "n_seeds": self.n_seeds, "profile": self.profile,
        }


def compute_influence_with_uncertainty(
    subsystem: str, policy: Sequence[float], belief: Sequence[float], outcome: Sequence[float],
) -> InfluenceWithUncertainty:
    n = len(policy)
    if n == 0: return InfluenceWithUncertainty(subsystem, 0, (0,0), 0, (0,0), 0, (0,0), 0, "inactive")
    _, plo, phi = bootstrap_ci(list(policy), n_resamples=2000)
    _, blo, bhi = bootstrap_ci(list(belief), n_resamples=2000)
    _, olo, ohi = bootstrap_ci(list(outcome), n_resamples=2000)
    pm, bm, om = sum(policy)/n, sum(belief)/n, sum(outcome)/n
    profile = ("policy+belief-dominant" if pm > 0.1 and bm > 0.01 else
               "policy-dominant" if pm > 0.1 else
               "belief-dominant" if bm > 0.01 else
               "outcome-dominant" if om > 5 else "inactive")
    return InfluenceWithUncertainty(subsystem, pm, (plo, phi), bm, (blo, bhi), om, (olo, ohi), n, profile)


def is_significant(estimate: float, ci: tuple[float, float], threshold: float = 0.0) -> bool:
    return ci[0] > threshold or ci[1] < threshold
