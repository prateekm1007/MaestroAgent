"""Loop 1.5 — Preserve and understand changing meaning.

External auditor's standard (AUDITOR-EXTERNAL-REVIEW-3):
> "Don't merely prove that Maestro can move data through a loop. Prove
> that it can preserve and understand the changing meaning of a real
> organizational situation over time."

Loop 1 proved Maestro can move data through a loop. Loop 1.5 tests
whether it can preserve and understand changing meaning. 5 capabilities:

1. Commitment mutation tracking — preserve the history of how a
   commitment's wording changes, don't overwrite.
2. Disagreement detection — surface when teams interpret the same
   commitment differently (requires claim_type + mutation tracking).
3. delivery_decision enum — 7 options including SUPPRESS_ALREADY_UNDERSTOOD
   (the "remain quiet" test).
4. Minimal Situation abstraction — 7 fields (what_is_happening, entities,
   commitments, evidence, current_state, prior_whispers, timeline).
5. Cold-start trust ladder mode — retrieval-only on day 1, no Whispers
   until enough evidence.

These tests are adversarial: each assertion is non-vacuous (would fail
on the pre-Loop-1.5 codebase). Write first, watch fail, then build.
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


# ─── 1. Commitment Mutation Tracking ───────────────────────────────────────

def test_commitment_mutation_preserves_history(now):
    """When a commitment's wording changes, the old wording is preserved.

    A commitment to Globex starts as "Deliver SSO by 2024-12-15".
    Later, a new commitment signal arrives: "Deliver SSO by 2025-01-31"
    (deadline moved). The mutation tracker must:
      - Record BOTH wordings (old + new)
      - Record the mutation event (when it changed, who changed it)
      - NOT overwrite the old wording

    Old codebase: commitment signals were a flat list — the latest one
    wins, history is lost. Loop 1.5 preserves the mutation history.
    """
    from maestro_oem.commitment_mutation_tracker import CommitmentMutationTracker

    tracker = CommitmentMutationTracker()

    # First commitment — original wording
    sig1 = MockSignal(
        SignalType.CUSTOMER_COMMITMENT_MADE,
        actor="jane.d@acme.com",
        artifact="crm:globex-commit-1",
        metadata={"customer": "Globex", "commitment": "Deliver SSO by 2024-12-15"},
        timestamp=now - timedelta(days=30),
    )
    tracker.record_commitment(sig1)

    # Second commitment — mutated wording (deadline moved)
    sig2 = MockSignal(
        SignalType.CUSTOMER_COMMITMENT_MADE,
        actor="jane.d@acme.com",
        artifact="crm:globex-commit-2",
        metadata={"customer": "Globex", "commitment": "Deliver SSO by 2025-01-31"},
        timestamp=now - timedelta(days=5),
    )
    tracker.record_commitment(sig2)

    # Get the mutation history for Globex
    history = tracker.get_mutation_history("Globex")

    assert len(history) >= 2, \
        f"Mutation history must preserve BOTH wordings. Got {len(history)} entries."
    wordings = [entry.commitment_text for entry in history]
    assert "Deliver SSO by 2024-12-15" in wordings, \
        f"Original wording must be preserved. Got: {wordings}"
    assert "Deliver SSO by 2025-01-31" in wordings, \
        f"Mutated wording must be preserved. Got: {wordings}"

    # The mutation event must be recorded
    mutations = tracker.get_mutations("Globex")
    assert len(mutations) >= 1, \
        "At least 1 mutation event must be recorded (wording changed)"
    mutation = mutations[0]
    assert mutation.old_text == "Deliver SSO by 2024-12-15", \
        f"Mutation old_text must be the original wording. Got: {mutation.old_text!r}"
    assert mutation.new_text == "Deliver SSO by 2025-01-31", \
        f"Mutation new_text must be the mutated wording. Got: {mutation.new_text!r}"
    assert mutation.actor == "jane.d@acme.com", \
        f"Mutation actor must be recorded. Got: {mutation.actor!r}"


def test_commitment_mutation_no_mutation_when_unchanged(now):
    """When the same commitment wording arrives twice, no mutation is recorded.

    This is the non-vacuous counter-test: the tracker must NOT flag a
    mutation when the wording hasn't changed. False positives are worse
    than false negatives here — crying wolf erodes trust.
    """
    from maestro_oem.commitment_mutation_tracker import CommitmentMutationTracker

    tracker = CommitmentMutationTracker()

    sig1 = MockSignal(
        SignalType.CUSTOMER_COMMITMENT_MADE,
        actor="jane.d@acme.com",
        artifact="crm:globex-commit-1",
        metadata={"customer": "Globex", "commitment": "Deliver SSO by 2024-12-15"},
        timestamp=now - timedelta(days=30),
    )
    sig2 = MockSignal(
        SignalType.CUSTOMER_COMMITMENT_MADE,
        actor="jane.d@acme.com",
        artifact="crm:globex-commit-2",
        metadata={"customer": "Globex", "commitment": "Deliver SSO by 2024-12-15"},  # SAME wording
        timestamp=now - timedelta(days=5),
    )
    tracker.record_commitment(sig1)
    tracker.record_commitment(sig2)

    mutations = tracker.get_mutations("Globex")
    assert len(mutations) == 0, \
        f"No mutation should be recorded when wording is unchanged. Got: {mutations}"


# ─── 2. Disagreement Detection ─────────────────────────────────────────────

def test_disagreement_detection_finds_cross_claim_type_conflict(now):
    """Surface when two Evidence objects with different claim_types conflict.

    Scenario:
      - Engineering has a reported_statement: "SSO is on track for Q4"
      - The customer (Globex) has an observed_fact: "SSO missed the Q4 deadline"

    These two claims disagree. The DisagreementDetector must find this
    conflict because:
      - Same entity (Globex / SSO)
      - Different claim_types (reported_statement vs observed_fact)
      - Conflicting content ("on track" vs "missed")

    This is the core Loop 1.5 capability — Maestro detects when teams
    interpret the same situation differently. Without claim_type, this
    would be impossible (both would be flat "claims").
    """
    from maestro_oem.disagreement_detector import DisagreementDetector
    from maestro_oem.evidence import Evidence

    evidence_list = [
        # Engineering's reported statement
        Evidence(
            claim="SSO is on track for Q4",
            observed_facts=[{"source": "engineering", "date": "2026-06-15", "text": "SSO on track", "people": ["eng@acme.com"]}],
            claim_type="reported_statement",
        ),
        # Customer's observed fact (the release actually missed)
        Evidence(
            claim="SSO missed the Q4 deadline",
            observed_facts=[{"source": "customer signals", "date": "2026-07-01", "text": "SSO not delivered", "people": ["jane.d@acme.com"]}],
            claim_type="observed_fact",
        ),
    ]

    detector = DisagreementDetector()
    disagreements = detector.detect(evidence_list, entity="Globex", topic="SSO")

    assert len(disagreements) >= 1, \
        f"Must detect the disagreement between 'on track' and 'missed'. Got: {disagreements}"
    d = disagreements[0]
    assert d.claim_a_claim_type != d.claim_b_claim_type, \
        f"Disagreement must be between different claim_types. Got: {d.claim_a_claim_type} vs {d.claim_b_claim_type}"
    # The observed_fact should be weighted higher than the reported_statement
    # (observed facts are direct evidence; reported statements are hearsay)
    assert d.resolution_favors in ("a", "b"), \
        f"Disagreement must have a resolution (favors a or b). Got: {d.resolution_favors}"
    # The resolution should favor the observed_fact (more epistemically reliable)
    favored_claim_type = d.claim_a_claim_type if d.resolution_favors == "a" else d.claim_b_claim_type
    assert favored_claim_type == "observed_fact", \
        f"Resolution should favor observed_fact over reported_statement. Got: {favored_claim_type}"


def test_disagreement_detection_no_disagreement_when_aligned(now):
    """When two Evidence objects agree, no disagreement is detected.

    Non-vacuous counter-test: if Engineering says "SSO is on track" and
    the customer also observes "SSO delivered", there's no disagreement.
    False positives erode trust.
    """
    from maestro_oem.disagreement_detector import DisagreementDetector
    from maestro_oem.evidence import Evidence

    evidence_list = [
        Evidence(
            claim="SSO is on track for Q4",
            observed_facts=[{"source": "engineering", "date": "2026-06-15", "text": "SSO on track", "people": []}],
            claim_type="reported_statement",
        ),
        Evidence(
            claim="SSO was delivered for Q4",
            observed_facts=[{"source": "customer signals", "date": "2026-07-01", "text": "SSO delivered", "people": []}],
            claim_type="observed_fact",
        ),
    ]

    detector = DisagreementDetector()
    disagreements = detector.detect(evidence_list, entity="Globex", topic="SSO")
    assert len(disagreements) == 0, \
        f"No disagreement should be detected when claims align. Got: {disagreements}"


# ─── 3. delivery_decision enum ─────────────────────────────────────────────

def test_delivery_decision_enum_has_7_options():
    """The delivery_decision enum must have exactly 7 options.

    Per the directive: '7 options including SUPPRESS_ALREADY_UNDERSTOOD'.
    """
    from maestro_oem.delivery_decision import DeliveryDecision

    options = list(DeliveryDecision)
    assert len(options) == 7, \
        f"delivery_decision must have exactly 7 options. Got: {len(options)}: {[o.name for o in options]}"

    option_names = {o.name for o in options}
    assert "SUPPRESS_ALREADY_UNDERSTOOD" in option_names, \
        f"SUPPRESS_ALREADY_UNDERSTOOD must be one of the 7 options. Got: {option_names}"


def test_delivery_decision_suppress_already_understood(now):
    """The 'remain quiet' test — when the exec has already acknowledged a
    commitment, the Whisper is suppressed.

    This is the external auditor's product test: Maestro should know when
    NOT to speak. If the exec already acted on the Whisper (action_taken=
    'acted') and nothing has materially changed since, the delivery_decision
    must be SUPPRESS_ALREADY_UNDERSTOOD.
    """
    from maestro_oem.delivery_decision import DeliveryDecision, decide_delivery

    # The exec already acted on this Whisper, nothing changed since
    decision = decide_delivery(
        exec_already_acted=True,
        materially_changed_since_last_shown=False,
        has_high_stakes_signal=False,
        is_cold_start=False,
        shown_count=1,
    )
    assert decision == DeliveryDecision.SUPPRESS_ALREADY_UNDERSTOOD, \
        f"When exec already acted + nothing changed, must SUPPRESS_ALREADY_UNDERSTOOD. Got: {decision}"


def test_delivery_decision_deliver_now_when_high_stakes_and_changed(now):
    """When the stakes are high AND something materially changed, DELIVER_NOW."""
    from maestro_oem.delivery_decision import DeliveryDecision, decide_delivery

    decision = decide_delivery(
        exec_already_acted=False,
        materially_changed_since_last_shown=True,
        has_high_stakes_signal=True,
        is_cold_start=False,
        shown_count=0,
    )
    assert decision == DeliveryDecision.DELIVER_NOW, \
        f"High stakes + materially changed + not yet shown → DELIVER_NOW. Got: {decision}"


def test_delivery_decision_defer_until_evidence_in_cold_start(now):
    """In cold-start mode (few signals) WITHOUT high-stakes, DEFER_UNTIL_EVIDENCE.

    CRITICAL-01 fix: cold-start with high-stakes signals NO LONGER defers
    (matching ColdStartMode's high-stakes override safety valve).
    """
    from maestro_oem.delivery_decision import DeliveryDecision, decide_delivery

    # Cold-start + NO high-stakes → DEFER_UNTIL_EVIDENCE
    decision = decide_delivery(
        exec_already_acted=False,
        materially_changed_since_last_shown=True,
        has_high_stakes_signal=False,
        is_cold_start=True,
        shown_count=0,
    )
    assert decision == DeliveryDecision.DEFER_UNTIL_EVIDENCE, \
        f"Cold-start (no high-stakes) → DEFER_UNTIL_EVIDENCE. Got: {decision}"

    # Cold-start + high-stakes → does NOT defer (safety valve override)
    decision_override = decide_delivery(
        exec_already_acted=False,
        materially_changed_since_last_shown=True,
        has_high_stakes_signal=True,
        is_cold_start=True,
        shown_count=0,
    )
    assert decision_override != DeliveryDecision.DEFER_UNTIL_EVIDENCE, \
        f"Cold-start + high-stakes → must NOT defer (safety valve). Got: {decision_override}"


# ─── 4. Minimal Situation Abstraction ──────────────────────────────────────

def test_situation_abstraction_has_7_fields(now):
    """The Situation dataclass must have exactly 7 fields.

    Per the directive: what_is_happening, entities, commitments, evidence,
    current_state, prior_whispers, timeline.
    """
    from maestro_oem.situation import Situation

    situation = Situation(
        what_is_happening="Globex Quarterly Review tomorrow",
        entities=["Globex"],
        commitments=[{"customer": "Globex", "text": "Deliver SSO by 2024-12-15"}],
        evidence=[],
        current_state="at_risk",
        prior_whispers=["wspr-loop1-6b39d95f"],
        timeline=[{"date": "2026-06-13", "event": "Commitment made"}],
    )

    # Verify all 7 fields exist
    assert hasattr(situation, "what_is_happening"), "Situation must have what_is_happening"
    assert hasattr(situation, "entities"), "Situation must have entities"
    assert hasattr(situation, "commitments"), "Situation must have commitments"
    assert hasattr(situation, "evidence"), "Situation must have evidence"
    assert hasattr(situation, "current_state"), "Situation must have current_state"
    assert hasattr(situation, "prior_whispers"), "Situation must have prior_whispers"
    assert hasattr(situation, "timeline"), "Situation must have timeline"

    # Verify the fields are populated
    assert situation.what_is_happening == "Globex Quarterly Review tomorrow"
    assert "Globex" in situation.entities
    assert len(situation.commitments) == 1
    assert situation.current_state == "at_risk"
    assert len(situation.prior_whispers) == 1
    assert len(situation.timeline) == 1


def test_situation_builder_from_signals_and_history(now):
    """A SituationBuilder constructs a Situation from signals + whisper history.

    This is the working memory that Maestro reasons over. It pulls:
      - what_is_happening from the next consequential meeting
      - entities from the signals
      - commitments from commitment signals
      - evidence from EvidenceBuilder
      - current_state from at_risk computation
      - prior_whispers from the whisper store
      - timeline from signal timestamps
    """
    from maestro_oem.situation import SituationBuilder
    from maestro_oem.calendar_source import CalendarEvent, StaticCalendarSource

    tomorrow = now + timedelta(days=1)
    signals = [
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane.d@acme.com",
            artifact="crm:globex-commit-1",
            metadata={"customer": "Globex", "commitment": "Deliver SSO by 2024-12-15"},
            timestamp=now - timedelta(days=20),
        ),
    ]
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
        def get_all_history(self, org_id="default"):
            return {"wspr-1": {"entity": "Globex", "insight": "Commitment at risk"}}

    builder = SituationBuilder(signals=signals, calendar_source=calendar, whisper_store=MockStore(), now=now)
    situation = builder.build_for_entity("Globex", org_id="default")

    assert situation is not None, "Situation must be built for Globex"
    assert "Globex" in situation.entities
    assert len(situation.commitments) >= 1
    assert situation.commitments[0]["text"] == "Deliver SSO by 2024-12-15"
    assert len(situation.prior_whispers) >= 1
    assert len(situation.timeline) >= 1


# ─── 5. Cold-Start Trust Ladder Mode ───────────────────────────────────────

def test_cold_start_mode_suppresses_whispers_with_few_signals(now):
    """On day 1 with few signals, no Whispers fire (retrieval only).

    The trust ladder:
      - 0-4 signals: RETRIEVAL_ONLY (no Whispers; Maestro listens, doesn't speak)
      - 5-14 signals: LOW_CONFIDENCE_WHISPERS (Whispers fire but marked low confidence)
      - 15+ signals: FULL_WHISPERS (normal operation)

    This prevents Maestro from speaking with false authority on day 1,
    before it has enough evidence to understand the organization.
    """
    from maestro_oem.cold_start_mode import ColdStartMode, TrustLadderRung

    # Day 1: 3 signals → retrieval only
    cold_start = ColdStartMode(signal_count=3)
    assert cold_start.rung == TrustLadderRung.RETRIEVAL_ONLY, \
        f"3 signals → RETRIEVAL_ONLY. Got: {cold_start.rung}"
    assert cold_start.should_suppress_whispers() is True, \
        "Retrieval-only mode must suppress Whispers"

    # 10 signals → low confidence
    cold_start = ColdStartMode(signal_count=10)
    assert cold_start.rung == TrustLadderRung.LOW_CONFIDENCE_WHISPERS, \
        f"10 signals → LOW_CONFIDENCE_WHISPERS. Got: {cold_start.rung}"
    assert cold_start.should_suppress_whispers() is False, \
        "Low-confidence mode must NOT suppress Whispers (they fire, marked low confidence)"

    # 20 signals → full
    cold_start = ColdStartMode(signal_count=20)
    assert cold_start.rung == TrustLadderRung.FULL_WHISPERS, \
        f"20 signals → FULL_WHISPERS. Got: {cold_start.rung}"
    assert cold_start.should_suppress_whispers() is False, \
        "Full mode must NOT suppress Whispers"


def test_cold_start_mode_is_overridden_by_high_stakes(now):
    """Even in cold-start mode, a high-stakes signal (broken commitment,
    churn) overrides the suppression.

    This is the safety valve: if a customer churns on day 1, Maestro
    must speak — even if it's only day 1. The trust ladder is a default,
    not a hard rule. High-stakes signals override.
    """
    from maestro_oem.cold_start_mode import ColdStartMode, TrustLadderRung

    cold_start = ColdStartMode(signal_count=3, has_high_stakes_signal=True)
    # Rung is still RETRIEVAL_ONLY (3 signals), but high-stakes overrides suppression
    assert cold_start.rung == TrustLadderRung.RETRIEVAL_ONLY, \
        f"Rung is based on signal count. Got: {cold_start.rung}"
    assert cold_start.should_suppress_whispers() is False, \
        "High-stakes signal must override cold-start suppression — Maestro must speak"
