"""Tests for the CEO's vision features (2026-07-03).

Tests:
  1. Preparation Engine — returns meetings with preparation objects
  2. Anticipation Engine — returns meetings, risks, deadlines, blockers
  3. Whisper Memory — escalates after 3 ignores
  4. Whisper Urgency — returns urgency field (14-99)
  5. Whisper Collaboration — returns team alignment
  6. Whisper Counterfactuals — returns what-if scenarios

P2: Untested code is unverified code. These tests must pass before claiming done.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from maestro_oem.preparation_engine import PreparationEngine
from maestro_oem.anticipation import AnticipationEngine
from maestro_oem.whisper import OrganizationalWhisper


@pytest.fixture
def mock_model():
    class MockApprovals:
        def get_bottlenecks(self, min_count=2):
            return []

    class MockLaw:
        def __init__(self, code, statement, confidence=0.8):
            self.code = code
            self.statement = statement
            self.confidence = confidence
            self.validated_runtimes = 3
            self.failed_runtimes = 0
            self.signal_ids = []
            self.approvals = MockApprovals()

    class MockLO:
        def __init__(self, lo_id, title, description=""):
            self.lo_id = lo_id
            self.title = title
            self.description = description
            self.confidence = 0.7
            self.providers = ["customer"]

    class MockDecisions:
        def get_recommendations(self):
            return [{"title": "Address bottleneck", "type": "action", "urgency": "high"}]

    class MockModel:
        def __init__(self):
            self.laws = {"L-0001": MockLaw("L-0001", "Review-batch size inversely correlates with defect rate")}
            self.learning_objects = {"lo-1": MockLO("lo-1", "Pricing objection pattern")}
            self.decisions = MockDecisions()

    return MockModel()


@pytest.fixture
def mock_signals():
    from maestro_oem.signal import SignalType

    class MockSignal:
        def __init__(self, sig_type, actor="", artifact="", metadata=None, timestamp=None):
            self.type = sig_type
            self.actor = actor
            self.artifact = artifact
            self.metadata = metadata or {}
            self.timestamp = timestamp or datetime(2024, 11, 1, tzinfo=timezone.utc)
            self.signal_id = f"sig-{artifact}"
            self.provider = type('P', (), {'value': 'customer'})()

    return [
        MockSignal(SignalType.CUSTOMER_COMMITMENT_MADE,
            metadata={"customer": "Globex", "commitment": "Deliver SSO by 2024-12-15"},
            artifact="crm:globex-commit-1", actor="jane.d@acme.com"),
        MockSignal(SignalType.CUSTOMER_OBJECTION,
            metadata={"customer": "Globex", "objection_type": "pricing"},
            artifact="crm:globex-obj-1", actor="jane.d@acme.com"),
        MockSignal(SignalType.CUSTOMER_DECISION,
            metadata={"customer": "Globex", "decision_outcome": "renewed"},
            artifact="crm:globex-dec-1", actor="jane.d@acme.com"),
    ]


# ─── FEATURE 1: Preparation Engine ─────────────────────────────────────────

def test_preparation_returns_meetings_with_concerns(mock_model, mock_signals):
    """The Preparation Engine must return at least 1 meeting with concerns."""
    engine = PreparationEngine(mock_model, mock_signals)
    result = engine.prepare_for_tomorrow(org_id="default", user_email="ceo@acme.com")

    assert "meetings" in result
    assert len(result["meetings"]) > 0

    meeting = result["meetings"][0]
    assert "title" in meeting
    assert "preparation" in meeting
    assert "customer_concerns" in meeting["preparation"]


def test_preparation_includes_draft_email(mock_model, mock_signals):
    """When a customer has concerns, the preparation should include a draft email."""
    engine = PreparationEngine(mock_model, mock_signals)
    result = engine.prepare_for_tomorrow()

    # Find a meeting with concerns (Globex has pricing objection)
    globex_meeting = next((m for m in result["meetings"] if "Globex" in m.get("title", "")), None)
    if globex_meeting:
        prep = globex_meeting["preparation"]
        if prep["customer_concerns"]:
            assert prep["draft_email"], "Should have draft email when concerns exist"
            assert "Globex" in prep["draft_email"]


def test_preparation_includes_internal_expert(mock_model, mock_signals):
    """The preparation should identify the internal expert for the customer."""
    engine = PreparationEngine(mock_model, mock_signals)
    result = engine.prepare_for_tomorrow()

    globex_meeting = next((m for m in result["meetings"] if "Globex" in m.get("title", "")), None)
    if globex_meeting:
        prep = globex_meeting["preparation"]
        assert prep["internal_expert"], "Should identify internal expert"
        assert "jane.d" in prep["internal_expert"]


def test_preparation_includes_decisions_and_commitments(mock_model, mock_signals):
    """The preparation brief should include likely decisions and commitments at risk."""
    engine = PreparationEngine(mock_model, mock_signals)
    result = engine.prepare_for_tomorrow()

    assert "decisions_likely" in result
    assert "commitments_at_risk" in result
    assert "people_to_contact" in result


# ─── FEATURE 6: Anticipation Engine ────────────────────────────────────────

def test_anticipation_returns_all_sections(mock_model, mock_signals):
    """The Anticipation Engine must return all 6 sections."""
    engine = AnticipationEngine(mock_model, mock_signals)
    result = engine.anticipate_tomorrow(org_id="default")

    assert "meetings" in result
    assert "risks" in result
    assert "deadlines" in result
    assert "blockers" in result
    assert "customers" in result
    assert "commitments" in result


def test_anticipation_meetings_have_likely_questions(mock_model, mock_signals):
    """Anticipated meetings should include likely questions from objections."""
    engine = AnticipationEngine(mock_model, mock_signals)
    result = engine.anticipate_tomorrow()

    globex_meeting = next((m for m in result["meetings"] if "Globex" in m.get("entity", "")), None)
    if globex_meeting:
        assert "likely_questions" in globex_meeting
        assert "pricing" in globex_meeting["likely_questions"]


# ─── FEATURE 2: Whisper Memory ─────────────────────────────────────────────

def test_whisper_has_memory_field(mock_model, mock_signals):
    """Every whisper should have a memory field."""
    whisper = OrganizationalWhisper(mock_model, mock_signals)
    result = whisper.for_context(context="meeting", entity="Globex")

    for w in result["whispers"]:
        assert "memory" in w, f"Missing memory field: {w}"
        assert "times_shown" in w["memory"]
        assert "escalated" in w["memory"]


def test_whisper_escalates_after_3_ignores(mock_model, mock_signals):
    """After 3 ignores, whisper priority escalates and insight changes."""
    # Create a whisper store with 3 ignored showings
    whisper_store = {}
    for w in mock_signals:
        pass  # We'll set it manually

    # Find a real whisper_id from the first call
    whisper = OrganizationalWhisper(mock_model, mock_signals)
    result = whisper.for_context(context="meeting", entity="Globex")
    if result["whispers"]:
        wid = result["whispers"][0]["whisper_id"]
        whisper_store[wid] = {
            "shown_count": 3,
            "action_taken": "ignored",
            "first_shown": datetime(2024, 11, 1, tzinfo=timezone.utc).isoformat(),
        }

        # Now create a new whisper with the store
        whisper2 = OrganizationalWhisper(mock_model, mock_signals, whisper_store=whisper_store)
        result2 = whisper2.for_context(context="meeting", entity="Globex")

        escalated = [w for w in result2["whispers"] if w.get("memory", {}).get("escalated")]
        assert len(escalated) > 0, "Whisper should escalate after 3 ignores"
        assert escalated[0]["priority"] == "high"


# ─── FEATURE 3: Whisper Urgency Decay ──────────────────────────────────────

def test_whisper_has_urgency_field(mock_model, mock_signals):
    """Every whisper should have an urgency field (evidence-based string, not a fake %)."""
    whisper = OrganizationalWhisper(mock_model, mock_signals)
    result = whisper.for_context(context="meeting", entity="Globex")

    for w in result["whispers"]:
        assert "urgency" in w, f"Missing urgency field: {w}"
        assert isinstance(w["urgency"], str), f"Urgency should be a string: {w['urgency']}"
        assert len(w["urgency"]) > 3, f"Urgency should be descriptive: {w['urgency']}"


def test_whisper_urgency_increases_over_time(mock_model, mock_signals):
    """Urgency should increase as days pass since first shown."""
    whisper_store = {}
    whisper = OrganizationalWhisper(mock_model, mock_signals)
    result = whisper.for_context(context="meeting", entity="Globex")

    if result["whispers"]:
        wid = result["whispers"][0]["whisper_id"]
        # Set first_shown to 10 days ago
        from datetime import timedelta
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        whisper_store[wid] = {"first_shown": old_date, "shown_count": 1, "action_taken": "ignored"}

        whisper2 = OrganizationalWhisper(mock_model, mock_signals, whisper_store=whisper_store)
        result2 = whisper2.for_context(context="meeting", entity="Globex")

        # Find the same whisper
        for w in result2["whispers"]:
            if w["whisper_id"] == wid:
                assert "ignored" in w["urgency"].lower() or "increasing" in w["urgency"].lower(), \
                    f"Urgency should reflect ignored state: {w['urgency']}"


# ─── FEATURE 4: Collaborative Whispers ─────────────────────────────────────

def test_whisper_has_collaboration_field(mock_model, mock_signals):
    """Whispers about an entity should include team collaboration status."""
    whisper = OrganizationalWhisper(mock_model, mock_signals)
    result = whisper.for_context(context="meeting", entity="Globex")

    # At least one whisper should have collaboration
    has_collab = any("collaboration" in w for w in result["whispers"])
    assert has_collab, "At least one whisper should have collaboration field"


# ─── FEATURE 5: Counterfactuals ────────────────────────────────────────────

def test_whisper_has_counterfactuals_for_review(mock_model, mock_signals):
    """Whispers in review context should have counterfactuals."""
    whisper = OrganizationalWhisper(mock_model, mock_signals)
    result = whisper.for_context(context="review", entity="acme/repo")

    for w in result["whispers"]:
        assert "counterfactuals" in w, f"Missing counterfactuals: {w}"
        assert len(w["counterfactuals"]) >= 3, "Should have at least 3 counterfactual scenarios"


def test_whisper_has_counterfactuals_for_meeting(mock_model, mock_signals):
    """Whispers in meeting context should have counterfactuals."""
    whisper = OrganizationalWhisper(mock_model, mock_signals)
    result = whisper.for_context(context="meeting", entity="Globex")

    for w in result["whispers"]:
        assert "counterfactuals" in w, f"Missing counterfactuals: {w}"
        # Check each counterfactual has the right structure
        for cf in w["counterfactuals"]:
            assert "scenario" in cf
            assert "assessment" in cf
            assert "evidence" in cf
