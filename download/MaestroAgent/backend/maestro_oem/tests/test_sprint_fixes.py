"""
Tests for behaviors introduced in commit 00a6314
("fix: resolve all 6 known limitations — 250/250 tests pass, 0 skipped").

These tests specifically cover:

1. Pattern.is_law_candidate_relaxed — single-entity patterns with evidence >= 3
2. PatternDetector aggregation across LOs for the same entity:
   - hidden_experts, bottlenecks, velocity_drops, knowledge_death, approval_gates
3. EventBus.start() — graceful handling when no event loop is running
4. EventBus.start_async() — async-safe start for use in async fixtures
5. RunStatus import — must be importable from maestro_core (not just maestro_core.state)

These tests protect against regressions of the fixes from that commit.
"""

from __future__ import annotations

import asyncio
import pytest
from uuid import uuid4

from maestro_oem.learning_object import LearningObject, LearningObjectType
from maestro_oem.pattern import Pattern, PatternDetector, PatternType


# ============================================================
# 1. is_law_candidate_relaxed — single-entity patterns
# ============================================================


class TestLawCandidateRelaxed:
    """Verify the relaxed threshold for single-entity patterns.

    Background: Before commit 00a6314, patterns required coverage >= 2 to
    become law candidates. This blocked legitimate single-entity patterns
    (e.g., one bottleneck gate with 5 observations) from ever being promoted.
    The fix introduces is_law_candidate_relaxed: evidence_count >= 3 with
    coverage >= 1.
    """

    def test_relaxed_passes_when_strict_fails(self):
        """A pattern with 3 evidence but coverage=1 must pass the relaxed check."""
        p = Pattern(
            type=PatternType.CAUSAL,
            description="Single-entity pattern with enough evidence",
            learning_object_ids=[uuid4(), uuid4(), uuid4()],
            coverage=1,
        )
        assert not p.is_law_candidate, "Strict check should fail (coverage < 2)"
        assert p.is_law_candidate_relaxed, "Relaxed check should pass (evidence >= 3)"

    def test_relaxed_fails_when_evidence_below_threshold(self):
        """A pattern with 2 evidence and coverage=1 must fail both checks."""
        p = Pattern(
            type=PatternType.INFLUENCE,
            description="Insufficient evidence",
            learning_object_ids=[uuid4(), uuid4()],
            coverage=1,
        )
        assert not p.is_law_candidate
        assert not p.is_law_candidate_relaxed

    def test_relaxed_fails_when_no_evidence(self):
        """A pattern with zero evidence must fail both checks."""
        p = Pattern(
            type=PatternType.VELOCITY,
            description="Empty pattern",
            coverage=0,
        )
        assert not p.is_law_candidate
        assert not p.is_law_candidate_relaxed

    def test_strict_and_relaxed_both_pass_for_multi_entity(self):
        """A pattern with 3+ evidence and 2+ coverage must pass both checks."""
        p = Pattern(
            type=PatternType.STRUCTURAL,
            description="Multi-entity pattern",
            learning_object_ids=[uuid4(), uuid4(), uuid4(), uuid4()],
            coverage=3,
        )
        assert p.is_law_candidate
        assert p.is_law_candidate_relaxed

    def test_relaxed_boundary_exactly_three_evidence(self):
        """Boundary case: exactly 3 evidence with coverage=1."""
        p = Pattern(
            type=PatternType.KNOWLEDGE,
            description="Boundary pattern",
            learning_object_ids=[uuid4(), uuid4(), uuid4()],
            coverage=1,
        )
        assert p.is_law_candidate_relaxed
        assert not p.is_law_candidate

    def test_relaxed_boundary_two_evidence_fails(self):
        """Boundary case: 2 evidence with coverage=1 must fail."""
        p = Pattern(
            type=PatternType.APPROVAL,
            description="Just below threshold",
            learning_object_ids=[uuid4(), uuid4()],
            coverage=1,
        )
        assert not p.is_law_candidate_relaxed


# ============================================================
# 2. PatternDetector aggregation across LOs
# ============================================================


def _make_lo(
    lo_type: LearningObjectType,
    entities: list[str],
    evidence_count: int = 1,
    metadata: dict | None = None,
    providers: set[str] | None = None,
) -> LearningObject:
    """Helper: build a LearningObject with N supporting signals."""
    lo = LearningObject(
        type=lo_type,
        title=f"Test LO: {lo_type.value}",
        description="Test",
        entities=entities,
        evidence_count=evidence_count,
        providers=providers or {"github"},
        metadata=metadata or {},
    )
    # Pad signal_ids to match evidence_count
    lo.signal_ids = [uuid4() for _ in range(evidence_count)]
    return lo


class TestPatternAggregation:
    """Verify that PatternDetector aggregates evidence across LOs for the same entity.

    Background: Before commit 00a6314, each detector required a single LO to
    have evidence_count >= 3 (or 2) on its own. But in practice, each LO had
    evidence_count=1 (one signal per observation). This meant patterns were
    never promoted to law candidates, which cascaded into 3 skipped tests
    in test_evidence_graph.py.

    The fix: detectors now group LOs by entity and sum evidence_count across
    all LOs in the group. If the aggregated total meets the threshold, a
    pattern is created spanning all the grouped LOs.
    """

    def test_hidden_experts_aggregates_across_three_single_evidence_los(self):
        """Three hidden_expert LOs (evidence_count=1 each) for the same person
        must produce one INFLUENCE pattern with aggregated evidence_count=3."""
        los = [
            _make_lo(LearningObjectType.HIDDEN_EXPERT, ["priya.m@acme.com"]),
            _make_lo(LearningObjectType.HIDDEN_EXPERT, ["priya.m@acme.com"]),
            _make_lo(LearningObjectType.HIDDEN_EXPERT, ["priya.m@acme.com"]),
        ]
        detector = PatternDetector()
        patterns = detector.detect(los)

        influence_patterns = [p for p in patterns if p.type == PatternType.INFLUENCE]
        assert len(influence_patterns) == 1, f"Expected 1 influence pattern, got {len(influence_patterns)}"
        p = influence_patterns[0]
        assert len(p.learning_object_ids) == 3, "Pattern must span all 3 LOs"
        assert p.metadata.get("expert") == "priya.m@acme.com"
        assert p.metadata.get("total_evidence") == 3

    def test_hidden_experts_below_threshold_produces_no_pattern(self):
        """Two hidden_expert LOs (evidence_count=1 each) for the same person
        sum to 2, below the threshold of 3 — no pattern should be created."""
        los = [
            _make_lo(LearningObjectType.HIDDEN_EXPERT, ["priya.m@acme.com"]),
            _make_lo(LearningObjectType.HIDDEN_EXPERT, ["priya.m@acme.com"]),
        ]
        detector = PatternDetector()
        patterns = detector.detect(los)
        assert not any(p.type == PatternType.INFLUENCE for p in patterns)

    def test_hidden_experts_separates_different_entities(self):
        """Two entities, each with 3 LOs, must produce 2 separate patterns."""
        los = [
            *_make_los(3, LearningObjectType.HIDDEN_EXPERT, ["alice@acme.com"]),
            *_make_los(3, LearningObjectType.HIDDEN_EXPERT, ["bob@acme.com"]),
        ]
        detector = PatternDetector()
        patterns = detector.detect(los)
        influence = [p for p in patterns if p.type == PatternType.INFLUENCE]
        assert len(influence) == 2
        experts = {p.metadata["expert"] for p in influence}
        assert experts == {"alice@acme.com", "bob@acme.com"}

    def test_bottlenecks_aggregates_across_three_single_evidence_los(self):
        """Three bottleneck LOs (evidence_count=1 each) for the same gate sum to 3,
        meeting both the bottleneck detector threshold (>= 2) AND the relaxed
        law-candidate filter (evidence_count >= 3) — one CAUSAL pattern results."""
        los = _make_los(3, LearningObjectType.BOTTLENECK, ["legal-review"])
        detector = PatternDetector()
        patterns = detector.detect(los)
        causal = [p for p in patterns if p.type == PatternType.CAUSAL]
        assert len(causal) == 1
        assert causal[0].metadata.get("gate") == "legal-review"
        assert causal[0].metadata.get("total_evidence") == 3

    def test_velocity_drops_aggregates_across_three_los(self):
        """Three velocity_drop LOs (evidence_count=1 each) sum to 3, meeting the
        velocity threshold — one VELOCITY pattern should result."""
        los = _make_los(3, LearningObjectType.VELOCITY_DROP, ["team-alpha"])
        detector = PatternDetector()
        patterns = detector.detect(los)
        velocity = [p for p in patterns if p.type == PatternType.VELOCITY]
        assert len(velocity) == 1
        assert velocity[0].metadata.get("total_evidence") == 3

    def test_knowledge_death_aggregates_by_boundary(self):
        """Three knowledge_death LOs with the same boundary metadata should
        aggregate by boundary value, not by entity."""
        los = [
            _make_lo(
                LearningObjectType.KNOWLEDGE_DEATH,
                ["team-a"],
                metadata={"boundary": "frontend-backend"},
            ),
            _make_lo(
                LearningObjectType.KNOWLEDGE_DEATH,
                ["team-b"],
                metadata={"boundary": "frontend-backend"},
            ),
            _make_lo(
                LearningObjectType.KNOWLEDGE_DEATH,
                ["team-c"],
                metadata={"boundary": "frontend-backend"},
            ),
        ]
        detector = PatternDetector()
        patterns = detector.detect(los)
        knowledge = [p for p in patterns if p.type == PatternType.KNOWLEDGE]
        assert len(knowledge) == 1
        assert knowledge[0].metadata.get("boundary") == "frontend-backend"
        assert knowledge[0].metadata.get("total_evidence") == 3

    def test_approval_gates_aggregates_by_gate_entity(self):
        """Three approval_gate LOs for the same gate should aggregate."""
        los = _make_los(3, LearningObjectType.APPROVAL_GATE, ["sara.k@acme.com"])
        detector = PatternDetector()
        patterns = detector.detect(los)
        approval = [p for p in patterns if p.type == PatternType.APPROVAL]
        assert len(approval) == 1
        assert approval[0].metadata.get("gate") == "sara.k@acme.com"

    def test_aggregated_pattern_is_law_candidate_relaxed(self):
        """An aggregated pattern from single-entity LOs must satisfy the relaxed
        law-candidate threshold so it gets returned by detect()."""
        los = _make_los(3, LearningObjectType.HIDDEN_EXPERT, ["priya.m@acme.com"])
        detector = PatternDetector()
        patterns = detector.detect(los)
        assert len(patterns) >= 1
        for p in patterns:
            assert p.is_law_candidate or p.is_law_candidate_relaxed, (
                "Patterns returned by detect() must satisfy at least the relaxed threshold"
            )

    def test_aggregated_pattern_collects_all_providers(self):
        """When LOs come from different providers, the aggregated pattern must
        include all of them — provenance is preserved across aggregation."""
        los = [
            _make_lo(
                LearningObjectType.HIDDEN_EXPERT,
                ["priya.m@acme.com"],
                providers={"github"},
            ),
            _make_lo(
                LearningObjectType.HIDDEN_EXPERT,
                ["priya.m@acme.com"],
                providers={"slack"},
            ),
            _make_lo(
                LearningObjectType.HIDDEN_EXPERT,
                ["priya.m@acme.com"],
                providers={"jira", "confluence"},
            ),
        ]
        detector = PatternDetector()
        patterns = detector.detect(los)
        influence = [p for p in patterns if p.type == PatternType.INFLUENCE]
        assert len(influence) == 1
        assert influence[0].providers == {"github", "slack", "jira", "confluence"}

    def test_evidence_count_uses_lo_evidence_not_lo_count(self):
        """If LOs have evidence_count > 1 each, the aggregated total_evidence
        stored in pattern.metadata must be the SUM of evidence_count values,
        not just the count of LOs.

        Note: The pattern's `evidence_count` PROPERTY is `len(learning_object_ids)`
        (the LO count), while `metadata.total_evidence` is the aggregated sum.
        This distinction is important — the property is used for law-candidate
        filtering, while the metadata is used for human-readable descriptions."""
        los = [
            _make_lo(LearningObjectType.HIDDEN_EXPERT, ["x@acme.com"], evidence_count=2),
            _make_lo(LearningObjectType.HIDDEN_EXPERT, ["x@acme.com"], evidence_count=2),
            _make_lo(LearningObjectType.HIDDEN_EXPERT, ["x@acme.com"], evidence_count=2),
        ]
        detector = PatternDetector()
        patterns = detector.detect(los)
        influence = [p for p in patterns if p.type == PatternType.INFLUENCE]
        assert len(influence) == 1
        # metadata.total_evidence is the SUM of LO evidence_count values
        assert influence[0].metadata.get("total_evidence") == 6
        # pattern.evidence_count is the COUNT of LOs (property on Pattern)
        assert influence[0].evidence_count == 3


def _make_los(
    n: int,
    lo_type: LearningObjectType,
    entities: list[str],
    metadata: dict | None = None,
    providers: set[str] | None = None,
) -> list[LearningObject]:
    return [
        _make_lo(lo_type, entities, metadata=metadata, providers=providers)
        for _ in range(n)
    ]


# ============================================================
# 3. EventBus.start() — no running event loop
# ============================================================


class TestEventBusStart:
    """Verify EventBus.start() handles the no-running-loop case gracefully.

    Background: Before commit 00a6314, EventBus.start() called
    asyncio.create_task() unconditionally. This raised RuntimeError
    ("no running event loop") when called from a synchronous context
    (e.g., a pytest fixture that is not async). The fix wraps the call in
    a try/except and falls back to creating a new event loop.

    A separate start_async() method was added for async fixtures, which
    uses the running loop directly without the fallback.
    """

    def test_start_does_not_raise_without_running_loop(self):
        """Calling start() from a synchronous context (no running loop) must
        not raise. It should create a new loop and start the dispatch task.

        Note: the fallback loop created here is not run, so the dispatch task
        is created but never scheduled. This is acceptable for the sync-context
        escape hatch — callers who actually need dispatch should use
        start_async() from within an async context.
        """
        from maestro_core.streaming import EventBus

        bus = EventBus()
        # No running event loop here (we are in a sync test function).
        try:
            bus.start()
        except RuntimeError as e:
            pytest.fail(f"EventBus.start() raised RuntimeError in sync context: {e}")
        finally:
            # Cleanup: close any loop the fallback created. We don't run it
            # because doing so would block; we just close it to release
            # resources. The dispatch coroutine warning is benign here.
            try:
                if bus._task is not None:
                    # Cancel the unstarted task to suppress warnings.
                    bus._task.cancel()
            except Exception:
                pass

    def test_start_async_safe_in_async_context(self):
        """start_async() must succeed when a loop is running (async test)."""
        from maestro_core.streaming import EventBus

        async def scenario():
            bus = EventBus()
            await bus.start_async()
            assert bus._task is not None
            assert not bus._task.done()
            await bus.stop()

        asyncio.run(scenario())

    def test_start_idempotent_when_already_running(self):
        """Calling start_async() twice must not create a second task."""
        from maestro_core.streaming import EventBus

        async def scenario():
            bus = EventBus()
            await bus.start_async()
            first_task = bus._task
            await bus.start_async()
            assert bus._task is first_task, "start_async() must not replace an active task"
            await bus.stop()

        asyncio.run(scenario())

    def test_start_restarts_after_completion(self):
        """If the dispatch task has completed, start_async() must restart it."""
        from maestro_core.streaming import EventBus

        async def scenario():
            bus = EventBus()
            await bus.start_async()
            first_task = bus._task
            # Stop the bus — this will let the dispatch task complete.
            await bus.stop()
            assert first_task.done()
            # Restart — should create a new task.
            bus._closed = False  # reset for restart
            await bus.start_async()
            assert bus._task is not None
            assert bus._task is not first_task
            await bus.stop()

        asyncio.run(scenario())


# ============================================================
# 4. RunStatus import — must be importable from maestro_core
# ============================================================


class TestRunStatusImport:
    """Verify RunStatus is importable from maestro_core (not just state).

    Background: Before commit 00a6314, maestro_core/__init__.py imported
    RunStatus from maestro_core.context, but RunStatus is actually defined
    in maestro_core.state. This caused ImportError in test_core_engine.py
    and test_loops.py. The fix: import RunStatus from maestro_core.state.
    """

    def test_run_status_importable_from_package(self):
        """`from maestro_core import RunStatus` must work."""
        from maestro_core import RunStatus
        assert RunStatus is not None

    def test_run_status_importable_from_state_module(self):
        """`from maestro_core.state import RunStatus` must work."""
        from maestro_core.state import RunStatus
        assert RunStatus is not None

    def test_run_status_is_same_object_both_imports(self):
        """Both import paths must return the same class object."""
        from maestro_core import RunStatus as PkgRunStatus
        from maestro_core.state import RunStatus as StateRunStatus
        assert PkgRunStatus is StateRunStatus

    def test_run_status_has_expected_members(self):
        """RunStatus must have the expected enum members used by the engine.

        Note: the engine uses 'succeeded' (not 'completed') for successful runs.
        This was a source of confusion in the original import bug — tests were
        checking for 'completed' which doesn't exist.
        """
        from maestro_core import RunStatus
        expected = {"pending", "running", "paused", "succeeded", "failed"}
        actual = {s.value for s in RunStatus}
        missing = expected - actual
        assert not missing, f"RunStatus is missing expected members: {missing}"

    def test_context_no_longer_exports_run_status(self):
        """maestro_core.context must NOT export RunStatus (it was a bug source).

        If someone adds it back, the import in __init__.py becomes ambiguous.
        """
        import maestro_core.context as ctx
        assert not hasattr(ctx, "RunStatus"), (
            "RunStatus must not be defined in maestro_core.context — "
            "it caused the original ImportError. Define it only in maestro_core.state."
        )
