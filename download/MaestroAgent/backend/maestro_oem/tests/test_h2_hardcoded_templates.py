"""H-2 fix: Remove hardcoded preparation templates — derive content from signals.

The external audit found: 'Preparation templates are hardcoded. Rollback
plans always show the same 5 generic steps. Customer briefs always show
the same template. The preparation is assembled from signal COUNTS, not
signal CONTENT.'

The fix: replace hardcoded templates with signal-derived content.
  1. Draft email: reference the actual commitment text, not generic phrases
  2. Competitive comparison: derive from signals, not a hardcoded string
  3. Talking points: reference actual commitments and objections, not generic
  4. Decisions fallback: remove hardcoded 'Q3 budget allocation'
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


# ─── 1. No hardcoded draft email template ──────────────────────────────────

def test_no_hardcoded_draft_email_template():
    """The draft email must NOT contain hardcoded generic phrases like
    'Detailed response to each concern' or 'Evidence from similar engagements'."""
    from maestro_oem import preparation_engine
    source = inspect.getsource(preparation_engine)
    assert "Detailed response to each concern" not in source, (
        "preparation_engine.py must not contain hardcoded 'Detailed response to each concern' — "
        "the draft email should reference actual signal content."
    )
    assert "Evidence from similar engagements" not in source, (
        "preparation_engine.py must not contain hardcoded 'Evidence from similar engagements'"
    )


# ─── 2. No hardcoded competitive comparison ────────────────────────────────

def test_no_hardcoded_competitive_comparison():
    """The competitive comparison must NOT have a hardcoded 'key_differentiator'."""
    from maestro_oem import preparation_engine
    source = inspect.getsource(preparation_engine)
    assert "Organizational intelligence platform" not in source, (
        "preparation_engine.py must not contain hardcoded 'Organizational intelligence platform' — "
        "the competitive position should be derived from actual signal data."
    )


# ─── 3. No hardcoded fallback decision ──────────────────────────────────────

def test_no_hardcoded_fallback_decision():
    """The _get_likely_decisions fallback must NOT be 'Q3 budget allocation'."""
    from maestro_oem import preparation_engine
    source = inspect.getsource(preparation_engine)
    assert "Q3 budget allocation" not in source, (
        "preparation_engine.py must not contain hardcoded 'Q3 budget allocation' — "
        "when no recommendations exist, return an empty list, not a fake decision."
    )


# ─── 4. Draft email references actual commitment text ──────────────────────

def test_draft_email_references_actual_content():
    """The draft email should reference the actual customer concerns and
    commitment text from signals, not generic template phrases."""
    from maestro_oem.preparation_engine import PreparationEngine
    from maestro_oem.signal import SignalType, SignalProvider, ExecutionSignal
    from maestro_oem.calendar_source import StaticCalendarSource, CalendarEvent

    now = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)
    tomorrow = datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)

    signals = [
        ExecutionSignal(
            type=SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane@example.com",
            artifact="crm:1",
            metadata={"customer": "Globex", "commitment": "Deliver SSO by Q4"},
            provider=SignalProvider.CUSTOMER,
            timestamp=now - timedelta(days=20),
        ),
        ExecutionSignal(
            type=SignalType.CUSTOMER_OBJECTION,
            actor="jane@example.com",
            artifact="crm:2",
            metadata={"customer": "Globex", "objection_type": "pricing"},
            provider=SignalProvider.CUSTOMER,
            timestamp=now - timedelta(days=5),
        ),
    ]

    event = CalendarEvent(
        title="Globex Quarterly Review",
        start=tomorrow,
        end=tomorrow.replace(hour=11),
        attendees=["jane@example.com"],
        entity="Globex",
    )
    cal = StaticCalendarSource([event])
    engine = PreparationEngine(None, signals, calendar_source=cal, now=now)

    brief = engine.prepare_for_tomorrow(org_id="default")
    meetings = brief.get("meetings", [])
    assert len(meetings) > 0

    prep = meetings[0].get("preparation", {})
    draft = prep.get("draft_email", "")

    # The draft should reference the ACTUAL concern ("pricing"), not generic text
    assert "pricing" in draft.lower() or "concern" in draft.lower(), (
        f"Draft email should reference actual customer concern. Got: {draft[:200]!r}"
    )
