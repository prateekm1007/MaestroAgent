"""Formal model selection: AIC, BIC, MDL.

Replaces heuristic complexity comparisons (e.g., "2 assumptions for 2
predictions") with formal criteria that penalize complexity.

Uses a binomial likelihood model: each experiment is a Bernoulli trial
with p = n_correct / n_total.

  AIC = 2*k - 2*LL          (lower is better)
  BIC = k*ln(n) - 2*LL       (lower is better)
  MDL = k*log2(n) - LL/ln(2) (lower is better, in bits)

Where k = n_assumptions (model complexity) and n = n_total.
"""

from __future__ import annotations

import math
from typing import Any


def compute_model_selection_criteria(
    model_name: str, n_correct: int, n_total: int, n_assumptions: int,
) -> dict[str, Any]:
    """Compute AIC, BIC, and MDL for a model.

    Args:
        model_name: name of the model.
        n_correct: number of correct predictions.
        n_total: total number of predictions.
        n_assumptions: number of assumptions/parameters (model complexity).
    """
    p = n_correct / n_total if n_total > 0 else 0.5
    p = max(1e-10, min(1 - 1e-10, p))  # avoid log(0)

    ll = n_correct * math.log(p) + (n_total - n_correct) * math.log(1 - p)
    k = n_assumptions
    n = n_total

    aic = 2 * k - 2 * ll
    bic = k * math.log(n) - 2 * ll if n > 0 else float('inf')
    mdl = k * math.log2(n) - ll / math.log(2) if n > 0 else float('inf')

    return {
        "model": model_name,
        "n_correct": n_correct,
        "n_total": n_total,
        "n_assumptions": k,
        "log_likelihood": round(ll, 4),
        "AIC": round(aic, 4),
        "BIC": round(bic, 4),
        "MDL_bits": round(mdl, 4),
        "accuracy": round(p, 4),
    }


def compare_models(
    models: list[tuple[str, int, int, int]],
) -> list[dict[str, Any]]:
    """Compare multiple models using AIC, BIC, and MDL.

    Args:
        models: list of (model_name, n_correct, n_total, n_assumptions)

    Returns:
        List of model criteria dicts, sorted by AIC (best first).
    """
    results = []
    for name, correct, total, assumptions in models:
        results.append(compute_model_selection_criteria(name, correct, total, assumptions))

    # Sort by AIC (lower is better).
    results.sort(key=lambda m: m["AIC"])
    return results


def is_complexity_justified(
    model_a: dict[str, Any], model_b: dict[str, Any],
) -> dict[str, Any]:
    """Check if the more complex model (more assumptions) is justified.

    Args:
        model_a: simpler model (fewer assumptions).
        model_b: more complex model (more assumptions).

    Returns:
        Dict with per-criterion verdicts.
    """
    verdicts = {}
    for criterion in ["AIC", "BIC", "MDL_bits"]:
        delta = model_b[criterion] - model_a[criterion]
        justified = delta < 0  # lower is better
        verdicts[criterion] = {
            "delta": round(delta, 4),
            "justified": justified,
            "interpretation": (
                f"{'Justified' if justified else 'NOT justified'} under {criterion} "
                f"(Δ={delta:+.4f})"
            ),
        }

    any_justified = any(v["justified"] for v in verdicts.values())
    all_justified = all(v["justified"] for v in verdicts.values())

    return {
        "model_a": model_a["model"],
        "model_b": model_b["model"],
        "verdicts": verdicts,
        "any_justified": any_justified,
        "all_justified": all_justified,
        "summary": (
            f"Complexity {'IS' if all_justified else ('PARTIALLY' if any_justified else 'is NOT')} "
            f"justified: {model_b['model']} vs {model_a['model']}"
        ),
    }
