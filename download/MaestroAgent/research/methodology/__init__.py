"""Research methodology: pre-registration, validity regions, model selection.

These are tools FOR DOING science, not scientific findings themselves.
They survive independently of any particular theory.
"""

from __future__ import annotations

import hashlib, json, math, os, time
from dataclasses import dataclass, field, asdict
from typing import Any


# ---------------------------------------------------------------------------
# Pre-registration.
# ---------------------------------------------------------------------------

@dataclass
class PreRegistration:
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
        d = {k: v for k, v in asdict(self).items() if k != "registration_hash"}
        self.registration_hash = hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()[:16]
        path = os.path.join(directory, f"{self.experiment_name}_{int(self.registered_at)}.json")
        if os.path.exists(path):
            raise FileExistsError(f"Pre-registration {path} already exists — write-once.")
        with open(path, "w") as f: json.dump(asdict(self), f, indent=2, default=str)
        return path

    def evaluate(self, results: dict, conclusion: str, directory: str = "/home/z/my-project/download/preregistrations") -> dict:
        ev = {**asdict(self), "evaluated_at": time.time(), "results": results, "conclusion": conclusion}
        path = os.path.join(directory, f"{self.experiment_name}_{int(self.registered_at)}_result.json")
        with open(path, "w") as f: json.dump(ev, f, indent=2, default=str)
        return ev

    def update_explanation_status(self, explanation: str, status: str, evidence: str = "") -> None:
        for ae in self.alternative_explanations:
            if ae.get("explanation") == explanation:
                ae["status"] = status; ae["evidence"] = evidence; return
        self.amendments.append({"timestamp": time.time(), "reason": f"Not pre-registered: {explanation}", "change": f"Status: {status}, Evidence: {evidence}"})


# ---------------------------------------------------------------------------
# Model selection: AIC, BIC, MDL.
# ---------------------------------------------------------------------------

def compute_model_selection_criteria(model_name: str, n_correct: int, n_total: int, n_assumptions: int) -> dict[str, Any]:
    p = max(1e-10, min(1-1e-10, n_correct / n_total if n_total > 0 else 0.5))
    ll = n_correct * math.log(p) + (n_total - n_correct) * math.log(1 - p)
    k, n = n_assumptions, n_total
    return {"model": model_name, "n_correct": n_correct, "n_total": n_total, "n_assumptions": k,
            "log_likelihood": round(ll, 4), "AIC": round(2*k - 2*ll, 4),
            "BIC": round(k*math.log(n) - 2*ll, 4) if n > 0 else float('inf'),
            "MDL_bits": round(k*math.log2(n) - ll/math.log(2), 4) if n > 0 else float('inf'),
            "accuracy": round(p, 4)}


def compare_models(models: list[tuple[str, int, int, int]]) -> list[dict[str, Any]]:
    results = [compute_model_selection_criteria(n, c, t, a) for n, c, t, a in models]
    results.sort(key=lambda m: m["AIC"])
    return results


def is_complexity_justified(simple: dict, complex: dict) -> dict[str, Any]:
    verdicts = {}
    for crit in ["AIC", "BIC", "MDL_bits"]:
        delta = complex[crit] - simple[crit]
        verdicts[crit] = {"delta": round(delta, 4), "justified": delta < 0}
    return {"model_a": simple["model"], "model_b": complex["model"], "verdicts": verdicts,
            "all_justified": all(v["justified"] for v in verdicts.values()),
            "summary": f"Complexity {'IS' if all(v['justified'] for v in verdicts.values()) else 'is NOT'} justified"}


# ---------------------------------------------------------------------------
# Validity regions.
# ---------------------------------------------------------------------------

@dataclass
class ValidityRegion:
    mechanism: str
    expected_to_help: list[dict[str, str]] = field(default_factory=list)
    expected_to_fail: list[dict[str, str]] = field(default_factory=list)
    unknown: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"mechanism": self.mechanism, "expected_to_help": self.expected_to_help,
                "expected_to_fail": self.expected_to_fail, "unknown": self.unknown, "summary": self.summary}
