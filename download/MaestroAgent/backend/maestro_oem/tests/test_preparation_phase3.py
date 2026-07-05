"""Phase 3: Adversarial tests for Anticipatory Preparation.

Director directive (2026-07-03, AUDIT-0644916):

> Phase 3 spec is in the worklog (EXT-AUDITOR-SYNTHESIS). Calendar
> integration is the first trigger source. Filter to consequential
> conversations (not all meetings). Populate preparation fields from
> real signals via EvidenceBuilder.

Adversarial tests — write first, watch fail, then build until pass:

  1. test_preparation_filters_to_consequential
     Given a calendar with 5 events (2 trivial standups + 3 customer
     meetings with active signals), only the 3 consequential ones are
     prepared. Old engine prepped for first 3 customers regardless.

  2. test_preparation_uses_calendar_source
     The meeting list comes from an injected CalendarSource, NOT from
     a hardcoded "{customer} Quarterly Review" generator. Proves the
     engine is calendar-driven, not signal-driven.

  3. test_preparation_includes_evidence_from_signals
     Each prepared meeting has an Evidence Spine with observed_facts
     populated from REAL signals (commitments, objections) — not
     placeholders, not empty.

  4. test_preparation_includes_objection_history
     For a meeting with Globex (who has pricing objections), the prep
     must include the objection history. Old engine populated
     previous_objections but the new engine must surface it in the
     evidence_spine.conflicting_evidence too.

  5. test_preparation_flags_commitment_risk
     For a meeting with a customer who has a broken commitment, the
     prep must flag the meeting as at_risk=True with the broken
     commitment in the evidence.

P2: Untested code is unverified code. P5: Self-certification is weak
evidence. P6: Fail closed — placeholder evidence rejected.
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

from maestro_oem.preparation_engine import PreparationEngine
from maestro_oem.calendar_source import CalendarSource, CalendarEvent, StaticCalendarSource
from maestro_oem.evidence import Evidence


# ─── Fixtures ──────────────────────────────────────────────────────────────

class MockSignal:
    """Mock OEM signal — mirrors real ExecutionSignal shape."""

    def __init__(
        self,
        sig_type: Any,
        actor: str = "",
        artifact: str = "",
        metadata: dict | None = None,
        timestamp: datetime | None = None,
        provider: str = "customer",
    ):
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
    """Signals for Globex — has a commitment + a pricing objection."""
    from maestro_oem.signal import SignalType
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


@pytest.fixture
def initech_signals(now):
    """Signals for Initech — has a broken commitment."""
    from maestro_oem.signal import SignalType
    return [
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="bill.l@initech.com",
            artifact="crm:initech-commit-1",
            metadata={"customer": "Initech", "commitment": "API integration by Q3"},
            timestamp=now - timedelta(days=40),
        ),
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_BROKEN,
            actor="bill.l@initech.com",
            artifact="crm:initech-broken-1",
            metadata={"customer": "Initech", "commitment": "API integration by Q3"},
            timestamp=now - timedelta(days=2),
        ),
    ]


@pytest.fixture
def consequential_calendar(tomorrow):
    """Calendar with 5 events: 2 trivial + 3 consequential.

    The 2 trivial events (standup, lunch) should be FILTERED OUT.
    The 3 consequential events (customer meetings with active signals)
    should be PREPARED FOR.
    """
    return StaticCalendarSource([
        # Trivial — should be filtered out
        CalendarEvent(
            title="Daily Standup",
            start=tomorrow.replace(hour=9, minute=0),
            end=tomorrow.replace(hour=9, minute=15),
            entity="",
            attendees=["team@acme.com"],
        ),
        CalendarEvent(
            title="Lunch with Sam",
            start=tomorrow.replace(hour=12, minute=30),
            end=tomorrow.replace(hour=13, minute=30),
            entity="",
            attendees=["sam@acme.com"],
        ),
        # Consequential — customer meetings with entities
        CalendarEvent(
            title="Globex Quarterly Review",
            start=tomorrow.replace(hour=10, minute=0),
            end=tomorrow.replace(hour=11, minute=0),
            entity="Globex",
            attendees=["ceo@globex.com", "jane.d@acme.com"],
        ),
        CalendarEvent(
            title="Initech Renewal Discussion",
            start=tomorrow.replace(hour=14, minute=0),
            end=tomorrow.replace(hour=15, minute=0),
            entity="Initech",
            attendees=["ceo@initech.com", "bill.l@initech.com"],
        ),
        CalendarEvent(
            title="Hooli Expansion Call",
            start=tomorrow.replace(hour=16, minute=0),
            end=tomorrow.replace(hour=16, minute=30),
            entity="Hooli",
            attendees=["vp@hooli.com"],
        ),
    ])


# ─── Adversarial Test 1: Filter to consequential conversations ─────────────

def test_preparation_filters_to_consequential(
    consequential_calendar, globex_signals, initech_signals, now
):
    """Only consequential meetings should be prepared — not standups, not lunch.

    Old engine: generated synthetic "{customer} Quarterly Review" for
    every customer with signals, regardless of whether a meeting was
    actually scheduled. Did NOT filter trivial events because it had no
    calendar source.

    New engine: takes a CalendarSource, filters out events with no
    entity AND no consequentiality signal. Returns only the 3 customer
    meetings.
    """
    all_signals = globex_signals + initech_signals
    engine = PreparationEngine(
        model=None,
        signals=all_signals,
        calendar_source=consequential_calendar,
        now=now,
    )
    brief = engine.prepare_for_tomorrow(org_id="default")

    meetings = brief.get("meetings", [])
    meeting_titles = [m.get("title", "") for m in meetings]

    # The 2 trivial events MUST be excluded
    assert "Daily Standup" not in meeting_titles, \
        f"Trivial standup must be filtered out, got: {meeting_titles}"
    assert "Lunch with Sam" not in meeting_titles, \
        f"Trivial lunch must be filtered out, got: {meeting_titles}"

    # The 3 consequential customer meetings MUST be included
    assert "Globex Quarterly Review" in meeting_titles, \
        f"Globex meeting must be included, got: {meeting_titles}"
    assert "Initech Renewal Discussion" in meeting_titles, \
        f"Initech meeting must be included, got: {meeting_titles}"
    assert "Hooli Expansion Call" in meeting_titles, \
        f"Hooli meeting must be included, got: {meeting_titles}"


# ─── Adversarial Test 2: Meeting list comes from calendar source ───────────

def test_preparation_uses_calendar_source(
    consequential_calendar, globex_signals, now
):
    """The meeting list must come from the injected CalendarSource.

    Old engine: generated synthetic "{customer} Quarterly Review" at
    "10:00" for the first 3 customers with signals. No real calendar
    integration.

    New engine: accepts a CalendarSource. The meeting titles, times,
    and attendees come from the source — not from signal-driven
    synthesis.
    """
    engine = PreparationEngine(
        model=None,
        signals=globex_signals,
        calendar_source=consequential_calendar,
        now=now,
    )
    brief = engine.prepare_for_tomorrow(org_id="default")

    meetings = brief.get("meetings", [])
    assert len(meetings) > 0, "Must have at least 1 meeting"

    # Check that meeting TIMES come from the calendar (not hardcoded "10:00")
    # The Globex meeting is at 10:00, Initech at 14:00, Hooli at 16:00
    meeting_times = {m.get("time", "") for m in meetings}
    # At least 2 distinct times — proves they're not all "10:00"
    assert len(meeting_times) >= 2, \
        f"Meeting times must come from calendar (varied), got: {meeting_times}"

    # Check that meeting TITLES come from the calendar (not synthesized)
    for m in meetings:
        title = m.get("title", "")
        # Old engine would generate "Globex Quarterly Review" via f-string,
        # but the calendar has the EXACT title. Check it matches the source.
        # Specifically: the Initech meeting title is "Initech Renewal Discussion"
        # — old engine would have generated "Initech Quarterly Review"
        if "Initech" in title:
            assert title == "Initech Renewal Discussion", \
                f"Initech title must come from calendar, got: {title!r}"

    # Check attendees are propagated from the calendar
    globex_meeting = next((m for m in meetings if "Globex" in m.get("title", "")), None)
    assert globex_meeting is not None, "Globex meeting must be present"
    attendees = globex_meeting.get("attendees", [])
    assert "ceo@globex.com" in attendees, \
        f"Attendees must come from calendar, got: {attendees}"


# ─── Adversarial Test 3: Evidence from real signals, not placeholders ──────

def test_preparation_includes_evidence_from_signals(
    consequential_calendar, globex_signals, now
):
    """Each prepared meeting must have an Evidence Spine with observed_facts
    populated from REAL signals — not placeholders, not empty.

    The auditor's Phase 1 audit required: "observed_facts non-empty, not
    placeholder strings." Phase 3 raises the bar: the observed_facts
    must reference actual signal content (commitment text, objection
    type) for the meeting's entity.
    """
    engine = PreparationEngine(
        model=None,
        signals=globex_signals,
        calendar_source=consequential_calendar,
        now=now,
    )
    brief = engine.prepare_for_tomorrow(org_id="default")

    globex_meeting = next(
        (m for m in brief["meetings"] if "Globex" in m.get("title", "")),
        None,
    )
    assert globex_meeting is not None, "Globex meeting must be present"

    es = globex_meeting.get("evidence_spine", {})
    assert "observed_facts" in es, "evidence_spine missing observed_facts"
    assert len(es["observed_facts"]) > 0, "observed_facts must be non-empty"

    FORBIDDEN_PLACEHOLDERS = {
        "",
        "No specific commitments found",
        "Maestro detected relevant organizational knowledge",
        "Recorded in OEM",
        "Recorded in calendar",
    }
    facts_text = ""
    for fact in es["observed_facts"]:
        text = fact.get("text", "")
        assert text not in FORBIDDEN_PLACEHOLDERS, \
            f"Placeholder text forbidden in observed_facts: {text!r}"
        facts_text += " " + text

    # The observed_facts must reference the actual commitment text from
    # the Globex signal ("Deliver SSO by 2024-12-15") OR the actual
    # objection type ("pricing"). This proves the engine pulled from
    # real signals, not from a template.
    assert "SSO" in facts_text or "pricing" in facts_text.lower() or "commitment" in facts_text.lower(), \
        f"observed_facts must reference real signal content, got: {facts_text!r}"


# ─── Adversarial Test 4: Objection history surfaces in evidence ────────────

def test_preparation_includes_objection_history(
    consequential_calendar, globex_signals, now
):
    """For a meeting with Globex (who has pricing objections), the prep
    must surface the objection history in the evidence.

    Old engine: populated `previous_objections` in the preparation dict
    but did NOT surface it in the evidence_spine. The Evidence Spine
    only had commitment facts, not objection facts.

    New engine: when an entity has BOTH commitments AND objections, the
    evidence_spine.conflicting_evidence must include the objection —
    this is exactly what EvidenceBuilder._build_commitment_evidence
    already does (Phase 1). Phase 3 must USE it.
    """
    engine = PreparationEngine(
        model=None,
        signals=globex_signals,
        calendar_source=consequential_calendar,
        now=now,
    )
    brief = engine.prepare_for_tomorrow(org_id="default")

    globex_meeting = next(
        (m for m in brief["meetings"] if "Globex" in m.get("title", "")),
        None,
    )
    assert globex_meeting is not None

    es = globex_meeting["evidence_spine"]

    # Globex has a pricing objection — it must appear somewhere in the
    # evidence (either in observed_facts OR in conflicting_evidence)
    has_objection_in_facts = any(
        "pricing" in f.get("text", "").lower() or "objection" in f.get("text", "").lower()
        for f in es.get("observed_facts", [])
    )
    has_objection_in_conflicts = any(
        "pricing" in c.get("claim", "").lower() or "objection" in c.get("claim", "").lower()
        for c in es.get("conflicting_evidence", [])
    )
    assert has_objection_in_facts or has_objection_in_conflicts, \
        f"Globex pricing objection must surface in evidence (facts or conflicts). " \
        f"observed_facts={es.get('observed_facts')}, " \
        f"conflicting_evidence={es.get('conflicting_evidence')}"

    # The preparation dict must also include previous_objections
    prep = globex_meeting.get("preparation", {})
    prev_objections = prep.get("previous_objections", [])
    assert len(prev_objections) > 0, \
        "preparation.previous_objections must be non-empty for Globex (has pricing objection)"
    assert any("pricing" in o.get("type", "").lower() for o in prev_objections), \
        f"previous_objections must include pricing, got: {prev_objections}"


# ─── Adversarial Test 5: Broken commitments flag meeting as at-risk ────────

def test_preparation_flags_commitment_risk(
    consequential_calendar, globex_signals, initech_signals, now
):
    """For a meeting with Initech (who has a broken commitment), the prep
    must flag the meeting as at_risk=True with the broken commitment
    in the evidence.

    Old engine: did not compute at_risk flag. Commitments_at_risk was
    a separate top-level list, not per-meeting.

    New engine: each meeting has an at_risk boolean. True when the
    entity has a CUSTOMER_COMMITMENT_BROKEN signal. The broken
    commitment text must appear in the evidence.
    """
    all_signals = globex_signals + initech_signals
    engine = PreparationEngine(
        model=None,
        signals=all_signals,
        calendar_source=consequential_calendar,
        now=now,
    )
    brief = engine.prepare_for_tomorrow(org_id="default")

    initech_meeting = next(
        (m for m in brief["meetings"] if "Initech" in m.get("title", "")),
        None,
    )
    assert initech_meeting is not None, "Initech meeting must be present"

    # at_risk flag must be True (Initech has a broken commitment)
    assert initech_meeting.get("at_risk") is True, \
        f"Initech meeting must be flagged at_risk=True (broken commitment). Got: {initech_meeting.get('at_risk')}"

    # The Globex meeting (no broken commitment) must NOT be at_risk
    globex_meeting = next(
        (m for m in brief["meetings"] if "Globex" in m.get("title", "")),
        None,
    )
    assert globex_meeting is not None
    assert globex_meeting.get("at_risk") is False, \
        f"Globex meeting must be at_risk=False (no broken commitment). Got: {globex_meeting.get('at_risk')}"

    # The Initech evidence must reference the broken commitment
    es = initech_meeting["evidence_spine"]
    all_evidence_text = " ".join(
        f.get("text", "") for f in es.get("observed_facts", [])
    ) + " " + " ".join(
        c.get("claim", "") for c in es.get("conflicting_evidence", [])
    )
    assert "broken" in all_evidence_text.lower() or "broke" in all_evidence_text.lower() or "missed" in all_evidence_text.lower(), \
        f"Initech evidence must reference the broken commitment. Got: {all_evidence_text!r}"
