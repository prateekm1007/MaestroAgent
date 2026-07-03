"""Loop 1.5 — Cold-Start Trust Ladder Mode.

External auditor (AUDITOR-EXTERNAL-REVIEW-3):
> Cold-start trust ladder mode — retrieval-only on day 1, no Whispers
> until enough evidence.

The trust ladder has 3 rungs:
  - RETRIEVAL_ONLY (0-4 signals): Maestro listens, doesn't speak. No
    Whispers fire. The exec can still Ask Maestro (retrieval works),
    but Maestro doesn't push Whispers. This prevents false authority
    on day 1.
  - LOW_CONFIDENCE_WHISPERS (5-14 signals): Whispers fire but are
    marked low confidence. The exec sees them but knows Maestro is
    still learning the organization.
  - FULL_WHISPERS (15+ signals): Normal operation. Whispers fire at
    full confidence.

Safety valve: high-stakes signals (broken commitment, churn, champion
quiet) override the suppression. If a customer churns on day 1, Maestro
must speak — even if it's only day 1. The trust ladder is a default,
not a hard rule.

This is the difference between a tool that speaks with false authority
on day 1 and a tool that earns trust by listening first.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class TrustLadderRung(str, Enum):
    """The 3 rungs of the cold-start trust ladder."""

    RETRIEVAL_ONLY = "retrieval_only"
    LOW_CONFIDENCE_WHISPERS = "low_confidence_whispers"
    FULL_WHISPERS = "full_whispers"


# Signal count thresholds for each rung
RETRIEVAL_ONLY_THRESHOLD = 5  # 0-4 signals → retrieval only
LOW_CONFIDENCE_THRESHOLD = 15  # 5-14 signals → low confidence; 15+ → full


class ColdStartMode:
    """Determine the trust ladder rung based on signal count.

    Usage:
        cold_start = ColdStartMode(signal_count=3)
        if cold_start.should_suppress_whispers():
            # Don't fire Whispers — retrieval only
        else:
            # Fire Whispers (optionally marked low confidence)
    """

    def __init__(
        self,
        signal_count: int = 0,
        has_high_stakes_signal: bool = False,
    ) -> None:
        self._signal_count = signal_count
        self._has_high_stakes = has_high_stakes_signal
        self._rung = self._compute_rung(signal_count)

    def _compute_rung(self, signal_count: int) -> TrustLadderRung:
        """Compute the trust ladder rung from signal count."""
        if signal_count < RETRIEVAL_ONLY_THRESHOLD:
            return TrustLadderRung.RETRIEVAL_ONLY
        if signal_count < LOW_CONFIDENCE_THRESHOLD:
            return TrustLadderRung.LOW_CONFIDENCE_WHISPERS
        return TrustLadderRung.FULL_WHISPERS

    @property
    def rung(self) -> TrustLadderRung:
        """The current trust ladder rung (based on signal count)."""
        return self._rung

    @property
    def is_low_confidence(self) -> bool:
        """True if Whispers should be marked low confidence (rung 2)."""
        return self._rung == TrustLadderRung.LOW_CONFIDENCE_WHISPERS

    def should_suppress_whispers(self) -> bool:
        """Whether Whispers should be suppressed.

        Returns True if:
          - Rung is RETRIEVAL_ONLY AND no high-stakes signal override

        Returns False if:
          - Rung is LOW_CONFIDENCE_WHISPERS or FULL_WHISPERS
          - Rung is RETRIEVAL_ONLY but a high-stakes signal overrides
            (broken commitment, churn, champion quiet — Maestro must speak)
        """
        if self._rung != TrustLadderRung.RETRIEVAL_ONLY:
            return False
        # In RETRIEVAL_ONLY, suppress UNLESS high-stakes override
        if self._has_high_stakes:
            return False  # Override — Maestro must speak
        return True

    def whisper_confidence_level(self) -> str:
        """The confidence level to mark on Whispers that DO fire.

        Returns:
          - "low" if in LOW_CONFIDENCE_WHISPERS rung
          - "full" otherwise (FULL_WHISPERS or high-stakes override)
        """
        if self._rung == TrustLadderRung.LOW_CONFIDENCE_WHISPERS:
            return "low"
        return "full"

    def to_dict(self) -> dict:
        """Serialize for API responses / debugging."""
        return {
            "rung": self._rung.value,
            "signal_count": self._signal_count,
            "has_high_stakes_signal": self._has_high_stakes,
            "should_suppress_whispers": self.should_suppress_whispers(),
            "whisper_confidence_level": self.whisper_confidence_level(),
            "thresholds": {
                "retrieval_only": RETRIEVAL_ONLY_THRESHOLD,
                "low_confidence": LOW_CONFIDENCE_THRESHOLD,
            },
        }
