"""Loop 4 — Organizational Learning Composer.

CEO directive (auditor recommendation, CEO-validated): "Loop 4 —
Organizational Learning. This is where the moat compounds — the system
learning about its own delivery effectiveness."

The OrganizationalLearningComposer composes the final Organizational
Learning Ledger entry — one honest sentence (or paragraph) about what
Maestro learned across all 3 loops.

The entry is:
  - Honest: references actual cross-loop patterns
  - Signal-derived: based on real data from the ledger
  - Acknowledges sample-size limitations: "3 data points is not a trend"
  - Rich: ≥80 chars (the system learning about its own learning —
    richest of all the Learning Ledger entries)
  - NOT a template: two different patterns produce different entries

This is the capstone. Loops 1-3 each wrote their own honest sentence.
Loop 4 writes the sentence that connects them all.
"""

from __future__ import annotations

from typing import Any


class OrganizationalLearningComposer:
    """Compose the Organizational Learning Ledger entry.

    Usage:
        composer = OrganizationalLearningComposer()
        entry = composer.compose(patterns, sample_size=ledger.total_entries())
    """

    def compose(
        self,
        patterns: list,
        sample_size: int = 0,
        delivery_policies: list | None = None,
    ) -> str:
        """Compose the Organizational Learning Ledger entry.

        Args:
            patterns: List of CrossLoopPattern objects
            sample_size: Total number of learning entries in the ledger
            delivery_policies: Optional list of DeliveryPolicy objects

        Returns:
            One honest sentence/paragraph about what Maestro learned.
        """
        if not patterns and not delivery_policies:
            return (
                "Maestro has not yet detected any cross-loop patterns. "
                "More data is needed before organizational learning can be composed."
            )

        parts: list[str] = []

        # ── Part 1: The cross-loop patterns found ──────────────────────
        if patterns:
            parts.append(self._describe_patterns(patterns))

        # ── Part 2: The delivery policies learned ──────────────────────
        if delivery_policies:
            parts.append(self._describe_policies(delivery_policies))

        # ── Part 3: Sample-size honesty ────────────────────────────────
        # Maestro never claims a trend from 3 data points. It honestly
        # acknowledges the sample size.
        parts.append(self._sample_size_disclaimer(sample_size))

        # ── Part 4: Causality uncertainty ──────────────────────────────
        # Maestro never claims the patterns PROVE causation. They are
        # correlations.
        if patterns:
            parts.append(
                "Maestro does not claim these patterns prove causation — "
                "they are correlations observed in the data."
            )

        return " ".join(parts)

    def _describe_patterns(self, patterns: list) -> str:
        """Describe the cross-loop patterns found."""
        if len(patterns) == 1:
            return f"Cross-loop pattern detected: {patterns[0].description}"
        descriptions = [p.description for p in patterns[:3]]
        return f"Cross-loop patterns detected: {'; '.join(descriptions)}"

    def _describe_policies(self, policies: list) -> str:
        """Describe the delivery policies learned."""
        if len(policies) == 1:
            return f"Delivery policy learned: {policies[0].description}"
        descriptions = [p.description for p in policies[:3]]
        return f"Delivery policies learned: {'; '.join(descriptions)}"

    def _sample_size_disclaimer(self, sample_size: int) -> str:
        """Honest acknowledgment of sample size limitations."""
        if sample_size == 0:
            return "No data available."
        if sample_size < 5:
            return (
                f"This learning is based on {sample_size} data point(s) — "
                f"a small sample that may not represent a trend."
            )
        if sample_size < 10:
            return (
                f"This learning is based on {sample_size} data points — "
                f"a moderate sample; patterns should be treated as preliminary."
            )
        return f"This learning is based on {sample_size} data points."
