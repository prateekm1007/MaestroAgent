"""Round 3 Fix 2: Recipient routing — deliver to the right person, not a generic default.

External auditor finding (Round 3):
> Recipient routing: escalation_recipient parameter exists with inline
> comment 'HIGH-risk parameter, not used in the gate logic.' Every
> Whisper assumes a single recipient.

The RecipientRouter determines the right recipient for each Whisper
based on signal actors + meeting attendees (not a generic default).

Routing priority:
  1. Signal actor — who made the commitment / raised the objection /
     was involved in the signal that generated this Whisper?
  2. Meeting attendee — if no signal actor, who is attending the
     upcoming meeting with this entity?
  3. Default — fall back to a configured default (e.g., the CEO)

Usage:
    router = RecipientRouter(signals=signals, default_recipient="ceo@example.com")
    recipient = router.route(whisper_entity="TestCorp", meeting_attendees=["jane@example.com"])
    # recipient = "jane@example.com" (signal actor or meeting attendee)
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RecipientRouter:
    """Determine the right recipient for a Whisper.

    The router uses signal actors + meeting attendees to determine WHO
    should receive a Whisper. This replaces the generic "deliver to the
    CEO" default with evidence-based routing.

    P13: The recipient is DERIVED from signal actors + meeting attendees,
    not caller-supplied. The caller provides the entity and optional
    meeting attendees; the router looks up the signal actor.
    """

    def __init__(
        self,
        signals: list[Any] | None = None,
        default_recipient: str = "",
    ) -> None:
        self._signals = signals or []
        self._default_recipient = default_recipient

    def route(
        self,
        whisper_entity: str,
        meeting_attendees: list[str] | None = None,
    ) -> str:
        """Determine the recipient for a Whisper.

        Args:
            whisper_entity: The customer/entity the Whisper is about
            meeting_attendees: Optional list of meeting attendee emails

        Returns:
            The recipient email. Priority:
              1. Signal actor (who was involved in the signal for this entity)
              2. First meeting attendee
              3. Default recipient
        """
        meeting_attendees = meeting_attendees or []

        # 1. Try to find a signal actor for this entity
        for sig in self._signals:
            try:
                sig_entity = ""
                if hasattr(sig, "metadata"):
                    sig_entity = sig.metadata.get("customer", "") or sig.metadata.get("entity", "")
                if sig_entity == whisper_entity and hasattr(sig, "actor") and sig.actor:
                    logger.debug(
                        "RecipientRouter: routed whisper for %s to signal actor %s",
                        whisper_entity, sig.actor,
                    )
                    return sig.actor
            except Exception:
                continue

        # 2. Use the first meeting attendee
        if meeting_attendees:
            recipient = meeting_attendees[0]
            logger.debug(
                "RecipientRouter: routed whisper for %s to meeting attendee %s",
                whisper_entity, recipient,
            )
            return recipient

        # 3. Fall back to default
        logger.debug(
            "RecipientRouter: routed whisper for %s to default %s",
            whisper_entity, self._default_recipient,
        )
        return self._default_recipient
