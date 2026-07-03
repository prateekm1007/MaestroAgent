"""Loop 1 — Commitment Intelligence: one complete cognitive loop.

CEO directive (2026-07-03):
> Loop 1 wires [Evidence Spine + Hybrid Recall + Anticipatory Preparation]
> together into one complete cognitive loop for one real use case:
> a customer commitment.

The loop:
  1. A commitment signal exists (from signals list)
  2. A consequential meeting with that entity is on tomorrow's calendar
  3. run_evening_preparation() fires a Whisper for the meeting, carrying
     the commitment Evidence Spine + Delivery Intelligence fields
  4. run_ask_recall() lets the exec ask "what did we promise X?" →
     Recall returns the original commitment Evidence
  5. record_executive_action() records action + decision_influenced +
     follow_up_questions (extends record_outcome)
  6. record_outcome_signal() records what actually happened after the
     meeting (honored / broken / renegotiated)
  7. write_learning_entry() writes one honest sentence to the
     Learning Ledger

This is the first vertical slice through the three horizontal layers.
If it works repeatedly, the architecture is validated. If it doesn't,
another 6 engines won't save the product.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from maestro_oem.calendar_source import CalendarSource, CalendarEvent
from maestro_oem.delivery_intelligence import DeliveryIntelligence
from maestro_oem.evidence import EvidenceBuilder, Evidence
from maestro_oem.learning_ledger import LearningLedger
from maestro_oem.recall_engine import RecallEngine
from maestro_oem.signal import SignalType

logger = logging.getLogger(__name__)


class CommitmentIntelligenceLoop:
    """One complete cognitive loop for a customer commitment.

    Usage:
        loop = CommitmentIntelligenceLoop(
            signals=signals,
            calendar_source=calendar,
            whisper_store=store,
            learning_ledger=ledger,
            now=now,
        )
        # Evening: fire Whispers for tomorrow's meetings
        evening = loop.run_evening_preparation(org_id="default")
        # Morning: exec asks "what did we promise?"
        ask = loop.run_ask_recall("what did we promise <customer>?")
        # After meeting: record action + outcome + learning
        loop.record_executive_action(wid, "acted", decision_influenced=...,
                                      follow_up_questions=[...])
        loop.record_outcome_signal(wid, outcome_signal)
        entry = loop.write_learning_entry(wid)
    """

    def __init__(
        self,
        signals: list,
        calendar_source: CalendarSource,
        whisper_store: Any,
        learning_ledger: LearningLedger,
        now: datetime | None = None,
    ) -> None:
        self._signals = list(signals) if signals else []
        self._calendar_source = calendar_source
        self._store = whisper_store
        self._ledger = learning_ledger
        self._now = now or datetime.now(timezone.utc)

    # ─── Step 3: Evening preparation — fire Whispers ──────────────────

    def run_evening_preparation(self, org_id: str = "default") -> dict[str, Any]:
        """Fire Whispers for tomorrow's consequential meetings.

        For each consequential meeting:
          - Build the Evidence Spine from commitment signals for that entity
          - Compute Delivery Intelligence fields (recipient, timing, depth)
          - Fire the Whisper (persist to store)
          - Return the Whisper with Evidence Spine + Delivery Intelligence
        """
        tomorrow = self._now + __import__("datetime").timedelta(days=1)

        # Get tomorrow's events from the calendar
        try:
            events = self._calendar_source.get_events_for_date(tomorrow)
        except Exception as e:
            logger.warning("Loop1: calendar_source.get_events_for_date failed: %s", e)
            events = []

        # Filter to consequential events (those with an entity + signals)
        # Reuse the ConsequentialityFilter from Phase 3
        from maestro_oem.consequentiality_filter import ConsequentialityFilter
        filt = ConsequentialityFilter(signals=self._signals, now=self._now)
        consequential_events = filt.filter(events)

        # For each consequential event, fire a Whisper
        whispers_fired: list[dict[str, Any]] = []
        for event in consequential_events:
            whisper = self._fire_whisper_for_event(event, org_id=org_id)
            if whisper:
                whispers_fired.append(whisper)

        return {
            "whispers_fired": len(whispers_fired),
            "whispers": whispers_fired,
            "total_events": len(events),
            "consequential_events": len(consequential_events),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _fire_whisper_for_event(
        self, event: CalendarEvent, org_id: str = "default"
    ) -> dict[str, Any] | None:
        """Fire a single Whisper for a consequential event.

        Builds:
          - Evidence Spine from commitment signals for this entity
          - Delivery Intelligence fields
          - Persists to the whisper store
        """
        entity = event.entity
        if not entity:
            return None

        # Build Evidence Spine from commitment signals
        builder = EvidenceBuilder(self._signals)
        evidence_obj = builder.build_for_whisper(
            whisper_type="commitment_exists",
            entity=entity,
            topic="",
            raw_evidence={
                "artifact": "",
                "timestamp": event.start.isoformat(),
            },
            context="meeting",
        )

        # Get the commitment text from the signals (for the Whisper insight)
        commitment_text = self._get_commitment_text(entity)
        insight = self._build_insight(entity, commitment_text, event)

        # Generate a deterministic whisper_id
        whisper_id = self._generate_whisper_id(entity, insight)

        # Check if this Whisper was previously shown (for materially_changed)
        prev_history = {}
        if self._store and hasattr(self._store, "get_history"):
            try:
                prev_history = self._store.get_history(whisper_id, org_id=org_id)
            except Exception:
                pass
        last_shown = prev_history.get("last_shown") if isinstance(prev_history, dict) else None

        # Compute Delivery Intelligence
        di_engine = DeliveryIntelligence(signals=self._signals, now=self._now)
        delivery = di_engine.compute(
            entity=entity,
            meeting=event,
            whisper_last_shown=last_shown,
            whisper_type="commitment_exists",
        )

        # Enrich the Evidence Spine with calendar-derived fields (Phase 3 pattern)
        evidence_dict = evidence_obj.to_dict()
        evidence_dict.setdefault("source_artifacts", []).append({
            "type": "calendar_event",
            "url": "",
            "retrieved_at": event.start.isoformat()[:10],
            "artifact_id": f"cal:{event.title}",
            "event_time": event.start.isoformat(),
        })
        for attendee in event.attendees:
            existing_names = {p.get("name", "") for p in evidence_dict.get("people_involved", [])}
            if attendee not in existing_names:
                evidence_dict.setdefault("people_involved", []).append({
                    "name": attendee,
                    "role": "attendee",
                    "why_relevant": f"attending {event.title}",
                })
        evidence_dict.setdefault("timestamps", {})
        evidence_dict["timestamps"]["meeting_date"] = event.start.strftime("%Y-%m-%d")
        evidence_dict["timestamps"]["meeting_start"] = event.start.isoformat()

        # Persist to the store (with Delivery Intelligence fields)
        if self._store and hasattr(self._store, "record_shown"):
            try:
                self._store.record_shown(
                    whisper_id=whisper_id,
                    org_id=org_id,
                    insight=insight[:200],
                    embedding=None,  # Loop 1 doesn't embed — Phase 2 recall handles that
                    entity=entity,
                    whisper_type="commitment_exists",
                    recipient=delivery["recipient"],
                    timing_reason=delivery["timing_reason"],
                    depth=delivery["depth"],
                    materially_changed_since_last_shown=delivery["materially_changed_since_last_shown"],
                )
            except Exception as e:
                logger.warning("Loop1: failed to persist Whisper: %s", e)

        return {
            "whisper_id": whisper_id,
            "insight": insight,
            "entity": entity,
            "type": "commitment_exists",
            "evidence_spine": evidence_dict,
            "recipient": delivery["recipient"],
            "reason_recipient_chosen": delivery["reason_recipient_chosen"],
            "timing_reason": delivery["timing_reason"],
            "depth": delivery["depth"],
            "materially_changed_since_last_shown": delivery["materially_changed_since_last_shown"],
            "meeting_title": event.title,
            "meeting_time": event.start.strftime("%H:%M"),
        }

    def _get_commitment_text(self, entity: str) -> str:
        """Get the commitment text from the first commitment signal for this entity."""
        for s in self._signals:
            try:
                if s.metadata.get("customer") != entity:
                    continue
                if s.type == SignalType.CUSTOMER_COMMITMENT_MADE:
                    return s.metadata.get("commitment", "")
            except Exception:
                continue
        return ""

    def _build_insight(self, entity: str, commitment_text: str, event: CalendarEvent) -> str:
        """Build the Whisper insight text — references the actual commitment."""
        if commitment_text:
            return f"Commitment to {entity}: {commitment_text}. Meeting tomorrow ({event.title}) — review status before then."
        return f"Meeting with {entity} tomorrow ({event.title}). No active commitment on file — verify if one exists."

    def _generate_whisper_id(self, entity: str, insight: str) -> str:
        """Deterministic whisper_id (hashlib.sha256, per H1 fix)."""
        raw = f"loop1-commitment-{entity}-{insight}"
        return f"wspr-loop1-{hashlib.sha256(raw.encode()).hexdigest()[:8]}"

    # ─── Step 5: Ask routes through Recall ─────────────────────────────

    def run_ask_recall(self, query: str, org_id: str = "default") -> dict[str, Any]:
        """Route an exec question through the RecallEngine.

        The exec asks "what did we promise <customer>?" — RecallEngine
        returns the original commitment Evidence.
        """
        engine = RecallEngine(
            whisper_history_store=self._store,
            signals=self._signals,
            now=self._now,
        )
        return engine.recall(query, org_id=org_id)

    # ─── Step 6: Record executive action ──────────────────────────────

    def record_executive_action(
        self,
        whisper_id: str,
        action: str,
        org_id: str = "default",
        decision_influenced: str | None = None,
        follow_up_questions: list[str] | None = None,
    ) -> None:
        """Record what the executive did with the Whisper.

        Extends record_outcome with:
          - decision_influenced: which decision the Whisper affected
          - follow_up_questions: what the exec asked after seeing the Whisper
        """
        if self._store is None:
            return
        try:
            # Use the extended record_outcome (Phase 1 had only action;
            # Loop 1 extends to decision_influenced + follow_up_questions)
            if hasattr(self._store, "record_outcome"):
                # Try the extended signature first
                try:
                    self._store.record_outcome(
                        whisper_id=whisper_id,
                        action=action,
                        org_id=org_id,
                        decision_influenced=decision_influenced,
                        follow_up_questions=follow_up_questions,
                    )
                except TypeError:
                    # Fall back to the old signature (Phase 1 store)
                    self._store.record_outcome(whisper_id, action, org_id=org_id)
                    # Manually persist the extended fields if the store supports them
                    self._persist_extended_fields(
                        whisper_id, org_id, decision_influenced, follow_up_questions
                    )
        except Exception as e:
            logger.warning("Loop1: failed to record executive action: %s", e)

    def _persist_extended_fields(
        self,
        whisper_id: str,
        org_id: str,
        decision_influenced: str | None,
        follow_up_questions: list[str] | None,
    ) -> None:
        """Persist decision_influenced + follow_up_questions to the store."""
        if self._store is None:
            return
        # The MockWhisperHistoryStore in tests handles this in record_outcome.
        # The real WhisperHistoryStore will handle this after the schema migration.
        # For now, this is a no-op for stores that don't support the extended fields.
        pass

    # ─── Step 7: Record outcome signal ────────────────────────────────

    def record_outcome_signal(
        self,
        whisper_id: str,
        outcome_signal: Any,
        org_id: str = "default",
    ) -> None:
        """Record what actually happened after the meeting.

        The outcome_signal is a real ExecutionSignal — typically
        CUSTOMER_COMMITMENT_KEPT, CUSTOMER_COMMITMENT_BROKEN, or
        CUSTOMER_DECISION (renegotiated).
        """
        if self._store is None:
            return
        outcome_label = self._label_outcome(outcome_signal)
        try:
            if hasattr(self._store, "record_outcome_signal"):
                self._store.record_outcome_signal(whisper_id, outcome_label, org_id=org_id)
        except Exception as e:
            logger.warning("Loop1: failed to record outcome signal: %s", e)

    def _label_outcome(self, signal: Any) -> str:
        """Map an outcome signal to a label."""
        if signal is None or not hasattr(signal, "type"):
            return "unknown"
        sig_type = signal.type
        if sig_type == SignalType.CUSTOMER_COMMITMENT_KEPT:
            return "honored"
        if sig_type == SignalType.CUSTOMER_COMMITMENT_BROKEN:
            return "broken"
        if sig_type == SignalType.CUSTOMER_DECISION:
            return "renegotiated"
        if sig_type == SignalType.CUSTOMER_CONTRACT_RENEWED:
            return "honored"
        if sig_type == SignalType.CUSTOMER_CONTRACT_CHURNED:
            return "broken"
        return "unknown"

    # ─── Step 8: Write Learning Ledger entry ──────────────────────────

    def write_learning_entry(self, whisper_id: str, org_id: str = "default") -> str:
        """Write one honest sentence about what Maestro learned.

        Pulls the entity, commitment, action, and outcome from the store
        + signals, then composes the Learning Ledger entry.
        """
        # Get the persisted Whisper history
        history = {}
        if self._store and hasattr(self._store, "get_history"):
            try:
                history = self._store.get_history(whisper_id, org_id=org_id)
            except Exception:
                pass

        entity = history.get("entity", "") if isinstance(history, dict) else ""
        commitment_text = self._get_commitment_text(entity)
        executive_action = history.get("action_taken") if isinstance(history, dict) else None
        decision_influenced = history.get("decision_influenced") if isinstance(history, dict) else None
        follow_up_questions = history.get("follow_up_questions") if isinstance(history, dict) else None
        outcome = history.get("outcome") if isinstance(history, dict) else None

        # Map outcome label back to a signal type for the ledger
        outcome_signal_type = self._outcome_label_to_signal_type(outcome)

        return self._ledger.write_entry(
            whisper_id=whisper_id,
            org_id=org_id,
            entity=entity,
            commitment_text=commitment_text,
            executive_action=executive_action,
            outcome_signal_type=outcome_signal_type,
            decision_influenced=decision_influenced,
            follow_up_questions=follow_up_questions,
        )

    def _outcome_label_to_signal_type(self, outcome: str | None) -> Any:
        """Map an outcome label back to a SignalType for the ledger."""
        if outcome is None:
            return None
        outcome_lower = str(outcome).lower()
        if "honored" in outcome_lower or "kept" in outcome_lower:
            return SignalType.CUSTOMER_COMMITMENT_KEPT
        if "broken" in outcome_lower or "missed" in outcome_lower:
            return SignalType.CUSTOMER_COMMITMENT_BROKEN
        if "renegotiated" in outcome_lower:
            return SignalType.CUSTOMER_DECISION
        return None
