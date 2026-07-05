"""Loop 1 — Commitment Intelligence: end-to-end adversarial test.

CEO directive (2026-07-03):
> Loop 1 wires [Evidence Spine + Hybrid Recall + Anticipatory Preparation]
> together into one complete cognitive loop for one real use case:
> a customer commitment.

This is ONE test that exercises the whole loop. If any step fails,
the loop is broken. The test is adversarial: every assertion is
non-vacuous (would fail on the pre-Loop-1 codebase).

The loop:
  1. A commitment signal exists (Globex, "Deliver SSO by 2024-12-15")
  2. A consequential meeting with Globex is on tomorrow's calendar
  3. Preparation Engine runs → a Whisper fires for the Globex meeting,
     carrying the commitment Evidence Spine
  4. The Whisper has recipient, timing_reason, depth recorded
     (Delivery Intelligence)
  5. The exec asks "what did we promise Globex?" → Ask routes through
     Recall, returns the original commitment Evidence
  6. The exec records action="acted" + decision_influenced +
     follow_up_questions
  7. After the meeting, an outcome signal is recorded (commitment
     honored or broken)
  8. A Learning Ledger entry is written: one honest sentence about
     what happened

P2: Untested code is unverified code. P5: Self-certification is weak.
P6: Fail closed — placeholder Learning Ledger entries REJECTED.
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

from maestro_oem.calendar_source import CalendarEvent, StaticCalendarSource
from maestro_oem.preparation_engine import PreparationEngine
from maestro_oem.recall_engine import RecallEngine
from maestro_oem.evidence import Evidence
from maestro_oem.delivery_intelligence import DeliveryIntelligence
from maestro_oem.learning_ledger import LearningLedger
from maestro_oem.loop1_commitment_intelligence import CommitmentIntelligenceLoop
from maestro_oem.signal import SignalType


# ─── Mocks (legitimate DI — only external deps) ────────────────────────────

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


class MockWhisperHistoryStore:
    """In-memory whisper history store — same interface as WhisperHistoryStore.

    Tracks ALL fields needed by Loop 1: shown_count, action_taken,
    recipient, timing_reason, depth, decision_influenced,
    follow_up_questions, outcome, learning_entry.
    """
    def __init__(self):
        self._history: dict[str, dict[str, Any]] = {}

    def record_shown(self, whisper_id, org_id="default", insight="", embedding=None,
                     entity="", whisper_type="", recipient="", timing_reason="",
                     depth="", materially_changed_since_last_shown=False):
        now = datetime.now(timezone.utc).isoformat()
        if whisper_id not in self._history:
            self._history[whisper_id] = {
                "whisper_id": whisper_id,
                "org_id": org_id,
                "shown_count": 0,
                "action_taken": None,
                "first_shown": now,
                "last_shown": now,
                "insight": insight,
                "entity": entity,
                "type": whisper_type,
                "embedding": embedding,
                "recipient": recipient,
                "timing_reason": timing_reason,
                "depth": depth,
                "materially_changed_since_last_shown": materially_changed_since_last_shown,
                "decision_influenced": None,
                "follow_up_questions": [],
                "outcome": None,
                "learning_entry": None,
            }
        self._history[whisper_id]["shown_count"] += 1
        self._history[whisper_id]["last_shown"] = now
        if recipient:
            self._history[whisper_id]["recipient"] = recipient
        if timing_reason:
            self._history[whisper_id]["timing_reason"] = timing_reason
        if depth:
            self._history[whisper_id]["depth"] = depth

    def record_outcome(self, whisper_id, action, org_id="default",
                       decision_influenced=None, follow_up_questions=None):
        now = datetime.now(timezone.utc).isoformat()
        if whisper_id not in self._history:
            self._history[whisper_id] = {
                "whisper_id": whisper_id, "org_id": org_id,
                "shown_count": 0, "action_taken": None,
                "first_shown": now, "last_shown": now, "insight": "",
            }
        self._history[whisper_id]["action_taken"] = action
        self._history[whisper_id]["last_shown"] = now
        if decision_influenced is not None:
            self._history[whisper_id]["decision_influenced"] = decision_influenced
        if follow_up_questions is not None:
            self._history[whisper_id]["follow_up_questions"] = list(follow_up_questions)

    def record_outcome_signal(self, whisper_id, outcome, org_id="default"):
        """Record what actually happened after the meeting (honored/broken/renegotiated)."""
        if whisper_id not in self._history:
            return
        self._history[whisper_id]["outcome"] = outcome

    def record_learning(self, whisper_id, learning_entry, org_id="default"):
        """Record the Learning Ledger entry (one honest sentence)."""
        if whisper_id not in self._history:
            return
        self._history[whisper_id]["learning_entry"] = learning_entry

    def get_history(self, whisper_id, org_id="default"):
        return self._history.get(whisper_id, {})

    def get_all_history(self, org_id="default"):
        return dict(self._history)


# ─── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def now():
    return datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def tomorrow():
    return datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def globex_commitment_signal(now):
    """The ONE real commitment signal that drives Loop 1."""
    return MockSignal(
        SignalType.CUSTOMER_COMMITMENT_MADE,
        actor="jane.d@acme.com",
        artifact="crm:globex-commit-1",
        metadata={
            "customer": "Globex",
            "commitment": "Deliver SSO by 2024-12-15",
        },
        timestamp=now - timedelta(days=20),
    )


@pytest.fixture
def globex_objection_signal(now):
    """Globex also raised a pricing objection — surfaces as conflicting evidence."""
    return MockSignal(
        SignalType.CUSTOMER_OBJECTION,
        actor="jane.d@acme.com",
        artifact="crm:globex-obj-1",
        metadata={"customer": "Globex", "objection_type": "pricing"},
        timestamp=now - timedelta(days=5),
    )


@pytest.fixture
def globex_meeting_calendar(tomorrow):
    """Calendar with one consequential Globex meeting tomorrow."""
    return StaticCalendarSource([
        CalendarEvent(
            title="Globex Quarterly Review",
            start=tomorrow.replace(hour=10, minute=0),
            end=tomorrow.replace(hour=11, minute=0),
            entity="Globex",
            attendees=["ceo@globex.com", "jane.d@acme.com", "ceo@acme.com"],
        ),
    ])


@pytest.fixture
def globex_outcome_signal_honored(now):
    """After the meeting, Globex's commitment was honored."""
    return MockSignal(
        SignalType.CUSTOMER_COMMITMENT_KEPT,
        actor="jane.d@acme.com",
        artifact="crm:globex-kept-1",
        metadata={
            "customer": "Globex",
            "commitment": "Deliver SSO by 2024-12-15",
        },
        timestamp=now + timedelta(days=1),
    )


# ─── The End-to-End Loop 1 Test ────────────────────────────────────────────

def test_loop1_commitment_intelligence_end_to_end(
    now,
    globex_commitment_signal,
    globex_objection_signal,
    globex_meeting_calendar,
    globex_outcome_signal_honored,
):
    """ONE test that exercises the whole Loop 1 cognitive loop.

    Steps:
      1. Commitment signal exists
      2. Consequential meeting on calendar
      3. Preparation runs → Whisper fires with Evidence Spine
      4. Whisper has Delivery Intelligence fields
      5. Exec asks "what did we promise Globex?" → Recall returns Evidence
      6. Exec records action + decision_influenced + follow_up_questions
      7. Outcome signal recorded (honored)
      8. Learning Ledger entry written (one honest sentence)
    """
    signals = [globex_commitment_signal, globex_objection_signal]
    store = MockWhisperHistoryStore()
    ledger = LearningLedger(store=store)

    # ── Step 1-2: Build the loop with the commitment signal + calendar ──
    loop = CommitmentIntelligenceLoop(
        signals=signals,
        calendar_source=globex_meeting_calendar,
        whisper_store=store,
        learning_ledger=ledger,
        now=now,
    )

    # ── Step 3: Run the loop's "evening preparation" phase ──────────────
    # This fires Whispers for consequential meetings, carrying Evidence Spines
    evening_result = loop.run_evening_preparation(org_id="default")

    # Must have fired at least 1 Whisper for the Globex meeting
    assert evening_result["whispers_fired"] >= 1, \
        f"Loop 1 must fire a Whisper for the Globex meeting, got {evening_result['whispers_fired']}"
    globex_whisper = next(
        (w for w in evening_result["whispers"] if "Globex" in w.get("entity", "")),
        None,
    )
    assert globex_whisper is not None, \
        "Loop 1 must fire a Whisper with entity=Globex"

    # The Whisper MUST carry an Evidence Spine from the commitment signal
    es = globex_whisper.get("evidence_spine", {})
    assert "observed_facts" in es, "Whisper evidence_spine missing observed_facts"
    assert len(es["observed_facts"]) > 0, "observed_facts must be non-empty"

    # The observed_facts MUST reference the commitment text ("SSO")
    facts_text = " ".join(f.get("text", "") for f in es["observed_facts"])
    assert "SSO" in facts_text or "commitment" in facts_text.lower(), \
        f"Whisper evidence must reference the commitment signal content. Got: {facts_text!r}"

    # ── Step 4: Delivery Intelligence fields are populated ──────────────
    # recipient, timing_reason, depth, materially_changed_since_last_shown
    assert globex_whisper.get("recipient"), \
        "Whisper must have a recipient (Delivery Intelligence)"
    assert globex_whisper.get("timing_reason"), \
        "Whisper must have a timing_reason (Delivery Intelligence)"
    assert globex_whisper.get("depth"), \
        "Whisper must have a depth (Delivery Intelligence)"
    # materially_changed_since_last_shown must be a boolean (not None, not missing)
    assert "materially_changed_since_last_shown" in globex_whisper, \
        "Whisper must have materially_changed_since_last_shown field"
    assert isinstance(globex_whisper["materially_changed_since_last_shown"], bool), \
        "materially_changed_since_last_shown must be a boolean"

    # The Whisper was persisted to the store (with Delivery Intelligence fields)
    wid = globex_whisper["whisper_id"]
    persisted = store.get_history(wid)
    assert persisted.get("recipient"), "Persisted whisper must have recipient"
    assert persisted.get("timing_reason"), "Persisted whisper must have timing_reason"
    assert persisted.get("depth"), "Persisted whisper must have depth"

    # ── Step 5: Exec asks "what did we promise Globex?" → Recall ────────
    ask_result = loop.run_ask_recall("what did we promise Globex?", org_id="default")

    assert ask_result["found"] is True, \
        "Recall must find the commitment when exec asks 'what did we promise Globex?'"
    assert ask_result["match_count"] >= 1

    # The recalled item must carry the commitment Evidence Spine
    recalled = ask_result["whispers"][0]
    recalled_es = recalled.get("evidence_spine", {})
    assert "observed_facts" in recalled_es
    assert len(recalled_es["observed_facts"]) > 0
    recalled_facts = " ".join(f.get("text", "") for f in recalled_es["observed_facts"])
    assert "SSO" in recalled_facts or "commitment" in recalled_facts.lower(), \
        f"Recalled evidence must reference the original commitment. Got: {recalled_facts!r}"

    # ── Step 6: Exec records action + decision_influenced + follow_ups ──
    loop.record_executive_action(
        whisper_id=wid,
        action="acted",
        decision_influenced="Q4 SSO delivery prioritized over Initech integration",
        follow_up_questions=[
            "What did we promise Globex?",
            "Who is the internal expert on SSO?",
        ],
        org_id="default",
    )
    persisted_after = store.get_history(wid)
    assert persisted_after["action_taken"] == "acted", \
        "action_taken must be 'acted' after record_executive_action"
    assert persisted_after.get("decision_influenced") == "Q4 SSO delivery prioritized over Initech integration", \
        "decision_influenced must be persisted"
    assert len(persisted_after.get("follow_up_questions", [])) == 2, \
        "follow_up_questions must be persisted (2 questions)"

    # ── Step 7: Outcome observed — commitment honored ───────────────────
    loop.record_outcome_signal(
        whisper_id=wid,
        outcome_signal=globex_outcome_signal_honored,
        org_id="default",
    )
    persisted_outcome = store.get_history(wid)
    assert persisted_outcome.get("outcome") is not None, \
        "outcome must be recorded after record_outcome_signal"
    # The outcome must reference the kept/honored signal
    outcome_str = str(persisted_outcome["outcome"]).lower()
    assert "kept" in outcome_str or "honored" in outcome_str or "fulfilled" in outcome_str, \
        f"outcome must reference the honored commitment. Got: {persisted_outcome['outcome']!r}"

    # ── Step 8: Learning Ledger entry written ───────────────────────────
    ledger_entry = loop.write_learning_entry(whisper_id=wid, org_id="default")

    assert ledger_entry, "Learning Ledger entry must be non-empty"
    assert isinstance(ledger_entry, str), "Learning Ledger entry must be a string"
    assert len(ledger_entry) >= 20, \
        f"Learning Ledger entry must be a real sentence (≥20 chars). Got: {ledger_entry!r}"

    # REJECT placeholder/template Learning Ledger entries (P6)
    FORBIDDEN_LEDGER_PHRASES = [
        "Learning recorded.",
        "Outcome observed.",
        "Loop complete.",
        "Maestro learned something.",
        "The system learned.",
        "TODO",
        "placeholder",
    ]
    for phrase in FORBIDDEN_LEDGER_PHRASES:
        assert phrase.lower() not in ledger_entry.lower(), \
            f"Learning Ledger entry must not be a placeholder. Got: {ledger_entry!r}"

    # The entry MUST reference what actually happened — the commitment
    # was honored. This proves the ledger is signal-derived, not template.
    assert "globex" in ledger_entry.lower() or "sso" in ledger_entry.lower() or "commitment" in ledger_entry.lower(), \
        f"Learning Ledger entry must reference the actual commitment. Got: {ledger_entry!r}"
    assert "honored" in ledger_entry.lower() or "kept" in ledger_entry.lower() or "fulfilled" in ledger_entry.lower() or "met" in ledger_entry.lower(), \
        f"Learning Ledger entry must reference the honored outcome. Got: {ledger_entry!r}"

    # The entry is persisted to the store
    persisted_final = store.get_history(wid)
    assert persisted_final.get("learning_entry") == ledger_entry, \
        "Learning Ledger entry must be persisted to the store"


# ─── Additional Adversarial Tests (Loop variants) ──────────────────────────

def test_loop1_learning_ledger_when_commitment_broken(
    now,
    globex_commitment_signal,
    globex_objection_signal,
    globex_meeting_calendar,
):
    """When the commitment is BROKEN (not honored), the Learning Ledger
    entry must honestly say so — not spin it as a learning opportunity.

    Maestro never invents precision. If the commitment was broken, the
    ledger says it was broken. No false positives.
    """
    from maestro_oem.learning_ledger import LearningLedger
    from maestro_oem.loop1_commitment_intelligence import CommitmentIntelligenceLoop

    broken_signal = MockSignal(
        SignalType.CUSTOMER_COMMITMENT_BROKEN,
        actor="jane.d@acme.com",
        artifact="crm:globex-broken-1",
        metadata={"customer": "Globex", "commitment": "Deliver SSO by 2024-12-15"},
        timestamp=now + timedelta(days=1),
    )

    signals = [globex_commitment_signal, globex_objection_signal]
    store = MockWhisperHistoryStore()
    ledger = LearningLedger(store=store)
    loop = CommitmentIntelligenceLoop(
        signals=signals,
        calendar_source=globex_meeting_calendar,
        whisper_store=store,
        learning_ledger=ledger,
        now=now,
    )

    evening_result = loop.run_evening_preparation(org_id="default")
    wid = evening_result["whispers"][0]["whisper_id"]

    loop.record_executive_action(
        whisper_id=wid, action="ignored",
        decision_influenced=None,
        follow_up_questions=[],
        org_id="default",
    )
    loop.record_outcome_signal(
        whisper_id=wid,
        outcome_signal=broken_signal,
        org_id="default",
    )
    entry = loop.write_learning_entry(whisper_id=wid, org_id="default")

    # The entry MUST honestly say the commitment was broken
    assert "broken" in entry.lower() or "missed" in entry.lower() or "not honored" in entry.lower() or "failed" in entry.lower(), \
        f"Learning Ledger must honestly say commitment was broken. Got: {entry!r}"
    # Must NOT spin it positively
    assert "honored" not in entry.lower() and "kept" not in entry.lower() and "fulfilled" not in entry.lower(), \
        f"Learning Ledger must NOT spin a broken commitment as honored. Got: {entry!r}"


def test_loop1_delivery_intelligence_recipient_is_not_generic(
    now,
    globex_commitment_signal,
    globex_meeting_calendar,
):
    """The Delivery Intelligence recipient must be a real person (email or
    named role), not a generic placeholder like 'the executive' or 'you'.

    External auditor correction #3: Delivery Intelligence means knowing
    WHO needs to know, WHEN, and HOW DEEPLY. Generic recipients are
    not Delivery Intelligence — they're the absence of it.
    """
    from maestro_oem.learning_ledger import LearningLedger
    from maestro_oem.loop1_commitment_intelligence import CommitmentIntelligenceLoop

    signals = [globex_commitment_signal]
    store = MockWhisperHistoryStore()
    ledger = LearningLedger(store=store)
    loop = CommitmentIntelligenceLoop(
        signals=signals,
        calendar_source=globex_meeting_calendar,
        whisper_store=store,
        learning_ledger=ledger,
        now=now,
    )

    evening_result = loop.run_evening_preparation(org_id="default")
    wid = evening_result["whispers"][0]["whisper_id"]
    persisted = store.get_history(wid)

    recipient = persisted.get("recipient", "")
    assert recipient, "recipient must be populated"
    FORBIDDEN_RECIPIENTS = {"the executive", "you", "user", "ceo", ""}
    assert recipient.lower() not in FORBIDDEN_RECIPIENTS, \
        f"recipient must be a real person/email, not generic. Got: {recipient!r}"
    # Must look like an email or a named person
    assert "@" in recipient or any(c.isupper() for c in recipient) or "." in recipient, \
        f"recipient must be an email or named person. Got: {recipient!r}"
