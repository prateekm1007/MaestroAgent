"""Loop 4 — Organizational Learning: adversarial tests.

CEO directive (auditor recommendation, CEO-validated): "Loop 4 —
Organizational Learning: cross-case pattern detection and delivery-policy
learning. This is the final loop — it connects the first three loops into
a unified learning system. This is where the moat compounds — the system
learning about its own delivery effectiveness."

Loop 4 aggregates Learning Ledger entries from Loops 1-3 into a unified
Organizational Learning Ledger. It detects cross-loop patterns:

  1. Cross-case pattern detection: "decisions based on the 'Globex will
     renew' assumption fail 3 times" (decision + cross-case). But more
     powerfully: "commitment warnings that the exec ignored were followed
     by broken commitments 2 out of 3 times" (Loop 1 + Loop 1 outcome).

  2. Delivery-policy learning: "commitment warnings are more useful before
     account meetings than during weekly planning" (commitment + meeting).
     The system learns about its own delivery effectiveness.

  3. Honest aggregation: the Organizational Learning Ledger entry is honest,
     signal-derived, references actual cross-loop patterns, and acknowledges
     sample-size limitations ("3 data points is not a trend" — no fake
     precision).

These tests are adversarial: each assertion is non-vacuous (would fail on
the pre-Loop-4 codebase). Write first, watch fail, then build.

Design decisions (documented for audit per CEO directive):
  - OrganizationalLearningLedger collects entries from Loop 1 (commitments),
    Loop 2 (meetings), and Loop 3 (decisions)
  - CrossLoopPatternDetector finds patterns that span loops
  - DeliveryPolicyLearner learns about Maestro's own delivery effectiveness
  - The Organizational Learning Ledger entry is honest, signal-derived,
    references cross-loop patterns, acknowledges sample-size limitations
  - HTTP endpoints ship in the same commit (per established pattern)
  - Richness lesson applied: entries should be the richest yet (the system
    is learning about its own learning)
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


@pytest.fixture
def now():
    return datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)


# ─── 1. Organizational Learning Ledger collects from all 3 loops ───────────

def test_organizational_learning_ledger_collects_from_all_loops(now):
    """The OrganizationalLearningLedger must collect entries from Loop 1
    (commitments), Loop 2 (meetings), and Loop 3 (decisions).

    Old codebase: each loop had its own Learning Ledger. No aggregation.
    Loop 4 unifies them.
    """
    from maestro_oem.organizational_learning_ledger import OrganizationalLearningLedger

    ledger = OrganizationalLearningLedger()

    # Record entries from all 3 loops
    ledger.record_commitment_learning(
        entity="Globex",
        whisper_id="wspr-1",
        action="ignored",
        outcome="broken",
        learning_entry="Globex broke its commitment after the exec ignored the Whisper.",
    )
    ledger.record_meeting_learning(
        entity="Globex",
        meeting_id="mtg-1",
        outcome="commitment_broken",
        learning_entry="The Globex meeting ended with a broken commitment.",
    )
    ledger.record_decision_learning(
        entity="Globex",
        decision_id="dec-1",
        hypothesis="SSO will ship by Q4",
        outcome="SSO missed Q4",
        learning_entry="The decision to prioritize SSO was based on a wrong hypothesis.",
    )

    all_entries = ledger.get_all_entries()
    assert len(all_entries) >= 3, \
        f"Must collect entries from all 3 loops. Got {len(all_entries)}"
    sources = {e.source_loop for e in all_entries}
    assert "commitment" in sources, f"Must include commitment entries. Got: {sources}"
    assert "meeting" in sources, f"Must include meeting entries. Got: {sources}"
    assert "decision" in sources, f"Must include decision entries. Got: {sources}"


# ─── 2. Cross-loop pattern detection ───────────────────────────────────────

def test_cross_loop_pattern_detects_ignored_whisper_then_broken_commitment(now):
    """When the exec ignores a commitment Whisper AND the commitment is
    later broken, that's a cross-loop pattern.

    Pattern: "ignored Whisper → broken commitment" appears N times.
    This spans Loop 1 (the Whisper + action) and Loop 1's outcome observation.
    The CrossLoopPatternDetector must find this.

    Old codebase: no cross-loop pattern detection. Each loop was isolated.
    Loop 4 connects them.
    """
    from maestro_oem.organizational_learning_ledger import OrganizationalLearningLedger
    from maestro_oem.cross_loop_patterns import CrossLoopPatternDetector

    ledger = OrganizationalLearningLedger()

    # 3 cases: exec ignored the Whisper, commitment was broken
    for i in range(3):
        ledger.record_commitment_learning(
            entity=f"Entity{i}",
            whisper_id=f"wspr-{i}",
            action="ignored",
            outcome="broken",
            learning_entry=f"Entity{i} broke its commitment after the exec ignored the Whisper.",
        )

    detector = CrossLoopPatternDetector()
    patterns = detector.detect(ledger)

    assert len(patterns) >= 1, \
        f"Must detect the 'ignored Whisper → broken commitment' pattern. Got: {patterns}"
    # Find the specific pattern
    ignored_broken_pattern = next(
        (p for p in patterns if "ignored" in p.description.lower() and "broken" in p.description.lower()),
        None,
    )
    assert ignored_broken_pattern is not None, \
        f"Must detect the ignored→broken pattern specifically. Got: {[p.description for p in patterns]}"
    assert ignored_broken_pattern.case_count >= 3, \
        f"Pattern must count 3 cases. Got: {ignored_broken_pattern.case_count}"


def test_cross_loop_pattern_no_false_positive_when_no_correlation(now):
    """When ignored Whispers are NOT followed by broken commitments, no
    pattern is detected.

    Non-vacuous counter-test: false positives erode trust.
    """
    from maestro_oem.organizational_learning_ledger import OrganizationalLearningLedger
    from maestro_oem.cross_loop_patterns import CrossLoopPatternDetector

    ledger = OrganizationalLearningLedger()

    # 3 cases: exec ignored, but commitment was HONORED (no correlation)
    for i in range(3):
        ledger.record_commitment_learning(
            entity=f"Entity{i}",
            whisper_id=f"wspr-{i}",
            action="ignored",
            outcome="honored",  # NOT broken
            learning_entry=f"Entity{i} honored its commitment despite the exec ignoring the Whisper.",
        )

    detector = CrossLoopPatternDetector()
    patterns = detector.detect(ledger)

    # Should NOT find the ignored→broken pattern (because outcome was honored)
    ignored_broken = next(
        (p for p in patterns if "ignored" in p.description.lower() and "broken" in p.description.lower()),
        None,
    )
    assert ignored_broken is None, \
        f"Must NOT detect ignored→broken when outcome was honored. Got: {ignored_broken}"


# ─── 3. Delivery-policy learning ───────────────────────────────────────────

def test_delivery_policy_learner_identifies_effective_timing(now):
    """The DeliveryPolicyLearner learns about Maestro's own delivery
    effectiveness.

    Scenario: commitment warnings delivered BEFORE account meetings led to
    the exec acting (action='acted') 3 times. Warnings delivered during
    weekly planning led to the exec ignoring them 3 times.

    The learner must identify: "commitment warnings are more effective
    before account meetings than during weekly planning."

    Old codebase: no delivery-policy learning. Maestro didn't learn about
    its own effectiveness. Loop 4 fixes this.
    """
    from maestro_oem.organizational_learning_ledger import OrganizationalLearningLedger
    from maestro_oem.delivery_policy_learner import DeliveryPolicyLearner

    ledger = OrganizationalLearningLedger()

    # 3 cases: warning before meeting → exec acted
    for i in range(3):
        ledger.record_commitment_learning(
            entity=f"Entity{i}",
            whisper_id=f"wspr-meeting-{i}",
            action="acted",
            outcome="honored",
            learning_entry=f"Entity{i} honored its commitment after the exec acted on the pre-meeting Whisper.",
            delivery_context="before_account_meeting",
        )

    # 3 cases: warning during weekly planning → exec ignored
    for i in range(3):
        ledger.record_commitment_learning(
            entity=f"Entity{i}",
            whisper_id=f"wspr-planning-{i}",
            action="ignored",
            outcome="broken",
            learning_entry=f"Entity{i} broke its commitment after the exec ignored the weekly-planning Whisper.",
            delivery_context="weekly_planning",
        )

    learner = DeliveryPolicyLearner()
    policies = learner.learn(ledger)

    assert len(policies) >= 1, \
        f"Must learn at least 1 delivery policy. Got: {policies}"
    # Find the policy about meeting vs planning effectiveness
    meeting_policy = next(
        (p for p in policies if "meeting" in p.description.lower() and "planning" in p.description.lower()),
        None,
    )
    assert meeting_policy is not None, \
        f"Must identify the meeting-vs-planning effectiveness policy. Got: {[p.description for p in policies]}"
    # The policy must state that meeting-time delivery is more effective
    assert "more effective" in meeting_policy.description.lower() or "better" in meeting_policy.description.lower(), \
        f"Policy must state which timing is more effective. Got: {meeting_policy.description!r}"


# ─── 4. Organizational Learning Ledger entry — honest + cross-loop ────────

def test_organizational_learning_entry_is_honest_and_cross_loop(now):
    """The Organizational Learning Ledger entry is one honest sentence
    that references actual cross-loop patterns.

    It must:
      - Reference the cross-loop pattern found
      - Acknowledge sample-size limitations ("3 data points is not a trend")
      - NOT claim certainty Maestro doesn't have
      - Be signal-derived, not templated
      - Be rich (≥80 chars — the system learning about its own learning)
    """
    from maestro_oem.organizational_learning_ledger import OrganizationalLearningLedger
    from maestro_oem.cross_loop_patterns import CrossLoopPatternDetector
    from maestro_oem.organizational_learning_composer import OrganizationalLearningComposer

    ledger = OrganizationalLearningLedger()

    # 3 cases: ignored Whisper → broken commitment
    for i in range(3):
        ledger.record_commitment_learning(
            entity=f"Entity{i}",
            whisper_id=f"wspr-{i}",
            action="ignored",
            outcome="broken",
            learning_entry=f"Entity{i} broke its commitment after the exec ignored the Whisper.",
        )

    detector = CrossLoopPatternDetector()
    patterns = detector.detect(ledger)

    composer = OrganizationalLearningComposer()
    entry = composer.compose(patterns, sample_size=ledger.total_entries())

    assert entry, "Organizational Learning entry must be non-empty"
    assert len(entry) >= 80, \
        f"Entry must be rich (≥80 chars — the system learning about its own learning). Got: {entry!r} (len={len(entry)})"

    # REJECT placeholders (P6)
    FORBIDDEN = ["Learning recorded.", "System learned.", "TODO", "placeholder", "Organizational learning complete."]
    for phrase in FORBIDDEN:
        assert phrase.lower() not in entry.lower(), \
            f"Entry must not be a placeholder. Got: {entry!r}"

    # Must reference the cross-loop pattern
    assert "ignored" in entry.lower() or "broken" in entry.lower() or "pattern" in entry.lower(), \
        f"Entry must reference the cross-loop pattern. Got: {entry!r}"

    # Must acknowledge sample-size limitations (no fake precision)
    assert "sample" in entry.lower() or "data point" in entry.lower() or "not a trend" in entry.lower() or "limited" in entry.lower() or "small" in entry.lower() or "may not" in entry.lower(), \
        f"Entry must acknowledge sample-size limitations (no fake precision). Got: {entry!r}"


# ─── 5. Full Loop 4 end-to-end ─────────────────────────────────────────────

def test_loop4_organizational_learning_full_lifecycle(now):
    """ONE test that exercises the whole Loop 4:

    1. Record learnings from all 3 loops (commitment, meeting, decision)
    2. Detect cross-loop patterns
    3. Learn delivery policies
    4. Compose the Organizational Learning Ledger entry
    5. Verify the entry is honest, cross-loop, and acknowledges limitations
    """
    from maestro_oem.organizational_learning_ledger import OrganizationalLearningLedger
    from maestro_oem.cross_loop_patterns import CrossLoopPatternDetector
    from maestro_oem.delivery_policy_learner import DeliveryPolicyLearner
    from maestro_oem.organizational_learning_composer import OrganizationalLearningComposer

    ledger = OrganizationalLearningLedger()

    # Step 1: Record learnings from all 3 loops
    # Loop 1: commitment learnings (ignored → broken, 3 cases)
    for i in range(3):
        ledger.record_commitment_learning(
            entity=f"CommitEntity{i}",
            whisper_id=f"wspr-{i}",
            action="ignored",
            outcome="broken",
            learning_entry=f"CommitEntity{i} broke its commitment after the exec ignored the Whisper.",
            delivery_context="before_account_meeting" if i < 2 else "weekly_planning",
        )

    # Loop 2: meeting learnings
    ledger.record_meeting_learning(
        entity="Globex",
        meeting_id="mtg-1",
        outcome="commitment_broken",
        learning_entry="The Globex meeting ended with a broken commitment.",
    )

    # Loop 3: decision learnings
    ledger.record_decision_learning(
        entity="Globex",
        decision_id="dec-1",
        hypothesis="SSO will ship by Q4",
        outcome="SSO missed Q4",
        learning_entry="The decision to prioritize SSO was based on a wrong hypothesis.",
    )

    # Step 2: Detect cross-loop patterns
    detector = CrossLoopPatternDetector()
    patterns = detector.detect(ledger)
    assert len(patterns) >= 1, "Must detect cross-loop patterns"

    # Step 3: Learn delivery policies
    learner = DeliveryPolicyLearner()
    policies = learner.learn(ledger)

    # Step 4: Compose the Organizational Learning Ledger entry
    composer = OrganizationalLearningComposer()
    entry = composer.compose(patterns, sample_size=ledger.total_entries())

    # Step 5: Verify the entry
    assert entry, "Entry must be non-empty"
    assert len(entry) >= 80, f"Entry must be rich. Got: {entry!r}"

    FORBIDDEN = ["Learning recorded.", "System learned.", "TODO", "placeholder"]
    for phrase in FORBIDDEN:
        assert phrase.lower() not in entry.lower(), \
            f"Entry must not be a placeholder. Got: {entry!r}"

    # Must reference the cross-loop pattern OR the delivery policy
    assert any(word in entry.lower() for word in ["ignored", "broken", "pattern", "meeting", "planning", "effective"]), \
        f"Entry must reference cross-loop patterns or delivery policies. Got: {entry!r}"

    # Must acknowledge sample-size limitations
    assert any(word in entry.lower() for word in ["sample", "data point", "not a trend", "limited", "small", "may not"]), \
        f"Entry must acknowledge sample-size limitations. Got: {entry!r}"

    # The ledger must have collected from all 3 loops
    all_entries = ledger.get_all_entries()
    sources = {e.source_loop for e in all_entries}
    assert "commitment" in sources
    assert "meeting" in sources
    assert "decision" in sources
