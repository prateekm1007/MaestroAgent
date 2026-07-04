"""
ConfidenceCalculator — fully explainable Bayesian confidence computation.

No arbitrary constants. Every factor is derived from:
1. Evidence volume (Beta-Binomial posterior)
2. Evidence quality (provider diversity, coverage)
3. Historical success (validated vs failed runtimes)
4. Recency (exponential decay with documented half-life)
5. Contradiction rate (counter-examples reduce posterior)
6. Calibration history (SHR adjusts the prior)

Every confidence value can be explained via the ConfidenceExplanation object,
which exposes: evidence count, supporting evidence, contradictions, calibration
history, and the exact formula used.

Model:
  Beta-Binomial with informative prior calibrated from SHR.

  alpha = ALPHA_PRIOR * SHR + validated_runtimes
  beta  = BETA_PRIOR * (1 - SHR) + failed_runtimes

  posterior_mean = alpha / (alpha + beta)

  confidence = posterior_mean * evidence_weight * recency_factor * diversity_factor

  Where:
    evidence_weight = 1 - exp(-evidence_count / EVIDENCE_SCALE)
      (saturating function — more evidence = more confidence, diminishing returns)
    recency_factor = 0.5 ^ (days_since / RECENCY_HALF_LIFE_DAYS)
      (exponential decay — half-life of 90 days)
    diversity_factor = 1 + log2(1 + num_providers) / 10
      (logarithmic — each provider adds decreasing marginal confidence)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import exp, log2


# ─── Model Parameters (all explainable) ───

# Beta distribution priors — weak/uninformative
# alpha=1, beta=1 → uniform prior (no assumption about reliability)
ALPHA_PRIOR = 1.0
BETA_PRIOR = 1.0

# Recency decay — evidence older than this contributes less
# Justification: organizational dynamics shift on a quarterly cadence.
# Evidence from 90 days ago is half as relevant as evidence from today.
RECENCY_HALF_LIFE_DAYS = 90.0

# Evidence scale — controls how fast evidence_weight saturates
# Round 48 FIX 5: reduced from 5.0 to 2.0 so that evidence_count=1
# produces evidence_weight ≈ 0.39 (not 0.18), and evidence_count=3
# produces ≈ 0.78. The old value (5.0) crushed all single-evidence
# LOs to ~0.15, making confidence non-discriminative.
EVIDENCE_SCALE = 2.0

# Recency floor — evidence never contributes less than this fraction
# Justification: old evidence is weaker but not worthless (historical baseline)
RECENCY_FLOOR = 0.3


@dataclass
class ConfidenceExplanation:
    """
    Full explanation of how a confidence value was computed.

    Every confidence value in Maestro returns both the float AND this explanation.
    The CEO can ask "why 0.78?" and get a complete, auditable answer.
    """
    value: float
    formula: str
    evidence_count: int
    supporting_evidence: int
    contradicting_evidence: int
    providers: list[str] = field(default_factory=list)
    validated_runtimes: int = 0
    failed_runtimes: int = 0
    calibration_shr: float = 0.0
    recency_factor: float = 1.0
    evidence_weight: float = 0.0
    diversity_factor: float = 1.0
    posterior_mean: float = 0.0
    last_seen: datetime | None = None
    days_since_last: int = 0

    def to_dict(self) -> dict:
        """Convert to a UI-friendly dict."""
        return {
            "value": round(self.value, 4),
            "formula": self.formula,
            "evidence_count": self.evidence_count,
            "supporting_evidence": self.supporting_evidence,
            "contradicting_evidence": self.contradicting_evidence,
            "providers": self.providers,
            "validated_runtimes": self.validated_runtimes,
            "failed_runtimes": self.failed_runtimes,
            "calibration_shr": round(self.calibration_shr, 4),
            "recency_factor": round(self.recency_factor, 4),
            "evidence_weight": round(self.evidence_weight, 4),
            "diversity_factor": round(self.diversity_factor, 4),
            "posterior_mean": round(self.posterior_mean, 4),
            "days_since_last": self.days_since_last,
        }


class ConfidenceCalculator:
    """
    Computes confidence scores from evidence using Bayesian inference.

    All methods are pure functions — no state, no side effects.
    Every method returns both the float value AND a ConfidenceExplanation.

    The SHR (Surprise Hit Rate) is used to calibrate the prior:
    - If SHR is high (Maestro has been right), the prior shifts toward success
    - If SHR is low (Maestro has been wrong), the prior shifts toward failure
    - If SHR is 0 (no history yet), uses uniform prior (alpha=1, beta=1)
    """

    # ─── Law Confidence ───

    @staticmethod
    def compute_law_confidence(
        validated_runtimes: int,
        failed_runtimes: int,
        evidence_count: int,
        providers: set[str],
        last_validated: datetime | None = None,
        calibration_shr: float = 0.0,
    ) -> float:
        """Compute confidence for an OrganizationalLaw. Returns float only."""
        return ConfidenceCalculator.compute_law_confidence_explained(
            validated_runtimes, failed_runtimes, evidence_count,
            providers, last_validated, calibration_shr
        ).value

    @staticmethod
    def compute_law_confidence_explained(
        validated_runtimes: int,
        failed_runtimes: int,
        evidence_count: int,
        providers: set[str],
        last_validated: datetime | None = None,
        calibration_shr: float = 0.0,
    ) -> ConfidenceExplanation:
        """
        Compute confidence for an OrganizationalLaw with full explanation.

        Model: Beta-Binomial with SHR-calibrated prior.

        alpha = ALPHA_PRIOR * shr + validated_runtimes
        beta  = BETA_PRIOR * (1 - shr) + failed_runtimes

        posterior_mean = alpha / (alpha + beta)
        evidence_weight = 1 - exp(-evidence_count / EVIDENCE_SCALE)
        diversity_factor = 1 + log2(1 + num_providers) / 10
        recency_factor = max(RECENCY_FLOOR, 0.5 ^ (days / HALF_LIFE))

        confidence = posterior_mean * evidence_weight * recency_factor * diversity_factor
        """
        # Use SHR to calibrate the prior
        # If SHR=0 (no history), use uniform prior (alpha=1, beta=1)
        # If SHR=0.83 (good track record), prior shifts: alpha=0.83, beta=0.17
        shr = calibration_shr if calibration_shr > 0 else 0.5  # uniform when no history
        alpha = ALPHA_PRIOR * shr + validated_runtimes
        beta = BETA_PRIOR * (1.0 - shr) + failed_runtimes
        posterior_mean = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.0

        # Evidence weight: saturating function
        # 1 piece → 0.18, 5 pieces → 0.63, 15 pieces → 0.95, 30 pieces → 0.997
        evidence_weight = 1.0 - exp(-evidence_count / EVIDENCE_SCALE) if evidence_count > 0 else 0.0

        # Diversity factor: logarithmic in number of providers
        # 1 provider → 1.0, 2 → 1.10, 3 → 1.16, 5 → 1.23
        diversity_factor = 1.0 + log2(1 + len(providers)) / 10.0

        # Recency decay
        recency_factor = 1.0
        days_since = 0
        if last_validated:
            now = datetime.now(timezone.utc)
            lv = last_validated if last_validated.tzinfo else last_validated.replace(tzinfo=timezone.utc)
            days_since = max(0, (now - lv).days)
            if days_since > 0:
                recency_factor = max(RECENCY_FLOOR, 0.5 ** (days_since / RECENCY_HALF_LIFE_DAYS))

        # Final confidence
        confidence = posterior_mean * evidence_weight * recency_factor * diversity_factor

        # D3 fix: Cap confidence below 1.0 to prevent false certainty.
        # The Beta-Binomial formula can produce 0.994+ when validated_runtimes
        # is high and failed_runtimes is 0. But 81 validations from 65 signals
        # means the law was validated by signals that may not be truly related
        # (over-matching relevance heuristic). An executive seeing "100% confident
        # Organizational Law" from a handful of signals is the opposite of the
        # product's epistemic honesty thesis.
        #
        # Cap: confidence can NEVER reach 1.0 (epistemic humility).
        # With <10 unique signals, cap at 0.80.
        # With <50 unique signals, cap at 0.90.
        # With <200 unique signals, cap at 0.95.
        # With 200+ signals, cap at 0.98.
        # This preserves ranking while preventing false certainty.
        if evidence_count < 10:
            confidence = min(confidence, 0.80)
        elif evidence_count < 50:
            confidence = min(confidence, 0.90)
        elif evidence_count < 200:
            confidence = min(confidence, 0.95)
        else:
            confidence = min(confidence, 0.98)

        confidence = max(0.0, min(1.0, confidence))

        formula = (
            f"posterior({alpha:.2f}, {beta:.2f}) = {posterior_mean:.4f} × "
            f"evidence_weight({evidence_weight:.4f}) × "
            f"recency({recency_factor:.4f}) × "
            f"diversity({diversity_factor:.4f}) = {confidence:.4f}"
        )

        return ConfidenceExplanation(
            value=confidence,
            formula=formula,
            evidence_count=evidence_count,
            supporting_evidence=validated_runtimes,
            contradicting_evidence=failed_runtimes,
            providers=sorted(providers),
            validated_runtimes=validated_runtimes,
            failed_runtimes=failed_runtimes,
            calibration_shr=shr,
            recency_factor=recency_factor,
            evidence_weight=evidence_weight,
            diversity_factor=diversity_factor,
            posterior_mean=posterior_mean,
            last_seen=last_validated,
            days_since_last=days_since,
        )

    # ─── Learning Object Confidence ───

    @staticmethod
    def compute_lo_confidence(
        evidence_count: int,
        contradiction_count: int,
        providers: set[str],
        first_seen: datetime,
        last_seen: datetime,
        calibration_shr: float = 0.0,
        authority_weights: list[float] | None = None,
    ) -> float:
        """Compute confidence for a LearningObject. Returns float only."""
        return ConfidenceCalculator.compute_lo_confidence_explained(
            evidence_count, contradiction_count, providers,
            first_seen, last_seen, calibration_shr, authority_weights
        ).value

    @staticmethod
    def compute_lo_confidence_explained(
        evidence_count: int,
        contradiction_count: int,
        providers: set[str],
        first_seen: datetime,
        last_seen: datetime,
        calibration_shr: float = 0.0,
        authority_weights: list[float] | None = None,
    ) -> ConfidenceExplanation:
        """
        Compute confidence for a LearningObject with full explanation.

        Same Beta-Binomial model, but using evidence/contradiction
        instead of validated/failed.

        H-05 fix: authority_weights modulates evidence contribution.
        - If None or empty: neutral (1.0 multiplier, backward-compatible)
        - If provided: mean(authority_weights) scales evidence_count
          (high-authority evidence counts more toward alpha)
        - Authority NEVER reduces evidence below 0 — it modulates, never
          silences (P6).
        """
        shr = calibration_shr if calibration_shr > 0 else 0.5

        # H-05: authority-weighted evidence count
        # Mean authority > 0.5 boosts evidence; mean < 0.5 reduces it.
        # Neutral (0.5) produces no change — backward-compatible.
        if authority_weights:
            mean_authority = sum(authority_weights) / len(authority_weights)
            # Scale evidence_count by (2 * mean_authority) so 0.5 → 1.0 (neutral)
            authority_factor = 2.0 * mean_authority
            weighted_evidence = evidence_count * authority_factor
        else:
            mean_authority = 0.5
            authority_factor = 1.0
            weighted_evidence = float(evidence_count)

        alpha = ALPHA_PRIOR * shr + weighted_evidence
        beta = BETA_PRIOR * (1.0 - shr) + contradiction_count
        posterior_mean = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.0

        evidence_weight = 1.0 - exp(-weighted_evidence / EVIDENCE_SCALE) if weighted_evidence > 0 else 0.0
        diversity_factor = 1.0 + log2(1 + len(providers)) / 10.0

        now = datetime.now(timezone.utc)
        ls = last_seen if last_seen.tzinfo else last_seen.replace(tzinfo=timezone.utc)
        days_since = max(0, (now - ls).days)
        recency_factor = max(RECENCY_FLOOR, 0.5 ** (days_since / RECENCY_HALF_LIFE_DAYS)) if days_since > 0 else 1.0

        confidence = posterior_mean * evidence_weight * recency_factor * diversity_factor
        confidence = max(0.0, min(1.0, confidence))

        formula = (
            f"posterior({alpha:.2f}, {beta:.2f}) = {posterior_mean:.4f} × "
            f"evidence_weight({evidence_weight:.4f}) × "
            f"recency({recency_factor:.4f}) × "
            f"diversity({diversity_factor:.4f})"
            + (f" × authority({authority_factor:.4f}, mean={mean_authority:.2f})" if authority_weights else "")
            + f" = {confidence:.4f}"
        )

        return ConfidenceExplanation(
            value=confidence,
            formula=formula,
            evidence_count=evidence_count,
            supporting_evidence=evidence_count,
            contradicting_evidence=contradiction_count,
            providers=sorted(providers),
            calibration_shr=shr,
            recency_factor=recency_factor,
            evidence_weight=evidence_weight,
            diversity_factor=diversity_factor,
            posterior_mean=posterior_mean,
            last_seen=last_seen,
            days_since_last=days_since,
        )

    # ─── Pattern Strength ───

    @staticmethod
    def compute_pattern_strength(
        evidence_count: int,
        coverage: int,
    ) -> float:
        """
        Compute pattern strength from evidence and coverage.

        Uses the same saturating function for evidence, plus a coverage factor.
        No arbitrary multipliers.
        """
        if evidence_count == 0:
            return 0.0
        # Evidence saturation
        evidence_factor = 1.0 - exp(-evidence_count / EVIDENCE_SCALE)
        # Coverage: saturating function — more teams = more generalizable
        coverage_factor = 1.0 - exp(-coverage / 3.0)  # 1 team → 0.28, 3 → 0.63, 6 → 0.86
        return max(0.0, min(1.0, evidence_factor * coverage_factor))

    # ─── Recommendation Confidence ───

    @staticmethod
    def compute_recommendation_confidence(
        evidence_count: int,
        contradiction_count: int,
        providers: set[str],
        linked_law_confidences: list[float],
        last_seen: datetime,
        calibration_shr: float = 0.0,
    ) -> ConfidenceExplanation:
        """
        Compute confidence for a Recommendation.

        A recommendation's confidence is derived from:
        1. The confidence of its linked laws (average, weighted by law confidence)
        2. The evidence volume supporting it
        3. Contradictions (CEO rejections, counter-examples)
        4. Provider diversity
        5. Recency of last evidence
        6. Calibration SHR

        No arbitrary formulas like `0.5 + count * 0.05`.
        """
        shr = calibration_shr if calibration_shr > 0 else 0.5

        # Law-based confidence: weighted average of linked law confidences
        if linked_law_confidences:
            # Weight each law by its own confidence (more confident laws weigh more)
            total_weight = sum(linked_law_confidences)
            if total_weight > 0:
                law_confidence = sum(c * c for c in linked_law_confidences) / total_weight
            else:
                law_confidence = sum(linked_law_confidences) / len(linked_law_confidences)
        else:
            # No linked laws — use evidence directly
            alpha = ALPHA_PRIOR * shr + evidence_count
            beta = BETA_PRIOR * (1.0 - shr) + contradiction_count
            law_confidence = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.0

        # Evidence weight (saturating)
        evidence_weight = 1.0 - exp(-evidence_count / EVIDENCE_SCALE) if evidence_count > 0 else 0.0

        # Contradiction penalty: more contradictions = lower confidence
        # Using Beta-Binomial: contradictions increase beta
        alpha = ALPHA_PRIOR * shr + max(evidence_count, 1)
        beta = BETA_PRIOR * (1.0 - shr) + contradiction_count
        contradiction_factor = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.0

        # Diversity
        diversity_factor = 1.0 + log2(1 + len(providers)) / 10.0

        # Recency
        now = datetime.now(timezone.utc)
        ls = last_seen if last_seen.tzinfo else last_seen.replace(tzinfo=timezone.utc)
        days_since = max(0, (now - ls).days)
        recency_factor = max(RECENCY_FLOOR, 0.5 ** (days_since / RECENCY_HALF_LIFE_DAYS)) if days_since > 0 else 1.0

        # Final: law confidence × evidence × contradiction × recency × diversity
        confidence = law_confidence * evidence_weight * contradiction_factor * recency_factor * diversity_factor
        confidence = max(0.0, min(1.0, confidence))

        formula = (
            f"law_conf({law_confidence:.4f}) × "
            f"evidence({evidence_weight:.4f}) × "
            f"contradiction({contradiction_factor:.4f}) × "
            f"recency({recency_factor:.4f}) × "
            f"diversity({diversity_factor:.4f}) = {confidence:.4f}"
        )

        return ConfidenceExplanation(
            value=confidence,
            formula=formula,
            evidence_count=evidence_count,
            supporting_evidence=evidence_count,
            contradicting_evidence=contradiction_count,
            providers=sorted(providers),
            calibration_shr=shr,
            recency_factor=recency_factor,
            evidence_weight=evidence_weight,
            diversity_factor=diversity_factor,
            posterior_mean=law_confidence,
            last_seen=last_seen,
            days_since_last=days_since,
        )

    # ─── Risk Probability (departure risk, bottleneck risk) ───

    @staticmethod
    def compute_risk_probability(
        signal_count: int,
        contradiction_count: int,
        providers: set[str],
        last_signal: datetime,
        calibration_shr: float = 0.0,
    ) -> ConfidenceExplanation:
        """
        Compute risk probability (e.g., departure risk, bottleneck risk).

        No hardcoded 0.71. Probability is derived from:
        - Number of risk signals detected
        - Contradicting signals (e.g., retention actions taken)
        - Provider diversity (Slack + Gmail = stronger signal)
        - Recency (recent signals = higher probability)
        - Calibration SHR
        """
        shr = calibration_shr if calibration_shr > 0 else 0.5

        alpha = ALPHA_PRIOR * shr + signal_count
        beta = BETA_PRIOR * (1.0 - shr) + contradiction_count
        posterior_mean = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.0

        evidence_weight = 1.0 - exp(-signal_count / EVIDENCE_SCALE) if signal_count > 0 else 0.0
        diversity_factor = 1.0 + log2(1 + len(providers)) / 10.0

        now = datetime.now(timezone.utc)
        ls = last_signal if last_signal.tzinfo else last_signal.replace(tzinfo=timezone.utc)
        days_since = max(0, (now - ls).days)
        recency_factor = max(RECENCY_FLOOR, 0.5 ** (days_since / RECENCY_HALF_LIFE_DAYS)) if days_since > 0 else 1.0

        probability = posterior_mean * evidence_weight * recency_factor * diversity_factor
        probability = max(0.0, min(1.0, probability))

        formula = (
            f"posterior({alpha:.2f}, {beta:.2f}) = {posterior_mean:.4f} × "
            f"evidence({evidence_weight:.4f}) × "
            f"recency({recency_factor:.4f}) × "
            f"diversity({diversity_factor:.4f}) = {probability:.4f}"
        )

        return ConfidenceExplanation(
            value=probability,
            formula=formula,
            evidence_count=signal_count,
            supporting_evidence=signal_count,
            contradicting_evidence=contradiction_count,
            providers=sorted(providers),
            calibration_shr=shr,
            recency_factor=recency_factor,
            evidence_weight=evidence_weight,
            diversity_factor=diversity_factor,
            posterior_mean=posterior_mean,
            last_seen=last_signal,
            days_since_last=days_since,
        )

    # ─── SHR ───

    @staticmethod
    def compute_shr(hits: int, misses: int) -> float:
        """Surprise Hit Rate — fraction of predictions that held up."""
        total = hits + misses
        return hits / total if total > 0 else 0.0

    @staticmethod
    def is_within_shr_band(shr: float, low: float = 0.80, high: float = 0.88) -> bool:
        """Check if SHR is within the target band."""
        return low <= shr <= high

    @staticmethod
    def compute_confidence_bucket(confidence: float) -> int:
        """Map confidence to a 0-9 bucket for calibration curves."""
        return min(9, int(confidence * 10))
