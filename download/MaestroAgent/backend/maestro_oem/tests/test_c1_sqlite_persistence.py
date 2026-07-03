"""C1 fix: SQLite persistence for all cognitive state — restart-survival tests.

Adversarial audit finding (ADVERSARIAL-AUDIT-24PHASE):
> C1: All Loop 2/3/4 cognitive state is in-memory — lost on restart.
> MeetingStore = in-memory dict. _loop3_decision_store = module-level dict.
> OrganizationalLearningLedger = in-memory list. CommitmentMutationTracker =
> in-memory dict. Only WhisperHistoryStore is SQLite-backed.

The audit's #1 recommended experiment:
> SQLite persistence for all cognitive state. Make every store SQLite-backed.
> Then restart the server and verify all meetings, decisions, learning entries,
> and commitment mutations survive.

These tests exercise the EXACT restart scenario: seed data → close store →
create a NEW store pointing at the same DB → verify all data survived.
This is the test that distinguishes "product" from "demo."
"""
from __future__ import annotations

import sys
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture
def now():
    return datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)


# ─── 1. MeetingStore restart survival ─────────────────────────────────────

def test_meeting_store_survives_restart(tmp_path, now):
    """MeetingStore must persist meetings to SQLite and survive a restart.

    BEFORE C1 fix: MeetingStore was in-memory (dict). Server restart lost
    all meetings, lifecycle state, topics, commitments, outcomes, learning.

    AFTER C1 fix: MeetingStore is SQLite-backed. Restart preserves everything.
    """
    from maestro_oem.meeting_store import MeetingStore
    from maestro_oem.meeting import Meeting, MeetingStatus

    db_path = str(tmp_path / "meetings.db")

    # Store 1: create + record a meeting with full lifecycle
    store1 = MeetingStore(db_path)
    meeting = Meeting(
        title="Globex Quarterly Review",
        entity="Globex",
        attendees=["ceo@globex.com", "jane.d@acme.com"],
        start=now + timedelta(days=1),
        end=now + timedelta(days=1, hours=1),
    )
    meeting.status = MeetingStatus.OCCURRED
    meeting.topics_discussed = ["pricing", "SSO delivery"]
    meeting.commitments_made = ["Deliver SSO by 2024-12-15"]
    meeting.outcome = "commitment_honored"
    meeting.learning_entry = "Globex honored its commitment after the meeting."
    store1.record(meeting)
    store1.close()

    # Store 2: NEW process, same DB — does the meeting survive?
    store2 = MeetingStore(db_path)
    recovered = store2.get(meeting.meeting_id)

    assert recovered is not None, "Meeting must survive restart"
    assert recovered.title == "Globex Quarterly Review"
    assert recovered.entity == "Globex"
    assert recovered.status == MeetingStatus.OCCURRED
    assert "pricing" in recovered.topics_discussed
    assert len(recovered.commitments_made) == 1
    assert recovered.outcome == "commitment_honored"
    assert recovered.learning_entry == "Globex honored its commitment after the meeting."
    store2.close()


def test_meeting_store_get_by_entity_survives_restart(tmp_path, now):
    """get_by_entity must work after restart."""
    from maestro_oem.meeting_store import MeetingStore
    from maestro_oem.meeting import Meeting

    db_path = str(tmp_path / "meetings2.db")
    store1 = MeetingStore(db_path)
    for i in range(3):
        store1.record(Meeting(
            title=f"Globex Meeting #{i+1}",
            entity="Globex",
            attendees=[],
            start=now + timedelta(days=i),
            end=now + timedelta(days=i, hours=1),
        ))
    store1.close()

    store2 = MeetingStore(db_path)
    globex_meetings = store2.get_by_entity("Globex")
    assert len(globex_meetings) == 3, f"Must find 3 Globex meetings after restart. Got: {len(globex_meetings)}"
    store2.close()


# ─── 2. DecisionStore restart survival ────────────────────────────────────

def test_decision_store_survives_restart(tmp_path, now):
    """DecisionStore must persist decisions to SQLite and survive a restart.

    BEFORE C1 fix: _loop3_decision_store was a module-level dict.
    AFTER C1 fix: SQLite-backed.
    """
    from maestro_oem.decision_store import DecisionStore
    from maestro_oem.decision_v2 import Decision, DecisionStatus

    db_path = str(tmp_path / "decisions.db")

    store1 = DecisionStore(db_path)
    decision = Decision(intent="Prioritize SSO for Globex", entity="Globex")
    decision.status = DecisionStatus.LEARNING_RECORDED
    decision.assumptions = [
        {"text": "Globex will renew if SSO ships", "source": "sales", "claim_type": "assumption"},
    ]
    decision.hypothesis = {"text": "SSO will ship by Q4", "claim_type": "prediction"}
    decision.decision_text = "Prioritize SSO over Initech"
    decision.outcome = {"text": "SSO shipped, Globex renewed", "claim_type": "outcome"}
    decision.learning_entry = "The decision was correct — hypothesis confirmed."
    store1.record(decision)
    store1.close()

    store2 = DecisionStore(db_path)
    recovered = store2.get(decision.decision_id)

    assert recovered is not None, "Decision must survive restart"
    assert recovered.intent == "Prioritize SSO for Globex"
    assert recovered.entity == "Globex"
    assert recovered.status == DecisionStatus.LEARNING_RECORDED
    assert len(recovered.assumptions) == 1
    assert recovered.hypothesis is not None
    assert recovered.decision_text == "Prioritize SSO over Initech"
    assert recovered.outcome is not None
    assert recovered.learning_entry == "The decision was correct — hypothesis confirmed."
    store2.close()


def test_decision_store_get_all_survives_restart(tmp_path):
    """get_all must work after restart."""
    from maestro_oem.decision_store import DecisionStore
    from maestro_oem.decision_v2 import Decision

    db_path = str(tmp_path / "decisions2.db")
    store1 = DecisionStore(db_path)
    for i in range(3):
        store1.record(Decision(intent=f"Decision #{i+1}", entity="Globex"))
    store1.close()

    store2 = DecisionStore(db_path)
    all_decisions = store2.get_all()
    assert len(all_decisions) == 3, f"Must find 3 decisions after restart. Got: {len(all_decisions)}"
    store2.close()


# ─── 3. OrganizationalLearningLedger restart survival ────────────────────

def test_org_learning_ledger_survives_restart(tmp_path):
    """OrganizationalLearningLedger must persist to SQLite and survive restart.

    BEFORE C1 fix: in-memory list. Server restart lost all learning entries.
    AFTER C1 fix: SQLite-backed.
    """
    from maestro_oem.organizational_learning_ledger import OrganizationalLearningLedger

    db_path = str(tmp_path / "org_learning.db")

    ledger1 = OrganizationalLearningLedger(db_path)
    ledger1.record_commitment_learning(
        entity="Globex", whisper_id="wspr-1",
        action="ignored", outcome="broken",
        learning_entry="Globex broke its commitment after the exec ignored the Whisper.",
    )
    ledger1.record_meeting_learning(
        entity="Globex", meeting_id="mtg-1",
        outcome="commitment_broken",
        learning_entry="The Globex meeting ended with a broken commitment.",
    )
    ledger1.record_decision_learning(
        entity="Globex", decision_id="dec-1",
        hypothesis="SSO will ship by Q4", outcome="SSO missed Q4",
        learning_entry="The decision was based on a wrong hypothesis.",
    )
    ledger1.close()

    ledger2 = OrganizationalLearningLedger(db_path)
    entries = ledger2.get_all_entries()

    assert len(entries) == 3, f"Must recover 3 entries after restart. Got: {len(entries)}"
    sources = {e.source_loop for e in entries}
    assert "commitment" in sources
    assert "meeting" in sources
    assert "decision" in sources

    # Verify content survived
    commitment_entry = next(e for e in entries if e.source_loop == "commitment")
    assert commitment_entry.entity == "Globex"
    assert commitment_entry.action == "ignored"
    assert commitment_entry.outcome == "broken"
    assert "broke its commitment" in commitment_entry.learning_entry
    ledger2.close()


def test_org_learning_ledger_total_count_survives_restart(tmp_path):
    """total_entries must be correct after restart."""
    from maestro_oem.organizational_learning_ledger import OrganizationalLearningLedger

    db_path = str(tmp_path / "org_learning2.db")
    ledger1 = OrganizationalLearningLedger(db_path)
    for i in range(5):
        ledger1.record_commitment_learning(
            entity=f"Entity{i}", whisper_id=f"wspr-{i}",
            action="acted", outcome="honored",
            learning_entry=f"Entity{i} honored its commitment.",
        )
    assert ledger1.total_entries() == 5
    ledger1.close()

    ledger2 = OrganizationalLearningLedger(db_path)
    assert ledger2.total_entries() == 5, f"Total must survive restart. Got: {ledger2.total_entries()}"
    ledger2.close()


# ─── 4. CommitmentMutationTracker restart survival ───────────────────────

def test_mutation_tracker_survives_restart(tmp_path, now):
    """CommitmentMutationTracker must persist to SQLite and survive restart.

    BEFORE C1 fix: in-memory dicts. Server restart lost all commitment
    wording history and mutation events.
    AFTER C1 fix: SQLite-backed.
    """
    from maestro_oem.commitment_mutation_tracker import CommitmentMutationTracker
    from maestro_oem.signal import SignalType

    class MockSignal:
        def __init__(self, sig_type, actor="", artifact="", metadata=None, timestamp=None):
            self.type = sig_type
            self.actor = actor
            self.artifact = artifact
            self.metadata = metadata or {}
            self.timestamp = timestamp or datetime.now(timezone.utc)
            self.signal_id = f"sig-{artifact or id(self)}"

    db_path = str(tmp_path / "mutations.db")

    # Store 1: record original + mutated commitment
    tracker1 = CommitmentMutationTracker(db_path)
    tracker1.record_commitment(MockSignal(
        SignalType.CUSTOMER_COMMITMENT_MADE,
        actor="jane.d@acme.com",
        artifact="crm:globex-1",
        metadata={"customer": "Globex", "commitment": "Deliver SSO by 2024-12-15"},
        timestamp=now - timedelta(days=30),
    ))
    tracker1.record_commitment(MockSignal(
        SignalType.CUSTOMER_COMMITMENT_MADE,
        actor="jane.d@acme.com",
        artifact="crm:globex-2",
        metadata={"customer": "Globex", "commitment": "Deliver SSO by 2025-01-31"},
        timestamp=now - timedelta(days=5),
    ))
    tracker1.close()

    # Store 2: NEW process, same DB — does the history survive?
    tracker2 = CommitmentMutationTracker(db_path)
    history = tracker2.get_mutation_history("Globex")

    assert len(history) >= 2, f"Must recover 2 commitment entries after restart. Got: {len(history)}"
    wordings = [e.commitment_text for e in history]
    assert "Deliver SSO by 2024-12-15" in wordings, "Original wording must survive restart"
    assert "Deliver SSO by 2025-01-31" in wordings, "Mutated wording must survive restart"

    mutations = tracker2.get_mutations("Globex")
    assert len(mutations) >= 1, f"Must recover mutation event after restart. Got: {len(mutations)}"
    mutation = mutations[0]
    assert mutation.old_text == "Deliver SSO by 2024-12-15"
    assert mutation.new_text == "Deliver SSO by 2025-01-31"
    tracker2.close()


# ─── 5. Full restart simulation — all 4 stores ────────────────────────────

def test_all_cognitive_state_survives_full_restart(tmp_path, now):
    """The audit's exact experiment: seed ALL cognitive state, restart,
    verify ALL of it survived.

    This is the one test that tests "product or demo."
    """
    from maestro_oem.meeting_store import MeetingStore
    from maestro_oem.meeting import Meeting, MeetingStatus
    from maestro_oem.decision_store import DecisionStore
    from maestro_oem.decision_v2 import Decision, DecisionStatus
    from maestro_oem.organizational_learning_ledger import OrganizationalLearningLedger
    from maestro_oem.commitment_mutation_tracker import CommitmentMutationTracker
    from maestro_oem.signal import SignalType

    class MockSignal:
        def __init__(self, sig_type, actor="", artifact="", metadata=None, timestamp=None):
            self.type = sig_type
            self.actor = actor
            self.artifact = artifact
            self.metadata = metadata or {}
            self.timestamp = timestamp or datetime.now(timezone.utc)
            self.signal_id = f"sig-{artifact or id(self)}"

    # ── Phase 1: Seed all cognitive state ────────────────────────────
    meeting_store1 = MeetingStore(str(tmp_path / "meetings.db"))
    decision_store1 = DecisionStore(str(tmp_path / "decisions.db"))
    org_ledger1 = OrganizationalLearningLedger(str(tmp_path / "org_learning.db"))
    mutation_tracker1 = CommitmentMutationTracker(str(tmp_path / "mutations.db"))

    # Seed a meeting
    meeting = Meeting(
        title="Globex Quarterly Review",
        entity="Globex",
        attendees=["ceo@globex.com"],
        start=now + timedelta(days=1),
        end=now + timedelta(days=1, hours=1),
    )
    meeting.status = MeetingStatus.LEARNING_RECORDED
    meeting.topics_discussed = ["pricing"]
    meeting.learning_entry = "Meeting learning entry."
    meeting_store1.record(meeting)

    # Seed a decision
    decision = Decision(intent="Prioritize SSO", entity="Globex")
    decision.status = DecisionStatus.LEARNING_RECORDED
    decision.decision_text = "Ship SSO first"
    decision_store1.record(decision)

    # Seed org learning
    org_ledger1.record_commitment_learning(
        entity="Globex", whisper_id="wspr-1",
        action="acted", outcome="honored",
        learning_entry="Commitment honored.",
    )

    # Seed mutation history
    mutation_tracker1.record_commitment(MockSignal(
        SignalType.CUSTOMER_COMMITMENT_MADE,
        metadata={"customer": "Globex", "commitment": "Deliver SSO by Q4"},
    ))

    # Close all stores (simulates server shutdown)
    meeting_store1.close()
    decision_store1.close()
    org_ledger1.close()
    mutation_tracker1.close()

    # ── Phase 2: Restart — new stores, same DBs ─────────────────────
    meeting_store2 = MeetingStore(str(tmp_path / "meetings.db"))
    decision_store2 = DecisionStore(str(tmp_path / "decisions.db"))
    org_ledger2 = OrganizationalLearningLedger(str(tmp_path / "org_learning.db"))
    mutation_tracker2 = CommitmentMutationTracker(str(tmp_path / "mutations.db"))

    # ── Phase 3: Verify ALL cognitive state survived ─────────────────
    # Meeting survived
    recovered_meeting = meeting_store2.get(meeting.meeting_id)
    assert recovered_meeting is not None, "Meeting must survive restart"
    assert recovered_meeting.title == "Globex Quarterly Review"
    assert recovered_meeting.status == MeetingStatus.LEARNING_RECORDED
    assert "pricing" in recovered_meeting.topics_discussed

    # Decision survived
    recovered_decision = decision_store2.get(decision.decision_id)
    assert recovered_decision is not None, "Decision must survive restart"
    assert recovered_decision.intent == "Prioritize SSO"
    assert recovered_decision.status == DecisionStatus.LEARNING_RECORDED

    # Org learning survived
    recovered_entries = org_ledger2.get_all_entries()
    assert len(recovered_entries) >= 1, "Org learning entries must survive restart"
    assert recovered_entries[0].entity == "Globex"

    # Mutation history survived
    recovered_history = mutation_tracker2.get_mutation_history("Globex")
    assert len(recovered_history) >= 1, "Mutation history must survive restart"
    assert "Deliver SSO by Q4" in recovered_history[0].commitment_text

    # Cleanup
    meeting_store2.close()
    decision_store2.close()
    org_ledger2.close()
    mutation_tracker2.close()
