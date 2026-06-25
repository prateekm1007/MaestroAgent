"""Statistical evaluation tools for adaptive agent systems.

This module provides research-grade statistical methods for evaluating
adaptive multi-agent systems:

  - Bootstrap confidence intervals
  - Effect sizes (Cohen's d, Cliff's delta)
  - Significance tests (Mann-Whitney U, permutation test)
  - Power analysis (minimum detectable effect, required sample size)
  - Stability analysis across seeds (mean, std, CV, worst, best)
  - Cumulative regret + convergence analysis
  - Transfer efficiency (OOD improvement / ID improvement)
  - Full statistical comparison of two configurations

This is NOT a runtime module. It sits OUTSIDE the engine and analyzes
benchmark output. The goal is to answer: "Is this improvement real, or
could it be noise?"
"""

from __future__ import annotations

import math
import random
import statistics
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Sequence


# ---------------------------------------------------------------------------
# Bootstrap confidence intervals.
# ---------------------------------------------------------------------------


def bootstrap_ci(
    samples: Sequence[float],
    statistic: str = "mean",
    n_resamples: int = 10000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Bootstrap confidence interval for a statistic.

    Returns:
        (point_estimate, ci_low, ci_high)
    """
    rng = random.Random(seed)
    n = len(samples)
    if n == 0:
        return 0.0, 0.0, 0.0

    def compute_stat(data: list[float]) -> float:
        if statistic == "median":
            return statistics.median(data)
        elif statistic == "std":
            return statistics.stdev(data) if len(data) > 1 else 0.0
        else:
            return sum(data) / len(data)

    point_estimate = compute_stat(list(samples))
    boot_stats: list[float] = []
    for _ in range(n_resamples):
        resample = [samples[rng.randint(0, n - 1)] for _ in range(n)]
        boot_stats.append(compute_stat(resample))

    boot_stats.sort()
    alpha = 1.0 - confidence
    lo_idx = int((alpha / 2) * n_resamples)
    hi_idx = int((1 - alpha / 2) * n_resamples)
    return round(point_estimate, 4), round(boot_stats[lo_idx], 4), round(boot_stats[hi_idx], 4)


# ---------------------------------------------------------------------------
# Effect sizes.
# ---------------------------------------------------------------------------


def cohens_d(group_a: Sequence[float], group_b: Sequence[float]) -> float:
    """Cohen's d: standardized mean difference.

    |d| < 0.2 negligible, ~0.2 small, ~0.5 medium, ~0.8 large, >1.2 very large.
    """
    if len(group_a) < 2 or len(group_b) < 2:
        return 0.0
    mean_a = statistics.mean(group_a)
    mean_b = statistics.mean(group_b)
    var_a = statistics.variance(group_a)
    var_b = statistics.variance(group_b)
    pooled_std = math.sqrt((var_a + var_b) / 2)
    if pooled_std == 0:
        return 0.0
    return round((mean_a - mean_b) / pooled_std, 4)


def cliffs_delta(group_a: Sequence[float], group_b: Sequence[float]) -> float:
    """Cliff's delta: non-parametric effect size. Range [-1, 1]."""
    count = 0
    total = 0
    for a in group_a:
        for b in group_b:
            if a > b:
                count += 1
            elif a < b:
                count -= 1
            total += 1
    if total == 0:
        return 0.0
    return round(count / total, 4)


# ---------------------------------------------------------------------------
# Significance tests.
# ---------------------------------------------------------------------------


def mann_whitney_u(
    group_a: Sequence[float], group_b: Sequence[float],
) -> dict[str, float]:
    """Mann-Whitney U test (non-parametric)."""
    n1, n2 = len(group_a), len(group_b)
    if n1 < 1 or n2 < 1:
        return {"U": 0, "p_value": 1.0, "significant_at_0.05": False}

    combined = [(v, 0) for v in group_a] + [(v, 1) for v in group_b]
    combined.sort(key=lambda x: x[0])

    ranks: list[float] = [0.0] * len(combined)
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[k] = avg_rank
        i = j

    rank_sum_a = sum(ranks[k] for k in range(len(combined)) if combined[k][1] == 0)
    U_a = rank_sum_a - n1 * (n1 + 1) / 2
    U_b = n1 * n2 - U_a
    U = min(U_a, U_b)

    mu_U = n1 * n2 / 2
    sigma_U = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    if sigma_U == 0:
        return {"U": round(U, 2), "p_value": 1.0, "significant_at_0.05": False}
    z = (U - mu_U) / sigma_U
    p_value = 2 * (1 - _normal_cdf(abs(z)))
    return {
        "U": round(U, 2),
        "z": round(z, 4),
        "p_value": round(p_value, 4),
        "significant_at_0.05": p_value < 0.05,
    }


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def permutation_test(
    group_a: Sequence[float],
    group_b: Sequence[float],
    n_permutations: int = 10000,
    seed: int = 42,
) -> dict[str, float]:
    """Permutation test for difference of means."""
    rng = random.Random(seed)
    combined = list(group_a) + list(group_b)
    n1 = len(group_a)
    observed_diff = statistics.mean(group_a) - statistics.mean(group_b)

    count_extreme = 0
    for _ in range(n_permutations):
        rng.shuffle(combined)
        perm_diff = statistics.mean(combined[:n1]) - statistics.mean(combined[n1:])
        if abs(perm_diff) >= abs(observed_diff):
            count_extreme += 1

    p_value = count_extreme / n_permutations
    return {
        "observed_diff": round(observed_diff, 4),
        "p_value": round(p_value, 4),
        "significant_at_0.05": p_value < 0.05,
        "n_permutations": n_permutations,
    }


# ---------------------------------------------------------------------------
# Power analysis.
# ---------------------------------------------------------------------------


def minimum_detectable_effect(
    n: int, alpha: float = 0.05, power: float = 0.8, std: float = 1.0,
) -> float:
    """Minimum effect size detectable with given n and power."""
    z_alpha = _inverse_normal_cdf(1 - alpha / 2)
    z_beta = _inverse_normal_cdf(power)
    return round((z_alpha + z_beta) * std * math.sqrt(2 / max(n, 1)), 4)


def required_sample_size(
    effect_size: float, alpha: float = 0.05, power: float = 0.8,
) -> int:
    """Required sample size per group to detect a given effect size."""
    if effect_size == 0:
        return 999999
    z_alpha = _inverse_normal_cdf(1 - alpha / 2)
    z_beta = _inverse_normal_cdf(power)
    n = 2 * ((z_alpha + z_beta) / effect_size) ** 2
    return math.ceil(n)


def _inverse_normal_cdf(p: float) -> float:
    """Inverse normal CDF (probit function)."""
    if p <= 0:
        return -10
    if p >= 1:
        return 10
    a = [-3.969683028665376e+01, 2.209460984245205e+02,
         -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02,
         -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01,
         2.445134137142996e+00, 3.754408661907416e+00]
    p_low = 0.02425
    p_high = 1 - p_low
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
               ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1)
    elif p <= p_high:
        q = p - 0.5
        r = q * q
        return (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5]) * q / \
               (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1)
    else:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
               ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1)


# ---------------------------------------------------------------------------
# Stability analysis across seeds.
# ---------------------------------------------------------------------------


@dataclass
class StabilityReport:
    metric_name: str
    n_seeds: int
    mean: float
    std: float
    min: float
    max: float
    ci_low: float
    ci_high: float
    cv: float
    individual_values: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric_name, "n_seeds": self.n_seeds,
            "mean": round(self.mean, 4), "std": round(self.std, 4),
            "min": round(self.min, 4), "max": round(self.max, 4),
            "ci_95": [round(self.ci_low, 4), round(self.ci_high, 4)],
            "cv": round(self.cv, 4),
            "values": [round(v, 4) for v in self.individual_values],
        }


def stability_analysis(
    values: Sequence[float], metric_name: str = "metric",
) -> StabilityReport:
    n = len(values)
    if n == 0:
        return StabilityReport(metric_name, 0, 0, 0, 0, 0, 0, 0, 0)
    mean = statistics.mean(values)
    std = statistics.stdev(values) if n > 1 else 0.0
    _, ci_lo, ci_hi = bootstrap_ci(list(values), n_resamples=min(5000, max(1000, n * 100)))
    cv = std / abs(mean) if mean != 0 else 0.0
    return StabilityReport(metric_name, n, mean, std, min(values), max(values),
                           ci_lo, ci_hi, cv, list(values))


# ---------------------------------------------------------------------------
# Cumulative regret + convergence analysis.
# ---------------------------------------------------------------------------


@dataclass
class RegretReport:
    total_tasks: int
    total_regret: float
    avg_regret: float
    convergence_task: int | None
    convergence_threshold: float
    early_regret_rate: float
    late_regret_rate: float
    regret_reduction_pct: float
    interpretation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tasks": self.total_tasks,
            "total_regret": round(self.total_regret, 4),
            "avg_regret": round(self.avg_regret, 6),
            "convergence_task": self.convergence_task,
            "early_regret_rate": round(self.early_regret_rate, 6),
            "late_regret_rate": round(self.late_regret_rate, 6),
            "regret_reduction_pct": round(self.regret_reduction_pct, 2),
            "interpretation": self.interpretation,
        }


def compute_regret(
    actual_rewards: Sequence[float],
    optimal_rewards: Sequence[float],
    convergence_threshold: float = 0.05,
    window_size: int = 100,
) -> RegretReport:
    n = min(len(actual_rewards), len(optimal_rewards))
    if n == 0:
        return RegretReport(0, 0, 0, None, convergence_threshold, 0, 0, 0, "No data.")

    per_task_regret = [optimal_rewards[i] - actual_rewards[i] for i in range(n)]
    cumulative = []
    running = 0.0
    for r in per_task_regret:
        running += r
        cumulative.append(running)

    total_regret = cumulative[-1]
    avg_regret = total_regret / n

    convergence_task = None
    for start in range(0, n - window_size):
        window = per_task_regret[start:start + window_size]
        window_avg = sum(window) / len(window)
        if window_avg <= convergence_threshold:
            rest = per_task_regret[start + window_size:]
            if rest:
                rest_avg = sum(rest) / len(rest)
                if rest_avg <= convergence_threshold * 1.5:
                    convergence_task = start + window_size
                    break

    early_n = max(1, n // 10)
    late_n = max(1, n // 10)
    early_rate = sum(per_task_regret[:early_n]) / early_n
    late_rate = sum(per_task_regret[-late_n:]) / late_n
    reduction = (early_rate - late_rate) / early_rate * 100 if early_rate > 0 else 0.0

    conv_str = f"converged at task {convergence_task}" if convergence_task else "did not converge"
    interp = (f"Total regret {total_regret:.1f} over {n} tasks (avg {avg_regret:.4f}/task). "
              f"System {conv_str}. Early {early_rate:.4f}/task → late {late_rate:.4f}/task "
              f"({reduction:+.1f}% reduction).")

    return RegretReport(n, total_regret, avg_regret, convergence_task,
                        convergence_threshold, early_rate, late_rate, reduction, interp)


# ---------------------------------------------------------------------------
# Transfer efficiency.
# ---------------------------------------------------------------------------


@dataclass
class TransferEfficiencyReport:
    train_domain: str
    test_domain: str
    id_improvement: float
    ood_improvement: float
    transfer_efficiency: float
    interpretation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "train_domain": self.train_domain, "test_domain": self.test_domain,
            "id_improvement": round(self.id_improvement, 4),
            "ood_improvement": round(self.ood_improvement, 4),
            "transfer_efficiency": round(self.transfer_efficiency, 4),
            "interpretation": self.interpretation,
        }


def compute_transfer_efficiency(
    train_domain: str, test_domain: str,
    id_early: float, id_late: float,
    ood_early: float, ood_late: float,
    higher_is_better: bool = True,
) -> TransferEfficiencyReport:
    if higher_is_better:
        id_imp = id_late - id_early
        ood_imp = ood_late - ood_early
    else:
        id_imp = id_early - id_late
        ood_imp = ood_early - ood_late

    if abs(id_imp) < 1e-9:
        te = 0.0
        interp = "No ID improvement to compare against."
    else:
        te = ood_imp / id_imp
        if te >= 0.8:
            interp = f"Strong transfer (TE={te:.2f})"
        elif te >= 0.4:
            interp = f"Moderate transfer (TE={te:.2f})"
        elif te >= 0.0:
            interp = f"Weak transfer / memorization (TE={te:.2f})"
        else:
            interp = f"NEGATIVE transfer (TE={te:.2f})"

    return TransferEfficiencyReport(train_domain, test_domain, id_imp, ood_imp, te, interp)


# ---------------------------------------------------------------------------
# Full statistical comparison of two configurations.
# ---------------------------------------------------------------------------


@dataclass
class ComparisonReport:
    config_a: str
    config_b: str
    metric: str
    mean_a: float
    mean_b: float
    delta: float
    ci_low: float
    ci_high: float
    cohens_d: float
    cliffs_delta: float
    mann_whitney_p: float
    permutation_p: float
    significant: bool
    interpretation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_a": self.config_a, "config_b": self.config_b, "metric": self.metric,
            "mean_a": round(self.mean_a, 4), "mean_b": round(self.mean_b, 4),
            "delta": round(self.delta, 4),
            "ci_95": [round(self.ci_low, 4), round(self.ci_high, 4)],
            "cohens_d": round(self.cohens_d, 4),
            "cliffs_delta": round(self.cliffs_delta, 4),
            "mann_whitney_p": round(self.mann_whitney_p, 4),
            "permutation_p": round(self.permutation_p, 4),
            "significant": self.significant,
            "interpretation": self.interpretation,
        }


def compare_configs(
    config_a: str, values_a: Sequence[float],
    config_b: str, values_b: Sequence[float],
    metric: str, higher_is_better: bool = True,
) -> ComparisonReport:
    """Full statistical comparison of two configurations."""
    mean_a = statistics.mean(values_a) if values_a else 0
    mean_b = statistics.mean(values_b) if values_b else 0
    delta = mean_b - mean_a

    rng = random.Random(42)
    n_a, n_b = len(values_a), len(values_b)
    boot_deltas: list[float] = []
    for _ in range(5000):
        ra = [values_a[rng.randint(0, n_a - 1)] for _ in range(n_a)] if n_a > 0 else []
        rb = [values_b[rng.randint(0, n_b - 1)] for _ in range(n_b)] if n_b > 0 else []
        boot_deltas.append((sum(rb)/len(rb) if rb else 0) - (sum(ra)/len(ra) if ra else 0))
    boot_deltas.sort()
    ci_lo = boot_deltas[int(0.025 * len(boot_deltas))]
    ci_hi = boot_deltas[int(0.975 * len(boot_deltas))]

    d = cohens_d(values_b, values_a) if len(values_a) > 1 and len(values_b) > 1 else 0
    cd = cliffs_delta(values_b, values_a) if values_a and values_b else 0
    mw = mann_whitney_u(values_b, values_a)
    pt = permutation_test(values_b, values_a, n_permutations=5000)
    significant = mw["significant_at_0.05"] or pt["significant_at_0.05"]

    abs_d = abs(d)
    if abs_d < 0.2: effect_label = "negligible"
    elif abs_d < 0.5: effect_label = "small"
    elif abs_d < 0.8: effect_label = "medium"
    else: effect_label = "large"

    if significant and (ci_lo > 0 if higher_is_better else ci_hi < 0):
        better = "B is better"
    elif significant and (ci_hi < 0 if higher_is_better else ci_lo > 0):
        better = "A is better"
    elif significant:
        better = "significant but direction mixed"
    else:
        better = "no significant difference"

    interpretation = (f"{better} (Cohen's d={d:+.3f}, {effect_label} effect; "
                      f"MWU p={mw['p_value']:.4f}; permutation p={pt['p_value']:.4f})")

    return ComparisonReport(config_a, config_b, metric, mean_a, mean_b, delta,
                            ci_lo, ci_hi, d, cd, mw["p_value"], pt["p_value"],
                            significant, interpretation)
