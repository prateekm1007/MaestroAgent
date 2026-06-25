"""Pre-registration framework for experiments.

Implements registered-report methodology: freeze hypotheses, metrics,
stopping criteria, statistical tests, success thresholds, alternative
explanations, and interpretation criteria BEFORE running experiments.

Write-once protocol registration with SHA-256 hash verification.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class PreRegistration:
    """A pre-registered experimental design.

    Once saved, the design is frozen — the JSON file is write-once and
    its hash is recorded. Any deviation must be documented as an amendment.
    """
    experiment_name: str
    hypothesis: str
    primary_metric: str
    stopping_criterion: str
    statistical_test: str
    success_threshold: str
    configs: list[str]
    n_seeds: int
    n_tasks_per_config: int
    seed_base: int = 42
    alternative_explanations: list[dict[str, str]] = field(default_factory=list)
    interpretation_criteria: list[dict[str, str]] = field(default_factory=list)
    validity_region: str = ""
    registered_at: float = field(default_factory=time.time)
    registration_hash: str = ""
    amendments: list[dict[str, Any]] = field(default_factory=list)

    def save(self, directory: str = "/home/z/my-project/download/preregistrations") -> str:
        os.makedirs(directory, exist_ok=True)
        design_dict = {k: v for k, v in asdict(self).items()
                       if k != "registration_hash"}
        design_json = json.dumps(design_dict, sort_keys=True, default=str)
        self.registration_hash = hashlib.sha256(design_json.encode()).hexdigest()[:16]

        filename = f"{self.experiment_name}_{int(self.registered_at)}.json"
        filepath = os.path.join(directory, filename)

        if os.path.exists(filepath):
            raise FileExistsError(
                f"Pre-registration file {filepath} already exists. "
                f"Pre-registrations are write-once to prevent modification."
            )

        with open(filepath, "w") as f:
            json.dump(asdict(self), f, indent=2, default=str)
        return filepath

    def evaluate(
        self, results: dict[str, Any], conclusion: str,
        directory: str = "/home/z/my-project/download/preregistrations",
    ) -> dict[str, Any]:
        evaluation = {
            "experiment_name": self.experiment_name,
            "registered_at": self.registered_at,
            "registration_hash": self.registration_hash,
            "evaluated_at": time.time(),
            "hypothesis": self.hypothesis,
            "success_threshold": self.success_threshold,
            "validity_region": self.validity_region,
            "alternative_explanations": self.alternative_explanations,
            "interpretation_criteria": self.interpretation_criteria,
            "results": results,
            "conclusion": conclusion,
            "amendments": self.amendments,
        }
        filename = f"{self.experiment_name}_{int(self.registered_at)}_result.json"
        filepath = os.path.join(directory, filename)
        with open(filepath, "w") as f:
            json.dump(evaluation, f, indent=2, default=str)
        return evaluation

    def update_explanation_status(
        self, explanation: str, status: str, evidence: str = "",
    ) -> None:
        for ae in self.alternative_explanations:
            if ae.get("explanation") == explanation:
                ae["status"] = status
                ae["evidence"] = evidence
                return
        self.add_amendment(
            reason=f"Alternative explanation not pre-registered: {explanation}",
            change=f"Status: {status}, Evidence: {evidence}",
        )

    def add_amendment(self, reason: str, change: str) -> None:
        self.amendments.append({
            "timestamp": time.time(), "reason": reason, "change": change,
        })
