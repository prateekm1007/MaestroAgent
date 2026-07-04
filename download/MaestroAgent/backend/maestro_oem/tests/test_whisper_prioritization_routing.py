"""Round 3 Fix 2: Cross-whisper prioritization + recipient routing.

External auditor finding (Round 3):
> Recipient routing: escalation_recipient parameter exists with inline
> comment 'HIGH-risk parameter, not used in the gate logic.' Every
> Whisper assumes a single recipient.
>
> Batching/prioritization: decide_delivery evaluates per-whisper. No
> cross-whisper ranking. If 50 legitimately different things happened
> overnight, the system evaluates each independently rather than batching
> into a digest.

This module adds:
  1. WhisperPrioritizer — ranks delivered whispers by priority, returns
     top N + batches the rest for morning digest.
  2. RecipientRouter — determines the right recipient for each Whisper
     based on signal actors + meeting attendees (not a generic default).

Adversarial tests (write first, watch fail, then build):

  1. test_whisper_prioritizer_exists
  2. test_prioritizer_ranks_by_priority
     10 whispers → top 3 returned, 7 batched
  3. test_prioritizer_batched_whispers_field
     Response includes a 'batched_whispers' field
  4. test_prioritizer_ranking_uses_stakes
     High-stakes whispers rank above low-stakes
  5. test_recipient_router_exists
  6. test_recipient_router_uses_signal_actor
     A whisper about a commitment made by jane.d@ gets recipient=jane.d@
  7. test_recipient_router_falls_back_to_default
     When no actor/attendee is determinable, falls back to default
  8. test_recipient_router_uses_meeting_attendee
     If the commitment signal actor is unknown but a meeting attendee
     is known, use the attendee
  9. test_wiring_p11_prioritizer_in_whisper_py
  10. test_wiring_p11_recipient_in_whisper_py

P2: Untested code is unverified code.
P11: Wiring proved by grep + execution.
P13: Recipient is DERIVED from signal actors + meeting attendees, not caller-supplied.
"""
from __future__ import annotations

import sys
import inspect
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ═══ Fix 2: Prioritization + Recipient Routing ═════════════════════════════

# ─── 1. WhisperPrioritizer exists ──────────────────────────────────────────

def test_whisper_prioritizer_exists():
    """WhisperPrioritizer must exist and be importable."""
    from maestro_oem.whisper_prioritizer import WhisperPrioritizer
    assert WhisperPrioritizer is not None


# ─── 2. Ranks by priority, returns top N + batched ─────────────────────────

def test_prioritizer_ranks_by_priority():
    """10 whispers → top 3 returned, 7 batched."""
    from maestro_oem.whisper_prioritizer import WhisperPrioritizer

    whispers = []
    for i in range(10):
        whispers.append({
            "whisper_id": f"wspr-{i}",
            "entity": f"Customer{i}",
            "insight": f"Insight {i}",
            "delivery_decision": "DELIVER_NOW",
            "stakes": "high" if i < 3 else "low",  # first 3 are high-stakes
        })

    prioritizer = WhisperPrioritizer(top_n=3)
    result = prioritizer.prioritize(whispers)

    assert "delivered" in result, "Must return 'delivered' list"
    assert "batched_whispers" in result, "Must return 'batched_whispers' list"
    assert len(result["delivered"]) == 3, (
        f"Top 3 must be delivered. Got: {len(result['delivered'])}"
    )
    assert len(result["batched_whispers"]) == 7, (
        f"Remaining 7 must be batched. Got: {len(result['batched_whispers'])}"
    )


# ─── 3. batched_whispers field ─────────────────────────────────────────────

def test_prioritizer_batched_whispers_field():
    """Response includes a 'batched_whispers' field."""
    from maestro_oem.whisper_prioritizer import WhisperPrioritizer

    prioritizer = WhisperPrioritizer(top_n=3)
    result = prioritizer.prioritize([
        {"whisper_id": "w1", "entity": "C1", "insight": "i1", "delivery_decision": "DELIVER_NOW", "stakes": "low"},
        {"whisper_id": "w2", "entity": "C2", "insight": "i2", "delivery_decision": "DELIVER_NOW", "stakes": "low"},
    ])
    assert "batched_whispers" in result


# ─── 4. High-stakes rank above low-stakes ──────────────────────────────────

def test_prioritizer_ranking_uses_stakes():
    """High-stakes whispers rank above low-stakes."""
    from maestro_oem.whisper_prioritizer import WhisperPrioritizer

    whispers = [
        {"whisper_id": "w-low", "entity": "C1", "insight": "low stakes", "delivery_decision": "DELIVER_NOW", "stakes": "low"},
        {"whisper_id": "w-high", "entity": "C2", "insight": "high stakes", "delivery_decision": "DELIVER_NOW", "stakes": "high"},
        {"whisper_id": "w-low2", "entity": "C3", "insight": "low stakes 2", "delivery_decision": "DELIVER_NOW", "stakes": "low"},
    ]
    prioritizer = WhisperPrioritizer(top_n=1)
    result = prioritizer.prioritize(whispers)

    assert len(result["delivered"]) == 1
    assert result["delivered"][0]["whisper_id"] == "w-high", (
        f"High-stakes whisper must rank first. Got: {result['delivered'][0]['whisper_id']}"
    )


# ─── 5. RecipientRouter exists ─────────────────────────────────────────────

def test_recipient_router_exists():
    """RecipientRouter must exist and be importable."""
    from maestro_oem.whisper_router import RecipientRouter
    assert RecipientRouter is not None


# ─── 6. Uses signal actor ──────────────────────────────────────────────────

def test_recipient_router_uses_signal_actor():
    """A whisper about a commitment made by jane.d@ gets recipient=jane.d@."""
    from maestro_oem.whisper_router import RecipientRouter

    class MockSignal:
        def __init__(self, actor, customer):
            self.actor = actor
            self.metadata = {"customer": customer}
            self.type = type("T", (), {"value": "customer.commitment_made"})()

    signals = [MockSignal("jane.d@example.com", "TestCorp")]
    router = RecipientRouter(signals=signals)
    recipient = router.route(whisper_entity="TestCorp", meeting_attendees=[])

    assert recipient == "jane.d@example.com", (
        f"Recipient must be the signal actor. Got: {recipient}"
    )


# ─── 7. Falls back to default ──────────────────────────────────────────────

def test_recipient_router_falls_back_to_default():
    """When no actor/attendee is determinable, falls back to default."""
    from maestro_oem.whisper_router import RecipientRouter

    router = RecipientRouter(signals=[], default_recipient="ceo@example.com")
    recipient = router.route(whisper_entity="UnknownCorp", meeting_attendees=[])
    assert recipient == "ceo@example.com", (
        f"Must fall back to default recipient. Got: {recipient}"
    )


# ─── 8. Uses meeting attendee when actor unknown ───────────────────────────

def test_recipient_router_uses_meeting_attendee():
    """If the commitment signal actor is unknown but a meeting attendee
    is known, use the attendee."""
    from maestro_oem.whisper_router import RecipientRouter

    router = RecipientRouter(signals=[], default_recipient="ceo@example.com")
    recipient = router.route(
        whisper_entity="TestCorp",
        meeting_attendees=["sales@example.com", "eng@example.com"],
    )
    # Should use the first meeting attendee, not the default
    assert recipient == "sales@example.com", (
        f"Must use first meeting attendee. Got: {recipient}"
    )


# ─── 9. P11: prioritizer in whisper.py ─────────────────────────────────────

def test_wiring_p11_prioritizer_in_whisper_py():
    """P11: whisper.py must reference WhisperPrioritizer."""
    from maestro_oem import whisper
    source = inspect.getsource(whisper)
    assert "WhisperPrioritizer" in source or "whisper_prioritizer" in source, (
        "whisper.py must reference WhisperPrioritizer (P11 — wired into production)"
    )


# ─── 10. P11: recipient router in whisper.py ───────────────────────────────

def test_wiring_p11_recipient_in_whisper_py():
    """P11: whisper.py must reference RecipientRouter."""
    from maestro_oem import whisper
    source = inspect.getsource(whisper)
    assert "RecipientRouter" in source or "whisper_router" in source, (
        "whisper.py must reference RecipientRouter (P11 — wired into production)"
    )
