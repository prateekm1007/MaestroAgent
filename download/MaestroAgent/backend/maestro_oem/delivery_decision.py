"""Loop 1.5 — delivery_decision enum.

External auditor's product test (AUDITOR-EXTERNAL-REVIEW-3):
> Maestro should know when NOT to speak. The delivery_decision enum
> captures Maestro's decision about whether to deliver a Whisper.

The 7 options:
  1. DELIVER_NOW              — surface immediately (high stakes, materially changed, exec hasn't seen)
  2. DELIVER_AT_MEETING_TIME  — surface just before the next meeting (timing-driven)
  3. DELIVER_ON_ASK           — only surface if the exec asks via Ask Maestro (low stakes)
  4. SUPPRESS_ALREADY_UNDERSTOOD — the exec has already acknowledged/acted on this; remain quiet
  5. SUPPRESS_REDUNDANT       — already surfaced recently and nothing changed; don't repeat
  6. SUPPRESS_LOW_STAKES      — the stakes don't warrant interrupting (headline depth, no high-stakes signals)
  7. DEFER_UNTIL_EVIDENCE     — not enough evidence yet; wait (cold-start mode)

The `decide_delivery` function takes 5 deterministic inputs and returns
one of the 7 options. No learning. No ML. Just explicit rules — the
data model from day one.

This is the "remain quiet" test. Maestro's value is not just in what it
says, but in knowing when to stay silent. An executive who gets a Whisper
about something they already know learns to ignore Whispers. An executive
who gets a Whisper only when it matters learns to trust Whispers.
"""

from __future__ import annotations

from enum import Enum


class DeliveryDecision(str, Enum):
    """Maestro's decision about whether to deliver a Whisper.

    7 options. The order matters for the decide_delivery priority logic.
    """

    DELIVER_NOW = "deliver_now"
    DELIVER_AT_MEETING_TIME = "deliver_at_meeting_time"
    DELIVER_ON_ASK = "deliver_on_ask"
    SUPPRESS_ALREADY_UNDERSTOOD = "suppress_already_understood"
    SUPPRESS_REDUNDANT = "suppress_redundant"
    SUPPRESS_LOW_STAKES = "suppress_low_stakes"
    DEFER_UNTIL_EVIDENCE = "defer_until_evidence"


def decide_delivery(
    exec_already_acted: bool,
    materially_changed_since_last_shown: bool,
    has_high_stakes_signal: bool,
    is_cold_start: bool,
    shown_count: int,
    has_upcoming_meeting: bool = False,
) -> DeliveryDecision:
    """Decide whether to deliver a Whisper.

    Priority (highest first):
      1. Cold-start mode → DEFER_UNTIL_EVIDENCE (Maestro listens, doesn't speak)
      2. Exec already acted + nothing changed → SUPPRESS_ALREADY_UNDERSTOOD
      3. Already shown (shown_count > 0) + nothing changed → SUPPRESS_REDUNDANT
      4. High stakes + materially changed → DELIVER_NOW
      5. High stakes + upcoming meeting → DELIVER_AT_MEETING_TIME
      6. High stakes (no meeting, no change) → DELIVER_ON_ASK
      7. Low stakes → SUPPRESS_LOW_STAKES

    Args:
        exec_already_acted: True if the exec has already acted on this Whisper
        materially_changed_since_last_shown: True if new signals arrived since last shown
        has_high_stakes_signal: True if entity has broken commitment / objection / churn
        is_cold_start: True if in cold-start mode (few signals)
        shown_count: How many times this Whisper has been shown
        has_upcoming_meeting: True if there's a consequential meeting soon

    Returns:
        One of the 7 DeliveryDecision options.
    """
    # 1. Cold-start mode overrides everything — UNLESS high-stakes signals
    #    are present (matching ColdStartMode.should_suppress_whispers() logic:
    #    high-stakes signals override cold-start suppression because Maestro
    #    must speak even on day 1 if a customer churns or a commitment breaks)
    if is_cold_start and not has_high_stakes_signal:
        return DeliveryDecision.DEFER_UNTIL_EVIDENCE

    # 2. Exec already acted + nothing changed → remain quiet (the "remain quiet" test)
    if exec_already_acted and not materially_changed_since_last_shown:
        return DeliveryDecision.SUPPRESS_ALREADY_UNDERSTOOD

    # 3. Already shown + nothing changed → don't repeat
    if shown_count > 0 and not materially_changed_since_last_shown:
        return DeliveryDecision.SUPPRESS_REDUNDANT

    # 4. High stakes + materially changed → deliver now
    if has_high_stakes_signal and materially_changed_since_last_shown:
        return DeliveryDecision.DELIVER_NOW

    # 5. High stakes + upcoming meeting → deliver at meeting time
    if has_high_stakes_signal and has_upcoming_meeting:
        return DeliveryDecision.DELIVER_AT_MEETING_TIME

    # 6. High stakes (no meeting, no change) → deliver on ask
    if has_high_stakes_signal:
        return DeliveryDecision.DELIVER_ON_ASK

    # 7. First-time whisper (shown_count=0) → always deliver, even if low stakes.
    #    A whisper the user has never seen is NOT redundant — suppression for
    #    "low stakes" only applies when the whisper has been shown before and
    #    the user chose not to act on it.
    if shown_count == 0:
        return DeliveryDecision.DELIVER_ON_ASK

    # 8. Low stakes + already shown + not acted on → suppress
    return DeliveryDecision.SUPPRESS_LOW_STAKES
