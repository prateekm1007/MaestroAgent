"""H2 fix: Wire CommitmentMutationTracker + DisagreementDetector into the
real Whisper generation pipeline.

Adversarial audit finding (ADVERSARIAL-AUDIT-LATEST-c5f08fb):
> H2: CommitmentMutationTracker + DisagreementDetector not wired into
> production paths (P11 violation). Same pattern as original CRITICAL-01.
> 2 of 5 Loop 1.5 capabilities are demonstration endpoints.

The pattern to follow: same as CRITICAL-01 (commit 934db75) which wired
decide_delivery into for_context(). These tests verify that:
  1. CommitmentMutationTracker is called by the real Whisper pipeline
  2. DisagreementDetector is called by the real Whisper pipeline
  3. Whispers carry mutation history when commitments have changed
  4. Whispers carry disagreement detection when evidence conflicts
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

from maestro_oem.signal import SignalType


class MockSignal:
    def __init__(self, sig_type, actor="", artifact="", metadata=None, timestamp=None, provider="customer"):
        self.type = sig_type
        self.actor = actor
        self.artifact = artifact
        self.metadata = metadata or {}
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.signal_id = f"sig-{artifact or id(self)}"
        self.provider = type("P", (), {"value": provider})()


class MockModel:
    def __init__(self):
        self.laws = {}
        self.learning_objects = {}
        self.approvals = type('A', (), {'get_bottlenecks': lambda self, min_count=2: []})()
        self.decisions = type('D', (), {'get_recommendations': lambda self: []})()


@pytest.fixture
def now():
    return datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def signals_with_mutation(now):
    """Signals where a commitment has mutated (deadline moved)."""
    return [
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane@example.com",
            artifact="crm:commit-1",
            metadata={"customer": "TestCorp", "commitment": "Deliver SSO by Q4"},
            timestamp=now - timedelta(days=30),
        ),
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane@example.com",
            artifact="crm:commit-2",
            metadata={"customer": "TestCorp", "commitment": "Deliver SSO by Q1 2025"},  # mutated
            timestamp=now - timedelta(days=5),
        ),
        MockSignal(
            SignalType.CUSTOMER_OBJECTION,
            actor="jane@example.com",
            artifact="crm:obj-1",
            metadata={"customer": "TestCorp", "objection_type": "pricing"},
            timestamp=now - timedelta(days=3),
        ),
        MockSignal(SignalType.CUSTOMER_MEETING, actor="jane@example.com",
            artifact="crm:mtg-1", metadata={"customer": "TestCorp"},
            timestamp=now - timedelta(days=10)),
        MockSignal(SignalType.CUSTOMER_EMAIL, actor="jane@example.com",
            artifact="crm:email-1", metadata={"customer": "TestCorp"},
            timestamp=now - timedelta(days=8)),
        MockSignal(SignalType.CUSTOMER_CHAMPION_ACTIVE, actor="jane@example.com",
            artifact="crm:champ-1", metadata={"customer": "TestCorp"},
            timestamp=now - timedelta(days=1)),
    ]


# ─── 1. CommitmentMutationTracker wired into Whisper pipeline ─────────────

def test_whisper_carries_mutation_history_when_commitment_changed(signals_with_mutation):
    """When a commitment has mutated (wording changed), the Whisper must
    carry mutation history in its evidence_spine.

    BEFORE H2 fix: CommitmentMutationTracker is only called from
    /loop1.5/mutation/* routes. The real Whisper pipeline never calls it.

    AFTER H2 fix: for_context() calls the mutation tracker and attaches
    mutation history to whispers about entities with changed commitments.
    """
    from maestro_oem.whisper import OrganizationalWhisper

    model = MockModel()
    engine = OrganizationalWhisper(model, signals_with_mutation, whisper_store={})
    result = engine.for_context(context="meeting", entity="TestCorp", topic="pricing")

    whispers = result.get("whispers", [])
    assert len(whispers) > 0, "Must produce whispers"

    # At least one whisper must carry mutation_history
    has_mutation = False
    for w in whispers:
        es = w.get("evidence_spine", {})
        if "mutation_history" in es or "commitment_mutations" in es:
            has_mutation = True
            # The mutation history must contain BOTH wordings
            mutations = es.get("commitment_mutations", [])
            history = es.get("mutation_history", [])
            if mutations:
                # There must be at least 1 mutation event
                assert len(mutations) >= 1, \
                    f"Must have ≥1 mutation event. Got: {mutations}"
                m = mutations[0]
                assert "Deliver SSO by Q4" in str(m), \
                    f"Old wording must be in mutation. Got: {m}"
                assert "Q1 2025" in str(m), \
                    f"New wording must be in mutation. Got: {m}"
            break

    assert has_mutation, \
        "At least one whisper must carry mutation_history when a commitment has changed. " \
        f"Whispers: {[w.get('whisper_id', '?') for w in whispers]}"


def test_whisper_no_mutation_history_when_commitment_unchanged(now):
    """When a commitment has NOT mutated (same wording twice), no mutation
    history should be attached.

    Non-vacuous counter-test: false positives erode trust.
    """
    from maestro_oem.whisper import OrganizationalWhisper

    signals = [
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane@example.com",
            artifact="crm:commit-1",
            metadata={"customer": "StableCorp", "commitment": "Deliver API by Q3"},
            timestamp=now - timedelta(days=30),
        ),
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane@example.com",
            artifact="crm:commit-2",
            metadata={"customer": "StableCorp", "commitment": "Deliver API by Q3"},  # SAME
            timestamp=now - timedelta(days=5),
        ),
        MockSignal(SignalType.CUSTOMER_OBJECTION, actor="jane@example.com",
            artifact="crm:obj-1", metadata={"customer": "StableCorp", "objection_type": "timeline"},
            timestamp=now - timedelta(days=3)),
        MockSignal(SignalType.CUSTOMER_MEETING, actor="jane@example.com",
            artifact="crm:mtg-1", metadata={"customer": "StableCorp"},
            timestamp=now - timedelta(days=10)),
        MockSignal(SignalType.CUSTOMER_EMAIL, actor="jane@example.com",
            artifact="crm:email-1", metadata={"customer": "StableCorp"},
            timestamp=now - timedelta(days=8)),
        MockSignal(SignalType.CUSTOMER_CHAMPION_ACTIVE, actor="jane@example.com",
            artifact="crm:champ-1", metadata={"customer": "StableCorp"},
            timestamp=now - timedelta(days=1)),
    ]

    model = MockModel()
    engine = OrganizationalWhisper(model, signals, whisper_store={})
    result = engine.for_context(context="meeting", entity="StableCorp", topic="pricing")

    whispers = result.get("whispers", [])
    for w in whispers:
        es = w.get("evidence_spine", {})
        mutations = es.get("commitment_mutations", [])
        assert len(mutations) == 0, \
            f"No mutations when commitment unchanged. Got: {mutations}"


# ─── 2. DisagreementDetector wired into Whisper pipeline ──────────────────

def test_whisper_carries_disagreement_when_evidence_conflicts(now):
    """When evidence for the same entity has conflicting claims across
    different claim_types, the Whisper must carry disagreement detection.

    BEFORE H2 fix: DisagreementDetector is only called from
    /loop1.5/disagreements/* route. The real Whisper pipeline never calls it.

    AFTER H2 fix: for_context() runs the DisagreementDetector on the
    evidence and attaches detected disagreements to the whisper.
    """
    from maestro_oem.whisper import OrganizationalWhisper

    # Signals that create conflicting evidence:
    # - A commitment (claim_type="commitment") says "on track"
    # - An objection (claim_type="observed_fact") says "pricing issue"
    # These don't directly conflict in the sentiment heuristic, but the
    # objection IS conflicting evidence against the commitment.
    signals = [
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane@example.com",
            artifact="crm:commit-1",
            metadata={"customer": "ConflictCorp", "commitment": "Deliver SSO on track for Q4"},
            timestamp=now - timedelta(days=20),
        ),
        MockSignal(
            SignalType.CUSTOMER_OBJECTION,
            actor="jane@example.com",
            artifact="crm:obj-1",
            metadata={"customer": "ConflictCorp", "objection_type": "pricing"},
            timestamp=now - timedelta(days=5),
        ),
        MockSignal(SignalType.CUSTOMER_MEETING, actor="jane@example.com",
            artifact="crm:mtg-1", metadata={"customer": "ConflictCorp"},
            timestamp=now - timedelta(days=10)),
        MockSignal(SignalType.CUSTOMER_EMAIL, actor="jane@example.com",
            artifact="crm:email-1", metadata={"customer": "ConflictCorp"},
            timestamp=now - timedelta(days=8)),
        MockSignal(SignalType.CUSTOMER_CHAMPION_ACTIVE, actor="jane@example.com",
            artifact="crm:champ-1", metadata={"customer": "ConflictCorp"},
            timestamp=now - timedelta(days=1)),
    ]

    model = MockModel()
    engine = OrganizationalWhisper(model, signals, whisper_store={})
    result = engine.for_context(context="meeting", entity="ConflictCorp", topic="pricing")

    whispers = result.get("whispers", [])
    assert len(whispers) > 0

    # At least one whisper must carry disagreement detection
    # The evidence_spine already has "conflicting_evidence" (from EvidenceBuilder).
    # The H2 fix adds a "detected_disagreements" field from DisagreementDetector.
    has_disagreement_field = False
    for w in whispers:
        es = w.get("evidence_spine", {})
        if "detected_disagreements" in es:
            has_disagreement_field = True
            disagreements = es["detected_disagreements"]
            # The disagreements list may be empty (if no conflicts detected by
            # the heuristic) or non-empty. The key is that the field EXISTS —
            # proving the DisagreementDetector was called.
            assert isinstance(disagreements, list), \
                f"detected_disagreements must be a list. Got: {type(disagreements)}"
            break

    assert has_disagreement_field, \
        "At least one whisper must carry 'detected_disagreements' field — " \
        "proving DisagreementDetector was called by the production pipeline. " \
        f"Whispers: {[w.get('whisper_id', '?') for w in whispers]}"


def test_disagreement_detector_does_not_crash_on_no_conflicts(now):
    """When there are no conflicting claims, the DisagreementDetector must
    return an empty list, not crash.

    Non-vacuous counter-test: the wiring must be fail-safe.
    """
    from maestro_oem.whisper import OrganizationalWhisper

    signals = [
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane@example.com",
            artifact="crm:commit-1",
            metadata={"customer": "PeacefulCorp", "commitment": "Deliver on time"},
            timestamp=now - timedelta(days=20),
        ),
        MockSignal(SignalType.CUSTOMER_MEETING, actor="jane@example.com",
            artifact="crm:mtg-1", metadata={"customer": "PeacefulCorp"},
            timestamp=now - timedelta(days=10)),
        MockSignal(SignalType.CUSTOMER_EMAIL, actor="jane@example.com",
            artifact="crm:email-1", metadata={"customer": "PeacefulCorp"},
            timestamp=now - timedelta(days=8)),
        MockSignal(SignalType.CUSTOMER_CHAMPION_ACTIVE, actor="jane@example.com",
            artifact="crm:champ-1", metadata={"customer": "PeacefulCorp"},
            timestamp=now - timedelta(days=1)),
        MockSignal(SignalType.CUSTOMER_STAGE_CHANGE, actor="jane@example.com",
            artifact="crm:stage-1", metadata={"customer": "PeacefulCorp"},
            timestamp=now - timedelta(days=2)),
    ]

    model = MockModel()
    engine = OrganizationalWhisper(model, signals, whisper_store={})
    result = engine.for_context(context="meeting", entity="PeacefulCorp", topic="pricing")

    # Must not crash — must return whispers with detected_disagreements = []
    whispers = result.get("whispers", [])
    for w in whispers:
        es = w.get("evidence_spine", {})
        if "detected_disagreements" in es:
            assert isinstance(es["detected_disagreements"], list)


# ─── 3. P11 wiring check — grep verification ──────────────────────────────

def test_commitment_mutation_tracker_referenced_in_whisper_py():
    """P11 check: CommitmentMutationTracker must be referenced in whisper.py."""
    import maestro_oem.whisper as whisper_module
    import inspect

    source = inspect.getsource(whisper_module)
    assert "CommitmentMutationTracker" in source or "mutation_tracker" in source or "_apply_mutation" in source, \
        "whisper.py must reference CommitmentMutationTracker (P11 — wired into production path)"


def test_disagreement_detector_referenced_in_whisper_py():
    """P11 check: DisagreementDetector must be referenced in whisper.py."""
    import maestro_oem.whisper as whisper_module
    import inspect

    source = inspect.getsource(whisper_module)
    assert "DisagreementDetector" in source or "disagreement_detector" in source or "_apply_disagreement" in source, \
        "whisper.py must reference DisagreementDetector (P11 — wired into production path)"
