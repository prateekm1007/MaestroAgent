"""Standard experiment result schema.

Every experiment emits exactly the same JSON structure, regardless of
which runtime, benchmark, or theory it uses. This makes comparisons
trivial and enables automated theory evaluation.

Schema:
  ExperimentResult
    ├── configuration: what was run
    ├── seed: reproducibility
    ├── metrics: what was measured
    ├── confidence_intervals: uncertainty
    ├── threats_to_validity: limitations
    ├── environment: where it ran
    ├── runtime: which engine
    ├── theory_predictions: what theories predicted
    └── observed_results: what actually happened
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Configuration:
    """What was run."""
    config_name: str
    config_params: dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class Metrics:
    """What was measured."""
    success_rate: float = 0.0
    total_regret: float = 0.0
    avg_regret: float = 0.0
    calibration_mae: float = 0.0
    total_cost: float = 0.0
    net_value: float = 0.0
    approach_distribution: dict[str, int] = field(default_factory=dict)
    learning_curve: list[float] = field(default_factory=list)
    convergence_task: int | None = None


@dataclass
class ConfidenceIntervals:
    """Uncertainty on key metrics."""
    success_rate_ci: tuple[float, float] = (0.0, 1.0)
    regret_ci: tuple[float, float] = (0.0, 0.0)
    calibration_ci: tuple[float, float] = (0.0, 0.0)
    n_seeds: int = 1


@dataclass
class Environment:
    """Where it ran."""
    benchmark_version: str = ""
    domains: list[str] = field(default_factory=list)
    n_tasks_per_domain: int = 0
    seed: int = 42
    identifiability_notes: str = ""


@dataclass
class RuntimeInfo:
    """Which engine."""
    runtime_name: str = "maestro"
    runtime_version: str = "v2.2"
    adaptive_subsystems_active: list[str] = field(default_factory=list)


@dataclass
class TheoryPrediction:
    """What a theory predicted for this experiment."""
    theory_name: str
    theory_version: str
    prediction: str  # "interference" | "no_interference" | "not_applicable"
    confidence: str  # "Strong" | "Moderate" | "Weak"
    reasoning: str = ""
    correct: bool | None = None  # filled after comparing to observed


@dataclass
class ExperimentResult:
    """Standard result schema. Every experiment emits this structure."""
    experiment_id: str = field(default_factory=lambda: f"EXP-{uuid.uuid4().hex[:8]}")
    experiment_name: str = ""
    timestamp: float = field(default_factory=time.time)

    configuration: Configuration = field(default_factory=Configuration)
    environment: Environment = field(default_factory=Environment)
    runtime: RuntimeInfo = field(default_factory=RuntimeInfo)

    metrics: Metrics = field(default_factory=Metrics)
    confidence_intervals: ConfidenceIntervals = field(default_factory=ConfidenceIntervals)

    theory_predictions: list[TheoryPrediction] = field(default_factory=list)
    observed_outcome: str = ""  # "interference" | "no_interference" | ""

    threats_to_validity: list[str] = field(default_factory=list)
    notes: str = ""

    # Provenance chain.
    benchmark_spec: str = ""  # path to YAML spec
    commit_hash: str = ""  # git commit
    result_file: str = ""  # path to full result JSON

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Convert tuples to lists for JSON.
        d["confidence_intervals"]["success_rate_ci"] = list(d["confidence_intervals"]["success_rate_ci"])
        d["confidence_intervals"]["regret_ci"] = list(d["confidence_intervals"]["regret_ci"])
        d["confidence_intervals"]["calibration_ci"] = list(d["confidence_intervals"]["calibration_ci"])
        return d

    def to_json(self, path: str | None = None) -> str:
        import json
        s = json.dumps(self.to_dict(), indent=2, default=str)
        if path:
            with open(path, "w") as f:
                f.write(s)
        return s
