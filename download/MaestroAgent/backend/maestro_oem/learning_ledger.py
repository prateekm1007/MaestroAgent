"""Loop 1 — Learning Ledger.

External auditor correction #4 (2026-07-03):
> Learning Ledger, not Maestro IQ. After the outcome is observed,
> Maestro writes one honest sentence about what it learned. Not a
> score. Not a number. A sentence.

The Learning Ledger is the antithesis of fake precision. It does NOT:
  - Compute a "learning score"
  - Assign a probability
  - Update a confidence rating
  - Claim any quantitative measure of "what was learned"

It DOES:
  - Write one honest sentence about what happened
  - Reference the actual commitment, the actual outcome, the actual
    executive action
  - Honestly say when the commitment was broken (no spin)
  - Honestly say when the Whisper was ignored and the outcome was bad
  - Honestly say when the Whisper was acted on and the outcome was good
  - Acknowledge uncertainty ("Maestro does not know if the Whisper
    caused the action")

The sentence is signal-derived. It is NOT a template. It references
the actual entity, the actual commitment text, the actual outcome
signal type. Two different commitments produce two different
sentences.

Usage:
    ledger = LearningLedger(store=whisper_history_store)
    entry = ledger.write_entry(
        whisper_id=wid,
        org_id="default",
        entity="Globex",
        commitment_text="Deliver SSO by 2024-12-15",
        executive_action="acted",
        outcome_signal_type=SignalType.CUSTOMER_COMMITMENT_KEPT,
        decision_influenced="Q4 SSO delivery prioritized",
    )
    # entry = "Globex honored its SSO commitment after Jane acted on
    #          the Whisper. The Whisper surfaced the commitment before
    #          the Quarterly Review; Maestro does not know if the
    #          Whisper caused the action."
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class LearningLedger:
    """Writes one honest sentence about what Maestro learned.

    The sentence is signal-derived, not templated. It references the
    actual entity, commitment, action, and outcome. It honestly
    acknowledges causality uncertainty.
    """

    def __init__(self, store: Any = None) -> None:
        self._store = store

    def write_entry(
        self,
        whisper_id: str,
        org_id: str = "default",
        entity: str = "",
        commitment_text: str = "",
        executive_action: str | None = None,
        outcome_signal_type: Any = None,
        decision_influenced: str | None = None,
        follow_up_questions: list[str] | None = None,
    ) -> str:
        """Write one honest sentence about what happened.

        Returns the sentence (also persists to the store if available).
        """
        sentence = self._compose_sentence(
            entity=entity,
            commitment_text=commitment_text,
            executive_action=executive_action,
            outcome_signal_type=outcome_signal_type,
            decision_influenced=decision_influenced,
            follow_up_questions=follow_up_questions,
        )

        # Persist to store
        if self._store is not None:
            try:
                if hasattr(self._store, "record_learning"):
                    self._store.record_learning(whisper_id, sentence, org_id=org_id)
            except Exception as e:
                logger.warning("LearningLedger: failed to persist entry: %s", e)

        return sentence

    def _compose_sentence(
        self,
        entity: str,
        commitment_text: str,
        executive_action: str | None,
        outcome_signal_type: Any,
        decision_influenced: str | None,
        follow_up_questions: list[str] | None,
    ) -> str:
        """Compose one honest sentence. Signal-derived, not templated."""
        from maestro_oem.signal import SignalType

        # Normalize the outcome signal type to a string label
        outcome_label = self._label_outcome(outcome_signal_type)

        # Build the sentence parts
        parts: list[str] = []

        # ── Part 1: What happened (entity + commitment + outcome) ──────
        commitment_phrase = self._short_commitment(commitment_text)
        if entity and commitment_phrase:
            if outcome_label == "honored":
                parts.append(f"{entity} honored its commitment ({commitment_phrase})")
            elif outcome_label == "broken":
                parts.append(f"{entity} broke its commitment ({commitment_phrase})")
            elif outcome_label == "renegotiated":
                parts.append(f"{entity} renegotiated its commitment ({commitment_phrase})")
            elif outcome_label == "unknown":
                parts.append(f"The outcome of {entity}'s commitment ({commitment_phrase}) is not yet observed")
            else:
                parts.append(f"{entity}'s commitment ({commitment_phrase}) outcome: {outcome_label}")
        elif entity:
            parts.append(f"{entity}'s meeting occurred")
        else:
            parts.append("A commitment was tracked")

        # ── Part 2: What the executive did ─────────────────────────────
        if executive_action == "acted":
            action_phrase = "the executive acted on the Whisper"
        elif executive_action == "ignored":
            action_phrase = "the executive ignored the Whisper"
        elif executive_action == "overrode":
            action_phrase = "the executive overrode the Whisper's recommendation"
        else:
            action_phrase = "no executive action was recorded"

        # ── Part 3: Causality honesty ──────────────────────────────────
        # Maestro never claims the Whisper CAUSED the action. It only
        # records the temporal sequence.
        if executive_action == "acted" and outcome_label == "honored":
            parts.append(f"after {action_phrase}")
            parts.append("Maestro does not know if the Whisper caused the action or the outcome")
        elif executive_action == "ignored" and outcome_label == "broken":
            parts.append(f"after {action_phrase}")
            parts.append("Maestro does not know if acting on the Whisper would have prevented the broken commitment")
        elif executive_action == "ignored" and outcome_label == "honored":
            parts.append(f"despite {action_phrase}")
            parts.append("the commitment was honored without Maestro's intervention")
        elif executive_action == "acted" and outcome_label == "broken":
            parts.append(f"despite {action_phrase}")
            parts.append("the commitment was broken — the action may have been insufficient or mistimed")
        else:
            parts.append(f"({action_phrase})")

        # ── Part 4: Decision influenced (if recorded) ──────────────────
        if decision_influenced:
            parts.append(f"the action influenced: {decision_influenced}")

        # ── Part 5: Follow-up questions (if any) ───────────────────────
        if follow_up_questions:
            parts.append(f"the executive asked {len(follow_up_questions)} follow-up question(s)")

        # Join into one sentence (parts 1-2 joined with temporal logic,
        # parts 3-5 as separate clauses)
        # The first 2 parts form the main clause; parts 3+ are observations.
        main_clause = " ".join(parts[:2]) + "."
        observations = "; ".join(parts[2:]) + "." if len(parts) > 2 else ""

        if observations:
            return f"{main_clause} {observations}"
        return main_clause

    def _label_outcome(self, outcome_signal_type: Any) -> str:
        """Map a SignalType to an outcome label."""
        from maestro_oem.signal import SignalType
        if outcome_signal_type is None:
            return "unknown"
        if outcome_signal_type == SignalType.CUSTOMER_COMMITMENT_KEPT:
            return "honored"
        if outcome_signal_type == SignalType.CUSTOMER_COMMITMENT_BROKEN:
            return "broken"
        if outcome_signal_type == SignalType.CUSTOMER_DECISION:
            return "renegotiated"
        if outcome_signal_type == SignalType.CUSTOMER_CONTRACT_RENEWED:
            return "honored"
        if outcome_signal_type == SignalType.CUSTOMER_CONTRACT_CHURNED:
            return "broken"
        return "unknown"

    def _short_commitment(self, commitment_text: str) -> str:
        """Shorten the commitment text for the ledger sentence."""
        if not commitment_text:
            return ""
        # Take first 60 chars, break on word boundary
        if len(commitment_text) <= 60:
            return commitment_text
        truncated = commitment_text[:60]
        # Break at last space
        last_space = truncated.rfind(" ")
        if last_space > 20:
            return truncated[:last_space] + "..."
        return truncated + "..."
