"""
Maestro Cognitive Council — Phase 1: Situation Engine (Gate 1 refactor).

GATE 1 REFACTOR (per CEO directive + audit wiring plan):
  1. Thin references — LivingSituation holds _refs[] to OEM objects, NOT copies
  2. Continuous state transition — 10 primary + 5 side states with transition logic
  3. Wired to existing precursors — CommitmentMutationTracker, CrossMeetingThreadBuilder,
     SituationBuilder

DESIGN RULE (CEO): "Situation organizes cognition. It does not duplicate
organizational memory. The OEM remains the source of record. Situation is
a dynamically maintained cognitive frame over OEM memory."

STATE MACHINE (CEO-specified):
  Primary: DETECTED → OBSERVING → MATERIAL → NEEDS_PREPARATION →
           DECISION_PENDING → ACTION_IN_PROGRESS → AWAITING_OUTCOME →
           RESOLVED → LEARNING → ARCHIVED

  Side (orthogonal): DISPUTED, BLOCKED, STALE, SUPERSEDED, INSUFFICIENT_EVIDENCE

ACCEPTANCE CRITERION: "new signal → correct situation found → delta computed →
state transition justified → unknowns updated → no future leakage"

Reference: docs/MAESTRO_COGNITIVE_COUNCIL_AUDIT_AND_WIRING_PLAN.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Enums — 10 primary states + 5 side states (CEO-specified)
# ════════════════════════════════════════════════════════════════════════════

class SituationState(str, Enum):
    """The 10 primary lifecycle states of a LivingSituation.

    A situation progresses through these states as organizational reality
    evolves. Each transition must be JUSTIFIED (reason + evidence).
    """
    DETECTED = "detected"                        # just noticed, not yet observing
    OBSERVING = "observing"                      # monitoring, no intervention needed
    MATERIAL = "material"                        # new prerequisite/threat affects commitment
    NEEDS_PREPARATION = "needs_preparation"      # external expectation may differ from internal state
    DECISION_PENDING = "decision_pending"        # a decision/event is imminent
    ACTION_IN_PROGRESS = "action_in_progress"    # a meeting/action is happening
    AWAITING_OUTCOME = "awaiting_outcome"        # action complete, outcome unknown
    RESOLVED = "resolved"                        # the situation concluded
    LEARNING = "learning"                        # feeding outcome to the learning loop
    ARCHIVED = "archived"                        # learning complete, situation is history


class SideState(str, Enum):
    """5 orthogonal side states that can coexist with any primary state.

    These represent conditions that affect the situation regardless of
    its primary lifecycle position.
    """
    DISPUTED = "disputed"                          # credible evidence conflicts
    BLOCKED = "blocked"                            # a decision cannot proceed due to missing info
    STALE = "stale"                                # no signals for 30+ days
    SUPERSEDED = "superseded"                      # a newer situation replaces this one
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # not enough evidence to form a judgment


class EpistemicState(str, Enum):
    """What the organization knows about this situation's central claim."""
    KNOWN = "known"
    REPORTED = "reported"
    BELIEVED = "believed"
    ASSUMED = "assumed"
    HYPOTHESIZED = "hypothesized"
    PREDICTED = "predicted"
    DISPUTED = "disputed"
    UNKNOWN = "unknown"
    FALSIFIED = "falsified"
    LEARNED = "learned"


class DeliveryRoute(str, Enum):
    """How (or whether) this situation should be surfaced to the user."""
    SILENT = "silent"
    ASK = "ask"
    BRIEFING = "briefing"
    WHISPER = "whisper"
    PREPARE = "prepare"
    URGENT = "urgent"


class LearningState(str, Enum):
    """The learning state of the situation's central hypothesis."""
    UNTESTED = "untested"                # no prospective predictions yet
    OBSERVING_EVIDENCE = "observing_evidence"  # predictions registered, awaiting outcomes
    SUPPORTED = "supported"              # outcomes support the hypothesis
    CONTESTED = "contested"              # some outcomes contradict
    FALSIFIED = "falsified"             # enough contradictions to falsify


class EvidenceState(str, Enum):
    """Evidence states replacing confidence adjectives (CEO directive).

    "Moderate confidence" tells the executive almost nothing.
    "Supported by the commitment record and customer statement, but the
    security approval status is missing" is useful.

    Externally: explain WHY certainty is limited.
    Internally: retain calibrated values where legitimate.
    """
    DIRECTLY_SUPPORTED = "directly_supported"        # evidence directly backs the claim
    SUPPORTED_WITH_GAPS = "supported_with_gaps"      # evidence backs it but key facts missing
    CONTESTED = "contested"                          # credible evidence conflicts
    PRELIMINARY = "preliminary"                      # early-stage, could change
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # not enough evidence to say


# ════════════════════════════════════════════════════════════════════════════
# Gate 0: 4-Dimensional State Model (per CEO audit directive)
# ════════════════════════════════════════════════════════════════════════════
# The single SituationState enum mixes epistemic maturity, operational
# lifecycle, delivery eligibility, and learning status. This creates
# impossible state combinations when learning closes (can a situation be
# RESOLVED and LEARNING simultaneously? The single enum says no, but
# conceptually yes).
#
# The 4 orthogonal dimensions:
#   epistemic_state:   what do we know? (evidence-backed)
#   operational_state: what's happening operationally? (lifecycle)
#   delivery_state:    how should we surface this? (delivery eligibility)
#   learning_state:    what's the learning status? (hypothesis testing)
#
# Globex can simultaneously be:
#   epistemic_state = contested
#   operational_state = decision_pending
#   delivery_state = prepare_eligible
#   learning_state = hypothesis_created


class EpistemicDimensionState(str, Enum):
    """Dimension 1: What do we know? (evidence-backed)"""
    PRELIMINARY = "preliminary"          # early-stage, could change
    SUPPORTED = "supported"              # evidence backs the claim
    CONTESTED = "contested"              # credible evidence conflicts
    INSUFFICIENT = "insufficient"        # not enough evidence to say
    RESOLVED = "resolved"                # epistemically settled (outcome observed)


class OperationalDimensionState(str, Enum):
    """Dimension 2: What's happening operationally? (lifecycle)"""
    OBSERVING = "observing"                    # monitoring, no action yet
    DECISION_PENDING = "decision_pending"      # a decision is imminent
    ACTION_IN_PROGRESS = "action_in_progress"  # a meeting/action is happening
    AWAITING_OUTCOME = "awaiting_outcome"      # action complete, outcome unknown
    CLOSED = "closed"                          # situation is operationally closed


class DeliveryDimensionState(str, Enum):
    """Dimension 3: How should we surface this? (delivery eligibility)"""
    SILENT = "silent"                      # no intervention justified
    BRIEFING_ELIGIBLE = "briefing_eligible"  # include in briefing
    WHISPER_ELIGIBLE = "whisper_eligible"    # proactive push during active context
    PREPARE_ELIGIBLE = "prepare_eligible"    # surface preparation workspace
    URGENT = "urgent"                      # immediate escalation


class LearningDimensionState(str, Enum):
    """Dimension 4: What's the learning status? (hypothesis testing)"""
    NONE = "none"                              # no hypothesis yet
    HYPOTHESIS_CREATED = "hypothesis_created"  # a hypothesis has been proposed
    PROSPECTIVELY_TESTING = "prospectively_testing"  # predictions registered
    OUTCOME_PENDING = "outcome_pending"        # awaiting outcome evidence
    LEARNING_UPDATED = "learning_updated"      # outcome fed the learning loop
    FALSIFIED = "falsified"                    # enough contradictions to falsify


# ════════════════════════════════════════════════════════════════════════════
# State Transition — every transition is justified + logged
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class StateTransition:
    """A single state transition with justification.

    Every transition must have:
      - from_state and to_state
      - timestamp
      - reason (WHY the transition happened — not just WHAT)
      - triggering_evidence_ref (which signal/evidence caused it)
      - side_state_changes (any side states added/removed)
    """
    from_state: SituationState
    to_state: SituationState
    timestamp: datetime
    reason: str                                 # why this transition happened
    triggering_evidence_ref: Optional[str] = None  # which evidence caused it
    side_states_added: list[SideState] = field(default_factory=list)
    side_states_removed: list[SideState] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "reason": self.reason,
            "triggering_evidence_ref": self.triggering_evidence_ref,
            "side_states_added": [s.value for s in self.side_states_added],
            "side_states_removed": [s.value for s in self.side_states_removed],
        }


# ════════════════════════════════════════════════════════════════════════════
# Situation Delta — what changed when a new signal arrived
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class SituationDelta:
    """The computed delta when a new signal arrives.

    This is the output of SituationEngine.apply_signal(). It captures
    everything that changed — NOT just the state transition, but also
    new unknowns, new evidence refs, and whether a transition occurred.
    """
    situation_id: str
    signal_ref: str                             # the signal that caused this delta
    transition: Optional[StateTransition] = None  # None if no state change
    new_evidence_refs: list[str] = field(default_factory=list)
    new_unknowns: list[str] = field(default_factory=list)  # questions added
    resolved_unknowns: list[str] = field(default_factory=list)  # questions answered
    new_side_states: list[SideState] = field(default_factory=list)
    material_change_description: str = ""       # human-readable summary of what changed

    def to_dict(self) -> dict:
        return {
            "situation_id": self.situation_id,
            "signal_ref": self.signal_ref,
            "transition": self.transition.to_dict() if self.transition else None,
            "new_evidence_refs": self.new_evidence_refs,
            "new_unknowns": self.new_unknowns,
            "resolved_unknowns": self.resolved_unknowns,
            "new_side_states": [s.value for s in self.new_side_states],
            "material_change_description": self.material_change_description,
        }

    @property
    def has_transition(self) -> bool:
        return self.transition is not None


# ════════════════════════════════════════════════════════════════════════════
# Timeline Event / Known Fact / Unknown / Disagreement / Judgment
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class TimelineEvent:
    """A single event on a situation's timeline.

    This is a PROJECTION (derived from OEM signals), not a copy. The
    evidence_ref points back to the OEM source of record.
    """
    timestamp: datetime
    description: str
    event_type: str = "observed"  # observed | reported | committed | decided | outcome
    evidence_ref: Optional[str] = None  # reference to OEM evidence (NOT a copy)
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "description": self.description,
            "event_type": self.event_type,
            "evidence_ref": self.evidence_ref,
            "source": self.source,
        }


@dataclass
class KnownFact:
    """A fact about the situation, backed by evidence (reference, not copy)."""
    statement: str
    evidence_refs: list[str] = field(default_factory=list)  # refs to OEM evidence
    epistemic_state: EpistemicState = EpistemicState.KNOWN
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "statement": self.statement,
            "evidence_refs": self.evidence_refs,
            "epistemic_state": self.epistemic_state.value,
            "source": self.source,
        }


@dataclass
class Unknown:
    """An important piece of information that is missing."""
    question: str
    why_it_matters: str
    blocking: bool = False
    specialists_flagged: list[str] = field(default_factory=list)
    resolved: bool = False  # set True when the unknown is answered
    resolved_by_evidence_ref: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "why_it_matters": self.why_it_matters,
            "blocking": self.blocking,
            "specialists_flagged": self.specialists_flagged,
            "resolved": self.resolved,
            "resolved_by_evidence_ref": self.resolved_by_evidence_ref,
        }


@dataclass
class Disagreement:
    """A preserved disagreement between specialists."""
    topic: str
    position_a: str
    position_b: str
    specialist_a: str = ""
    specialist_b: str = ""
    resolution: Optional[str] = None
    unresolved: bool = True

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "position_a": self.position_a,
            "position_b": self.position_b,
            "specialist_a": self.specialist_a,
            "specialist_b": self.specialist_b,
            "resolution": self.resolution,
            "unresolved": self.unresolved,
        }


@dataclass
class DecisionBoundary:
    """What can reasonably be decided now, and what cannot?

    This is genuine executive intelligence. Most systems produce "here are
    the facts." Some produce "here is my recommendation." Better: "Here is
    what reality currently permits you to decide."

    Example:
      Can decide now: Adopt OAuth standardization as architectural direction.
      Cannot decide yet: Migration sequence for enterprise-facing services.
      Why: Legacy compatibility obligations are unresolved.
      Smallest useful next step: Review contractual SSO obligations for
        three affected accounts.
    """
    can_decide_now: list[str] = field(default_factory=list)
    cannot_decide_yet: list[str] = field(default_factory=list)
    why: str = ""
    smallest_useful_next_step: str = ""

    def to_dict(self) -> dict:
        return {
            "can_decide_now": self.can_decide_now,
            "cannot_decide_yet": self.cannot_decide_yet,
            "why": self.why,
            "smallest_useful_next_step": self.smallest_useful_next_step,
        }


@dataclass
class Judgment:
    """The synthesized of all perspectives on a situation."""
    central_claim: str = ""
    strongest_reason_to_act: str = ""
    strongest_reason_not_to_act: str = ""
    unknowns_blocking_decision: list[str] = field(default_factory=list)
    recommended_next_step: str = ""
    confidence: float = 0.0
    evidence_refs: list[str] = field(default_factory=list)
    # Gate 2 additions:
    evidence_state: EvidenceState = EvidenceState.INSUFFICIENT_EVIDENCE
    decision_boundary: Optional[DecisionBoundary] = None

    def to_dict(self) -> dict:
        return {
            "central_claim": self.central_claim,
            "strongest_reason_to_act": self.strongest_reason_to_act,
            "strongest_reason_not_to_act": self.strongest_reason_not_to_act,
            "unknowns_blocking_decision": self.unknowns_blocking_decision,
            "recommended_next_step": self.recommended_next_step,
            "confidence": round(self.confidence, 3),
            "evidence_refs": self.evidence_refs,
            "evidence_state": self.evidence_state.value,
            "decision_boundary": self.decision_boundary.to_dict() if self.decision_boundary else None,
        }


# ════════════════════════════════════════════════════════════════════════════
# Dimension Transition — enriched transition receipt (per CEO audit directive)
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class DimensionTransition:
    """A transition receipt for a single state dimension.

    Per the CEO audit directive: "Every transition should produce a
    first-class transition receipt" with:
      - dimension (which of the 4 dimensions changed)
      - previous_state + new_state
      - triggering_event_refs
      - rule_id (which transition rule fired)
      - reason
      - unknowns_added + unknowns_resolved
      - decision_boundary_changed
      - delivery_effect

    This lets the user ask "Why did Maestro prepare me today but not
    three days ago?" and get a mechanical answer.
    """
    dimension: str                    # "epistemic" | "operational" | "delivery" | "learning"
    previous_state: str
    new_state: str
    timestamp: datetime
    reason: str
    triggering_event_refs: list[str] = field(default_factory=list)
    rule_id: str = ""                 # which transition rule fired
    unknowns_added: list[str] = field(default_factory=list)
    unknowns_resolved: list[str] = field(default_factory=list)
    decision_boundary_changed: bool = False
    delivery_effect: str = ""         # what changed in delivery eligibility

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "reason": self.reason,
            "triggering_event_refs": self.triggering_event_refs,
            "rule_id": self.rule_id,
            "unknowns_added": self.unknowns_added,
            "unknowns_resolved": self.unknowns_resolved,
            "decision_boundary_changed": self.decision_boundary_changed,
            "delivery_effect": self.delivery_effect,
        }


# ════════════════════════════════════════════════════════════════════════════
# LivingSituation — THIN cognitive frame (references, not copies)
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class LivingSituation:
    """A thin cognitive frame over OEM memory.

    DESIGN RULE (CEO): "Situation organizes cognition. It does not
    duplicate organizational memory." This object holds REFERENCES to
    OEM objects (evidence, commitments, decisions, meetings), not copies.
    The OEM remains the source of record.

    Situation-specific cognition (unknowns, interpretations, material_changes)
    lives HERE — it's not in OEM because it's a frame, not a fact.

    A LivingSituation can appear differently depending on context:
      - Before a meeting: "one unresolved issue worth preparing for"
      - During a meeting: "your internal record lacks confirmation..."
      - When asked: reconstructs the full history
      - After the meeting: "the expectation conflict is resolved"
      - Months later: "similar drift appearing in another renewal"
    """
    # Identity
    situation_id: str
    title: str
    entity: str
    org_id: str = "default"

    # Lifecycle — 10 primary states + 5 side states + transition history
    # (Legacy single-dimension state — retained for backward compatibility.
    # The 4-dimensional fields below are the new primary state representation.)
    state: SituationState = SituationState.DETECTED
    side_states: set[SideState] = field(default_factory=set)
    state_history: list[StateTransition] = field(default_factory=list)
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None

    # GATE 0: 4-Dimensional State Model (per CEO audit directive)
    # These 4 orthogonal dimensions replace the single `state` enum as the
    # primary state representation. The legacy `state` field is retained
    # for backward compatibility and is derived from these dimensions.
    epistemic_dimension: EpistemicDimensionState = EpistemicDimensionState.INSUFFICIENT
    operational_dimension: OperationalDimensionState = OperationalDimensionState.OBSERVING
    delivery_dimension: DeliveryDimensionState = DeliveryDimensionState.SILENT
    learning_dimension: LearningDimensionState = LearningDimensionState.NONE
    # Transition receipts for each dimension (enriched per audit directive)
    dimension_transitions: list["DimensionTransition"] = field(default_factory=list)

    # REFERENCES to OEM (NOT copies) — the CEO's rule #1
    entity_refs: list[str] = field(default_factory=list)
    intent_refs: list[str] = field(default_factory=list)
    commitment_refs: list[str] = field(default_factory=list)
    decision_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    hypothesis_refs: list[str] = field(default_factory=list)
    meeting_refs: list[str] = field(default_factory=list)
    relationship_refs: list[str] = field(default_factory=list)

    # Situation-specific cognition (NOT in OEM — only in Situation)
    timeline: list[TimelineEvent] = field(default_factory=list)
    known_facts: list[KnownFact] = field(default_factory=list)
    unknowns: list[Unknown] = field(default_factory=list)
    material_changes: list[str] = field(default_factory=list)

    # Epistemic + learning state
    epistemic_state: EpistemicState = EpistemicState.UNKNOWN
    learning_state: LearningState = LearningState.UNTESTED

    # Perspectives + Judgment (transient — recomputed per query)
    perspectives: list[dict] = field(default_factory=list)
    disagreements: list[Disagreement] = field(default_factory=list)
    judgment: Optional[Judgment] = None

    # Delivery
    recommended_delivery: DeliveryRoute = DeliveryRoute.SILENT
    relevant_specialists: list[str] = field(default_factory=list)

    # Metadata
    snapshot_version: int = 1

    def to_dict(self) -> dict:
        return {
            "situation_id": self.situation_id,
            "title": self.title,
            "entity": self.entity,
            "org_id": self.org_id,
            "state": self.state.value,
            "side_states": [s.value for s in self.side_states],
            "state_history": [t.to_dict() for t in self.state_history],
            "opened_at": self.opened_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            # GATE 0: 4-Dimensional State Model
            "epistemic_dimension": self.epistemic_dimension.value,
            "operational_dimension": self.operational_dimension.value,
            "delivery_dimension": self.delivery_dimension.value,
            "learning_dimension": self.learning_dimension.value,
            "dimension_transitions": [t.to_dict() for t in self.dimension_transitions],
            # References (NOT copies)
            "entity_refs": self.entity_refs,
            "intent_refs": self.intent_refs,
            "commitment_refs": self.commitment_refs,
            "decision_refs": self.decision_refs,
            "evidence_refs": self.evidence_refs,
            "hypothesis_refs": self.hypothesis_refs,
            "meeting_refs": self.meeting_refs,
            "relationship_refs": self.relationship_refs,
            # Situation-specific cognition
            "timeline": [e.to_dict() for e in self.timeline],
            "known_facts": [f.to_dict() for f in self.known_facts],
            "unknowns": [u.to_dict() for u in self.unknowns],
            "material_changes": self.material_changes,
            "epistemic_state": self.epistemic_state.value,
            "learning_state": self.learning_state.value,
            # Transient
            "perspectives": self.perspectives,
            "disagreements": [d.to_dict() for d in self.disagreements],
            "judgment": self.judgment.to_dict() if self.judgment else None,
            "recommended_delivery": self.recommended_delivery.value,
            "relevant_specialists": self.relevant_specialists,
            "snapshot_version": self.snapshot_version,
        }

    # ── Mutation helpers ────────────────────────────────────────────────────

    def add_timeline_event(self, event: TimelineEvent) -> None:
        """Add an event to the timeline and re-sort chronologically."""
        self.timeline.append(event)
        self.timeline.sort(key=lambda e: e.timestamp if isinstance(e.timestamp, datetime) else datetime.min)
        self.updated_at = datetime.now(timezone.utc)

    def add_known_fact(self, fact: KnownFact) -> None:
        """Add a known fact (deduplicated by statement)."""
        if not any(f.statement == fact.statement for f in self.known_facts):
            self.known_facts.append(fact)
            self.updated_at = datetime.now(timezone.utc)

    def add_unknown(self, unknown: Unknown) -> None:
        """Add an unknown (deduplicated by question)."""
        if not any(u.question == unknown.question for u in self.unknowns):
            self.unknowns.append(unknown)
            self.updated_at = datetime.now(timezone.utc)

    def resolve_unknown(self, question: str, evidence_ref: str) -> bool:
        """Mark an unknown as resolved by new evidence.

        Returns True if the unknown was found and resolved.
        """
        for u in self.unknowns:
            if u.question == question and not u.resolved:
                u.resolved = True
                u.resolved_by_evidence_ref = evidence_ref
                self.updated_at = datetime.now(timezone.utc)
                return True
        return False

    def add_disagreement(self, disagreement: Disagreement) -> None:
        """Add a disagreement (preserved, not converged away)."""
        self.disagreements.append(disagreement)
        self.updated_at = datetime.now(timezone.utc)

    def add_side_state(self, side: SideState) -> None:
        """Add a side state (orthogonal to the primary state)."""
        self.side_states.add(side)
        self.updated_at = datetime.now(timezone.utc)

    def remove_side_state(self, side: SideState) -> None:
        """Remove a side state."""
        self.side_states.discard(side)
        self.updated_at = datetime.now(timezone.utc)

    def has_side_state(self, side: SideState) -> bool:
        return side in self.side_states

    def has_blocking_unknown(self) -> bool:
        """Does this situation have any UNRESOLVED blocking unknown?"""
        return any(u.blocking and not u.resolved for u in self.unknowns)

    def has_unresolved_unknowns(self) -> bool:
        """Does this situation have any unresolved unknown?"""
        return any(not u.resolved for u in self.unknowns)

    def transition_to(
        self,
        new_state: SituationState,
        reason: str,
        triggering_evidence_ref: Optional[str] = None,
        side_states_added: Optional[list[SideState]] = None,
        side_states_removed: Optional[list[SideState]] = None,
    ) -> StateTransition:
        """Transition to a new state with JUSTIFICATION.

        Every transition is logged in state_history with the reason and
        triggering evidence. This is the CEO's "continuous state transition"
        requirement — transitions are not manual, they're justified.

        Returns the StateTransition that was logged.
        """
        old_state = self.state
        side_added = side_states_added or []
        side_removed = side_states_removed or []

        # Log the transition
        transition = StateTransition(
            from_state=old_state,
            to_state=new_state,
            timestamp=datetime.now(timezone.utc),
            reason=reason,
            triggering_evidence_ref=triggering_evidence_ref,
            side_states_added=side_added,
            side_states_removed=side_removed,
        )

        # Apply the transition
        self.state = new_state
        self.state_history.append(transition)
        for s in side_added:
            self.side_states.add(s)
        for s in side_removed:
            self.side_states.discard(s)
        if new_state == SituationState.RESOLVED:
            self.resolved_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

        logger.info(
            "Situation %s transitioned: %s → %s (reason: %s)",
            self.situation_id, old_state.value, new_state.value, reason[:80],
        )
        return transition

    def get_latest_transition(self) -> Optional[StateTransition]:
        """Get the most recent state transition."""
        return self.state_history[-1] if self.state_history else None

    # ── Gate 0: 4-Dimensional transitions ──────────────────────────────────

    def transition_dimension(
        self,
        dimension: str,
        new_state: str,
        reason: str,
        triggering_event_refs: Optional[list[str]] = None,
        rule_id: str = "",
        unknowns_added: Optional[list[str]] = None,
        unknowns_resolved: Optional[list[str]] = None,
        decision_boundary_changed: bool = False,
        delivery_effect: str = "",
    ) -> DimensionTransition:
        """Transition a single dimension with an enriched receipt.

        Per the CEO audit directive: "Every transition should produce a
        first-class transition receipt" with dimension, rule_id, unknowns,
        and delivery_effect. This lets the user ask "Why did Maestro
        prepare me today but not three days ago?" and get a mechanical answer.

        Args:
            dimension: "epistemic" | "operational" | "delivery" | "learning"
            new_state: the new state value (string)
            reason: WHY the transition happened
            triggering_event_refs: which event(s) caused it
            rule_id: which transition rule fired
            unknowns_added: new unknowns introduced by this transition
            unknowns_resolved: unknowns resolved by this transition
            decision_boundary_changed: did the decision boundary change?
            delivery_effect: what changed in delivery eligibility
        """
        # Determine previous state based on dimension
        dim_map = {
            "epistemic": self.epistemic_dimension,
            "operational": self.operational_dimension,
            "delivery": self.delivery_dimension,
            "learning": self.learning_dimension,
        }
        prev_state_obj = dim_map.get(dimension)
        previous_state = prev_state_obj.value if prev_state_obj else ""

        # Skip if no actual change
        if previous_state == new_state:
            return DimensionTransition(
                dimension=dimension,
                previous_state=previous_state,
                new_state=new_state,
                timestamp=datetime.now(timezone.utc),
                reason="No change — same state",
                triggering_event_refs=triggering_event_refs or [],
                rule_id=rule_id,
            )

        # Create the transition receipt
        transition = DimensionTransition(
            dimension=dimension,
            previous_state=previous_state,
            new_state=new_state,
            timestamp=datetime.now(timezone.utc),
            reason=reason,
            triggering_event_refs=triggering_event_refs or [],
            rule_id=rule_id,
            unknowns_added=unknowns_added or [],
            unknowns_resolved=unknowns_resolved or [],
            decision_boundary_changed=decision_boundary_changed,
            delivery_effect=delivery_effect,
        )

        # Apply the new state
        if dimension == "epistemic":
            self.epistemic_dimension = EpistemicDimensionState(new_state)
        elif dimension == "operational":
            self.operational_dimension = OperationalDimensionState(new_state)
        elif dimension == "delivery":
            self.delivery_dimension = DeliveryDimensionState(new_state)
        elif dimension == "learning":
            self.learning_dimension = LearningDimensionState(new_state)

        self.dimension_transitions.append(transition)
        self.updated_at = datetime.now(timezone.utc)

        logger.info(
            "Situation %s %s dimension: %s → %s (rule: %s, reason: %s)",
            self.situation_id, dimension, previous_state, new_state,
            rule_id, reason[:80],
        )
        return transition

    def get_dimension_transitions(self, dimension: str) -> list[DimensionTransition]:
        """Get all transitions for a specific dimension."""
        return [t for t in self.dimension_transitions if t.dimension == dimension]

    def get_latest_dimension_transition(self, dimension: str) -> Optional[DimensionTransition]:
        """Get the most recent transition for a specific dimension."""
        transitions = self.get_dimension_transitions(dimension)
        return transitions[-1] if transitions else None


# ════════════════════════════════════════════════════════════════════════════
# SituationEngine — builds, maintains, and transitions LivingSituations
# ════════════════════════════════════════════════════════════════════════════

# Mapping from specialist → the entity domains it's relevant for.
SPECIALIST_DOMAIN_MAP: dict[str, set[str]] = {
    "growth":           {"renewal", "expansion", "upsell", "pipeline"},
    "sales":            {"renewal", "deal", "pipeline", "pricing", "contract"},
    "customer_success": {"renewal", "churn", "health", "satisfaction", "onboarding"},
    "finance":          {"deal", "contract", "budget", "cost", "revenue"},
    "product":          {"roadmap", "feature", "feedback", "release"},
    "engineering":      {"deployment", "bug", "incident", "integration", "architecture"},
    "marketing":        {"campaign", "positioning", "messaging"},
    "hr":               {"hiring", "retention", "burnout", "workload"},
    "legal":            {"contract", "compliance", "dpa", "sla", "obligation"},
    "operations":       {"process", "bottleneck", "capacity"},
    "support":          {"ticket", "issue", "escalation", "kb"},
    "data":             {"analytics", "trend", "metric"},
    "security":         {"security", "auth", "oauth", "sso", "vulnerability", "access"},
    "partnerships":     {"partner", "co-sell", "joint"},
    "strategy":         {"market", "competitive", "positioning", "bet"},
    "communications":   {"announcement", "internal-comms", "follow-up"},
    "chief_of_staff":   set(),
}


class SituationEngine:
    """Builds, maintains, and transitions LivingSituations from OEM signals.

    The engine is the bridge between Organizational Memory (Layer 2) and
    the Judgment layer (Layer 4). It:
      1. Detects situations from OEM signals (detect_situations)
      2. Applies new signals to existing situations (apply_signal)
      3. Computes deltas and justifies state transitions
      4. Routes only relevant specialists per situation

    Usage:
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        for signal in new_signals:
            delta = engine.apply_signal(situation, signal)
            if delta.has_transition:
                print(f"Transition: {delta.transition.reason}")
    """

    def __init__(self, oem_state: Any = None, situation_store: Any = None):
        self._oem_state = oem_state
        self._situations: dict[str, LivingSituation] = {}
        self._situation_store = situation_store  # Persistent store (SQLite)

    @property
    def oem_state(self) -> Any:
        if self._oem_state is None:
            try:
                from maestro_api.oem_state import oem_state
                self._oem_state = oem_state
            except ImportError:
                self._oem_state = _NullOemState()
        return self._oem_state

    def _get_signals(self, org_id: str = "default") -> list:
        signals = getattr(self.oem_state, "signals", None) or []
        result = []
        for s in signals:
            s_org = getattr(s, "org_id", None) or getattr(s, "tenant_id", None)
            if s_org is None or s_org == org_id:
                result.append(s)
        return result

    # ── Situation detection ─────────────────────────────────────────────────

    def detect_situations(self, org_id: str = "default") -> list[LivingSituation]:
        """Detect active situations from OEM signals.

        A situation is detected when an entity has 2+ signals. The first
        situation for an entity starts in OBSERVING state (not DETECTED —
        DETECTED is the pre-creation state).

        Returns a list of LivingSituations, sorted by update recency.
        """
        signals = self._get_signals(org_id)
        entities: dict[str, list] = {}

        for sig in signals:
            entity = (
                getattr(sig, "entity", None)
                or (getattr(sig, "metadata", {}) or {}).get("customer")
                or (getattr(sig, "metadata", {}) or {}).get("entity")
            )
            if entity:
                entities.setdefault(entity, []).append(sig)

        situations: list[LivingSituation] = []
        for entity, entity_signals in entities.items():
            # Engine Fix 7 (H5): Early-checkpoint detection.
            # Per external reviewer: 'A subtle but material change at Day 12
            # of a 60-day situation is not surfaced until Day 30 when a major
            # signal arrives.' The prior 2-signal threshold meant first
            # checkpoints (Day 1-15) with only 1 signal never created a situation.
            # Now: create a situation from 1 signal IF it's a high-salience type
            # (commitment, decision, pricing exception, security condition).
            # These signal types are significant enough to warrant situation
            # creation even without a second signal.
            #
            # Fix 2 (salience model): attempted to lower the threshold further
            # to ANY situation-worthy signal, but this caused Test 2 coherence
            # regressions (multi-entity stories create too many situations,
            # surfaces pick different top situations). The high-salience gate
            # from Fix 7 is the right balance: catches the most important first
            # signals without fragmenting multi-entity stories.
            if len(entity_signals) < 2:
                # Check if the single signal is high-salience
                if len(entity_signals) == 1 and self._is_high_salience_signal(entity_signals[0]):
                    pass  # Allow situation creation with 1 high-salience signal
                elif len(entity_signals) == 1 and len(entities) <= 2:
                    # Fix: single-entity stories (or 2-entity stories with
                    # shared signals) — allow 1 signal to create a situation.
                    # This catches early checkpoints in stories where the entity
                    # is the sole focus. Multi-entity stories (>2 entities) keep
                    # the 2-signal threshold to prevent fragmentation.
                    pass
                else:
                    continue
            # PERSISTENCE: check if a situation already exists for this entity
            existing = None
            if self._situation_store:
                existing = self._situation_store.load_situation(entity, org_id)

            if existing:
                # EVOLVE: update the existing situation with new signals (delta-driven)
                situation = self._evolve_situation(existing, entity, entity_signals, org_id)
            else:
                # CREATE: build a new situation from scratch
                situation = self._build_situation(entity, entity_signals, org_id)

            if situation:
                self._situations[situation.situation_id] = situation
                # PERSIST: save the situation to the store
                if self._situation_store:
                    self._situation_store.save_situation(situation)
                situations.append(situation)

        # Engine Fix 3 (C11): Outcome-only detection — cross-entity pattern situations.
        # Per external reviewer: 'The engine detects outcomes but not early-checkpoint
        # changes, hypothesis-testing state, or decision-boundary language.' Story 10
        # (reorg falsification) has 7 outcome signals across 7 entities — each entity
        # has only 1 signal, below the 2-signal threshold. The engine should detect a
        # CROSS-ENTITY pattern situation when there are 3+ outcome signals with a
        # common theme (e.g., "Early Security involvement correlates with renewal
        # success"). This is how organizational learning works: patterns emerge across
        # entities, not just within one entity's timeline.
        cross_entity_situations = self._detect_cross_entity_pattern_situations(signals, org_id)
        for situation in cross_entity_situations:
            if situation.situation_id not in self._situations:
                self._situations[situation.situation_id] = situation
                if self._situation_store:
                    self._situation_store.save_situation(situation)
                situations.append(situation)

        situations.sort(key=lambda s: s.updated_at, reverse=True)

        # Fix: Duplicate-work meta-situation (Story 6 design question resolved).
        # When 2+ entities have signals with >60% text overlap on the same
        # artifact type (e.g., both building "authentication API"), create a
        # meta-situation that links them. This ensures Ask/Briefing/Prepare
        # all find the SAME situation when duplicate work exists.
        meta_situations = self._detect_duplicate_work_meta_situations(signals, org_id, situations)
        for ms in meta_situations:
            if ms.situation_id not in self._situations:
                self._situations[ms.situation_id] = ms
                situations.append(ms)
        # Re-sort with meta-situations included (meta-situations are most
        # recently updated because they're created last)
        situations.sort(key=lambda s: s.updated_at, reverse=True)
        return situations

    def _detect_duplicate_work_meta_situations(
        self,
        signals: list,
        org_id: str,
        existing_situations: list,
    ) -> list[LivingSituation]:
        """Detect duplicate work across entities and create meta-situations.

        Per CEO design decision: when 2+ entities are working on the same
        artifact (detected via text overlap on work_started/commitment signals),
        create a meta-situation that links both teams. This ensures all surfaces
        (Ask, Briefing, Prepare) find the same situation.

        Detection: extract work descriptions from engineering.work_started and
        engineering.commitment signals. If 2+ entities have >60% word overlap,
        create a meta-situation with entity="Internal" and title mentioning
        both teams.
        """
        from difflib import SequenceMatcher

        # Collect work descriptions per entity
        entity_works: dict[str, list[str]] = {}
        for sig in signals:
            sig_type_raw = getattr(sig, "type", None)
            sig_type_val = getattr(sig_type_raw, "value", str(sig_type_raw)) if sig_type_raw else ""
            sig_type = str(sig_type_val).lower()
            if "work_started" in sig_type or "engineering.commitment" in sig_type:
                entity = getattr(sig, "entity", "")
                text = (getattr(sig, "text", "") or "").lower()
                if entity and text:
                    entity_works.setdefault(entity, []).append(text)

        if len(entity_works) < 2:
            return []

        # Check for text overlap between entities
        entities = list(entity_works.keys())
        meta_situations = []
        for i in range(len(entities)):
            for j in range(i + 1, len(entities)):
                ent_a = entities[i]
                ent_b = entities[j]
                works_a = entity_works[ent_a]
                works_b = entity_works[ent_b]
                # Check if any work description pair has >60% similarity
                best_ratio = 0.0
                for wa in works_a:
                    for wb in works_b:
                        ratio = SequenceMatcher(None, wa, wb).ratio()
                        best_ratio = max(best_ratio, ratio)
                if best_ratio > 0.6:
                    # Duplicate work detected — create meta-situation
                    # Collect all signals from both entities
                    dup_signals = [
                        s for s in signals
                        if getattr(s, "entity", "") in (ent_a, ent_b)
                    ]
                    # Also check for explicit duplicate.detected signal
                    has_explicit_duplicate = any(
                        "duplicate" in str(getattr(
                            getattr(s, "type", None), "value", ""
                        )).lower()
                        for s in signals
                    )
                    meta_entity = "Internal"
                    meta_situation = self._build_situation(meta_entity, dup_signals, org_id)
                    if meta_situation:
                        meta_situation.title = (
                            f"Duplicate work: {ent_a} and {ent_b} building "
                            f"the same artifact"
                        )
                        # Mark as duplicate work
                        meta_situation.add_side_state(SideState.DISPUTED)
                        meta_situation.add_unknown(Unknown(
                            question=f"Are {ent_a} and {ent_b} actually doing duplicate work?",
                            why_it_matters="If confirmed, consolidate to avoid wasted effort. "
                                          "If not, they may be building complementary components.",
                            blocking=True,
                            specialists_flagged=["engineering", "chief_of_staff"],
                        ))
                        meta_situations.append(meta_situation)
                        logger.info(
                            "Duplicate work meta-situation created: %s and %s "
                            "(text overlap: %.0f%%, explicit: %s)",
                            ent_a, ent_b, best_ratio * 100, has_explicit_duplicate,
                        )
        return meta_situations
        """Fix 2 (salience model): Check if a signal is situation-worthy.

        Per CEO directive: the first signal for an entity should create a
        situation if the signal represents organizational activity (not just
        an observation). This catches low-salience first signals that the
        high-salience gate (Fix 7) missed — incidents, reports, meetings.

        Signal types that are situation-worthy:
          - High-salience: commitment_made, decision.proposed, org.reorganization
          - Medium-salience: incident.*, reported_statement, customer.meeting,
            pricing.exception, security.condition, scope_change, budget_cut,
            engineering.concern, legal.concern, sales.concern

        Signal types that are NOT situation-worthy (need 2+):
          - outcome.* (observations of other activity, not situations themselves)
          - calendar.meeting (metadata, not a situation)
        """
        sig_type_raw = getattr(signal, "type", None)
        sig_type_val = getattr(sig_type_raw, "value", str(sig_type_raw)) if sig_type_raw else ""
        sig_type = str(sig_type_val).lower()

        # High-salience (from Fix 7)
        high_salience = {
            "commitment_made", "customer.commitment_made",
            "decision.proposed", "decision_made",
            "org.reorganization", "reorganization",
        }
        if sig_type in high_salience:
            return True

        # Medium-salience: organizational activity signals
        medium_salience_prefixes = (
            "incident", "reported_statement", "customer.meeting",
            "pricing.exception", "security.condition", "security.concern",
            "scope_change", "budget_cut", "hiring",
            "engineering.concern", "legal.concern", "sales.concern",
            "customer_success.concern", "expert.bottleneck", "duplicate_work",
            "assumption.collapse",
        )
        for prefix in medium_salience_prefixes:
            if prefix in sig_type:
                return True

        # Also check signal text for organizational activity keywords
        sig_text = (getattr(signal, "text", "") or "").lower()
        activity_keywords = (
            "incident", "bottleneck", "blocked", "delayed", "at risk",
            "scope", "budget", "hiring", "concern", "objection",
            "pricing", "security", "legal",
        )
        for kw in activity_keywords:
            if kw in sig_text:
                return True

        return False

    def _is_high_salience_signal(self, signal: Any) -> bool:
        """Engine Fix 7 (H5): Check if a signal is high-salience enough to
        warrant situation creation with only 1 signal.

        Per external reviewer: 'A subtle but material change at Day 12 of a
        60-day situation is not surfaced until Day 30.' These signal types
        are significant enough to create a situation immediately:
          - customer.commitment_made (a commitment is a situation by itself)
          - decision.proposed (a decision question is a situation by itself)
          - org.reorganization (an org change is a situation by itself)

        NOTE: pricing.exception and security.condition are NOT in this list
        because they need a second signal (precedent reference, commitment)
        to be meaningful as situations.
        """
        sig_type_raw = getattr(signal, "type", None)
        sig_type_val = getattr(sig_type_raw, "value", str(sig_type_raw)) if sig_type_raw else ""
        sig_type = str(sig_type_val).lower()
        high_salience_types = {
            "commitment_made", "customer.commitment_made",
            "decision.proposed", "decision_made",
            "org.reorganization", "reorganization",
        }
        return sig_type in high_salience_types

    def _detect_cross_entity_pattern_situations(
        self,
        signals: list,
        org_id: str,
    ) -> list[LivingSituation]:
        """Detect cross-entity pattern situations from outcome signals.

        Per Engine Fix 3 (C11): when 3+ outcome signals share a common theme
        (e.g., all mention "Security involved early"), the engine should
        create a pattern situation that spans entities. This is how
        organizational learning works — patterns emerge across customers,
        not just within one customer's timeline.

        This detects:
          - 3+ outcome.positive signals with shared keywords → pattern situation
          - 3+ outcome.negative signals with shared keywords → pattern situation
          - org.reorganization signals → creates an "org change" situation
        """
        # Group outcome signals by shared theme (keyword overlap)
        outcome_signals = []
        reorg_signals = []
        for sig in signals:
            sig_type_raw = getattr(sig, "type", None)
            sig_type_val = getattr(sig_type_raw, "value", str(sig_type_raw)) if sig_type_raw else ""
            sig_type = str(sig_type_val).lower()
            if "outcome" in sig_type:
                outcome_signals.append(sig)
            elif "reorganization" in sig_type or "org.reorganization" in sig_type:
                reorg_signals.append(sig)

        situations: list[LivingSituation] = []

        # Detect outcome patterns (3+ outcomes with shared keywords)
        if len(outcome_signals) >= 3:
            # Extract common theme from outcome text
            texts = [(getattr(s, "text", "") or "").lower() for s in outcome_signals]
            # Find shared keywords (3+ word phrases that appear in 3+ signals)
            from collections import Counter
            word_counts = Counter()
            for text in texts:
                words = set(text.split())
                word_counts.update(words)
            shared_keywords = [w for w, c in word_counts.items() if c >= 3 and len(w) > 3]

            if shared_keywords:
                # Create a pattern situation
                top_keyword = shared_keywords[0]
                pattern_entity = "Internal"  # cross-entity patterns are internal
                pattern_text = f"Pattern: {top_keyword} correlates with outcomes"
                situation = self._build_situation(pattern_entity, outcome_signals, org_id)
                if situation:
                    situation.title = f"Cross-entity outcome pattern: {top_keyword}"
                    situations.append(situation)

        # Detect reorganization situations
        if reorg_signals:
            situation = self._build_situation("Internal", reorg_signals, org_id)
            if situation:
                situation.title = "Organizational reorganization"
                situations.append(situation)

        return situations

    def _evolve_situation(
        self,
        existing_data: dict,
        entity: str,
        entity_signals: list,
        org_id: str,
    ) -> Optional[LivingSituation]:
        """Evolve an existing situation with new signals (delta-driven).

        Instead of rebuilding from the full corpus, this:
          1. Reconstructs the LivingSituation from the stored data
          2. Checks for new signals not already in evidence_refs
          3. Applies only the new signals via apply_signal() (delta-driven)
          4. Returns the evolved situation

        This is the "over time" coherence the audit demands.
        """
        # Reconstruct the LivingSituation from stored data
        situation = LivingSituation(
            situation_id=existing_data.get("situation_id", ""),
            title=existing_data.get("title", f"{entity} situation"),
            entity=entity,
            org_id=org_id,
            state=SituationState(existing_data.get("state", "observing")),
            epistemic_state=EpistemicState(existing_data.get("epistemic_state", "unknown")),
        )

        # Restore evidence_refs
        existing_refs = set(existing_data.get("evidence_refs", []))
        situation.evidence_refs = list(existing_refs)

        # Restore commitment_refs
        situation.commitment_refs = existing_data.get("commitment_refs", [])
        situation.decision_refs = existing_data.get("decision_refs", [])
        situation.meeting_refs = existing_data.get("meeting_refs", [])

        # Restore timeline
        for tl in existing_data.get("timeline", []):
            ts_str = tl.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)
            situation.timeline.append(TimelineEvent(
                timestamp=ts,
                description=tl.get("description", ""),
                event_type=tl.get("event_type", "observed"),
                evidence_ref=tl.get("evidence_ref"),
                source=tl.get("source", ""),
            ))

        # Restore known_facts
        for kf in existing_data.get("known_facts", []):
            situation.known_facts.append(KnownFact(
                statement=kf.get("statement", ""),
                evidence_refs=kf.get("evidence_refs", []),
                epistemic_state=EpistemicState(kf.get("epistemic_state", "reported")),
                source=kf.get("source", ""),
            ))

        # Restore unknowns
        for u in existing_data.get("unknowns", []):
            situation.unknowns.append(Unknown(
                question=u.get("question", ""),
                why_it_matters=u.get("why_it_matters", ""),
                blocking=u.get("blocking", False),
                specialists_flagged=u.get("specialists_flagged", []),
                resolved=u.get("resolved", False),
                resolved_by_evidence_ref=u.get("resolved_by_evidence_ref"),
            ))

        # Restore material_changes
        situation.material_changes = existing_data.get("material_changes", [])

        # Find NEW signals not already in evidence_refs
        new_signals = []
        for sig in entity_signals:
            sig_id = getattr(sig, "signal_id", "") or str(id(sig))
            # Audit C-A fix: real OEM signals use UUID-typed signal_ids (maestro_oem/model.py:268).
            # Without stringification, UUIDs leak into evidence_refs / timeline evidence_ref /
            # triggering_evidence_ref fields and crash JSON serialization at the API layer
            # ("Object of type UUID is not JSON serializable"). Stringify defensively here
            # so every downstream consumer (to_dict, JSON response, situation_store) sees a str.
            if sig_id is not None and not isinstance(sig_id, str):
                sig_id = str(sig_id)
            if sig_id not in existing_refs:
                new_signals.append(sig)

        # Apply only new signals (delta-driven evolution)
        for sig in new_signals:
            self.apply_signal(situation, sig)

        # Re-evaluate state transitions based on new signals
        if new_signals:
            self._evaluate_initial_transitions(situation, entity_signals)

        # Update relevant_specialists
        situation.relevant_specialists = self.route_specialists(situation)

        return situation

    def _build_situation(
        self,
        entity: str,
        entity_signals: list,
        org_id: str,
    ) -> Optional[LivingSituation]:
        """Build a LivingSituation from an entity's signals.

        Uses REFERENCES to OEM objects, not copies. The situation holds
        refs (evidence_refs, commitment_refs, meeting_refs) that point
        back to the OEM source of record.
        """
        # Engine Fix 1 (C9): Stable situation_id via deterministic hash.
        # Per external reviewer: 'situation_id is not stable across duplicate
        # reports of one event, renames, or corrections.' The prior uuid4()
        # approach meant each engine instance generated a new ID for the same
        # logical situation. Now we derive the ID from a hash of (entity, org_id)
        # so two engines processing the same entity produce the same ID.
        # This enables cross-surface coherence (Ask/Briefing/Prepare agree),
        # duplicate-lineage suppression, and tombstone enforcement at the row level.
        import hashlib
        id_source = f"{entity.lower()}:{org_id.lower()}"
        id_hash = hashlib.sha256(id_source.encode()).hexdigest()[:12]
        situation_id = f"sit-{entity.lower().replace(' ', '-')}-{id_hash}"
        title = self._derive_title(entity, entity_signals)

        # Start in OBSERVING (first creation — DETECTED is conceptual)
        situation = LivingSituation(
            situation_id=situation_id,
            title=title,
            entity=entity,
            org_id=org_id,
            state=SituationState.OBSERVING,
        )

        # Log the initial transition DETECTED → OBSERVING
        situation.state_history.append(StateTransition(
            from_state=SituationState.DETECTED,
            to_state=SituationState.OBSERVING,
            timestamp=situation.opened_at,
            reason=f"Situation detected from {len(entity_signals)} signals for {entity}",
            triggering_evidence_ref=getattr(entity_signals[0], "signal_id", None),
        ))

        # Build timeline + evidence_refs from signals (REFERENCES, not copies)
        for sig in entity_signals:
            ts = getattr(sig, "timestamp", datetime.now(timezone.utc))
            sig_type = getattr(getattr(sig, "type", None), "value", str(getattr(sig, "type", "")))
            text = getattr(sig, "text", "") or (getattr(sig, "metadata", {}) or {}).get("text", "")
            sig_id = getattr(sig, "signal_id", "") or str(id(sig))
            # Audit C-A fix: real OEM signals use UUID-typed signal_ids (maestro_oem/model.py:268).
            # Without stringification, UUIDs leak into evidence_refs / timeline evidence_ref /
            # triggering_evidence_ref fields and crash JSON serialization at the API layer
            # ("Object of type UUID is not JSON serializable"). Stringify defensively here
            # so every downstream consumer (to_dict, JSON response, situation_store) sees a str.
            if sig_id is not None and not isinstance(sig_id, str):
                sig_id = str(sig_id)

            # Add evidence REFERENCE (not a copy)
            if sig_id not in situation.evidence_refs:
                situation.evidence_refs.append(sig_id)

            event_type = "observed"
            if "commitment" in sig_type.lower():
                event_type = "committed"
                if sig_id not in situation.commitment_refs:
                    situation.commitment_refs.append(sig_id)
            elif "decision" in sig_type.lower():
                event_type = "decided"
                if sig_id not in situation.decision_refs:
                    situation.decision_refs.append(sig_id)
            elif "outcome" in sig_type.lower():
                event_type = "outcome"
            elif "reported" in sig_type.lower():
                event_type = "reported"
            elif "meeting" in sig_type.lower():
                if sig_id not in situation.meeting_refs:
                    situation.meeting_refs.append(sig_id)

            situation.add_timeline_event(TimelineEvent(
                timestamp=ts if isinstance(ts, datetime) else datetime.now(timezone.utc),
                description=text or f"{sig_type} for {entity}",
                event_type=event_type,
                evidence_ref=sig_id,
                source=sig_type,
            ))

        # Extract known facts (with evidence REFS)
        for sig in entity_signals:
            text = getattr(sig, "text", "") or (getattr(sig, "metadata", {}) or {}).get("text", "")
            sig_id = getattr(sig, "signal_id", "") or str(id(sig))
            # Audit C-A fix: real OEM signals use UUID-typed signal_ids (maestro_oem/model.py:268).
            # Without stringification, UUIDs leak into evidence_refs / timeline evidence_ref /
            # triggering_evidence_ref fields and crash JSON serialization at the API layer
            # ("Object of type UUID is not JSON serializable"). Stringify defensively here
            # so every downstream consumer (to_dict, JSON response, situation_store) sees a str.
            if sig_id is not None and not isinstance(sig_id, str):
                sig_id = str(sig_id)
            if text:
                epistemic = EpistemicState.REPORTED
                _t = getattr(sig, "type", None)
                _tv = getattr(_t, "value", None) if _t else None
                sig_type = str(_tv).lower() if _tv else str(_t).lower()
                if "commitment" in sig_type:
                    epistemic = EpistemicState.ASSUMED
                elif "outcome" in sig_type:
                    epistemic = EpistemicState.KNOWN
                situation.add_known_fact(KnownFact(
                    statement=text[:200],
                    evidence_refs=[sig_id],
                    epistemic_state=epistemic,
                    source=sig_type,
                ))

        # Detect unknowns (gaps in evidence)
        unknowns = self._detect_unknowns(entity, entity_signals)
        for u in unknowns:
            situation.add_unknown(u)

        # Determine epistemic state
        situation.epistemic_state = self._determine_epistemic_state(situation)

        # Determine initial state + side states via transition logic
        self._evaluate_initial_transitions(situation, entity_signals)

        # Route relevant specialists
        situation.relevant_specialists = self.route_specialists(situation)

        return situation

    def _derive_title(self, entity: str, signals: list) -> str:
        """Derive a human-readable title for the situation."""
        for sig in signals:
            _t = getattr(sig, "type", None)
            _tv = getattr(_t, "value", None) if _t else None
            sig_type = str(_tv).lower() if _tv else str(_t).lower()
            text = getattr(sig, "text", "") or ""
            if "commitment" in sig_type and text:
                return f"{entity}: {text[:60]}"
        return f"{entity} situation"

    def _detect_unknowns(self, entity: str, signals: list) -> list[Unknown]:
        """Detect important unknowns from signal gaps."""
        unknowns: list[Unknown] = []

        def _sig_type_str(s) -> str:
            t = getattr(s, "type", None)
            if t is None:
                return ""
            val = getattr(t, "value", None)
            return str(val).lower() if val is not None else str(t).lower()

        has_commitment = any("commitment" in _sig_type_str(s) for s in signals)
        has_outcome = any("outcome" in _sig_type_str(s) for s in signals)
        if has_commitment and not has_outcome:
            unknowns.append(Unknown(
                question=f"Was the commitment to {entity} fulfilled?",
                why_it_matters="Without outcome evidence, the commitment status remains assumed, not known.",
                blocking=False,
                specialists_flagged=["customer_success", "sales"],
            ))

        # Fix: Detect assumption-based unknowns (Story 4: hiring collapse)
        # When a plan assumes something (budget, resources, capacity), the
        # assumption is an unknown until validated by evidence.
        has_assumption = any(
            "assumption" in _sig_type_str(s)
            or "assumes" in (getattr(s, "text", "") or "").lower()
            or "assumption" in (getattr(s, "text", "") or "").lower()
            for s in signals
        )
        has_budget_validation = any(
            "budget" in _sig_type_str(s) and "cut" not in (getattr(s, "text", "") or "").lower()
            or "approved" in (getattr(s, "text", "") or "").lower()
            or "confirmed" in (getattr(s, "text", "") or "").lower()
            for s in signals
        )
        if has_assumption and not has_budget_validation:
            unknowns.append(Unknown(
                question="Was the budget assumption validated?",
                why_it_matters="Plans based on unvalidated budget assumptions are at risk if the budget changes.",
                blocking=True,
                specialists_flagged=["finance", "engineering"],
            ))

        has_security = any(
            "security" in _sig_type_str(s)
            or "security" in (getattr(s, "text", "") or "").lower()
            for s in signals
        )
        has_resolution = any(
            "resolved" in _sig_type_str(s)
            or "approved" in (getattr(s, "text", "") or "").lower()
            for s in signals
        )
        if has_security and not has_resolution:
            unknowns.append(Unknown(
                question=f"Was the security condition for {entity} cleared?",
                why_it_matters="Conditional security approvals that remain unresolved can block renewals and create audit exposure.",
                blocking=True,
                specialists_flagged=["security", "legal"],
            ))

        return unknowns

    def _determine_epistemic_state(self, situation: LivingSituation) -> EpistemicState:
        """Determine the overall epistemic state of the situation."""
        if not situation.known_facts:
            return EpistemicState.UNKNOWN
        if situation.has_blocking_unknown():
            return EpistemicState.DISPUTED
        states = [f.epistemic_state for f in situation.known_facts]
        if all(s == EpistemicState.KNOWN for s in states):
            return EpistemicState.KNOWN
        if any(s == EpistemicState.ASSUMED for s in states):
            return EpistemicState.ASSUMED
        return EpistemicState.REPORTED

    def _evaluate_initial_transitions(self, situation: LivingSituation, signals: list) -> None:
        """Evaluate whether the situation should transition from OBSERVING
        to a more advanced state based on initial signals.
        """
        # Helper: get the signal type as a lowercase string (handles both
        # real OEM enums and MagicMock test doubles)
        def _sig_type_str(s) -> str:
            t = getattr(s, "type", None)
            if t is None:
                return ""
            # Real OEM signals have type.value; mocks have type.value set too
            val = getattr(t, "value", None)
            if val is not None:
                return str(val).lower()
            return str(t).lower()

        # Check if there's a security prerequisite (→ MATERIAL)
        has_security_prereq = any(
            "security" in _sig_type_str(s)
            or "security" in (getattr(s, "text", "") or "").lower()
            for s in signals
        )
        has_commitment = any(
            "commitment" in _sig_type_str(s)
            for s in signals
        )

        if has_security_prereq and has_commitment:
            # New prerequisite threatens commitment feasibility → MATERIAL
            security_sig = next(
                s for s in signals
                if "security" in _sig_type_str(s)
                or "security" in (getattr(s, "text", "") or "").lower()
            )
            situation.transition_to(
                SituationState.MATERIAL,
                reason="Security prerequisite threatens commitment feasibility",
                triggering_evidence_ref=getattr(security_sig, "signal_id", None),
                side_states_added=[SideState.BLOCKED] if situation.has_blocking_unknown() else [],
            )

        # Check if there's an expectation mismatch (→ NEEDS_PREPARATION)
        # This can happen from OBSERVING (no security prereq) or MATERIAL
        # (security prereq + expectation mismatch).
        has_expectation_mismatch = any(
            "availability" in (getattr(s, "text", "") or "").lower()
            or "expectation" in (getattr(s, "text", "") or "").lower()
            or "production" in (getattr(s, "text", "") or "").lower()
            for s in signals
        )
        if has_expectation_mismatch and situation.state in (SituationState.MATERIAL, SituationState.OBSERVING):
            situation.transition_to(
                SituationState.NEEDS_PREPARATION,
                reason="External expectation may differ from internal completion state",
                triggering_evidence_ref=getattr(signals[-1], "signal_id", None),
            )

        # Engine Fix 4 (C12): Auto-disagreement detection from conflicting concerns.
        # Per external reviewer: 'The engine collapses disagreement into false
        # consensus when no explicit disagreement token is present.' When 2+
        # different function concerns are present (engineering.concern +
        # security.concern + legal.concern + sales.concern), the engine must
        # auto-create a Disagreement and set the DISPUTED side state. This
        # preserves cross-functional nuance instead of collapsing it.
        concern_map = {
            "engineering": "Engineering",
            "security": "Security",
            "legal": "Legal",
            "sales": "Sales",
            "customer_success": "Customer Success",
        }
        detected_concerns: dict[str, str] = {}  # function → signal text
        for sig in signals:
            sig_type = _sig_type_str(sig)
            sig_text = (getattr(sig, "text", "") or "").lower()
            for func_key, func_name in concern_map.items():
                if f"{func_key}.concern" in sig_type or f"{func_key}." in sig_type:
                    if func_key not in detected_concerns:
                        detected_concerns[func_key] = sig_text[:100]
                    break

        if len(detected_concerns) >= 2:
            # Auto-create a disagreement preserving the cross-functional positions
            concern_items = list(detected_concerns.items())
            func_a, text_a = concern_items[0]
            func_b, text_b = concern_items[1]
            disagreement = Disagreement(
                topic=f"Cross-functional disagreement: {concern_map[func_a]} vs {concern_map[func_b]}",
                position_a=text_a or f"{concern_map[func_a]} concern",
                position_b=text_b or f"{concern_map[func_b]} concern",
                specialist_a=func_a,
                specialist_b=func_b,
                unresolved=True,
            )
            situation.add_disagreement(disagreement)
            if not situation.has_side_state(SideState.DISPUTED):
                situation.add_side_state(SideState.DISPUTED)
            logger.info(
                "C12 FIX: Auto-detected disagreement between %s and %s for situation %s",
                concern_map[func_a], concern_map[func_b], situation.situation_id,
            )

        # Condition 5 fix (corrected audit): Reorg falsification — when an
        # organizational reorganization signal is present, mark the pattern
        # as contested and add the "does the pattern still hold?" unknown.
        # Per auditor: "When organizational reorganization is detected, the
        # engine must link post-reorg situations to pre-reorg patterns."
        has_reorg = any(
            "reorganization" in _sig_type_str(s)
            or "reorganization" in (getattr(s, "text", "") or "").lower()
            for s in signals
        )
        if has_reorg:
            # The reorg contests any previously learned pattern
            if not situation.has_side_state(SideState.DISPUTED):
                situation.add_side_state(SideState.DISPUTED)
            # Add the critical unknown: does the pattern survive the reorg?
            has_reorg_unknown = any(
                "reorg" in (getattr(u, "question", "").lower() or "")
                for u in situation.unknowns
            )
            if not has_reorg_unknown:
                situation.add_unknown(Unknown(
                    question="Does the learned pattern still hold after the reorg?",
                    why_it_matters=(
                        "Organizational restructuring can invalidate patterns "
                        "learned under the prior structure. The pattern must be "
                        "re-validated against post-reorg outcomes."
                    ),
                    blocking=True,
                    specialists_flagged=["chief_of_staff", "organizational_design"],
                ))
            logger.info(
                "C5 FIX: Reorg detected — pattern contested, unknown added for situation %s",
                situation.situation_id,
            )

    # ── Continuous state transition (the biggest missing capability) ────────

    def apply_signal(self, situation: LivingSituation, signal: Any) -> SituationDelta:
        """Apply a new signal to an existing situation and compute the delta."""
        sig_id = getattr(signal, "signal_id", "") or str(id(signal))
        # Audit C-A fix: see note above — real OEM signal_ids are UUID-typed, must stringify.
        if sig_id is not None and not isinstance(sig_id, str):
            sig_id = str(sig_id)
        # Get signal type as lowercase string (handles real enums + mocks)
        sig_type_raw = getattr(signal, "type", None)
        sig_type_val = getattr(sig_type_raw, "value", None) if sig_type_raw else None
        sig_type = str(sig_type_val).lower() if sig_type_val else str(sig_type_raw).lower()
        sig_text = getattr(signal, "text", "") or ""
        sig_ts = getattr(signal, "timestamp", datetime.now(timezone.utc))
        if not isinstance(sig_ts, datetime):
            sig_ts = datetime.now(timezone.utc)

        delta = SituationDelta(
            situation_id=situation.situation_id,
            signal_ref=sig_id,
        )

        # 1. Add evidence REFERENCE (not a copy)
        if sig_id not in situation.evidence_refs:
            situation.evidence_refs.append(sig_id)
            delta.new_evidence_refs.append(sig_id)

        # 2. Add timeline event (projection, with evidence_ref)
        event_type = "observed"
        if "commitment" in sig_type:
            event_type = "committed"
            if sig_id not in situation.commitment_refs:
                situation.commitment_refs.append(sig_id)
        elif "decision" in sig_type:
            event_type = "decided"
            if sig_id not in situation.decision_refs:
                situation.decision_refs.append(sig_id)
        elif "outcome" in sig_type:
            event_type = "outcome"
        elif "meeting" in sig_type or "calendar" in sig_type:
            event_type = "observed"
            if sig_id not in situation.meeting_refs:
                situation.meeting_refs.append(sig_id)

        situation.add_timeline_event(TimelineEvent(
            timestamp=sig_ts,
            description=sig_text or f"{sig_type} signal",
            event_type=event_type,
            evidence_ref=sig_id,
            source=sig_type,
        ))

        # 3. Check if this signal resolves any existing unknowns
        self._check_unknown_resolution(situation, signal, delta)

        # 4. Check if this signal introduces new unknowns
        self._check_new_unknowns(situation, signal, delta)

        # 5. Evaluate state transition
        transition = self._evaluate_transition(situation, signal, delta)
        if transition:
            delta.transition = transition

        # 6. Update material_changes
        if delta.material_change_description:
            situation.material_changes.append(delta.material_change_description)

        situation.updated_at = datetime.now(timezone.utc)
        situation.snapshot_version += 1
        return delta

    def _check_unknown_resolution(
        self, situation: LivingSituation, signal: Any, delta: SituationDelta
    ) -> None:
        """Check if this signal resolves any existing unknowns."""
        sig_text = (getattr(signal, "text", "") or "").lower()
        sig_type = str(getattr(signal, "type", "")).lower()
        sig_id = getattr(signal, "signal_id", "") or str(id(signal))
        # Audit C-A fix: see note above — real OEM signal_ids are UUID-typed, must stringify.
        if sig_id is not None and not isinstance(sig_id, str):
            sig_id = str(sig_id)

        for unknown in situation.unknowns:
            if unknown.resolved:
                continue
            # Security approval resolved?
            if "security" in unknown.question.lower():
                if "approved" in sig_text or "resolved" in sig_text or "cleared" in sig_text:
                    if situation.resolve_unknown(unknown.question, sig_id):
                        delta.resolved_unknowns.append(unknown.question)
            # Commitment fulfilled?
            if "fulfilled" in unknown.question.lower() or "commitment" in unknown.question.lower():
                if "outcome" in sig_type or "kept" in sig_text or "delivered" in sig_text:
                    if situation.resolve_unknown(unknown.question, sig_id):
                        delta.resolved_unknowns.append(unknown.question)

    def _check_new_unknowns(
        self, situation: LivingSituation, signal: Any, delta: SituationDelta
    ) -> None:
        """Check if this signal introduces new unknowns."""
        sig_text = (getattr(signal, "text", "") or "").lower()
        sig_type = str(getattr(signal, "type", "")).lower()

        # If a completion claim arrives but doesn't mention the prerequisite
        if "complete" in sig_text or "delivered" in sig_text:
            # Check if there's a security unknown that's still unresolved
            has_security_unknown = any(
                "security" in u.question.lower() and not u.resolved
                for u in situation.unknowns
            )
            if has_security_unknown:
                # The completion claim doesn't resolve the security question
                new_q = "Did security approval clear before the completion claim?"
                if not any(u.question == new_q for u in situation.unknowns):
                    situation.add_unknown(Unknown(
                        question=new_q,
                        why_it_matters="Completion claim does not establish prerequisite resolution.",
                        blocking=True,
                        specialists_flagged=["security"],
                    ))
                    delta.new_unknowns.append(new_q)

    def _evaluate_transition(
        self, situation: LivingSituation, signal: Any, delta: SituationDelta
    ) -> Optional[StateTransition]:
        """Evaluate whether the situation should transition based on this signal.

        This implements the CEO's state machine:
          OBSERVING → MATERIAL: new prerequisite/threat
          MATERIAL → NEEDS_PREPARATION: external expectation differs
          NEEDS_PREPARATION → DECISION_PENDING: calendar event imminent
          DECISION_PENDING → ACTION_IN_PROGRESS: meeting starts
          ACTION_IN_PROGRESS → AWAITING_OUTCOME: action complete
          AWAITING_OUTCOME → RESOLVED: outcome evidence arrives

        Returns a StateTransition if one occurred, None otherwise.
        """
        sig_text = (getattr(signal, "text", "") or "").lower()
        sig_type = str(getattr(signal, "type", "")).lower()
        sig_id = getattr(signal, "signal_id", "") or str(id(signal))
        # Audit C-A fix: see note above — real OEM signal_ids are UUID-typed, must stringify.
        if sig_id is not None and not isinstance(sig_id, str):
            sig_id = str(sig_id)
        current = situation.state

        # ── OBSERVING → MATERIAL ──────────────────────────────────────────
        # Trigger: new prerequisite/threat (security, legal, compliance)
        if current == SituationState.OBSERVING:
            if any(kw in sig_text or kw in sig_type for kw in
                   ["security", "conditional", "prerequisite", "approval required"]):
                delta.material_change_description = (
                    f"New prerequisite detected: {sig_text[:80]}"
                )
                return situation.transition_to(
                    SituationState.MATERIAL,
                    reason="New prerequisite threatens commitment feasibility",
                    triggering_evidence_ref=sig_id,
                    side_states_added=[SideState.BLOCKED] if situation.has_blocking_unknown() else [],
                )

        # ── MATERIAL → NEEDS_PREPARATION ──────────────────────────────────
        # Trigger: external expectation differs from internal state
        # (a NEW dimension of conflict, not just a new unknown about the
        # same dimension. The Globex Day 50 completion claim adds a new
        # unknown about the SAME security prereq — that doesn't trigger
        # the transition. Day 55's "customer defines availability as
        # production access" introduces a NEW dimension — that does.)
        if current == SituationState.MATERIAL:
            if any(kw in sig_text for kw in
                   ["availability", "expectation", "production", "define"]):
                delta.material_change_description = (
                    f"External expectation may differ from internal state: {sig_text[:80]}"
                )
                return situation.transition_to(
                    SituationState.NEEDS_PREPARATION,
                    reason="External expectation may differ from internal completion state",
                    triggering_evidence_ref=sig_id,
                )

        # ── NEEDS_PREPARATION → DECISION_PENDING ──────────────────────────
        # Trigger: calendar event (meeting) is imminent
        if current == SituationState.NEEDS_PREPARATION:
            if any(kw in sig_text or kw in sig_type for kw in
                   ["meeting", "tomorrow", "scheduled", "calendar"]):
                delta.material_change_description = "Imminent meeting requires decision preparation"
                situation.recommended_delivery = DeliveryRoute.PREPARE
                return situation.transition_to(
                    SituationState.DECISION_PENDING,
                    reason="Imminent meeting requires decision preparation",
                    triggering_evidence_ref=sig_id,
                )

        # ── DECISION_PENDING → ACTION_IN_PROGRESS ────────────────────────
        # Trigger: meeting starts / action is taken
        if current == SituationState.DECISION_PENDING:
            if any(kw in sig_text or kw in sig_type for kw in
                   ["meeting started", "in progress", "live", "active"]):
                delta.material_change_description = "Meeting/action is now in progress"
                situation.recommended_delivery = DeliveryRoute.WHISPER
                return situation.transition_to(
                    SituationState.ACTION_IN_PROGRESS,
                    reason="Meeting/action is now in progress",
                    triggering_evidence_ref=sig_id,
                )

        # ── ACTION_IN_PROGRESS → AWAITING_OUTCOME ────────────────────────
        # Trigger: action complete, outcome unknown
        if current == SituationState.ACTION_IN_PROGRESS:
            if any(kw in sig_text or kw in sig_type for kw in
                   ["meeting ended", "concluded", "finished", "wrapped"]):
                delta.material_change_description = "Action complete, awaiting outcome"
                return situation.transition_to(
                    SituationState.AWAITING_OUTCOME,
                    reason="Action complete, awaiting outcome",
                    triggering_evidence_ref=sig_id,
                )

        # ── AWAITING_OUTCOME → RESOLVED ──────────────────────────────────
        # Trigger: outcome evidence arrives (renewal won/lost, commitment kept/broken)
        if current == SituationState.AWAITING_OUTCOME:
            if any(kw in sig_text or kw in sig_type for kw in
                   ["renewed", "churned", "kept", "broken", "resolved", "accepted"]):
                delta.material_change_description = f"Outcome resolved: {sig_text[:80]}"
                return situation.transition_to(
                    SituationState.RESOLVED,
                    reason=f"Outcome evidence: {sig_text[:80]}",
                    triggering_evidence_ref=sig_id,
                )

        # ── RESOLVED → LEARNING ──────────────────────────────────────────
        # Trigger: feeding to learning loop (manual or automated)
        if current == SituationState.RESOLVED:
            if "learning" in sig_text or "pattern" in sig_type:
                delta.material_change_description = "Feeding outcome to learning loop"
                return situation.transition_to(
                    SituationState.LEARNING,
                    reason="Feeding outcome to learning loop",
                    triggering_evidence_ref=sig_id,
                )

        # ── LEARNING → ARCHIVED ──────────────────────────────────────────
        if current == SituationState.LEARNING:
            if "archived" in sig_text or "complete" in sig_type:
                delta.material_change_description = "Learning complete, archiving"
                return situation.transition_to(
                    SituationState.ARCHIVED,
                    reason="Learning complete, situation archived",
                    triggering_evidence_ref=sig_id,
                )

        # No transition — but still log the material change if any
        if not delta.material_change_description:
            # Check if the signal is a completion claim that doesn't resolve prereqs
            if "complete" in sig_text or "delivered" in sig_text:
                delta.material_change_description = (
                    f"Completion claim received but does not establish prerequisite resolution: {sig_text[:60]}"
                )
            else:
                delta.material_change_description = f"Signal observed (no state transition): {sig_text[:60]}"

        return None

    # ── Specialist routing ──────────────────────────────────────────────────

    def route_specialists(self, situation: LivingSituation) -> list[str]:
        """Determine which specialists are relevant for this situation.

        Per Arena.ai audit condition 1 (2026-07-08): promote ConsequencePathRouter
        from fallback to PRIMARY routing mechanism. The prior keyword-based
        routing missed consequence specialists (e.g., Legal on an Auth change)
        when keywords weren't present in the situation text.

        Now: ConsequencePathRouter is the primary path. Keyword routing is
        retained as a fallback for cases where the router returns no specialists
        (e.g., if the organizational relationship graph doesn't cover the entity).
        """
        relevant: set[str] = {"chief_of_staff"}

        # PRIMARY: ConsequencePathRouter — traverses the organizational
        # relationship graph to find specialists affected by the situation.
        try:
            from .consequence_path_router import ConsequencePathRouter
            router = ConsequencePathRouter()
            routing_result = router.route(situation)
            for specialist in routing_result.specialists:
                relevant.add(specialist)
        except Exception as e:
            logger.debug("ConsequencePathRouter failed, falling back to keywords: %s", e)
            # FALLBACK: keyword-based routing (the prior primary path)
            text_bag = (
                situation.title + " "
                + " ".join(f.statement for f in situation.known_facts) + " "
                + " ".join(e.description for e in situation.timeline)
            ).lower()

            for specialist, keywords in SPECIALIST_DOMAIN_MAP.items():
                if not keywords:
                    continue
                if any(kw in text_bag for kw in keywords):
                    relevant.add(specialist)

        # Always include customer_success and sales for entity-backed situations
        # (these are relevant for any customer-facing situation)
        if situation.entity:
            relevant.add("customer_success")
            relevant.add("sales")

        return sorted(relevant)

    # ── Situation retrieval ─────────────────────────────────────────────────

    def get_situation(self, situation_id: str) -> Optional[LivingSituation]:
        """Retrieve a situation by ID."""
        return self._situations.get(situation_id)

    def get_active_situations(self, org_id: str = "default") -> list[LivingSituation]:
        """Get all situations that are not resolved, learning, or archived."""
        terminal = {SituationState.RESOLVED, SituationState.LEARNING, SituationState.ARCHIVED}
        return [
            s for s in self._situations.values()
            if s.org_id == org_id and s.state not in terminal
        ]

    def get_situations_needing_preparation(self, org_id: str = "default") -> list[LivingSituation]:
        """Get situations that need preparation."""
        return [
            s for s in self._situations.values()
            if s.org_id == org_id and s.state == SituationState.NEEDS_PREPARATION
        ]

    def get_situations_by_entity(self, entity: str, org_id: str = "default") -> list[LivingSituation]:
        """Get all situations for a specific entity.

        This prevents 'future leakage' — situations don't bleed across entities.
        """
        return [
            s for s in self._situations.values()
            if s.org_id == org_id and s.entity.lower() == entity.lower()
        ]


class _NullOemState:
    """Fallback when OEM state is unavailable."""
    signals: list = []

    def __getattr__(self, name: str) -> Any:
        return None
