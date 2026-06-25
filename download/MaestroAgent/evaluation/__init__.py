"""Evaluation framework: pure statistical infrastructure.

No theory dependencies. Survives if every theory is falsified.

Modules:
  - statistics: bootstrap CIs, effect sizes, significance tests, power analysis,
    stability analysis, regret, transfer efficiency, comparison reports
  - uncertainty: three-dimensional influence with bootstrap CIs
  - reporting: standard experiment result schema (one JSON structure, forever)
"""

from evaluation.statistics import (
    bootstrap_ci, cohens_d, cliffs_delta, mann_whitney_u, permutation_test,
    minimum_detectable_effect, required_sample_size, stability_analysis,
    compare_configs, compute_regret, compute_transfer_efficiency,
    StabilityReport, ComparisonReport, RegretReport, TransferEfficiencyReport,
)
from evaluation.uncertainty import (
    InfluenceWithUncertainty, compute_influence_with_uncertainty, is_significant,
)
from evaluation.reporting import (
    ExperimentResult, Configuration, Metrics, ConfidenceIntervals,
    Environment, RuntimeInfo, TheoryPrediction,
)
