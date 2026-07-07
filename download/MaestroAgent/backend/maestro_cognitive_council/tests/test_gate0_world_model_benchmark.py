"""Tests for the World Model Benchmark — Gate 0.

These tests verify that all 10 benchmark stories are well-formed:
  - Each story has a unique ID
  - Each story tests a unique failure shape
  - Each story has signals spanning 30-90 days
  - Each story has at least 2 checkpoints
  - Each story specifies forbidden future leakage
  - No story's signals contain entities from its forbidden list
  - The 12 checkpoint questions are testable (at least some expectations set)

This benchmark is the acceptance criterion for Gate 4. It must be built
BEFORE Gate 4 code to prevent Globex overfitting.
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Benchmark Integrity Tests
# ════════════════════════════════════════════════════════════════════════════

class TestBenchmarkIntegrity:
    """All 10 benchmark stories must be well-formed."""

    def test_exactly_10_stories(self):
        """The benchmark has exactly 10 stories (one per failure shape)."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        assert len(ALL_STORIES) == 10, f"Expected 10 stories, got {len(ALL_STORIES)}"

    def test_all_story_ids_unique(self):
        """Every story has a unique ID."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        ids = [s.story_id for s in ALL_STORIES]
        assert len(ids) == len(set(ids)), f"Duplicate story IDs: {ids}"

    def test_all_failure_shapes_unique(self):
        """Every story tests a unique failure shape."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        shapes = [s.failure_shape for s in ALL_STORIES]
        assert len(shapes) == len(set(shapes)), f"Duplicate failure shapes: {shapes}"

    def test_all_stories_span_30_to_90_days(self):
        """Every story spans 30-90 simulated days."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        for story in ALL_STORIES:
            assert 30 <= story.total_days <= 90, (
                f"{story.story_id} spans {story.total_days} days — must be 30-90"
            )

    def test_all_stories_have_at_least_2_checkpoints(self):
        """Every story has at least 2 checkpoints."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        for story in ALL_STORIES:
            assert len(story.checkpoints) >= 2, (
                f"{story.story_id} has {len(story.checkpoints)} checkpoints — need ≥2"
            )

    def test_all_stories_specify_forbidden_leakage(self):
        """Every story specifies forbidden future leakage entities."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        for story in ALL_STORIES:
            assert len(story.forbidden_future_leakage) > 0, (
                f"{story.story_id} must specify forbidden future leakage entities"
            )

    def test_no_story_signals_contain_forbidden_entities(self):
        """No story's signals contain entities from its forbidden list."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        for story in ALL_STORIES:
            forbidden_lower = [e.lower() for e in story.forbidden_future_leakage]
            for signal in story.signals:
                entity_lower = signal.entity.lower()
                assert entity_lower not in forbidden_lower, (
                    f"{story.story_id}: signal entity '{signal.entity}' is in "
                    f"forbidden_future_leakage — this is self-contradictory"
                )


# ════════════════════════════════════════════════════════════════════════════
# The 10 Failure Shapes — Each Tested
# ════════════════════════════════════════════════════════════════════════════

class TestAll10FailureShapes:
    """Each of the 10 failure shapes is tested by at least one story."""

    def test_commitment_drift(self):
        """Failure shape 1: customer commitment drift."""
        from maestro_cognitive_council.world_model_benchmark import get_stories_by_failure_shape
        stories = get_stories_by_failure_shape("commitment_drift")
        assert len(stories) >= 1
        assert "drift" in stories[0].title.lower() or "renewal" in stories[0].title.lower()

    def test_security_prerequisite_failure(self):
        """Failure shape 2: security prerequisite failure."""
        from maestro_cognitive_council.world_model_benchmark import get_stories_by_failure_shape
        stories = get_stories_by_failure_shape("security_prerequisite_failure")
        assert len(stories) >= 1

    def test_pricing_exception_leakage(self):
        """Failure shape 3: pricing exception leakage."""
        from maestro_cognitive_council.world_model_benchmark import get_stories_by_failure_shape
        stories = get_stories_by_failure_shape("pricing_exception_leakage")
        assert len(stories) >= 1

    def test_assumption_collapse(self):
        """Failure shape 4: hiring-plan assumption collapse."""
        from maestro_cognitive_council.world_model_benchmark import get_stories_by_failure_shape
        stories = get_stories_by_failure_shape("assumption_collapse")
        assert len(stories) >= 1

    def test_scope_mutation(self):
        """Failure shape 5: product launch scope mutation."""
        from maestro_cognitive_council.world_model_benchmark import get_stories_by_failure_shape
        stories = get_stories_by_failure_shape("scope_mutation")
        assert len(stories) >= 1

    def test_duplicate_work(self):
        """Failure shape 6: duplicate work across teams."""
        from maestro_cognitive_council.world_model_benchmark import get_stories_by_failure_shape
        stories = get_stories_by_failure_shape("duplicate_work")
        assert len(stories) >= 1

    def test_expert_bottleneck(self):
        """Failure shape 7: expert bottleneck emergence."""
        from maestro_cognitive_council.world_model_benchmark import get_stories_by_failure_shape
        stories = get_stories_by_failure_shape("expert_bottleneck")
        assert len(stories) >= 1

    def test_legal_disagreement(self):
        """Failure shape 8: legal interpretation disagreement."""
        from maestro_cognitive_council.world_model_benchmark import get_stories_by_failure_shape
        stories = get_stories_by_failure_shape("legal_disagreement")
        assert len(stories) >= 1

    def test_coincidental_pattern(self):
        """Failure shape 9: incident pattern that's coincidence."""
        from maestro_cognitive_council.world_model_benchmark import get_stories_by_failure_shape
        stories = get_stories_by_failure_shape("coincidental_pattern")
        assert len(stories) >= 1

    def test_reorg_falsification(self):
        """Failure shape 10: previously learned pattern becoming false after reorg."""
        from maestro_cognitive_council.world_model_benchmark import get_stories_by_failure_shape
        stories = get_stories_by_failure_shape("reorg_falsification")
        assert len(stories) >= 1


# ════════════════════════════════════════════════════════════════════════════
# Checkpoint Question Coverage
# ════════════════════════════════════════════════════════════════════════════

class TestCheckpointQuestionCoverage:
    """The 12 checkpoint questions are testable across the benchmark.

    Not every checkpoint tests every question, but across all 10 stories,
    every question must be testable at least once.
    """

    def test_epistemic_state_testable(self):
        """At least one checkpoint tests expected_epistemic_state."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        count = sum(
            1 for story in ALL_STORIES
            for cp in story.checkpoints
            if cp.expected_epistemic_state is not None
        )
        assert count >= 5, f"Only {count} checkpoints test epistemic_state — need ≥5"

    def test_operational_state_testable(self):
        """At least one checkpoint tests expected_operational_state."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        count = sum(
            1 for story in ALL_STORIES
            for cp in story.checkpoints
            if cp.expected_operational_state is not None
        )
        assert count >= 3, f"Only {count} checkpoints test operational_state — need ≥3"

    def test_delivery_state_testable(self):
        """At least one checkpoint tests expected_delivery_state."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        count = sum(
            1 for story in ALL_STORIES
            for cp in story.checkpoints
            if cp.expected_delivery_state is not None
        )
        assert count >= 2, f"Only {count} checkpoints test delivery_state — need ≥2"

    def test_learning_state_testable(self):
        """At least one checkpoint tests expected_learning_state."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        count = sum(
            1 for story in ALL_STORIES
            for cp in story.checkpoints
            if cp.expected_learning_state is not None
        )
        assert count >= 3, f"Only {count} checkpoints test learning_state — need ≥3"

    def test_unknowns_testable(self):
        """At least one checkpoint tests expected_unknowns."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        count = sum(
            1 for story in ALL_STORIES
            for cp in story.checkpoints
            if len(cp.expected_unknowns) > 0
        )
        assert count >= 3, f"Only {count} checkpoints test unknowns — need ≥3"

    def test_disputes_testable(self):
        """At least one checkpoint tests expected_disputes."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        count = sum(
            1 for story in ALL_STORIES
            for cp in story.checkpoints
            if cp.expected_disputes > 0
        )
        assert count >= 2, f"Only {count} checkpoints test disputes — need ≥2"

    def test_decision_boundary_testable(self):
        """At least one checkpoint tests expected_can_decide or expected_cannot_decide."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        count = sum(
            1 for story in ALL_STORIES
            for cp in story.checkpoints
            if len(cp.expected_can_decide) > 0 or len(cp.expected_cannot_decide) > 0
        )
        assert count >= 3, f"Only {count} checkpoints test decision boundary — need ≥3"

    def test_prepare_activates_testable(self):
        """At least one checkpoint tests expected_prepare_activates."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        count = sum(
            1 for story in ALL_STORIES
            for cp in story.checkpoints
            if cp.expected_prepare_activates is not None
        )
        assert count >= 2, f"Only {count} checkpoints test prepare_activates — need ≥2"

    def test_whisper_silent_testable(self):
        """At least one checkpoint tests expected_whisper_silent."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        count = sum(
            1 for story in ALL_STORIES
            for cp in story.checkpoints
            if cp.expected_whisper_silent is not None
        )
        assert count >= 1, f"Only {count} checkpoints test whisper_silent — need ≥1"

    def test_learning_effect_testable(self):
        """At least one checkpoint tests expected_learning_effect."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        count = sum(
            1 for story in ALL_STORIES
            for cp in story.checkpoints
            if cp.expected_learning_effect is not None
        )
        assert count >= 3, f"Only {count} checkpoints test learning_effect — need ≥3"

    def test_belief_testable(self):
        """At least one checkpoint tests expected_belief."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        count = sum(
            1 for story in ALL_STORIES
            for cp in story.checkpoints
            if cp.expected_belief is not None
        )
        assert count >= 3, f"Only {count} checkpoints test belief — need ≥3"

    def test_forbidden_leakage_testable(self):
        """Every story tests forbidden future leakage."""
        from maestro_cognitive_council.world_model_benchmark import ALL_STORIES
        for story in ALL_STORIES:
            assert len(story.forbidden_future_leakage) > 0


# ════════════════════════════════════════════════════════════════════════════
# Specific Story Sanity Checks
# ════════════════════════════════════════════════════════════════════════════

class TestStory1GlobexDrift:
    """Story 1: Customer commitment drift (Globex renewal)."""

    def test_story_1_exists(self):
        from maestro_cognitive_council.world_model_benchmark import get_story
        story = get_story("story-01-globex-drift")
        assert story is not None
        assert story.failure_shape == "commitment_drift"

    def test_story_1_has_5_signals(self):
        """Globex drift has 5 signals (Day 12, 40, 50, 55, 59)."""
        from maestro_cognitive_council.world_model_benchmark import get_story
        story = get_story("story-01-globex-drift")
        assert len(story.signals) == 5

    def test_story_1_signals_are_chronological(self):
        """Signals are in chronological order."""
        from maestro_cognitive_council.world_model_benchmark import get_story
        story = get_story("story-01-globex-drift")
        days = [s.day for s in story.signals]
        assert days == sorted(days)

    def test_story_1_has_5_checkpoints(self):
        """Globex drift has 5 checkpoints (Day 12, 40, 50, 55, 59)."""
        from maestro_cognitive_council.world_model_benchmark import get_story
        story = get_story("story-01-globex-drift")
        assert len(story.checkpoints) == 5

    def test_story_1_forbids_initech_and_hooli(self):
        """Globex story must not leak Initech or Hooli entities."""
        from maestro_cognitive_council.world_model_benchmark import get_story
        story = get_story("story-01-globex-drift")
        assert "Initech" in story.forbidden_future_leakage
        assert "Hooli" in story.forbidden_future_leakage


class TestStory9CoincidentalPattern:
    """Story 9: Incident pattern that's coincidence (false pattern)."""

    def test_story_9_tests_falsification(self):
        """Story 9 must test belief weakening and falsification."""
        from maestro_cognitive_council.world_model_benchmark import get_story
        story = get_story("story-09-coincidental-pattern")
        # Should have checkpoints testing belief_weakened and falsified
        effects = [cp.expected_learning_effect for cp in story.checkpoints]
        assert "belief_weakened" in effects
        assert "falsified" in effects

    def test_story_9_has_3_friday_incidents_then_3_clean_fridays(self):
        """3 Friday incidents, then 3 Fridays without incidents."""
        from maestro_cognitive_council.world_model_benchmark import get_story
        story = get_story("story-09-coincidental-pattern")
        incident_signals = [s for s in story.signals if "incident.friday" in s.signal_type]
        clean_signals = [s for s in story.signals if "incident.none" in s.signal_type]
        assert len(incident_signals) == 3
        assert len(clean_signals) == 3


class TestStory10ReorgFalsification:
    """Story 10: Previously learned pattern becoming false after reorg."""

    def test_story_10_tests_learning_then_falsification(self):
        """Story 10 must test learning_updated then falsified."""
        from maestro_cognitive_council.world_model_benchmark import get_story
        story = get_story("story-10-reorg-falsification")
        learning_states = [cp.expected_learning_state for cp in story.checkpoints]
        assert "learning_updated" in learning_states
        assert "falsified" in learning_states

    def test_story_10_has_reorg_signal(self):
        """Story 10 must have an org.reorganization signal."""
        from maestro_cognitive_council.world_model_benchmark import get_story
        story = get_story("story-10-reorg-falsification")
        reorg_signals = [s for s in story.signals if "reorganization" in s.signal_type]
        assert len(reorg_signals) >= 1

    def test_story_10_spans_90_days(self):
        """Story 10 spans the full 90 days (longest longitudinal test)."""
        from maestro_cognitive_council.world_model_benchmark import get_story
        story = get_story("story-10-reorg-falsification")
        assert story.total_days == 90
