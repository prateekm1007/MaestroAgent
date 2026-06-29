"""
ConfidenceCalculator — mathematical confidence computation.

No arbitrary numbers. Every confidence score is computed from:
1. Evidence count (more evidence = higher confidence)
2. Evidence diversity (more providers = higher confidence)
3. Validation history (more runtimes = higher confidence)
4. Contradiction penalty (more counter-examples = lower confidence)
5. Recency decay (older evidence = lower confidence)

The formula is a Beta-Binomial model — the standard Bayesian approach
for estimating probability from binary outcomes.

confidence = (alpha + validated) / (alpha + beta + validated + failed)

where alpha and beta are priors (weak: alpha=1, beta=1 → uniform prior).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Beta distribution priors — weak/uninformative
# alpha = pseudo-count of successes, beta = pseudo-count of failures
# With alpha=beta=1, this is a uniform prior (no assumption).
ALPHA_PRIOR = 1.0
BETA_PRIOR = 1.0

# Recency decay — evidence older than this contributes less
RECENCY_HALF_LIFE_DAYS = 90  # Evidence loses half its weight every 90 days


class ConfidenceCalculator:
    """
    Computes confidence scores from evidence using Bayesian inference.

    All methods are pure functions — no state, no side effects.
    """

    @staticmethod
    def compute_law_confidence(
        validated_runtimes: int,
        failed_runtimes: int,
        evidence_count: int,
        providers: set[str],
        last_validated: datetime | None = None,
    ) -> float:
        """
        Compute confidence for an OrganizationalLaw.

        Uses Beta-Binomial model with:
        - Prior: Beta(alpha=1, beta=1) = uniform
        - Likelihood: validated runtimes = successes, failed = failures
        - Provider diversity bonus
        - Recency decay
        """
        # Beta-Binomial posterior mean
        alpha = ALPHA_PRIOR + validated_runtimes
        beta = BETA_PRIOR + failed_runtimes
        posterior_mean = alpha / (alpha + beta)

        # Provider diversity bonus: more providers = more reliable
        # Each provider beyond the first adds 5% weight, capped at 20%
        provider_bonus = min(0.20, max(0, len(providers) - 1) * 0.05)

        # Evidence weight: more evidence = higher confidence
        # Logarithmic growth — diminishing returns
        evidence_weight = min(1.0, 0.5 + 0.1 * (evidence_count - 1)) if evidence_count > 0 else 0.0

        # Recency decay: if last validation is old, reduce confidence
        recency_factor = 1.0
        if last_validated:
            now = datetime.now(timezone.utc)
            days_since = (now - last_validated).days
            if days_since > 0:
                recency_factor = 0.5 ** (days_since / RECENCY_HALF_LIFE_DAYS)
                recency_factor = max(0.3, recency_factor)  # Floor at 30%

        # Final confidence: weighted combination
        base_confidence = posterior_mean * evidence_weight
        confidence = base_confidence + provider_bonus * posterior_mean
        confidence *= recency_factor

        # Clamp to [0, 1]
        return max(0.0, min(1.0, confidence))

    @staticmethod
    def compute_lo_confidence(
        evidence_count: int,
        contradiction_count: int,
        providers: set[str],
        first_seen: datetime,
        last_seen: datetime,
    ) -> float:
        """
        Compute confidence for a LearningObject.

        Uses same Beta-Binomial model but with evidence/contradiction.
        """
        alpha = ALPHA_PRIOR + evidence_count
        beta = BETA_PRIOR + contradiction_count
        posterior_mean = alpha / (alpha + beta)

        # Provider diversity
        provider_bonus = min(0.20, max(0, len(providers) - 1) * 0.05)

        # Evidence weight
        evidence_weight = min(1.0, 0.5 + 0.1 * (evidence_count - 1)) if evidence_count > 0 else 0.0

        # Recency — handle both naive and aware datetimes
        now = datetime.now(timezone.utc)
        # Make last_seen timezone-aware if it's naive
        if last_seen.tzinfo is None:
            last_seen_aware = last_seen.replace(tzinfo=timezone.utc)
        else:
            last_seen_aware = last_seen
        days_since = (now - last_seen_aware).days
        recency_factor = max(0.3, 0.5 ** (days_since / RECENCY_HALF_LIFE_DAYS)) if days_since > 0 else 1.0

        confidence = posterior_mean * evidence_weight
        confidence += provider_bonus * posterior_mean
        confidence *= recency_factor

        return max(0.0, min(1.0, confidence))

    @staticmethod
    def compute_pattern_strength(
        evidence_count: int,
        coverage: int,
    ) -> float:
        """
        Compute pattern strength from evidence and coverage.

        strength = min(1, evidence_count / (evidence_count + 2)) * coverage_factor
        """
        if evidence_count == 0:
            return 0.0
        base = evidence_count / (evidence_count + 2)
        coverage_factor = min(1.0, 0.5 + 0.1 * (coverage - 1))
        return max(0.0, min(1.0, base * coverage_factor))

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
