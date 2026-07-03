"""Loop 3 — Decision Intelligence Loop.

CEO directive (auditor recommendation, CEO-validated): "Loop 3 — Decision
Intelligence. Decisions have intent, assumptions, hypotheses, and outcomes.
This exercises the claim_type epistemic types (assumption, inference,
prediction, outcome) more deeply than Loops 1 and 2 did."

The loop:
  1. record_assumptions(decision, assumptions)  — PROPOSED → ASSUMPTIONS_RECORDED
     Each assumption gets claim_type="assumption"
  2. state_hypothesis(decision, hypothesis)     — ASSUMPTIONS_RECORDED → HYPOTHESIS_STATED
     The hypothesis gets claim_type="prediction"
  3. decide(decision, decision_text)            — HYPOTHESIS_STATED → DECIDED
     Records the chosen course of action
  4. observe_outcome(decision, outcome)         — DECIDED → OUTCOME_OBSERVED
     The outcome gets claim_type="outcome"
  5. record_learning(decision)                  — OUTCOME_OBSERVED → LEARNING_RECORDED
     Writes a Decision Learning Ledger entry

The Decision Learning Ledger entry is honest, signal-derived, references
the actual decision + assumptions + hypothesis + outcome, and acknowledges
causality uncertainty (richness lesson from Loop 2 audit — entries must
be ≥50 chars, not the 97-char shorthand).

When the hypothesis was WRONG (outcome contradicts it), the entry honestly
says so — no spin. Maestro never invents precision.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from maestro_oem.decision_v2 import Decision, DecisionStatus

logger = logging.getLogger(__name__)


class DecisionIntelligenceLoop:
    """Wires the Decision lifecycle: record_assumptions → state_hypothesis →
    decide → observe_outcome → record_learning.

    Usage:
        loop = DecisionIntelligenceLoop()
        loop.record_assumptions(decision, assumptions=[...])
        loop.state_hypothesis(decision, hypothesis="...")
        loop.decide(decision, decision_text="...")
        loop.observe_outcome(decision, outcome="...")
        entry = loop.record_learning(decision)
    """

    def record_assumptions(
        self,
        decision: Decision,
        assumptions: list[dict],
    ) -> None:
        """Transition PROPOSED → ASSUMPTIONS_RECORDED.

        Each assumption is recorded with claim_type="assumption".

        Args:
            decision: The decision to record assumptions for
            assumptions: List of dicts, each with at least "text" and "source"
        """
        if decision.status != DecisionStatus.PROPOSED:
            logger.warning(
                "DecisionIntelligenceLoop.record_assumptions: decision %s is in state %s, expected PROPOSED",
                decision.decision_id, decision.status,
            )
            return

        decision.assumptions = []
        for a in assumptions:
            assumption_dict = {
                "text": a.get("text", ""),
                "source": a.get("source", ""),
                "claim_type": "assumption",
            }
            decision.assumptions.append(assumption_dict)

        decision.status = DecisionStatus.ASSUMPTIONS_RECORDED

    def state_hypothesis(
        self,
        decision: Decision,
        hypothesis: str,
    ) -> None:
        """Transition ASSUMPTIONS_RECORDED → HYPOTHESIS_STATED.

        The hypothesis is a conditional falsifiable prediction with
        claim_type="hypothesis" (C2 fix: distinct from "prediction" which
        is a direct forecast. A hypothesis has "if X then Y" structure and
        is falsifiable — the decision lifecycle tests it against the outcome).

        Args:
            decision: The decision to state a hypothesis for
            hypothesis: The falsifiable prediction ("SSO will ship by Q4 and Globex will renew")
        """
        if decision.status != DecisionStatus.ASSUMPTIONS_RECORDED:
            logger.warning(
                "DecisionIntelligenceLoop.state_hypothesis: decision %s is in state %s, expected ASSUMPTIONS_RECORDED",
                decision.decision_id, decision.status,
            )
            return

        decision.hypothesis = {
            "text": hypothesis,
            "claim_type": "hypothesis",
        }
        decision.status = DecisionStatus.HYPOTHESIS_STATED

    def decide(
        self,
        decision: Decision,
        decision_text: str,
    ) -> None:
        """Transition HYPOTHESIS_STATED → DECIDED.

        Records the chosen course of action.

        Args:
            decision: The decision being made
            decision_text: The chosen course of action ("Prioritize SSO for Q4")
        """
        if decision.status != DecisionStatus.HYPOTHESIS_STATED:
            logger.warning(
                "DecisionIntelligenceLoop.decide: decision %s is in state %s, expected HYPOTHESIS_STATED",
                decision.decision_id, decision.status,
            )
            return

        decision.decision_text = decision_text
        decision.status = DecisionStatus.DECIDED

    def observe_outcome(
        self,
        decision: Decision,
        outcome: str,
    ) -> None:
        """Transition DECIDED → OUTCOME_OBSERVED.

        The outcome is recorded with claim_type="outcome".

        Args:
            decision: The decision whose outcome is being observed
            outcome: What actually happened ("SSO shipped, Globex renewed")
        """
        if decision.status != DecisionStatus.DECIDED:
            logger.warning(
                "DecisionIntelligenceLoop.observe_outcome: decision %s is in state %s, expected DECIDED",
                decision.decision_id, decision.status,
            )
            return

        decision.outcome = {
            "text": outcome,
            "claim_type": "outcome",
        }
        decision.status = DecisionStatus.OUTCOME_OBSERVED

    def record_learning(self, decision: Decision) -> str:
        """Transition OUTCOME_OBSERVED → LEARNING_RECORDED. Write the learning entry.

        The Decision Learning Ledger entry is one honest sentence about
        what Maestro learned from this decision's trajectory. It references:
          - The decision intent + entity
          - The assumptions made
          - The hypothesis stated
          - The observed outcome
          - Whether the hypothesis was right or wrong (honest — no spin)
          - Causality uncertainty acknowledgment (richness lesson from Loop 2)

        Returns:
            The learning entry (also persisted on the decision object).
        """
        if decision.status != DecisionStatus.OUTCOME_OBSERVED:
            logger.warning(
                "DecisionIntelligenceLoop.record_learning: decision %s is in state %s, expected OUTCOME_OBSERVED",
                decision.decision_id, decision.status,
            )
            return ""

        entry = self._compose_learning_entry(decision)
        decision.learning_entry = entry
        decision.status = DecisionStatus.LEARNING_RECORDED
        return entry

    def _compose_learning_entry(self, decision: Decision) -> str:
        """Compose one honest sentence about what Maestro learned from this decision.

        Signal-derived, not templated. References the actual decision,
        assumptions, hypothesis, and outcome. Honestly says when the
        hypothesis was wrong (no spin). Acknowledges causality uncertainty
        (richness lesson from Loop 2 — entries must be ≥50 chars).
        """
        parts: list[str] = []

        # ── Part 1: The decision + intent ──────────────────────────────
        parts.append(
            f"The decision to '{decision.intent}' for {decision.entity} was made"
        )

        # ── Part 2: The assumptions ────────────────────────────────────
        if decision.assumptions:
            assumption_count = len(decision.assumptions)
            if assumption_count == 1:
                parts.append(f"based on 1 assumption: {decision.assumptions[0].get('text', '')}")
            else:
                parts.append(f"based on {assumption_count} assumptions")
        else:
            parts.append("based on no recorded assumptions")

        # ── Part 3: The hypothesis + whether it was right ──────────────
        if decision.hypothesis and decision.outcome:
            hypothesis_text = decision.hypothesis.get("text", "")
            outcome_text = decision.outcome.get("text", "")

            # Check if the hypothesis was right or wrong
            hypothesis_was_right = self._hypothesis_matches_outcome(hypothesis_text, outcome_text)

            if hypothesis_was_right:
                parts.append(f"the hypothesis ('{hypothesis_text[:60]}') was confirmed by the outcome ('{outcome_text[:60]}')")
            else:
                parts.append(f"the hypothesis ('{hypothesis_text[:60]}') was WRONG — the outcome was '{outcome_text[:60]}'")
        elif decision.hypothesis:
            parts.append(f"a hypothesis was stated: {decision.hypothesis.get('text', '')[:60]}")

        # ── Part 4: The outcome ────────────────────────────────────────
        if decision.outcome:
            parts.append(f"the observed outcome was: {decision.outcome.get('text', '')[:80]}")

        # ── Part 5: Causality uncertainty (richness lesson from Loop 2) ───
        # Maestro never claims the decision CAUSED the outcome. It records
        # the temporal sequence + the hypothesis validation.
        parts.append(
            "Maestro does not know if the decision caused the outcome or if the outcome would have occurred regardless"
        )

        # Join into one rich sentence
        main_clause = "; ".join(parts[:4]) + "."
        observation = " " + parts[4] + "."
        return f"{main_clause}{observation}"

    def _hypothesis_matches_outcome(self, hypothesis: str, outcome: str) -> bool:
        """Check if the outcome confirms or contradicts the hypothesis.

        Heuristic: if the outcome contains ANY negative words, the hypothesis
        was (at least partially) wrong. Mixed outcomes count as wrong because
        the hypothesis predicted a fully positive outcome.

        This is deliberately sensitive to negative words — false positives
        (flagging a hypothesis as wrong when it was partially right) are
        acceptable because the learning entry still references the actual
        outcome. False negatives (missing a wrong hypothesis) are worse —
        they'd hide the lesson.
        """
        o_lower = outcome.lower()
        negative = {"missed", "broken", "churned", "failed", "late", "delayed", "lost", "did not", "not renew", "did not renew"}

        # If the outcome contains ANY negative words, the hypothesis was wrong
        if any(word in o_lower for word in negative):
            return False
        return True
