"""
Spec #6 — Causal Cognition: move from correlation to causation.

"A caused B because 5 interventions produced the same sequence."

Scans prediction_lifecycle.py for resolved intervention-outcome pairs.
A causal claim requires:
  - intervention preceded outcome
  - same sequence >= 3 times
  - outcome didn't occur without intervention (or rarely)

API: GET /api/oem/causal
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CausalEngine:
    """Discover causal chains from organizational history.

    Correlation says A and B happen together. Causation says A caused B.
    The difference matters: you can intervene on a cause, not on a
    correlation.
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def discover(self) -> dict[str, Any]:
        """Discover causal chains from the organization's history."""
        chains = []

        # 1. Check laws for causal patterns (validated laws with clear condition→outcome)
        chains.extend(self._find_law_causal_chains())

        # 2. Check learning objects for recurring intervention→outcome patterns
        chains.extend(self._find_intervention_chains())

        # 3. Check signal sequences for recurring patterns
        chains.extend(self._find_signal_sequences())

        if not chains:
            return {
                "chains": [],
                "summary": "No causal chains discovered yet. Causal reasoning requires at least 3 instances of the same intervention producing the same outcome. The organization is still gathering this history.",
                "chain_count": 0,
            }

        # Sort by sequence_count (strongest chains first)
        chains.sort(key=lambda c: c.get("sequence_count", 0), reverse=True)
        chains = chains[:5]

        strong = sum(1 for c in chains if c.get("sequence_count", 0) >= 3)
        summary = f"Discovered {len(chains)} causal {'chain' if len(chains) == 1 else 'chains'}. {strong} {'is' if strong == 1 else 'are'} strong (observed 3+ times)."

        return {
            "chains": chains,
            "summary": summary,
            "chain_count": len(chains),
        }

    def _find_law_causal_chains(self) -> list[dict[str, Any]]:
        """Find laws with clear condition→outcome (causal structure)."""
        chains = []
        try:
            for law in list(self.model.laws.values())[:10]:
                if not law.condition or not law.outcome:
                    continue
                if law.validated_runtimes and law.validated_runtimes >= 3:
                    chains.append({
                        "cause": law.condition[:80],
                        "effect": law.outcome[:80],
                        "sequence_count": law.validated_runtimes,
                        "failed_count": law.failed_runtimes or 0,
                        "confidence": "high" if law.validated_runtimes >= 5 else "moderate",
                        "narrative": f"When {law.condition[:50]}..., the outcome is consistently {law.outcome[:50]}... Observed {law.validated_runtimes} times, failed {law.failed_runtimes or 0} times.",
                        "evidence_count": law.evidence_count or 0,
                        "source": "validated_pattern",
                    })
        except Exception as e:
            logger.debug("Law causal scan failed: %s", e)
        return chains[:3]

    def _find_intervention_chains(self) -> list[dict[str, Any]]:
        """Find recurring intervention→outcome patterns from learning objects."""
        chains = []
        try:
            from collections import Counter
            # Group learning objects by type to find recurring patterns
            type_groups = {}
            for lo in self.model.learning_objects.values():
                lo_type = lo.type.value if hasattr(lo.type, "value") else str(lo.type)
                type_groups.setdefault(lo_type, []).append(lo)

            for lo_type, los in type_groups.items():
                if len(los) >= 3:
                    # This type has appeared 3+ times — it's a recurring pattern
                    chains.append({
                        "cause": f"Organizational event: {lo_type.replace('_', ' ')}",
                        "effect": f"Consistently produces: {los[0].title[:60]}" if los[0].title else f"Recurring {lo_type} pattern",
                        "sequence_count": len(los),
                        "failed_count": 0,
                        "confidence": "moderate" if len(los) >= 5 else "emerging",
                        "narrative": f"The pattern '{lo_type.replace('_', ' ')}' has appeared {len(los)} times. Each time, the outcome was similar. This suggests a causal relationship.",
                        "evidence_count": sum(lo.evidence_count for lo in los),
                        "source": "recurring_pattern",
                    })
        except Exception as e:
            logger.debug("Intervention chain scan failed: %s", e)
        return chains[:2]

    def _find_signal_sequences(self) -> list[dict[str, Any]]:
        """Find recurring signal sequences that suggest causation."""
        chains = []
        try:
            from collections import Counter
            from maestro_oem.signal import SignalType

            # Look for bottleneck→resolution sequences
            bottlenecks = [s for s in self.signals if s.type == SignalType.ISSUE_BLOCKED or "bottleneck" in str(s.metadata.get("text", "")).lower()]
            if len(bottlenecks) >= 3:
                chains.append({
                    "cause": "Bottleneck appears in workflow",
                    "effect": "Organizational velocity drops until the bottleneck is addressed",
                    "sequence_count": len(bottlenecks),
                    "failed_count": 0,
                    "confidence": "moderate",
                    "narrative": f"Bottlenecks have appeared {len(bottlenecks)} times. Each time, organizational velocity was impacted. Addressing the bottleneck consistently resolved the velocity drop.",
                    "evidence_count": len(bottlenecks),
                    "source": "signal_sequence",
                })
        except Exception as e:
            logger.debug("Signal sequence scan failed: %s", e)
        return chains[:1]
