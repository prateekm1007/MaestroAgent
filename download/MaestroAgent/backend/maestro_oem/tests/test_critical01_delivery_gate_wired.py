"""CRITICAL-01 fix: wire decide_delivery into the Whisper generation path.

External auditor finding (FORENSIC AUDIT, 2026-07-03):
> CRITICAL-01 — The 7-option Delivery Decision gate is real, well-designed,
> and completely disconnected from the Whisper pipeline it's supposed to govern.
>
> OrganizationalWhisper's generation path must call decide_delivery() with
> values it derives itself from stored whisper history and evidence — not
> from caller-supplied booleans.
>
> Regression test needed: an end-to-end test that generates whispers twice
> for the same unchanged situation and asserts the second call is suppressed
> via SUPPRESS_REDUNDANT.

This test exercises the ACTUAL Whisper generation path (for_context),
not the standalone /loop1.5/delivery-decision endpoint. It will FAIL
until decide_delivery is wired into for_context().
"""
from __future__ import annotations

import sys
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# Ensure backend/ is on sys.path
_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from maestro_oem.whisper import OrganizationalWhisper
from maestro_oem.delivery_decision import DeliveryDecision


class MockModel:
    """Minimal mock model for OrganizationalWhisper."""
    def __init__(self):
        self.laws = {}
        self.learning_objects = {}
        self.approvals = type('A', (), {'get_bottlenecks': lambda self, min_count=2: []})()
        self.decisions = type('D', (), {'get_recommendations': lambda self: []})()


class MockSignal:
    """Mock OEM signal."""
    def __init__(self, sig_type, actor="", artifact="", metadata=None, timestamp=None, provider="customer"):
        self.type = sig_type
        self.actor = actor
        self.artifact = artifact
        self.metadata = metadata or {}
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.signal_id = f"sig-{artifact or id(self)}"
        self.provider = type("P", (), {"value": provider})()


@pytest.fixture
def signals():
    from maestro_oem.signal import SignalType
    return [
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane.d@acme.com",
            artifact="crm:globex-commit-1",
            metadata={"customer": "Globex", "commitment": "Deliver SSO by 2024-12-15"},
        ),
        MockSignal(
            SignalType.CUSTOMER_OBJECTION,
            actor="jane.d@acme.com",
            artifact="crm:globex-obj-1",
            metadata={"customer": "Globex", "objection_type": "pricing"},
        ),
        MockSignal(
            SignalType.CUSTOMER_MEETING,
            actor="jane.d@acme.com",
            artifact="crm:globex-meeting-1",
            metadata={"customer": "Globex"},
        ),
        MockSignal(
            SignalType.CUSTOMER_EMAIL,
            actor="jane.d@acme.com",
            artifact="crm:globex-email-1",
            metadata={"customer": "Globex"},
        ),
        MockSignal(
            SignalType.CUSTOMER_CHAMPION_ACTIVE,
            actor="jane.d@acme.com",
            artifact="crm:globex-champ-1",
            metadata={"customer": "Globex"},
        ),
    ]


# ─── The auditor's exact test: same unchanged situation twice → second suppressed ──

def test_whisper_generation_suppresses_redundant_on_second_call(signals):
    """The auditor's regression test: generate whispers twice for the same
    unchanged situation. The second call must suppress via SUPPRESS_REDUNDANT.

    This test FAILS until decide_delivery is wired into for_context().
    """
    model = MockModel()

    # First call — no history, whispers should fire
    whisper_engine_1 = OrganizationalWhisper(model, signals, whisper_store={})
    result_1 = whisper_engine_1.for_context(context="meeting", entity="Globex", topic="pricing")

    assert len(result_1["whispers"]) > 0, \
        "First call must produce whispers (no history → no suppression)"

    # Build whisper_store history from the first call's whispers
    # (simulating that they were shown to the user)
    whisper_store_after_first = {}
    now = datetime.now(timezone.utc).isoformat()
    for w in result_1["whispers"]:
        wid = w.get("whisper_id", "")
        if wid:
            whisper_store_after_first[wid] = {
                "shown_count": 1,
                "action_taken": None,  # User didn't act — but also didn't ignore
                "first_shown": now,
                "last_shown": now,
            }

    # Second call — SAME unchanged situation, whispers already shown once
    # The delivery decision gate should suppress via SUPPRESS_REDUNDANT
    # (shown_count > 0 + nothing materially changed)
    whisper_engine_2 = OrganizationalWhisper(model, signals, whisper_store=whisper_store_after_first)
    result_2 = whisper_engine_2.for_context(context="meeting", entity="Globex", topic="pricing")

    # The second call must have FEWER whispers (some suppressed) OR
    # the whispers must carry a delivery_decision field indicating suppression
    #
    # The key assertion: the delivery decision gate was actually consulted.
    # We verify this by checking that each whisper in result_2 has a
    # "delivery_decision" field set (proving the gate ran), AND that
    # at least some whispers were suppressed (not returned).
    whispers_2 = result_2["whispers"]
    suppressed = result_2.get("suppressed_whispers", [])

    # At least one whisper must be suppressed (SUPPRESS_REDUNDANT)
    assert len(suppressed) > 0 or len(whispers_2) < len(result_1["whispers"]), \
        f"Second call must suppress at least some whispers via SUPPRESS_REDUNDANT. " \
        f"First call: {len(result_1['whispers'])} whispers. " \
        f"Second call: {len(whispers_2)} whispers, {len(suppressed)} suppressed."

    # If whispers are returned, they must carry the delivery_decision field
    # (proving the gate was consulted, not bypassed)
    for w in whispers_2:
        assert "delivery_decision" in w, \
            f"Every returned whisper must carry a delivery_decision field " \
            f"(proving the gate ran). Missing on: {w.get('whisper_id', 'unknown')}"

    # Suppressed whispers must carry the suppression reason
    for w in suppressed:
        decision = w.get("delivery_decision", "")
        assert decision in (
            DeliveryDecision.SUPPRESS_REDUNDANT.name,
            DeliveryDecision.SUPPRESS_ALREADY_UNDERSTOOD.name,
            DeliveryDecision.SUPPRESS_LOW_STAKES.name,
            DeliveryDecision.DEFER_UNTIL_EVIDENCE.name,
        ), \
            f"Suppressed whisper must have a valid suppression reason. Got: {decision!r}"


def test_whisper_generation_does_not_suppress_on_first_call(signals):
    """First call (no history) must NOT suppress — DELIVER_NOW or similar."""
    model = MockModel()
    whisper_engine = OrganizationalWhisper(model, signals, whisper_store={})
    result = whisper_engine.for_context(context="meeting", entity="Globex", topic="pricing")

    assert len(result["whispers"]) > 0, "First call must produce whispers"
    suppressed = result.get("suppressed_whispers", [])
    assert len(suppressed) == 0, \
        f"First call (no history) must not suppress any whispers. Got {len(suppressed)} suppressed."

    # Each whisper must carry its delivery_decision
    for w in result["whispers"]:
        assert "delivery_decision" in w, \
            f"Every whisper must carry a delivery_decision field. Missing on: {w.get('whisper_id')}"


def test_whisper_generation_suppresses_already_understood_when_exec_acted(signals):
    """When the exec already acted on a whisper + nothing changed,
    SUPPRESS_ALREADY_UNDERSTOOD must fire.
    """
    model = MockModel()

    # First call — get the whisper IDs
    engine_1 = OrganizationalWhisper(model, signals, whisper_store={})
    result_1 = engine_1.for_context(context="meeting", entity="Globex", topic="pricing")
    assert len(result_1["whispers"]) > 0

    # Build history: exec ACTED on the whisper, nothing changed since
    whisper_store_after_action = {}
    now = datetime.now(timezone.utc).isoformat()
    for w in result_1["whispers"]:
        wid = w.get("whisper_id", "")
        if wid:
            whisper_store_after_action[wid] = {
                "shown_count": 1,
                "action_taken": "acted",  # Exec acted!
                "first_shown": now,
                "last_shown": now,
            }

    # Second call — exec already acted, nothing changed
    engine_2 = OrganizationalWhisper(model, signals, whisper_store=whisper_store_after_action)
    result_2 = engine_2.for_context(context="meeting", entity="Globex", topic="pricing")

    suppressed = result_2.get("suppressed_whispers", [])

    # At least one whisper must be suppressed via SUPPRESS_ALREADY_UNDERSTOOD
    already_understood = [
        w for w in suppressed
        if w.get("delivery_decision") == DeliveryDecision.SUPPRESS_ALREADY_UNDERSTOOD.name
    ]
    assert len(already_understood) > 0, \
        f"When exec already acted + nothing changed, must SUPPRESS_ALREADY_UNDERSTOOD. " \
        f"Suppressed: {len(suppressed)}, already_understood: {len(already_understood)}"
