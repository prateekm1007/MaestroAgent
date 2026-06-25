"""Statistical inference: bootstrap CIs, effect sizes, significance tests, power analysis.

Pure infrastructure — no theory dependencies. Survives if every theory
is falsified.
"""

from __future__ import annotations

import math
import random
import statistics
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Sequence


def bootstrap_ci(
    samples: Sequence[float], statistic: str = "mean",
    n_resamples: int = 10000, confidence: float = 0.95, seed: int = 42,
) -> tuple[float, float, float]:
    rng = random.Random(seed)
    n = len(samples)
    if n == 0: return 0.0, 0.0, 0.0
    def stat(data): return statistics.median(data) if statistic == "median" else (statistics.stdev(data) if len(data) > 1 else 0.0) if statistic == "std" else sum(data)/len(data)
    point = stat(list(samples))
    boots = [stat([samples[rng.randint(0, n-1)] for _ in range(n)]) for _ in range(n_resamples)]
    boots.sort()
    alpha = 1.0 - confidence
    return round(point, 4), round(boots[int((alpha/2)*n_resamples)], 4), round(boots[int((1-alpha/2)*n_resamples)], 4)


def cohens_d(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) < 2 or len(b) < 2: return 0.0
    va, vb = statistics.variance(a), statistics.variance(b)
    pooled = math.sqrt((va + vb) / 2)
    return round((statistics.mean(a) - statistics.mean(b)) / pooled, 4) if pooled else 0.0


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> float:
    count = sum((1 if x > y else -1 if x < y else 0) for x in a for y in b)
    total = len(a) * len(b)
    return round(count / total, 4) if total else 0.0


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _inverse_normal_cdf(p: float) -> float:
    if p <= 0: return -10
    if p >= 1: return 10
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    elif p <= ph:
        q = p - 0.5; r = q * q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5]) * q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    else:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def mann_whitney_u(a: Sequence[float], b: Sequence[float]) -> dict[str, float]:
    n1, n2 = len(a), len(b)
    if n1 < 1 or n2 < 1: return {"U": 0, "p_value": 1.0, "significant_at_0.05": False}
    combined = sorted([(v, 0) for v in a] + [(v, 1) for v in b], key=lambda x: x[0])
    ranks = [0.0] * len(combined)
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]: j += 1
        avg = (i + 1 + j) / 2.0
        for k in range(i, j): ranks[k] = avg
        i = j
    rsa = sum(ranks[k] for k in range(len(combined)) if combined[k][1] == 0)
    U = min(rsa - n1*(n1+1)/2, n1*n2 - (rsa - n1*(n1+1)/2))
    mu, sigma = n1*n2/2, math.sqrt(n1*n2*(n1+n2+1)/12)
    if sigma == 0: return {"U": round(U, 2), "p_value": 1.0, "significant_at_0.05": False}
    z = (U - mu) / sigma
    p = 2 * (1 - _normal_cdf(abs(z)))
    return {"U": round(U, 2), "z": round(z, 4), "p_value": round(p, 4), "significant_at_0.05": p < 0.05}


def permutation_test(a: Sequence[float], b: Sequence[float], n_perm: int = 10000, seed: int = 42) -> dict[str, float]:
    rng = random.Random(seed)
    combined = list(a) + list(b)
    n1 = len(a)
    obs = statistics.mean(a) - statistics.mean(b)
    count = sum(1 for _ in range(n_perm) if abs((lambda c: (rng.shuffle(c), statistics.mean(c[:n1]) - statistics.mean(c[n1:]))[1])(combined[:])) >= abs(obs))
    # Simpler approach:
    count = 0
    for _ in range(n_perm):
        rng.shuffle(combined)
        if abs(statistics.mean(combined[:n1]) - statistics.mean(combined[n1:])) >= abs(obs):
            count += 1
    p = count / n_perm
    return {"observed_diff": round(obs, 4), "p_value": round(p, 4), "significant_at_0.05": p < 0.05, "n_permutations": n_perm}


def minimum_detectable_effect(n: int, alpha: float = 0.05, power: float = 0.8, std: float = 1.0) -> float:
    return round((_inverse_normal_cdf(1-alpha/2) + _inverse_normal_cdf(power)) * std * math.sqrt(2/max(n, 1)), 4)


def required_sample_size(effect_size: float, alpha: float = 0.05, power: float = 0.8) -> int:
    if effect_size == 0: return 999999
    return math.ceil(2 * ((_inverse_normal_cdf(1-alpha/2) + _inverse_normal_cdf(power)) / effect_size) ** 2)


@dataclass
class StabilityReport:
    metric_name: str; n_seeds: int; mean: float; std: float
    min: float; max: float; ci_low: float; ci_high: float; cv: float
    individual_values: list[float] = field(default_factory=list)
    def to_dict(self) -> dict[str, Any]:
        return {"metric": self.metric_name, "n_seeds": self.n_seeds, "mean": round(self.mean, 4),
                "std": round(self.std, 4), "min": round(self.min, 4), "max": round(self.max, 4),
                "ci_95": [round(self.ci_low, 4), round(self.ci_high, 4)], "cv": round(self.cv, 4),
                "values": [round(v, 4) for v in self.individual_values]}


def stability_analysis(values: Sequence[float], metric_name: str = "metric") -> StabilityReport:
    n = len(values)
    if n == 0: return StabilityReport(metric_name, 0, 0, 0, 0, 0, 0, 0, 0)
    mean = statistics.mean(values)
    std = statistics.stdev(values) if n > 1 else 0.0
    _, ci_lo, ci_hi = bootstrap_ci(list(values), n_resamples=min(5000, max(1000, n*100)))
    cv = std / abs(mean) if mean != 0 else 0.0
    return StabilityReport(metric_name, n, mean, std, min(values), max(values), ci_lo, ci_hi, cv, list(values))


@dataclass
class RegretReport:
    total_tasks: int; total_regret: float; avg_regret: float
    convergence_task: int | None; convergence_threshold: float
    early_regret_rate: float; late_regret_rate: float
    regret_reduction_pct: float; interpretation: str
    def to_dict(self) -> dict[str, Any]:
        return {"total_tasks": self.total_tasks, "total_regret": round(self.total_regret, 4),
                "avg_regret": round(self.avg_regret, 6), "convergence_task": self.convergence_task,
                "early_regret_rate": round(self.early_regret_rate, 6),
                "late_regret_rate": round(self.late_regret_rate, 6),
                "regret_reduction_pct": round(self.regret_reduction_pct, 2),
                "interpretation": self.interpretation}


def compute_regret(actual: Sequence[float], optimal: Sequence[float],
                   convergence_threshold: float = 0.05, window_size: int = 100) -> RegretReport:
    n = min(len(actual), len(optimal))
    if n == 0: return RegretReport(0, 0, 0, None, convergence_threshold, 0, 0, 0, "No data.")
    per_task = [optimal[i] - actual[i] for i in range(n)]
    total = sum(per_task)
    avg = total / n
    conv = None
    for start in range(0, n - window_size):
        w = per_task[start:start+window_size]
        if sum(w)/len(w) <= convergence_threshold:
            rest = per_task[start+window_size:]
            if not rest or sum(rest)/len(rest) <= convergence_threshold * 1.5:
                conv = start + window_size; break
    en, ln = max(1, n//10), max(1, n//10)
    er, lr = sum(per_task[:en])/en, sum(per_task[-ln:])/ln
    red = (er - lr) / er * 100 if er > 0 else 0.0
    cs = f"converged at task {conv}" if conv else "did not converge"
    return RegretReport(n, total, avg, conv, convergence_threshold, er, lr, red,
                        f"Total regret {total:.1f} over {n} tasks (avg {avg:.4f}/task). System {cs}. Early {er:.4f} → late {lr:.4f} ({red:+.1f}%).")


@dataclass
class TransferEfficiencyReport:
    train_domain: str; test_domain: str
    id_improvement: float; ood_improvement: float
    transfer_efficiency: float; interpretation: str
    def to_dict(self) -> dict[str, Any]:
        return {"train_domain": self.train_domain, "test_domain": self.test_domain,
                "id_improvement": round(self.id_improvement, 4),
                "ood_improvement": round(self.ood_improvement, 4),
                "transfer_efficiency": round(self.transfer_efficiency, 4),
                "interpretation": self.interpretation}


def compute_transfer_efficiency(train_d: str, test_d: str, id_e: float, id_l: float,
                                ood_e: float, ood_l: float, higher_is_better: bool = True) -> TransferEfficiencyReport:
    id_imp = (id_l - id_e) if higher_is_better else (id_e - id_l)
    ood_imp = (ood_l - ood_e) if higher_is_better else (ood_e - ood_l)
    if abs(id_imp) < 1e-9:
        te, interp = 0.0, "No ID improvement."
    else:
        te = ood_imp / id_imp
        interp = (f"Strong transfer (TE={te:.2f})" if te >= 0.8 else
                  f"Moderate transfer (TE={te:.2f})" if te >= 0.4 else
                  f"Weak/memorization (TE={te:.2f})" if te >= 0.0 else
                  f"NEGATIVE transfer (TE={te:.2f})")
    return TransferEfficiencyReport(train_d, test_d, id_imp, ood_imp, te, interp)


@dataclass
class ComparisonReport:
    config_a: str; config_b: str; metric: str
    mean_a: float; mean_b: float; delta: float
    ci_low: float; ci_high: float; cohens_d: float; cliffs_delta: float
    mann_whitney_p: float; permutation_p: float; significant: bool; interpretation: str
    def to_dict(self) -> dict[str, Any]:
        return {"config_a": self.config_a, "config_b": self.config_b, "metric": self.metric,
                "mean_a": round(self.mean_a, 4), "mean_b": round(self.mean_b, 4),
                "delta": round(self.delta, 4), "ci_95": [round(self.ci_low, 4), round(self.ci_high, 4)],
                "cohens_d": round(self.cohens_d, 4), "cliffs_delta": round(self.cliffs_delta, 4),
                "mann_whitney_p": round(self.mann_whitney_p, 4),
                "permutation_p": round(self.permutation_p, 4),
                "significant": self.significant, "interpretation": self.interpretation}


def compare_configs(a_name: str, a_vals: Sequence[float], b_name: str, b_vals: Sequence[float],
                    metric: str, higher_is_better: bool = True) -> ComparisonReport:
    ma = statistics.mean(a_vals) if a_vals else 0
    mb = statistics.mean(b_vals) if b_vals else 0
    delta = mb - ma
    rng = random.Random(42)
    na, nb = len(a_vals), len(b_vals)
    boot = []
    for _ in range(5000):
        ra = [a_vals[rng.randint(0, na-1)] for _ in range(na)] if na > 0 else []
        rb = [b_vals[rng.randint(0, nb-1)] for _ in range(nb)] if nb > 0 else []
        boot.append((sum(rb)/len(rb) if rb else 0) - (sum(ra)/len(ra) if ra else 0))
    boot.sort()
    ci_lo, ci_hi = boot[int(0.025*len(boot))], boot[int(0.975*len(boot))]
    d = cohens_d(b_vals, a_vals) if len(a_vals) > 1 and len(b_vals) > 1 else 0
    cd = cliffs_delta(b_vals, a_vals) if a_vals and b_vals else 0
    mw = mann_whitney_u(b_vals, a_vals)
    pt = permutation_test(b_vals, a_vals, n_perm=5000)
    sig = mw["significant_at_0.05"] or pt["significant_at_0.05"]
    ad = abs(d)
    el = "negligible" if ad < 0.2 else "small" if ad < 0.5 else "medium" if ad < 0.8 else "large"
    better = ("B is better" if sig and (ci_lo > 0 if higher_is_better else ci_hi < 0) else
              "A is better" if sig and (ci_hi < 0 if higher_is_better else ci_lo > 0) else
              "significant but mixed" if sig else "no significant difference")
    return ComparisonReport(a_name, b_name, metric, ma, mb, delta, ci_lo, ci_hi, d, cd,
                            mw["p_value"], pt["p_value"], sig,
                            f"{better} (d={d:+.3f}, {el}; MWU p={mw['p_value']:.4f}; perm p={pt['p_value']:.4f})")
