"""Loop 4 — Cross-Loop Pattern Detection.

CEO directive (auditor recommendation, CEO-validated): "Loop 4 —
Organizational Learning: cross-case pattern detection and delivery-policy
learning."

A pattern within a single loop is a data point. A pattern ACROSS loops
is a signal. "Ignored commitment Whispers were followed by broken
commitments 3 out of 3 times" — this spans Loop 1's Whisper/action and
Loop 1's outcome observation, and it tells Maestro something it couldn't
learn from any single loop.

The CrossLoopPatternDetector:
  - Takes an OrganizationalLearningLedger (entries from all 3 loops)
  - Finds correlations across entries (e.g., action="ignored" correlates
    with outcome="broken")
  - Returns CrossLoopPattern objects with: the pattern description, the
    case count, the source loops involved

Current patterns detected:
  1. ignored_whisper_then_broken_commitment: when the exec ignores a
     commitment Whisper, the commitment is later broken (Loop 1 cross-
     entry correlation)

Future patterns (deferred):
  - wrong_assumption_then_bad_decision: when a decision's assumption is
    wrong, the decision's outcome is bad (Loop 3 cross-entry)
  - meeting_topic_then_decision: when a meeting discusses a topic, a
    decision is later made about it (Loop 2 → Loop 3)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CrossLoopPattern:
    """A detected pattern across loops (or across entries within loops).

    Attributes:
        pattern_type: The pattern identifier ("ignored_whisper_then_broken_commitment")
        description: A human-readable sentence about the pattern
        case_count: How many cases exhibited this pattern
        source_loops: Which loops are involved
    """

    pattern_type: str
    description: str
    case_count: int
    source_loops: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pattern_type": self.pattern_type,
            "description": self.description,
            "case_count": self.case_count,
            "source_loops": list(self.source_loops),
        }


class CrossLoopPatternDetector:
    """Detect patterns across loops (and across entries within loops).

    Usage:
        detector = CrossLoopPatternDetector()
        patterns = detector.detect(ledger)
    """

    def detect(self, ledger: Any) -> list[CrossLoopPattern]:
        """Detect cross-loop patterns in the ledger.

        Args:
            ledger: An OrganizationalLearningLedger with entries from all 3 loops.

        Returns:
            List of CrossLoopPattern objects.
        """
        patterns: list[CrossLoopPattern] = []
        entries = ledger.get_all_entries() if hasattr(ledger, "get_all_entries") else []

        # Pattern 1: ignored_whisper_then_broken_commitment
        # When the exec ignores a commitment Whisper (action="ignored"),
        # the commitment is later broken (outcome="broken").
        commitment_entries = [e for e in entries if e.source_loop == "commitment"]
        ignored_then_broken = [
            e for e in commitment_entries
            if e.action == "ignored" and e.outcome == "broken"
        ]
        if len(ignored_then_broken) >= 2:
            count = len(ignored_then_broken)
            entities = [e.entity for e in ignored_then_broken]
            patterns.append(CrossLoopPattern(
                pattern_type="ignored_whisper_then_broken_commitment",
                description=(
                    f"commitment warnings that the executive ignored were followed by "
                    f"broken commitments in {count} case(s) ({', '.join(entities[:3])}). "
                    f"This suggests that ignoring commitment warnings correlates with "
                    f"commitment failure."
                ),
                case_count=count,
                source_loops=["commitment"],
            ))

        # Pattern 2: acted_whisper_then_honored_commitment (the positive version)
        # When the exec acts on a commitment Whisper, the commitment is honored.
        acted_then_honored = [
            e for e in commitment_entries
            if e.action == "acted" and e.outcome == "honored"
        ]
        if len(acted_then_honored) >= 2:
            count = len(acted_then_honored)
            entities = [e.entity for e in acted_then_honored]
            patterns.append(CrossLoopPattern(
                pattern_type="acted_whisper_then_honored_commitment",
                description=(
                    f"commitment warnings that the executive acted on were followed by "
                    f"honored commitments in {count} case(s) ({', '.join(entities[:3])}). "
                    f"This suggests that acting on commitment warnings correlates with "
                    f"commitment success."
                ),
                case_count=count,
                source_loops=["commitment"],
            ))

        # Pattern 3: wrong_hypothesis_in_decisions
        # When a decision's hypothesis was wrong (outcome contains negative words).
        decision_entries = [e for e in entries if e.source_loop == "decision"]
        wrong_decisions = [
            e for e in decision_entries
            if e.outcome and any(word in (e.outcome or "").lower() for word in ["missed", "broken", "churned", "failed", "did not"])
        ]
        if len(wrong_decisions) >= 2:
            count = len(wrong_decisions)
            entities = [e.entity for e in wrong_decisions]
            patterns.append(CrossLoopPattern(
                pattern_type="wrong_hypothesis_in_decisions",
                description=(
                    f"decision hypotheses were wrong in {count} case(s) ({', '.join(entities[:3])}). "
                    f"This suggests that the assumptions underlying these decisions need "
                    f"to be re-examined."
                ),
                case_count=count,
                source_loops=["decision"],
            ))

        # Sort by case_count descending
        patterns.sort(key=lambda p: p.case_count, reverse=True)
        return patterns
