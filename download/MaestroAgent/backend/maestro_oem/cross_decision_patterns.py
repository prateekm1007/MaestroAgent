"""Loop 3 — Cross-Decision Pattern Detection.

CEO directive (auditor recommendation, CEO-validated): "Loop 3 — Decision
Intelligence. Decisions have intent, assumptions, hypotheses, and outcomes."

A single decision is a data point. A pattern across decisions is a signal.
If the same assumption is wrong across 3 decisions, that's a pattern —
Maestro connects decisions into a narrative about which assumptions keep
failing.

The CrossDecisionPatternDetector:
  - Takes a list of decisions (all with assumptions + outcome populated)
  - For each assumption text, counts how many decisions used it AND had
    a wrong hypothesis (outcome contradicted the assumption's implied
    prediction)
  - Returns CrossDecisionPattern objects for assumptions that appear in
    >= min_decisions decisions with wrong hypotheses

A pattern includes:
  - assumption_text: the recurring wrong assumption
  - decision_count: how many decisions used it with a wrong outcome
  - decision_intents: the intents of those decisions (for the narrative)
  - description: a human-readable sentence ("the assumption 'Globex will
    renew if we ship on time' was wrong in 3 decisions: ...")

This is the difference between "you made 3 decisions" and "you made 3
decisions based on the same wrong assumption — this assumption needs to
be re-examined."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CrossDecisionPattern:
    """A detected pattern across multiple decisions.

    Attributes:
        assumption_text: The recurring wrong assumption
        decision_count: How many decisions used it with a wrong outcome
        decision_intents: The intents of those decisions (for the narrative)
        description: A human-readable sentence about the pattern
    """

    assumption_text: str
    decision_count: int
    decision_intents: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "assumption_text": self.assumption_text,
            "decision_count": self.decision_count,
            "decision_intents": list(self.decision_intents),
            "description": self.description,
        }


class CrossDecisionPatternDetector:
    """Detect patterns across multiple decisions.

    Usage:
        detector = CrossDecisionPatternDetector()
        patterns = detector.detect(decisions, min_decisions=2)
    """

    # Ordinal lookup for human-readable frequency
    _ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}

    def detect(
        self,
        decisions: list,
        min_decisions: int = 2,
    ) -> list[CrossDecisionPattern]:
        """Detect cross-decision patterns.

        Args:
            decisions: List of Decision objects (each with assumptions + outcome populated)
            min_decisions: Minimum number of decisions for an assumption to be a pattern

        Returns:
            List of CrossDecisionPattern objects, sorted by decision_count descending.
        """
        if not decisions or min_decisions < 2:
            return []

        # Build a map: assumption_text → list of (decision_intent, was_wrong)
        assumption_map: dict[str, list[tuple[str, bool]]] = {}
        for decision in decisions:
            try:
                assumptions = getattr(decision, "assumptions", []) or []
                outcome = getattr(decision, "outcome", None)
                intent = getattr(decision, "intent", "Unknown")
                hypothesis = getattr(decision, "hypothesis", None)

                # Determine if this decision's hypothesis was wrong
                was_wrong = False
                if outcome and hypothesis:
                    outcome_text = outcome.get("text", "") if isinstance(outcome, dict) else str(outcome)
                    hypothesis_text = hypothesis.get("text", "") if isinstance(hypothesis, dict) else str(hypothesis)
                    was_wrong = self._hypothesis_was_wrong(hypothesis_text, outcome_text)

                for a in assumptions:
                    a_text = a.get("text", "") if isinstance(a, dict) else str(a)
                    if not a_text:
                        continue
                    # Normalize the assumption text for grouping (lowercase)
                    key = a_text.lower().strip()
                    if key not in assumption_map:
                        assumption_map[key] = []
                    assumption_map[key].append((intent, was_wrong))
            except Exception:
                continue

        # Filter to patterns meeting the threshold (only wrong assumptions count)
        patterns: list[CrossDecisionPattern] = []
        for assumption_text_lower, occurrences in assumption_map.items():
            # Only count decisions where the hypothesis was wrong
            wrong_decisions = [(intent, w) for intent, w in occurrences if w]
            if len(wrong_decisions) >= min_decisions:
                count = len(wrong_decisions)
                intents = [intent for intent, _ in wrong_decisions]
                ordinal = self._ORDINALS.get(count, str(count))

                # Build the description
                if count <= 3:
                    intents_str = ", ".join(intents)
                else:
                    intents_str = ", ".join(intents[:3]) + f", and {count - 3} more"

                description = (
                    f"the assumption '{assumption_text_lower}' was wrong in {count} "
                    f"decisions ({intents_str}). This is the {ordinal} time this "
                    f"assumption has failed — it needs to be re-examined."
                )
                patterns.append(CrossDecisionPattern(
                    assumption_text=assumption_text_lower,
                    decision_count=count,
                    decision_intents=intents,
                    description=description,
                ))

        # Sort by decision_count descending (most frequent patterns first)
        patterns.sort(key=lambda p: p.decision_count, reverse=True)
        return patterns

    def _hypothesis_was_wrong(self, hypothesis: str, outcome: str) -> bool:
        """Check if the outcome contradicts the hypothesis.

        Heuristic: if the outcome contains ANY negative words, the hypothesis
        was (at least partially) wrong. Mixed outcomes (e.g., "Shipped on
        time, Globex did not renew") count as wrong because the hypothesis
        predicted a fully positive outcome.

        This is deliberately sensitive to negative words — false positives
        (flagging a hypothesis as wrong when it was partially right) are
        acceptable because the pattern description still references the
        actual outcome. False negatives (missing a wrong hypothesis) are
        worse — they'd hide a failing pattern.
        """
        o_lower = outcome.lower()
        negative = {"missed", "broken", "churned", "failed", "late", "delayed", "lost", "did not", "not renew", "did not renew"}

        # If the outcome contains ANY negative words, the hypothesis was wrong
        if any(word in o_lower for word in negative):
            return True
        return False
