"""
Contradiction learning — Maestro can admit it is wrong.

CEO feedback actions:
  AGREE    — Maestro was right. Confidence strengthens.
  REJECT   — Maestro was wrong. Confidence falls. Law weakens.
  MODIFY   — Maestro was partially right. Confidence adjusts. Law gets counter-example.
  IGNORE   — CEO doesn't care. Confidence unchanged but prediction marked as ignored.

Every action produces a ContradictionEvent that is permanently stored.
History is never overwritten. Every contradiction is preserved.

Effects cascade:
  ContradictionEvent
    ↓
  LearningObject (evidence updated)
    ↓
  Pattern (strength recalculated)
    ↓
  OrganizationalLaw (confidence recalculated, possibly stressed/invalidated)
    ↓
  ExecutionModel (overall confidence recalibrated)
    ↓
  Future recommendations (changed by the feedback)

If enough contradictory evidence appears:
  - Law weakens (status → STRESSED)
  - Law invalidates (status → INVALIDATED)
  - Policy downgrades
  - Confidence recalibrates across the model
  - Future predictions improve (calibration adjusts)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class FeedbackAction(str, Enum):
    """CEO feedback on a recommendation or prediction."""
    AGREE = "agree"       # Maestro was right
    REJECT = "reject"     # Maestro was wrong
    MODIFY = "modify"     # Maestro was partially right
    IGNORE = "ignore"     # CEO doesn't care


class ContradictionEvent(BaseModel):
    """
    A permanent record of CEO feedback on a recommendation or prediction.

    This is append-only. Never overwritten. Never deleted.
    Every contradiction is preserved for audit and learning.
    """
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # What was feedback given on
    target_type: str  # "recommendation", "prediction", "law"
    target_id: str   # rec_id, prediction_id, or law code

    # The feedback
    action: FeedbackAction
    reasoning: str = ""  # CEO's explanation (optional but valuable)

    # What was the predicted outcome
    predicted_confidence: float = 0.0
    predicted_outcome: str = ""

    # What was the actual outcome (filled in later if known)
    actual_outcome: str = ""

    # Cascading effects (filled by the ContradictionEngine)
    affected_laws: list[str] = Field(default_factory=list)
    affected_los: list[UUID] = Field(default_factory=list)
    confidence_before: dict[str, float] = Field(default_factory=dict)  # law_code → confidence before
    confidence_after: dict[str, float] = Field(default_factory=dict)   # law_code → confidence after
    law_status_changes: dict[str, str] = Field(default_factory=dict)   # law_code → new status

    # Metadata
    actor: str = ""  # Who gave the feedback (email)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContradictionLog(BaseModel):
    """
    Append-only log of all contradiction events.

    This is the institutional memory of when Maestro was wrong.
    Never cleared. Never overwritten. Used for:
    - Calibration (SHR computation)
    - Audit trail
    - Learning from past mistakes
    """
    events: list[ContradictionEvent] = Field(default_factory=list)

    def append(self, event: ContradictionEvent) -> None:
        """Add a new contradiction event. Append-only."""
        self.events.append(event)

    def get_events_for_target(self, target_id: str) -> list[ContradictionEvent]:
        """Get all feedback events for a specific target."""
        return [e for e in self.events if e.target_id == target_id]

    def get_rejections(self) -> list[ContradictionEvent]:
        """Get all rejection events."""
        return [e for e in self.events if e.action == FeedbackAction.REJECT]

    def get_agreements(self) -> list[ContradictionEvent]:
        """Get all agreement events."""
        return [e for e in self.events if e.action == FeedbackAction.AGREE]

    def get_modifications(self) -> list[ContradictionEvent]:
        """Get all modification events."""
        return [e for e in self.events if e.action == FeedbackAction.MODIFY]

    def get_ignores(self) -> list[ContradictionEvent]:
        """Get all ignore events."""
        return [e for e in self.events if e.action == FeedbackAction.IGNORE]

    def get_events_for_law(self, law_code: str) -> list[ContradictionEvent]:
        """Get all contradiction events that affected a specific law."""
        return [e for e in self.events if law_code in e.affected_laws]

    def total_events(self) -> int:
        return len(self.events)

    def rejection_count(self) -> int:
        return len(self.get_rejections())

    def agreement_count(self) -> int:
        return len(self.get_agreements())

    def modification_count(self) -> int:
        return len(self.get_modifications())


class ContradictionEngine:
    """
    Processes CEO feedback and cascades the effects through the OEM.

    Usage:
        engine = ContradictionEngine(model, contradiction_log)
        event = engine.apply_feedback(
            target_type="recommendation",
            target_id="rec-abc123",
            action=FeedbackAction.REJECT,
            reasoning="This prediction was wrong — APAC churn didn't increase",
            actor="jane@example.com",
        )
    """

    def __init__(self, model: Any, log: ContradictionLog | None = None) -> None:
        self.model = model
        self.log = log or ContradictionLog()

    def apply_feedback(
        self,
        target_type: str,
        target_id: str,
        action: FeedbackAction,
        reasoning: str = "",
        actor: str = "",
        predicted_confidence: float = 0.0,
        predicted_outcome: str = "",
        actual_outcome: str = "",
    ) -> ContradictionEvent:
        """
        Apply CEO feedback and cascade effects through the OEM.

        Returns the ContradictionEvent (permanently stored in the log).
        """
        # Find linked laws for this target
        linked_laws = self._find_linked_laws(target_type, target_id)

        # Record confidence before
        confidence_before: dict[str, float] = {}
        for law_code in linked_laws:
            law = self.model.laws.get(law_code)
            if law:
                confidence_before[law_code] = law.confidence

        # Create the event
        event = ContradictionEvent(
            target_type=target_type,
            target_id=target_id,
            action=action,
            reasoning=reasoning,
            actor=actor,
            predicted_confidence=predicted_confidence,
            predicted_outcome=predicted_outcome,
            actual_outcome=actual_outcome,
            affected_laws=linked_laws,
            confidence_before=confidence_before,
        )

        # Apply the action's effects
        if action == FeedbackAction.AGREE:
            self._apply_agree(event, linked_laws)
        elif action == FeedbackAction.REJECT:
            self._apply_reject(event, linked_laws)
        elif action == FeedbackAction.MODIFY:
            self._apply_modify(event, linked_laws)
        elif action == FeedbackAction.IGNORE:
            self._apply_ignore(event, linked_laws)

        # Recompute all confidence scores
        self.model._recompute_confidence()

        # Record confidence after
        for law_code in linked_laws:
            law = self.model.laws.get(law_code)
            if law:
                event.confidence_after[law_code] = law.confidence
                if law_code in event.confidence_before:
                    before = event.confidence_before[law_code]
                    after = event.confidence_after[law_code]
                    if before != after:
                        event.law_status_changes[law_code] = law.status.value

        # Permanently store the event
        self.log.append(event)

        return event

    def _find_linked_laws(self, target_type: str, target_id: str) -> list[str]:
        """Find laws linked to a recommendation or prediction."""
        if target_type == "law":
            return [target_id] if target_id in self.model.laws else []

        if target_type == "recommendation":
            # Search for the recommendation in the DecisionEngine's output
            from maestro_oem.decision import DecisionEngine
            dec = DecisionEngine(self.model)
            for rec in dec.get_recommendations():
                if rec.rec_id == target_id:
                    return rec.linked_laws
            # If not found by ID, return all laws (the feedback applies broadly)
            return list(self.model.laws.keys())

        if target_type == "prediction":
            # Predictions are linked to laws via the law's signal_ids
            # For now, return all laws — in production, predictions would track their law links
            return list(self.model.laws.keys())

        return []

    def _apply_agree(self, event: ContradictionEvent, linked_laws: list[str]) -> None:
        """
        CEO agrees — Maestro was right.

        Effects:
        - Laws gain a validation
        - LOs gain supporting evidence
        - Confidence increases
        """
        from maestro_oem.confidence import ConfidenceCalculator

        # P20 fix: compute content_hash for the CEO feedback event so the
        # dedup logic in law.add_validation() fires. Without this, the same
        # CEO feedback event processed twice (e.g., via retry) would inflate
        # validated_runtimes. The hash is derived from the event_id + linked
        # laws so different events produce different hashes.
        import hashlib
        ceo_feedback_hash = hashlib.sha256(
            f"ceo_feedback|{event.event_id}|{'|'.join(sorted(linked_laws))}".encode()
        ).hexdigest()[:16]

        for law_code in linked_laws:
            law = self.model.laws.get(law_code)
            if not law:
                continue

            # Add a validation (P20: pass content_hash for dedup)
            law.add_validation(content_hash=ceo_feedback_hash)

            # If law was stressed, it can recover
            # (handled by add_validation which checks status)

        # Add supporting evidence to LOs linked to these laws
        for lo in self.model.learning_objects.values():
            if any(law_code in lo.metadata.get("linked_laws", []) for law_code in linked_laws):
                lo.add_evidence(event.event_id, "ceo_feedback", content_hash=ceo_feedback_hash)

    def _apply_reject(self, event: ContradictionEvent, linked_laws: list[str]) -> None:
        """
        CEO rejects — Maestro was wrong.

        Effects:
        - Laws gain a counter-example (failed runtime)
        - LOs gain a contradiction
        - Confidence decreases
        - If enough counter-examples: law → STRESSED → INVALIDATED
        - Law drift flag set
        """
        for law_code in linked_laws:
            law = self.model.laws.get(law_code)
            if not law:
                continue

            # Record the failure
            law.add_counter_example()

            # Mark drift
            law.drift_detected = True

            # Add contradiction to linked LOs
            for lo in self.model.learning_objects.values():
                if lo.metadata.get("linked_law") == law_code:
                    lo.add_contradiction()

            # If law is now stressed or invalidated, downgrade patterns
            if law.status.value in ("stressed", "invalidated"):
                self._downgrade_patterns_for_law(law_code)

        # Update risk surface — the rejection itself is a risk signal
        self.model.risks.add_bottleneck_risk(
            "ceo_rejection",
            min(1.0, 0.3 + len(linked_laws) * 0.1),
        )

    def _apply_modify(self, event: ContradictionEvent, linked_laws: list[str]) -> None:
        """
        CEO modifies — Maestro was partially right.

        Effects:
        - Laws gain both a validation and a counter-example (partial)
        - LOs gain both evidence and a contradiction
        - Confidence adjusts slightly downward
        """
        # P20 fix: compute content_hash for partial-feedback events
        import hashlib
        partial_feedback_hash = hashlib.sha256(
            f"partial_feedback|{event.event_id}|{'|'.join(sorted(linked_laws))}".encode()
        ).hexdigest()[:16]

        for law_code in linked_laws:
            law = self.model.laws.get(law_code)
            if not law:
                continue

            # Partial: add both validation and counter-example (P20: pass content_hash)
            law.add_validation(content_hash=partial_feedback_hash)
            law.add_counter_example()

            # Mark drift (mild)
            law.drift_detected = True

    def _apply_ignore(self, event: ContradictionEvent, linked_laws: list[str]) -> None:
        """
        CEO ignores — no strong opinion.

        Effects:
        - No confidence change
        - Event is recorded for audit
        - Law is marked as "not actionable" in metadata
        """
        for law_code in linked_laws:
            law = self.model.laws.get(law_code)
            if law:
                law.metadata.setdefault("ignored_count", 0)
                law.metadata["ignored_count"] += 1
                law.metadata["last_ignored"] = event.timestamp.isoformat()

    def _downgrade_patterns_for_law(self, law_code: str) -> None:
        """When a law is stressed/invalidated, downgrade its patterns."""
        law = self.model.laws.get(law_code)
        if not law:
            return

        for pattern_id in law.pattern_ids:
            for pattern in self.model.pattern_detector.patterns:
                if pattern.pattern_id == pattern_id:
                    # Reduce pattern strength
                    pattern.strength *= 0.5
                    pattern.metadata["downgraded"] = True
                    pattern.metadata["downgrade_reason"] = f"Law {law_code} stressed/invalidated"
                    break

    def get_calibration_impact(self) -> dict[str, Any]:
        """
        Compute how contradiction events have affected calibration.

        Returns:
        - total_feedback: total number of feedback events
        - agreement_rate: fraction of AGREE
        - rejection_rate: fraction of REJECT
        - modification_rate: fraction of MODIFY
        - laws_affected: number of distinct laws affected
        - laws_invalidated: number of laws invalidated due to feedback
        - average_confidence_delta: average change in law confidence after feedback
        """
        events = self.log.events
        if not events:
            return {
                "total_feedback": 0,
                "agreement_rate": 0.0,
                "rejection_rate": 0.0,
                "modification_rate": 0.0,
                "laws_affected": 0,
                "laws_invalidated": 0,
                "average_confidence_delta": 0.0,
            }

        total = len(events)
        agrees = len(self.log.get_agreements())
        rejects = len(self.log.get_rejections())
        modifies = len(self.log.get_modifications())

        all_laws: set[str] = set()
        for e in events:
            all_laws.update(e.affected_laws)

        laws_invalidated = 0
        for law_code in all_laws:
            law = self.model.laws.get(law_code)
            if law and law.status.value == "invalidated":
                laws_invalidated += 1

        # Average confidence delta
        deltas: list[float] = []
        for e in events:
            for law_code in e.affected_laws:
                before = e.confidence_before.get(law_code)
                after = e.confidence_after.get(law_code)
                if before is not None and after is not None:
                    deltas.append(after - before)

        avg_delta = sum(deltas) / len(deltas) if deltas else 0.0

        return {
            "total_feedback": total,
            "agreement_rate": agrees / total,
            "rejection_rate": rejects / total,
            "modification_rate": modifies / total,
            "laws_affected": len(all_laws),
            "laws_invalidated": laws_invalidated,
            "average_confidence_delta": avg_delta,
        }

    def shouldsuppress_law(self, law_code: str) -> bool:
        """
        Should Maestro stop recommending based on this law?

        A law is suppressed if:
        - It's invalidated
        - It has 3+ rejections in the last 30 days
        - Its confidence dropped below 0.3
        """
        law = self.model.laws.get(law_code)
        if not law:
            return True

        if law.status.value == "invalidated":
            return True

        if law.confidence < 0.3:
            return True

        # Check recent rejections
        law_events = self.log.get_events_for_law(law_code)
        recent_rejections = [
            e for e in law_events
            if e.action == FeedbackAction.REJECT
            and (datetime.now(timezone.utc) - e.timestamp).days <= 30
        ]
        if len(recent_rejections) >= 3:
            return True

        return False
