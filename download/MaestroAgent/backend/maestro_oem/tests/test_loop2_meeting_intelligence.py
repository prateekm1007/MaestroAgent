"""Loop 2 — Meeting Intelligence: adversarial tests.

CEO directive: build Loop 2 — Meeting Intelligence (auditor's recommendation,
now CEO-validated). "Builds naturally on Loop 1 (commitments surface in
meetings, meetings have preparation, preparation has recall). The Situation
abstraction from Loop 1.5 gives Meeting Intelligence a natural unit to work
with."

Loop 2 tests whether Maestro can:
  1. Treat a meeting as a first-class object with a lifecycle
     (scheduled → prepared → occurred → outcome_observed → learning_recorded)
  2. Assemble a Situation before the meeting (uses Loop 1.5 SituationBuilder)
  3. Record what was discussed/decided/committed during the meeting
  4. Observe the meeting's outcome (commitments made/mutated/broken)
  5. Write a Meeting Learning Ledger entry (extends Loop 1's LearningLedger)
  6. Detect cross-meeting patterns ("third meeting where pricing came up")

These tests are adversarial: each assertion is non-vacuous (would fail on
the pre-Loop-2 codebase). Write first, watch fail, then build.

Design decisions (documented for audit per CEO directive):
  - Meeting is a dataclass with lifecycle states (enum)
  - MeetingStore is in-memory for this iteration (SQLite migration deferred)
  - MeetingIntelligenceLoop wires the lifecycle using existing modules
    (SituationBuilder, CommitmentMutationTracker, LearningLedger)
  - Cross-meeting patterns detected by topic frequency across meetings
  - HTTP endpoints ship in the same commit (per established pattern)
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

from maestro_oem.signal import SignalType


# ─── Mocks (legitimate DI) ─────────────────────────────────────────────────

class MockSignal:
    """Mirror of real ExecutionSignal shape."""
    def __init__(self, sig_type, actor="", artifact="", metadata=None, timestamp=None, provider="customer"):
        self.type = sig_type
        self.actor = actor
        self.artifact = artifact
        self.metadata = metadata or {}
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.signal_id = f"sig-{artifact or id(self)}"
        self.provider = type("P", (), {"value": provider})()


@pytest.fixture
def now():
    return datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def tomorrow():
    return datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def globex_signals(now):
    """Signals for Globex — commitment + objection."""
    return [
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane.d@acme.com",
            artifact="crm:globex-commit-1",
            metadata={"customer": "Globex", "commitment": "Deliver SSO by 2024-12-15"},
            timestamp=now - timedelta(days=20),
        ),
        MockSignal(
            SignalType.CUSTOMER_OBJECTION,
            actor="jane.d@acme.com",
            artifact="crm:globex-obj-1",
            metadata={"customer": "Globex", "objection_type": "pricing"},
            timestamp=now - timedelta(days=5),
        ),
    ]


# ─── 1. Meeting dataclass + lifecycle ─────────────────────────────────────

def test_meeting_has_lifecycle_states():
    """Meeting must have a MeetingStatus enum with 5 lifecycle states.

    States: SCHEDULED, PREPARED, OCCURRED, OUTCOME_OBSERVED, LEARNING_RECORDED
    """
    from maestro_oem.meeting import MeetingStatus

    states = {s.name for s in MeetingStatus}
    assert "SCHEDULED" in states, f"SCHEDULED must be a lifecycle state. Got: {states}"
    assert "PREPARED" in states, f"PREPARED must be a lifecycle state. Got: {states}"
    assert "OCCURRED" in states, f"OCCURRED must be a lifecycle state. Got: {states}"
    assert "OUTCOME_OBSERVED" in states, f"OUTCOME_OBSERVED must be a lifecycle state. Got: {states}"
    assert "LEARNING_RECORDED" in states, f"LEARNING_RECORDED must be a lifecycle state. Got: {states}"


def test_meeting_dataclass_has_required_fields(now, tomorrow):
    """Meeting must have: id, title, entity, attendees, start, end, status,
    situation, topics_discussed, commitments_made, outcome, learning_entry.
    """
    from maestro_oem.meeting import Meeting, MeetingStatus

    meeting = Meeting(
        title="Globex Quarterly Review",
        entity="Globex",
        attendees=["ceo@globex.com", "jane.d@acme.com"],
        start=tomorrow.replace(hour=10, minute=0),
        end=tomorrow.replace(hour=11, minute=0),
    )

    assert meeting.title == "Globex Quarterly Review"
    assert meeting.entity == "Globex"
    assert meeting.status == MeetingStatus.SCHEDULED  # Default state
    assert meeting.situation is None  # Not yet prepared
    assert meeting.topics_discussed == []  # Not yet occurred
    assert meeting.commitments_made == []  # Not yet occurred
    assert meeting.outcome is None  # Not yet observed
    assert meeting.learning_entry is None  # Not yet recorded


# ─── 2. Meeting lifecycle transitions ─────────────────────────────────────

def test_meeting_lifecycle_prepare(globex_signals, now, tomorrow):
    """prepare() transitions SCHEDULED → PREPARED + assembles a Situation."""
    from maestro_oem.meeting import Meeting, MeetingStatus
    from maestro_oem.meeting_intelligence_loop import MeetingIntelligenceLoop

    meeting = Meeting(
        title="Globex Quarterly Review",
        entity="Globex",
        attendees=["ceo@globex.com", "jane.d@acme.com"],
        start=tomorrow.replace(hour=10, minute=0),
        end=tomorrow.replace(hour=11, minute=0),
    )

    loop = MeetingIntelligenceLoop(signals=globex_signals, now=now)
    loop.prepare(meeting)

    assert meeting.status == MeetingStatus.PREPARED, \
        f"prepare() must transition to PREPARED. Got: {meeting.status}"
    assert meeting.situation is not None, "prepare() must assemble a Situation"
    assert "Globex" in meeting.situation.entities, \
        f"Situation must include Globex. Got: {meeting.situation.entities}"


def test_meeting_lifecycle_occur(globex_signals, now, tomorrow):
    """occur() transitions PREPARED → OCCURRED + records topics + commitments."""
    from maestro_oem.meeting import Meeting, MeetingStatus
    from maestro_oem.meeting_intelligence_loop import MeetingIntelligenceLoop

    meeting = Meeting(
        title="Globex Quarterly Review",
        entity="Globex",
        attendees=["ceo@globex.com", "jane.d@acme.com"],
        start=tomorrow.replace(hour=10, minute=0),
        end=tomorrow.replace(hour=11, minute=0),
    )

    loop = MeetingIntelligenceLoop(signals=globex_signals, now=now)
    loop.prepare(meeting)
    loop.occur(meeting, topics_discussed=["pricing", "SSO delivery"],
               commitments_made=["Deliver SSO by 2024-12-15"])

    assert meeting.status == MeetingStatus.OCCURRED, \
        f"occur() must transition to OCCURRED. Got: {meeting.status}"
    assert "pricing" in meeting.topics_discussed, \
        f"topics_discussed must be recorded. Got: {meeting.topics_discussed}"
    assert len(meeting.commitments_made) >= 1, \
        f"commitments_made must be recorded. Got: {meeting.commitments_made}"


def test_meeting_lifecycle_observe_outcome(globex_signals, now, tomorrow):
    """observe_outcome() transitions OCCURRED → OUTCOME_OBSERVED + records outcome."""
    from maestro_oem.meeting import Meeting, MeetingStatus
    from maestro_oem.meeting_intelligence_loop import MeetingIntelligenceLoop

    meeting = Meeting(
        title="Globex Quarterly Review",
        entity="Globex",
        attendees=["ceo@globex.com", "jane.d@acme.com"],
        start=tomorrow.replace(hour=10, minute=0),
        end=tomorrow.replace(hour=11, minute=0),
    )

    loop = MeetingIntelligenceLoop(signals=globex_signals, now=now)
    loop.prepare(meeting)
    loop.occur(meeting, topics_discussed=["pricing"], commitments_made=["Deliver SSO by 2024-12-15"])
    loop.observe_outcome(meeting, outcome="commitment_honored")

    assert meeting.status == MeetingStatus.OUTCOME_OBSERVED, \
        f"observe_outcome() must transition to OUTCOME_OBSERVED. Got: {meeting.status}"
    assert meeting.outcome == "commitment_honored", \
        f"outcome must be recorded. Got: {meeting.outcome}"


def test_meeting_lifecycle_record_learning(globex_signals, now, tomorrow):
    """record_learning() transitions OUTCOME_OBSERVED → LEARNING_RECORDED + writes entry."""
    from maestro_oem.meeting import Meeting, MeetingStatus
    from maestro_oem.meeting_intelligence_loop import MeetingIntelligenceLoop

    meeting = Meeting(
        title="Globex Quarterly Review",
        entity="Globex",
        attendees=["ceo@globex.com", "jane.d@acme.com"],
        start=tomorrow.replace(hour=10, minute=0),
        end=tomorrow.replace(hour=11, minute=0),
    )

    loop = MeetingIntelligenceLoop(signals=globex_signals, now=now)
    loop.prepare(meeting)
    loop.occur(meeting, topics_discussed=["pricing", "SSO delivery"],
               commitments_made=["Deliver SSO by 2024-12-15"])
    loop.observe_outcome(meeting, outcome="commitment_honored")
    entry = loop.record_learning(meeting)

    assert meeting.status == MeetingStatus.LEARNING_RECORDED, \
        f"record_learning() must transition to LEARNING_RECORDED. Got: {meeting.status}"
    assert entry, "Learning entry must be non-empty"
    assert len(entry) >= 20, \
        f"Learning entry must be a real sentence (≥20 chars). Got: {entry!r}"

    # REJECT placeholders (P6)
    FORBIDDEN = ["Learning recorded.", "Meeting complete.", "TODO", "placeholder"]
    for phrase in FORBIDDEN:
        assert phrase.lower() not in entry.lower(), \
            f"Learning entry must not be a placeholder. Got: {entry!r}"

    # Must reference the actual meeting + outcome (signal-derived)
    assert "globex" in entry.lower() or "meeting" in entry.lower(), \
        f"Learning entry must reference the meeting/entity. Got: {entry!r}"
    assert "honored" in entry.lower() or "commitment" in entry.lower(), \
        f"Learning entry must reference the outcome. Got: {entry!r}"


# ─── 3. Meeting Learning Ledger honesty ────────────────────────────────────

def test_meeting_learning_honest_when_commitment_broken(globex_signals, now, tomorrow):
    """When the meeting's outcome is a broken commitment, the learning entry
    must honestly say so — no spin. Maestro never invents precision.
    """
    from maestro_oem.meeting import Meeting
    from maestro_oem.meeting_intelligence_loop import MeetingIntelligenceLoop

    meeting = Meeting(
        title="Globex Emergency Review",
        entity="Globex",
        attendees=["ceo@globex.com", "jane.d@acme.com"],
        start=tomorrow.replace(hour=10, minute=0),
        end=tomorrow.replace(hour=11, minute=0),
    )

    loop = MeetingIntelligenceLoop(signals=globex_signals, now=now)
    loop.prepare(meeting)
    loop.occur(meeting, topics_discussed=["pricing"], commitments_made=[])
    loop.observe_outcome(meeting, outcome="commitment_broken")
    entry = loop.record_learning(meeting)

    assert "broken" in entry.lower() or "missed" in entry.lower() or "failed" in entry.lower(), \
        f"Learning entry must honestly say commitment was broken. Got: {entry!r}"
    # Must NOT spin it positively
    assert "honored" not in entry.lower() and "fulfilled" not in entry.lower(), \
        f"Learning entry must NOT spin a broken commitment as honored. Got: {entry!r}"


# ─── 4. Cross-meeting pattern detection ────────────────────────────────────

def test_cross_meeting_pattern_detects_recurring_topic(globex_signals, now, tomorrow):
    """When the same topic (pricing) comes up in 3 meetings, Maestro detects
    the pattern: 'this is the third meeting where pricing came up.'

    This is the cross-meeting narrative capability — Maestro connects
    meetings into a story, not just a list.
    """
    from maestro_oem.meeting import Meeting
    from maestro_oem.meeting_intelligence_loop import MeetingIntelligenceLoop
    from maestro_oem.cross_meeting_patterns import CrossMeetingPatternDetector

    # Three meetings, all with "pricing" as a topic
    meetings = []
    for i in range(3):
        m = Meeting(
            title=f"Globex Review #{i+1}",
            entity="Globex",
            attendees=["ceo@globex.com"],
            start=tomorrow.replace(hour=10 + i),
            end=tomorrow.replace(hour=11 + i),
        )
        # Simulate that the meeting occurred with "pricing" discussed
        m.topics_discussed = ["pricing"]
        meetings.append(m)

    detector = CrossMeetingPatternDetector()
    patterns = detector.detect(meetings)

    assert len(patterns) >= 1, \
        f"Must detect the recurring pricing pattern. Got: {patterns}"
    pricing_pattern = next(
        (p for p in patterns if "pricing" in p.topic.lower()),
        None,
    )
    assert pricing_pattern is not None, "Must detect the pricing pattern specifically"
    assert pricing_pattern.meeting_count >= 3, \
        f"Pattern must count 3 meetings. Got: {pricing_pattern.meeting_count}"
    assert "third" in pricing_pattern.description.lower() or "3" in pricing_pattern.description, \
        f"Pattern description must mention frequency. Got: {pricing_pattern.description!r}"


def test_cross_meeting_pattern_no_false_positive_for_single_meeting(globex_signals, now, tomorrow):
    """A topic discussed in only 1 meeting does NOT trigger a pattern.

    Non-vacuous counter-test: false positives erode trust.
    """
    from maestro_oem.meeting import Meeting
    from maestro_oem.cross_meeting_patterns import CrossMeetingPatternDetector

    meetings = [
        Meeting(
            title="One-off meeting",
            entity="Globex",
            attendees=[],
            start=tomorrow.replace(hour=10),
            end=tomorrow.replace(hour=11),
        ),
    ]
    meetings[0].topics_discussed = ["one_off_topic"]

    detector = CrossMeetingPatternDetector()
    patterns = detector.detect(meetings, min_meetings=2)  # min 2 meetings to be a pattern

    assert len(patterns) == 0, \
        f"A topic in only 1 meeting must NOT trigger a pattern. Got: {patterns}"


# ─── 5. Full lifecycle end-to-end ──────────────────────────────────────────

def test_meeting_intelligence_full_lifecycle(globex_signals, now, tomorrow):
    """ONE test that exercises the whole Meeting Intelligence loop:

    schedule → prepare → occur → observe_outcome → record_learning

    The learning entry must be signal-derived, honest, and reference the
    actual meeting + outcome.
    """
    from maestro_oem.meeting import Meeting, MeetingStatus
    from maestro_oem.meeting_intelligence_loop import MeetingIntelligenceLoop

    meeting = Meeting(
        title="Globex Quarterly Review",
        entity="Globex",
        attendees=["ceo@globex.com", "jane.d@acme.com"],
        start=tomorrow.replace(hour=10, minute=0),
        end=tomorrow.replace(hour=11, minute=0),
    )

    loop = MeetingIntelligenceLoop(signals=globex_signals, now=now)

    # Full lifecycle
    loop.prepare(meeting)
    assert meeting.status == MeetingStatus.PREPARED

    loop.occur(meeting,
               topics_discussed=["pricing", "SSO delivery", "renewal"],
               commitments_made=["Deliver SSO by 2024-12-15"])
    assert meeting.status == MeetingStatus.OCCURRED

    loop.observe_outcome(meeting, outcome="commitment_honored")
    assert meeting.status == MeetingStatus.OUTCOME_OBSERVED

    entry = loop.record_learning(meeting)
    assert meeting.status == MeetingStatus.LEARNING_RECORDED
    assert entry
    assert len(entry) >= 20

    # The entry must reference what actually happened
    assert "globex" in entry.lower() or "meeting" in entry.lower(), \
        f"Must reference the meeting/entity. Got: {entry!r}"
    assert "honored" in entry.lower() or "commitment" in entry.lower(), \
        f"Must reference the outcome. Got: {entry!r}"

    # The meeting must carry the full history
    assert meeting.situation is not None, "Situation must be assembled"
    assert len(meeting.topics_discussed) == 3, "3 topics must be recorded"
    assert len(meeting.commitments_made) == 1, "1 commitment must be recorded"
    assert meeting.outcome == "commitment_honored"
    assert meeting.learning_entry == entry, "Learning entry must be persisted on the meeting"
