"""Evaluation framework public API.

An experimental platform for studying adaptive multi-agent systems using
reproducible benchmarks, pre-registered experiments, causal ablations,
and predictive theory evaluation.
"""

from evaluation.statistics import (
    bootstrap_ci, cohens_d, cliffs_delta, mann_whitney_u, permutation_test,
    minimum_detectable_effect, required_sample_size, stability_analysis,
    compare_configs, compute_regret, compute_transfer_efficiency,
    StabilityReport, ComparisonReport, RegretReport, TransferEfficiencyReport,
)
from evaluation.preregistration import PreRegistration
from evaluation.model_selection import (
    compute_model_selection_criteria, compare_models, is_complexity_justified,
)
from evaluation.uncertainty import (
    InfluenceWithUncertainty, compute_influence_with_uncertainty,
    is_statistically_significant,
)

__all__ = [
    # Statistics
    "bootstrap_ci", "cohens_d", "cliffs_delta", "mann_whitney_u",
    "permutation_test", "minimum_detectable_effect", "required_sample_size",
    "stability_analysis", "compare_configs", "compute_regret",
    "compute_transfer_efficiency",
    "StabilityReport", "ComparisonReport", "RegretReport", "TransferEfficiencyReport",
    # Pre-registration
    "PreRegistration",
    # Model selection
    "compute_model_selection_criteria", "compare_models", "is_complexity_justified",
    # Uncertainty
    "InfluenceWithUncertainty", "compute_influence_with_uncertainty",
    "is_statistically_significant",
]
