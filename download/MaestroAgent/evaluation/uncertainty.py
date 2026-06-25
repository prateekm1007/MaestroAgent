"""Uncertainty quantification for three-dimensional influence measurements.

Measures Policy influence (AIC), Belief influence (calibration shift),
and Outcome influence (regret delta) with bootstrap confidence intervals
across multiple seeds.

Every measurement is reported as: point estimate ± 95% CI.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Sequence

from evaluation.statistics import bootstrap_ci


@dataclass
class InfluenceWithUncertainty:
    """Three-dimensional influence measurement with confidence intervals."""
    subsystem: str
    policy_estimate: float
    policy_ci: tuple[float, float]
    belief_estimate: float
    belief_ci: tuple[float, float]
    outcome_estimate: float
    outcome_ci: tuple[float, float]
    n_seeds: int
    profile: str  # "belief-dominant" | "policy-dominant" | "policy+belief-dominant" | "inactive"

    def to_dict(self) -> dict[str, Any]:
        return {
            "subsystem": self.subsystem,
            "policy": {"estimate": round(self.policy_estimate, 4),
                       "ci_95": [round(self.policy_ci[0], 4), round(self.policy_ci[1], 4)]},
            "belief": {"estimate": round(self.belief_estimate, 4),
                       "ci_95": [round(self.belief_ci[0], 4), round(self.belief_ci[1], 4)]},
            "outcome": {"estimate": round(self.outcome_estimate, 2),
                        "ci_95": [round(self.outcome_ci[0], 2), round(self.outcome_ci[1], 2)]},
            "n_seeds": self.n_seeds,
            "profile": self.profile,
        }


def compute_influence_with_uncertainty(
    subsystem: str,
    policy_values: Sequence[float],
    belief_values: Sequence[float],
    outcome_values: Sequence[float],
) -> InfluenceWithUncertainty:
    """Compute three-dimensional influence with bootstrap CIs.

    Args:
        subsystem: name of the subsystem.
        policy_values: per-seed AIC measurements.
        belief_values: per-seed MAE delta measurements.
        outcome_values: per-seed regret delta measurements.

    Returns:
        InfluenceWithUncertainty with point estimates and 95% CIs.
    """
    n = len(policy_values)
    if n == 0:
        return InfluenceWithUncertainty(subsystem, 0, (0, 0), 0, (0, 0), 0, (0, 0), 0, "inactive")

    _, policy_lo, policy_hi = bootstrap_ci(list(policy_values), n_resamples=2000)
    _, belief_lo, belief_hi = bootstrap_ci(list(belief_values), n_resamples=2000)
    _, outcome_lo, outcome_hi = bootstrap_ci(list(outcome_values), n_resamples=2000)

    policy_mean = sum(policy_values) / n
    belief_mean = sum(belief_values) / n
    outcome_mean = sum(outcome_values) / n

    # Profile classification.
    if policy_mean > 0.1 and belief_mean > 0.01:
        profile = "policy+belief-dominant"
    elif policy_mean > 0.1:
        profile = "policy-dominant"
    elif belief_mean > 0.01:
        profile = "belief-dominant"
    elif outcome_mean > 5:
        profile = "outcome-dominant"
    else:
        profile = "inactive"

    return InfluenceWithUncertainty(
        subsystem=subsystem,
        policy_estimate=policy_mean,
        policy_ci=(policy_lo, policy_hi),
        belief_estimate=belief_mean,
        belief_ci=(belief_lo, belief_hi),
        outcome_estimate=outcome_mean,
        outcome_ci=(outcome_lo, outcome_hi),
        n_seeds=n,
        profile=profile,
    )


def is_statistically_significant(
    estimate: float, ci: tuple[float, float], threshold: float = 0.0,
) -> bool:
    """Check if an influence estimate is statistically significant.

    An estimate is significant if the 95% CI excludes the threshold
    (typically 0, meaning "no influence").
    """
    return ci[0] > threshold or ci[1] < threshold
