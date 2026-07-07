"""
Maestro Cognitive Council — Gate 0: World Model Benchmark.

10 longitudinal organizational stories, 30-90 simulated days each.

This benchmark is the acceptance criterion for Gate 4 (Behavioral Learning).
It prevents the architecture from being optimized around Globex alone.

Each story defines:
  - events over time (signals arriving at specific days)
  - information available at each checkpoint
  - expected situation state at each checkpoint
  - expected unknowns
  - expected disputes
  - expected decision boundary
  - expected delivery behavior
  - expected preparation behavior
  - expected learning effect
  - forbidden future leakage

At each checkpoint, 12 questions are tested:
  1. What does Ask say?
  2. Does Prepare activate?
  3. Does Whisper stay silent?
  4. What does Briefing include?
  5. What is currently unknown?
  6. What changed?
  7. What is disputed?
  8. What can be decided?
  9. What cannot yet be decided?
  10. What does Maestro believe?
  11. Why?
  12. What would change that belief?

The 10 failure shapes tested:
  1. Customer commitment drift (Globex renewal)
  2. Security prerequisite failure (OAuth conditional approval)
  3. Pricing exception leakage (enterprise discount precedent)
  4. Hiring-plan assumption collapse (budget cut mid-quarter)
  5. Product launch scope mutation (feature creep)
  6. Duplicate work across teams (two teams building same API)
  7. Expert bottleneck emergence (single point of failure)
  8. Legal interpretation disagreement (contract ambiguity)
  9. Incident pattern that's coincidence (false pattern)
  10. Previously learned pattern becoming false after reorg (falsification)

Reference: docs/MAESTRO_COGNITIVE_COUNCIL_AUDIT_AND_WIRING_PLAN.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from uuid import uuid4


# ════════════════════════════════════════════════════════════════════════════
# Benchmark Data Structures
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class BenchmarkSignal:
    """A signal arriving at a specific day in the simulation."""
    day: int                          # day number in the simulation (0-indexed)
    signal_type: str                  # e.g., "customer.commitment_made"
    entity: str                       # the customer/org entity
    text: str                         # the signal content
    signal_id: str = ""               # unique ID (auto-generated if empty)

    def __post_init__(self):
        if not self.signal_id:
            self.signal_id = f"sig-{self.entity.lower()}-{self.day}-{uuid4().hex[:6]}"


@dataclass
class CheckpointExpectation:
    """Expected state at a specific checkpoint in the story.

    Each checkpoint tests the 12 questions. Fields are Optional because
    not every checkpoint tests every question — but the benchmark runner
    will check every non-None field.
    """
    day: int                                      # when this checkpoint occurs
    description: str                              # what's happening at this checkpoint

    # Expected states (the 4 dimensions from the audit)
    expected_epistemic_state: Optional[str] = None      # preliminary|supported|contested|insufficient|resolved
    expected_operational_state: Optional[str] = None   # observing|decision_pending|action_in_progress|awaiting_outcome|closed
    expected_delivery_state: Optional[str] = None      # silent|briefing_eligible|whisper_eligible|prepare_eligible|urgent
    expected_learning_state: Optional[str] = None      # none|hypothesis_created|prospectively_testing|outcome_pending|learning_updated|falsified

    # Expected unknowns
    expected_unknowns: list[str] = field(default_factory=list)
    expected_unknowns_resolved: list[str] = field(default_factory=list)

    # Expected disputes
    expected_disputes: int = 0                    # count of expected disputes

    # Expected decision boundary
    expected_can_decide: list[str] = field(default_factory=list)
    expected_cannot_decide: list[str] = field(default_factory=list)

    # Expected delivery behavior
    expected_prepare_activates: Optional[bool] = None
    expected_whisper_silent: Optional[bool] = None
    expected_briefing_includes: list[str] = field(default_factory=list)

    # Expected learning effect
    expected_learning_effect: Optional[str] = None     # none|hypothesis_created|belief_strengthened|belief_weakened|falsified

    # Forbidden future leakage — no signals from other entities should appear
    forbidden_entities: list[str] = field(default_factory=list)

    # What Maestro believes + why + what would change it
    expected_belief: Optional[str] = None
    expected_why: Optional[str] = None
    expected_what_would_change_belief: Optional[str] = None


@dataclass
class BenchmarkStory:
    """A complete longitudinal benchmark story.

    Contains:
      - story_id: unique identifier
      - title: human-readable name
      - failure_shape: which of the 10 failure shapes this tests
      - description: what the story is about
      - total_days: simulation length (30-90 days)
      - signals: chronological list of signals
      - checkpoints: expected states at specific days
      - forbidden_future_leakage: entities that must NOT appear in this story
    """
    story_id: str
    title: str
    failure_shape: str                          # one of the 10 failure shapes
    description: str
    total_days: int                             # 30-90
    signals: list[BenchmarkSignal] = field(default_factory=list)
    checkpoints: list[CheckpointExpectation] = field(default_factory=list)
    forbidden_future_leakage: list[str] = field(default_factory=list)
