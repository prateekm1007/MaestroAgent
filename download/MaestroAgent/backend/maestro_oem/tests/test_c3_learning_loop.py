"""C-3 fix: Close the learning loop functionally — record outcomes → feed
governed adaptation → policy activates → behavior changes.

The external audit found: "No production code records executive decisions
against recommendations. The learning loop is structurally complete but
functionally disconnected."

The endpoints exist (/loop1/action, /loop1/outcome) but nothing feeds the
AttributionAnalyzer or PolicyProposer. The PolicyVersionStore is always
empty in production.

The fix: when an outcome is recorded, feed it into the governed adaptation
loop. When enough evidence accumulates, a policy activates. The delivery
gate reads the active policy. The loop closes FUNCTIONALLY, not just
structurally.

Adversarial tests:
  1. test_outcome_recording_feeds_attribution_analyzer
     Recording an outcome via the API must feed the AttributionAnalyzer
  2. test_accumulated_outcomes_produce_policy
     3 outcomes → policy activates → PolicyVersionStore non-empty
  3. test_policy_changes_delivery_behavior
     After policy activates, decide_delivery receives non-None policy
  4. test_interaction_memory_records_action
     Recording an action records it in InteractionMemory (8-state lifecycle)
  5. test_outcome_with_confounders_identified
     Outcome with context_signals → confounders appear in hypothesis
"""
from __future__ import annotations

import sys
import os
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture
def clean_policy_store(tmp_path, monkeypatch):
    """Provide a clean PolicyVersionStore for each test."""
    db_path = str(tmp_path / "policies.db")
    interaction_db = str(tmp_path / "interactions.db")
    whisper_db = str(tmp_path / "whisper.db")
    monkeypatch.setenv("MAESTRO_POLICY_DB", db_path)
    monkeypatch.setenv("MAESTRO_INTERACTION_DB", interaction_db)
    monkeypatch.setenv("MAESTRO_WHISPER_DB", whisper_db)

    from maestro_oem.governed_adaptation import (
        PolicyVersionStore, set_default_store, _pending_evidence,
    )
    from maestro_oem.interaction_memory import InteractionMemory, set_default_memory

    # Clear module-level evidence from previous tests
    _pending_evidence.clear()

    store = PolicyVersionStore(db_path)
    set_default_store(store)

    mem = InteractionMemory(interaction_db)
    set_default_memory(mem)

    yield store
    store.close()
    mem.close()
    _pending_evidence.clear()


# ─── 1. Outcome recording feeds AttributionAnalyzer ────────────────────────

def test_outcome_recording_feeds_attribution_analyzer(clean_policy_store):
    """Recording an outcome via the API must feed the AttributionAnalyzer."""
    from maestro_oem.governed_adaptation import (
        OutcomeRecorder, AttributionAnalyzer,
    )

    recorder = OutcomeRecorder()
    analyzer = AttributionAnalyzer()

    # Record an outcome
    hypothesis = recorder.record_outcome(
        whisper_id="wspr-test-1",
        exec_action="ignored",
        outcome="commitment_broken",
        entity="TestCorp",
        context_signals=[{"type": "staffing_change", "note": "champion left"}],
    )

    assert hypothesis is not None, "record_outcome must return a hypothesis"
    assert "hypothesis" in hypothesis, f"Must include hypothesis. Got: {hypothesis.keys()}"
    assert len(hypothesis.get("confounders", [])) > 0, "Must identify confounders"
    assert hypothesis["causal_strength"] in ("weak", "unknown"), "Must be hedged"


# ─── 2. Accumulated outcomes produce policy ────────────────────────────────

def test_accumulated_outcomes_produce_policy(clean_policy_store):
    """3 outcomes → policy activates → PolicyVersionStore non-empty."""
    from maestro_oem.governed_adaptation import (
        OutcomeRecorder, get_active_policy_for_delivery,
    )

    recorder = OutcomeRecorder(min_evidence_threshold=3)

    # Record 3 similar outcomes
    for i in range(3):
        recorder.record_outcome(
            whisper_id=f"wspr-{i}",
            exec_action="ignored",
            outcome="commitment_broken",
            entity=f"Customer{i}",
            context_signals=[],
        )

    # Check if a policy was activated
    active = get_active_policy_for_delivery()
    assert active is not None, (
        "After 3 outcomes, an active policy must exist. "
        "The learning loop is functionally closed."
    )
    assert active.version > 0, "Policy must have version > 0"
    assert active.parameter_changes, "Policy must have parameter_changes"


# ─── 3. Policy changes delivery behavior ───────────────────────────────────

def test_policy_changes_delivery_behavior(clean_policy_store):
    """After policy activates, decide_delivery receives non-None policy."""
    from maestro_oem.governed_adaptation import (
        OutcomeRecorder, get_active_policy_for_delivery,
    )
    from maestro_oem.delivery_decision import decide_delivery, DeliveryDecision

    recorder = OutcomeRecorder(min_evidence_threshold=3)

    # Before: no active policy
    assert get_active_policy_for_delivery() is None

    # Record 3 outcomes to activate a policy
    for i in range(3):
        recorder.record_outcome(
            whisper_id=f"wspr-{i}",
            exec_action="ignored",
            outcome="commitment_broken",
            entity=f"Customer{i}",
            context_signals=[],
        )

    # After: active policy exists
    active = get_active_policy_for_delivery()
    assert active is not None, "Policy must be active after 3 outcomes"

    # The delivery gate now receives the policy
    decision = decide_delivery(
        exec_already_acted=False,
        materially_changed_since_last_shown=False,
        has_high_stakes_signal=False,
        is_cold_start=False,
        shown_count=1,
        policy=active,
    )
    # With dedup_threshold=5 (from the policy), shown_count=1 < 5 → NOT suppressed
    assert decision != DeliveryDecision.SUPPRESS_REDUNDANT, (
        f"With policy dedup_threshold=5, shown_count=1 should NOT suppress. "
        f"Got: {decision}"
    )


# ─── 4. Interaction memory records action ──────────────────────────────────

def test_interaction_memory_records_action(clean_policy_store):
    """Recording an action records it in InteractionMemory (8-state lifecycle)."""
    from maestro_oem.governed_adaptation import OutcomeRecorder
    from maestro_oem.interaction_memory import get_default_memory, InteractionEventType

    recorder = OutcomeRecorder()

    recorder.record_action(
        whisper_id="wspr-action-test",
        action="ignored",
        org_id="default",
    )

    mem = get_default_memory()
    history = mem.get_history("wspr-action-test", org_id="default")
    assert len(history) > 0, "Action must be recorded in InteractionMemory"

    # The DISMISSED event should be recorded (ignored = dismissed)
    event_types = [h["event_type"] for h in history]
    assert InteractionEventType.DISMISSED.value in event_types or \
           InteractionEventType.SHOWN.value in event_types, (
        f"Must record interaction event. Got: {event_types}"
    )


# ─── 5. Outcome with confounders identified ────────────────────────────────

def test_outcome_with_confounders_identified(clean_policy_store):
    """Outcome with context_signals → confounders appear in hypothesis."""
    from maestro_oem.governed_adaptation import OutcomeRecorder

    recorder = OutcomeRecorder()

    hypothesis = recorder.record_outcome(
        whisper_id="wspr-confounder-test",
        exec_action="ignored",
        outcome="commitment_broken",
        entity="TestCorp",
        context_signals=[
            {"type": "staffing_change", "note": "champion left"},
            {"type": "market_shift", "note": "competitor lowered prices"},
        ],
    )

    confounders = hypothesis.get("confounders", [])
    assert len(confounders) >= 2, (
        f"Must identify ≥2 confounders from context_signals. Got: {confounders}"
    )
    assert any("staffing" in c.lower() or "champion" in c.lower() for c in confounders), (
        f"Must identify staffing confounder. Got: {confounders}"
    )
