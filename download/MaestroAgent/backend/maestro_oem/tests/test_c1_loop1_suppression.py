"""C1 fix: loop1 whisper suppression — route _fire_whisper_for_event
through decide_delivery().

External auditor finding (AUDITOR-ERROR-2-ACKNOWLEDGMENT-EDC99C3):
> C1 fix is INCOMPLETE. whisper.py:310 calls decide_delivery ✓.
> loop1_commitment_intelligence.py has 0 references. The "remain quiet"
> test still fails for evening preparation.

The bug: _fire_whisper_for_event in loop1_commitment_intelligence.py
builds and persists a Whisper directly, WITHOUT calling decide_delivery().
So the "remain quiet" capability (SUPPRESS_ALREADY_UNDERSTOOD) exists in
the main whisper.py path but NOT in the loop1 evening-preparation path.

The fix: call decide_delivery() in _fire_whisper_for_event. If it returns
SUPPRESS_*, skip the whisper (return None). This closes the loop1 path
the same way CRITICAL-01 closed the main whisper.py path.

Adversarial: written FIRST, watched FAIL, then fix applied (P2).
"""
from __future__ import annotations

import sys
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import uuid

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from maestro_oem.organizational_learning_ledger import OrganizationalLearningLedger


class MockSignal:
    def __init__(self, sig_type, actor="", artifact="", metadata=None, timestamp=None, provider="customer"):
        from maestro_oem.signal import SignalProvider
        self.type = sig_type
        self.actor = actor
        self.artifact = artifact
        self.metadata = metadata or {}
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.signal_id = uuid.uuid4()
        self.provider = SignalProvider.CUSTOMER if provider == "customer" else SignalProvider(provider)


@pytest.fixture
def now():
    return datetime(2026, 7, 4, 18, 0, tzinfo=timezone.utc)


# ─── Tests ─────────────────────────────────────────────────────────────────

def test_loop1_fire_whisper_calls_decide_delivery():
    """C1: _fire_whisper_for_event must call decide_delivery().

    Before the fix: loop1 built and persisted Whispers directly, bypassing
    the delivery-decision gate. The "remain quiet" capability existed in
    whisper.py but NOT in the loop1 path.

    This test verifies the call site exists by inspecting the source code.
    """
    import inspect
    from maestro_oem import loop1_commitment_intelligence

    source = inspect.getsource(loop1_commitment_intelligence.CommitmentIntelligenceLoop._fire_whisper_for_event)
    assert "decide_delivery" in source, \
        "_fire_whisper_for_event must call decide_delivery() to check whether " \
        "the Whisper should be suppressed. Before this fix, loop1 bypassed " \
        "the delivery-decision gate entirely (C1 incomplete)."


def test_loop1_suppresses_whisper_when_already_acted(now):
    """C1 KEY TEST: when the exec already acted + nothing changed, loop1
    must SUPPRESS the Whisper (not fire it).

    Scenario:
      - Globex commitment exists
      - Tomorrow's calendar has a Globex meeting
      - The exec already acted on the Globex Whisper previously
      - Nothing has materially changed since

    Before the fix: loop1 fires the Whisper anyway (bypasses decide_delivery).
    After the fix: decide_delivery returns SUPPRESS_ALREADY_UNDERSTOOD,
    loop1 skips the Whisper, returns None.
    """
    from maestro_oem.loop1_commitment_intelligence import CommitmentIntelligenceLoop
    from maestro_oem.signal import SignalType
    from maestro_oem.calendar_source import CalendarEvent, StaticCalendarSource

    # Build signals: Globex commitment + 4 noise signals (so it's not cold-start)
    # C1 suppression requires exec_already_acted=True + materially_changed=False
    # + NOT cold-start (5+ signals). With <5 signals, decide_delivery returns
    # DEFER_UNTIL_EVIDENCE (cold-start trust ladder), not SUPPRESS_ALREADY_UNDERSTOOD.
    signals = [
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane.d@acme.com",
            artifact="crm:globex-commit-1",
            metadata={"customer": "Globex", "commitment": "Deliver SSO by 2026-08-15"},
            timestamp=now - timedelta(days=10),
        ),
    ]
    # Add 4 noise signals to escape cold-start (5+ signals = FULL_WHISPERS)
    for i in range(4):
        signals.append(MockSignal(
            SignalType.CUSTOMER_MEETING,
            actor=f"rep{i}@acme.com",
            artifact=f"crm:noise-{i}",
            metadata={"customer": f"Customer{i}", "subject": f"meeting {i}"},
            timestamp=now - timedelta(days=20 - i),
        ))

    # Tomorrow's calendar: Globex meeting
    tomorrow = now + timedelta(days=1)
    calendar = StaticCalendarSource([
        CalendarEvent(
            title="Globex Quarterly Review",
            start=tomorrow.replace(hour=10, minute=0),
            end=tomorrow.replace(hour=11, minute=0),
            entity="Globex",
            attendees=["ceo@globex.com", "jane.d@acme.com"],
        ),
    ])

    # Mock store: simulates the exec already acted on this Whisper
    class MockStore:
        def get_history(self, whisper_id, org_id="default"):
            return {
                "last_shown": (now - timedelta(days=1)).isoformat(),
                "action_taken": "acted",  # exec already acted
                "shown_count": 1,
            }
        def record_shown(self, **kwargs):
            pass  # track that a whisper was fired
        def get_all_history(self, org_id="default"):
            return {}

    loop1 = CommitmentIntelligenceLoop(
        signals=signals,
        calendar_source=calendar,
        whisper_store=MockStore(), learning_ledger=OrganizationalLearningLedger(),
        now=now,
    )

    result = loop1.run_evening_preparation(org_id="default")

    # The fix: decide_delivery returns SUPPRESS_ALREADY_UNDERSTOOD because
    # exec_already_acted=True + materially_changed=False. The loop1 path
    # must respect this and fire 0 whispers.
    whispers_fired = result.get("whispers_fired", 0)
    assert whispers_fired == 0, \
        f"C1 REGRESSION: loop1 fired {whispers_fired} whisper(s) even though the exec " \
        f"already acted and nothing materially changed. decide_delivery should return " \
        f"SUPPRESS_ALREADY_UNDERSTOOD, and loop1 should skip the whisper. " \
        f"Whispers: {[w.get('insight', '')[:60] for w in result.get('whispers', [])]}"


def test_loop1_fires_whisper_when_materially_changed(now):
    """Counter-test: when something materially changed, loop1 DOES fire.

    Non-vacuous: don't suppress everything. If the commitment mutated
    (new deadline), the Whisper SHOULD fire even if the exec acted before.
    """
    from maestro_oem.loop1_commitment_intelligence import CommitmentIntelligenceLoop
    from maestro_oem.signal import SignalType
    from maestro_oem.calendar_source import CalendarEvent, StaticCalendarSource

    signals = [
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane.d@acme.com",
            artifact="crm:globex-commit-1",
            metadata={"customer": "Globex", "commitment": "Deliver SSO by 2026-08-15"},
            timestamp=now - timedelta(days=10),
        ),
        # Mutated commitment (deadline moved) — materially changed
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane.d@acme.com",
            artifact="crm:globex-commit-2",
            metadata={"customer": "Globex", "commitment": "Deliver SSO + MFA by 2026-09-30"},
            timestamp=now - timedelta(days=1),  # recent
        ),
        # High-stakes signal: broken commitment → decide_delivery returns DELIVER_NOW
        # (without this, decide_delivery returns SUPPRESS_LOW_STAKES even when
        # materially_changed=True, because the stakes don't warrant interrupting)
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_BROKEN,
            actor="jane.d@acme.com",
            artifact="crm:globex-broken-1",
            metadata={"customer": "Globex", "commitment": "Deliver SSO by 2026-08-15"},
            timestamp=now - timedelta(days=2),
        ),
    ]

    tomorrow = now + timedelta(days=1)
    calendar = StaticCalendarSource([
        CalendarEvent(
            title="Globex Quarterly Review",
            start=tomorrow.replace(hour=10, minute=0),
            end=tomorrow.replace(hour=11, minute=0),
            entity="Globex",
            attendees=["ceo@globex.com", "jane.d@acme.com"],
        ),
    ])

    class MockStore:
        def get_history(self, whisper_id, org_id="default"):
            return {
                "last_shown": (now - timedelta(days=5)).isoformat(),
                "action_taken": "acted",
                "shown_count": 1,
            }
        def record_shown(self, **kwargs):
            pass
        def get_all_history(self, org_id="default"):
            return {}

    loop1 = CommitmentIntelligenceLoop(
        signals=signals,
        calendar_source=calendar,
        whisper_store=MockStore(), learning_ledger=OrganizationalLearningLedger(),
        now=now,
    )

    result = loop1.run_evening_preparation(org_id="default")
    # With materially_changed=True, decide_delivery returns DELIVER_NOW,
    # so loop1 should fire the whisper.
    whispers_fired = result.get("whispers_fired", 0)
    assert whispers_fired >= 1, \
        f"Counter-test failed: loop1 should fire a whisper when the commitment " \
        f"materially changed (new deadline). Got whispers_fired={whispers_fired}."
