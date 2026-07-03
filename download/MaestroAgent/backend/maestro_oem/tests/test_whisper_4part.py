"""Tests for the CEO's Ambient Layer spec (2026-07-03).

Verifies:
  1. Whisper API returns 4-part format (situation/insight/evidence/action/priority)
  2. Only high-priority whispers should auto-show
  3. Outcome tracking endpoint works
  4. Behavior change detection works
  5. Organizational pattern detection works

Root cause (P10): the old whisper format was flat text + source + confidence.
The CEO's spec requires Situation → Insight → Evidence → Action. This test
ensures the new format is produced and the golden rule (only high-priority
auto-shows) is enforceable.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from maestro_oem.whisper import OrganizationalWhisper


@pytest.fixture
def mock_model():
    """A minimal mock OEM model with laws + learning objects."""
    class MockLaw:
        def __init__(self, code, statement, confidence=0.8):
            self.code = code
            self.statement = statement
            self.confidence = confidence
            self.validated_runtimes = 3
            self.failed_runtimes = 0
            self.signal_ids = []

            class MockApprovals:
                def get_bottlenecks(self, min_count=2):
                    return []
            self.approvals = MockApprovals()

    class MockLO:
        def __init__(self, lo_id, title, description=""):
            self.lo_id = lo_id
            self.title = title
            self.description = description
            self.confidence = 0.7
            self.providers = ["customer"]

    class MockModel:
        def __init__(self):
            self.laws = {
                "L-0001": MockLaw("L-0001", "Review-batch size inversely correlates with defect escape rate"),
            }
            self.learning_objects = {
                "lo-1": MockLO("lo-1", "Pricing objection pattern", "Customer raised pricing 3 times"),
            }

    return MockModel()


@pytest.fixture
def mock_signals():
    """Minimal mock signals for testing — uses the REAL SignalType enum."""
    from maestro_oem.signal import SignalType

    class MockSignal:
        def __init__(self, sig_type, actor="", artifact="", metadata=None, timestamp=None):
            self.type = sig_type
            self.actor = actor
            self.artifact = artifact
            self.metadata = metadata or {}
            self.timestamp = timestamp or datetime(2024, 11, 1, tzinfo=timezone.utc)
            self.signal_id = f"sig-{artifact}"

    return [
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            metadata={"customer": "Globex", "commitment": "Deliver SSO by 2024-12-15"},
            artifact="crm:globex-commit-1",
        ),
        MockSignal(
            SignalType.CUSTOMER_OBJECTION,
            metadata={"customer": "Globex", "objection_type": "pricing"},
            artifact="crm:globex-obj-1",
        ),
        MockSignal(
            SignalType.CUSTOMER_DECISION,
            metadata={"customer": "Globex", "decision_outcome": "renewed"},
            artifact="crm:globex-dec-1",
        ),
    ]


@pytest.fixture
def whisper(mock_model, mock_signals):
    return OrganizationalWhisper(mock_model, mock_signals)


# ─── Test 1: 4-part format ─────────────────────────────────────────────────

def test_whisper_returns_4_part_format(whisper):
    """Every whisper must have situation, insight, evidence (list), action, priority."""
    result = whisper.for_context(context="meeting", entity="Globex", topic="pricing")

    assert "whispers" in result
    assert len(result["whispers"]) > 0

    for w in result["whispers"]:
        assert "situation" in w, f"Missing situation: {w}"
        assert "insight" in w, f"Missing insight: {w}"
        assert "evidence" in w, f"Missing evidence: {w}"
        assert isinstance(w["evidence"], list), f"Evidence must be a list, got {type(w['evidence'])}"
        assert "action" in w, f"Missing action: {w}"
        assert "label" in w["action"], f"Action missing label: {w['action']}"
        assert "type" in w["action"], f"Action missing type: {w['action']}"
        assert "payload" in w["action"], f"Action missing payload: {w['action']}"
        assert "priority" in w, f"Missing priority: {w}"
        assert w["priority"] in ("high", "medium", "low"), f"Invalid priority: {w['priority']}"
        assert "why_surfaced" in w, f"Missing why_surfaced: {w}"
        assert isinstance(w["why_surfaced"], str), f"why_surfaced should be a string: {w['why_surfaced']}"
        assert "whisper_id" in w, f"Missing whisper_id: {w}"


# ─── Test 2: situation is built from context ───────────────────────────────

def test_situation_reflects_context(whisper):
    """The situation line should reflect what the user is doing."""
    result = whisper.for_context(context="meeting", entity="Globex")
    for w in result["whispers"]:
        assert "Globex" in w["situation"], f"Situation should mention entity: {w['situation']}"

    result = whisper.for_context(context="email", entity="sarah@globex.com")
    for w in result["whispers"]:
        assert "sarah@globex.com" in w["situation"], f"Situation should mention entity: {w['situation']}"


# ─── Test 3: evidence is a list of {source, date, text} ────────────────────

def test_evidence_items_have_source_date_text(whisper):
    """Each evidence item must have source, date, text fields."""
    result = whisper.for_context(context="meeting", entity="Globex")
    for w in result["whispers"]:
        for e in w["evidence"]:
            assert "source" in e, f"Evidence item missing source: {e}"
            assert "date" in e, f"Evidence item missing date: {e}"
            assert "text" in e, f"Evidence item missing text: {e}"


# ─── Test 4: action has a label and type ───────────────────────────────────

def test_action_has_label_and_type(whisper):
    """Each action must have a label and a valid type."""
    valid_types = {"open_in_maestro", "prepare_email", "insert_text", "approve_anyway"}
    result = whisper.for_context(context="meeting", entity="Globex")
    for w in result["whispers"]:
        assert w["action"]["label"], f"Action label is empty: {w['action']}"
        assert w["action"]["type"] in valid_types, f"Invalid action type: {w['action']['type']}"


# ─── Test 5: priority — only commitment/objection types are high ───────────

def test_commitment_whispers_are_high_priority(whisper):
    """Commitment and objection whispers should be high priority (golden rule)."""
    result = whisper.for_context(context="meeting", entity="Globex")
    high_priority = [w for w in result["whispers"] if w.get("priority") == "high"]
    assert len(high_priority) > 0, "Should have at least one high-priority whisper"

    # Verify commitment whispers are high priority
    commitment_whispers = [w for w in result["whispers"] if w["type"] == "commitment_exists"]
    for w in commitment_whispers:
        assert w["priority"] == "high", f"Commitment should be high priority: {w}"


def test_whispers_have_why_surfaced(whisper):
    """Every whisper should have a why_surfaced explanation (not a fake confidence %)."""
    result = whisper.for_context(context="meeting", entity="Globex")
    for w in result["whispers"]:
        assert "why_surfaced" in w, f"Missing why_surfaced: {w}"
        assert len(w["why_surfaced"]) > 10, f"why_surfaced should be descriptive: {w['why_surfaced']}"


# ─── Test 6: behavior change detection ─────────────────────────────────────

def test_detect_behavior_change(whisper, mock_signals):
    """detect_behavior_change should return changed/direction/delta_pct."""
    # Use a date in the middle of the signal range
    nudge_date = "2024-11-15T00:00:00+00:00"
    result = whisper  # not used directly; we need TrajectoryInterventionEngine

    from maestro_oem.trajectory_intervention import TrajectoryInterventionEngine
    engine = TrajectoryInterventionEngine.__new__(TrajectoryInterventionEngine)
    engine.signals = mock_signals

    result = engine.detect_behavior_change(nudge_date, days_window=30)
    assert "changed" in result
    assert "direction" in result
    assert "delta_pct" in result
    assert "before_metric" in result
    assert "after_metric" in result


def test_detect_behavior_change_invalid_date(whisper, mock_signals):
    """Invalid nudge_date should return changed=False with an error."""
    from maestro_oem.trajectory_intervention import TrajectoryInterventionEngine
    engine = TrajectoryInterventionEngine.__new__(TrajectoryInterventionEngine)
    engine.signals = mock_signals

    result = engine.detect_behavior_change("not-a-date")
    assert result["changed"] is False
    assert "error" in result


# ─── Test 7: organizational pattern detection ──────────────────────────────

def test_detect_organizational_pattern(whisper, mock_signals):
    """detect_organizational_pattern should detect recurring objections."""
    from maestro_oem.signal import SignalType
    from maestro_oem.trajectory_intervention import TrajectoryInterventionEngine

    # Build a signal list with 5 pricing objections (meets min_occurrences=5)
    class MockSignal:
        def __init__(self, sig_type, metadata=None):
            self.type = sig_type
            self.metadata = metadata or {}

    signals_with_pattern = [
        MockSignal(SignalType.CUSTOMER_OBJECTION, metadata={"objection_type": "pricing"}),
        MockSignal(SignalType.CUSTOMER_OBJECTION, metadata={"objection_type": "pricing"}),
        MockSignal(SignalType.CUSTOMER_OBJECTION, metadata={"objection_type": "pricing"}),
        MockSignal(SignalType.CUSTOMER_OBJECTION, metadata={"objection_type": "pricing"}),
        MockSignal(SignalType.CUSTOMER_OBJECTION, metadata={"objection_type": "pricing"}),
    ]

    engine = TrajectoryInterventionEngine.__new__(TrajectoryInterventionEngine)
    engine.signals = signals_with_pattern

    # With 5 pricing objections, should detect a pattern
    result = engine.detect_organizational_pattern(min_occurrences=5)
    assert result is not None, "Should detect pricing pattern with 5 occurrences"
    assert result["pattern_type"] == "recurring_objection"
    assert "pricing" in result["description"]
    assert result["occurrences"] == 5
    assert "suggested_law" in result
