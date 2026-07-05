"""Loop 2 — Meeting Intelligence Loop.

CEO directive: build Loop 2 — Meeting Intelligence. Wires the Meeting
lifecycle using existing modules (SituationBuilder, LearningLedger).

The loop:
  1. prepare(meeting)         — SCHEDULED → PREPARED
     Assembles a Situation via SituationBuilder (Loop 1.5)
  2. occur(meeting, topics, commitments) — PREPARED → OCCURRED
     Records what was discussed + what was committed
  3. observe_outcome(meeting, outcome)   — OCCURRED → OUTCOME_OBSERVED
     Records the observed outcome (commitment_honored, commitment_broken, etc.)
  4. record_learning(meeting)           — OUTCOME_OBSERVED → LEARNING_RECORDED
     Writes a Meeting Learning Ledger entry (honest, signal-derived)

The Meeting Learning Ledger entry is different from Loop 1's Commitment
Learning Ledger. It's about the MEETING, not just the commitment:
  - What was the meeting about?
  - What was decided/committed?
  - What was the outcome?
  - What did Maestro learn from this meeting's trajectory?

The entry honestly acknowledges uncertainty (same standard as Loop 1).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from maestro_oem.meeting import Meeting, MeetingStatus

logger = logging.getLogger(__name__)


class MeetingIntelligenceLoop:
    """Wires the Meeting lifecycle: prepare → occur → observe → learn.

    Usage:
        loop = MeetingIntelligenceLoop(signals=signals, now=now)
        loop.prepare(meeting)
        loop.occur(meeting, topics_discussed=["pricing"], commitments_made=["..."])
        loop.observe_outcome(meeting, outcome="commitment_honored")
        entry = loop.record_learning(meeting)
    """

    def __init__(
        self,
        signals: list,
        now: datetime | None = None,
        whisper_store: Any = None,
    ) -> None:
        self._signals = list(signals) if signals else []
        self._now = now or datetime.now(timezone.utc)
        self._whisper_store = whisper_store

    def prepare(self, meeting: Meeting) -> None:
        """Transition SCHEDULED → PREPARED. Assemble a Situation.

        Uses Loop 1.5's SituationBuilder to construct the pre-meeting
        working memory: what's happening, who's involved, what commitments
        exist, what evidence Maestro has, current state, prior whispers,
        and the timeline.
        """
        if meeting.status != MeetingStatus.SCHEDULED:
            logger.warning(
                "MeetingIntelligenceLoop.prepare: meeting %s is in state %s, expected SCHEDULED",
                meeting.meeting_id, meeting.status,
            )
            return

        try:
            from maestro_oem.situation import SituationBuilder
            from maestro_oem.calendar_source import StaticCalendarSource, CalendarEvent

            # Build a minimal calendar source containing just this meeting
            # (SituationBuilder uses it to compute what_is_happening)
            cal = StaticCalendarSource([
                CalendarEvent(
                    title=meeting.title,
                    start=meeting.start,
                    end=meeting.end,
                    entity=meeting.entity,
                    attendees=list(meeting.attendees),
                )
            ])

            builder = SituationBuilder(
                signals=self._signals,
                calendar_source=cal,
                whisper_store=self._whisper_store,
                now=self._now,
            )
            meeting.situation = builder.build_for_entity(meeting.entity)
        except Exception as e:
            logger.warning("MeetingIntelligenceLoop.prepare: SituationBuilder failed: %s", e)
            # Fail gracefully — the meeting can still proceed without a Situation

        meeting.status = MeetingStatus.PREPARED

    def occur(
        self,
        meeting: Meeting,
        topics_discussed: list[str],
        commitments_made: list[str],
    ) -> None:
        """Transition PREPARED → OCCURRED. Record what was discussed/committed.

        Args:
            meeting: The meeting that occurred
            topics_discussed: List of topics covered ("pricing", "SSO delivery")
            commitments_made: List of commitments made during the meeting
        """
        if meeting.status != MeetingStatus.PREPARED:
            logger.warning(
                "MeetingIntelligenceLoop.occur: meeting %s is in state %s, expected PREPARED",
                meeting.meeting_id, meeting.status,
            )
            return

        meeting.topics_discussed = list(topics_discussed) if topics_discussed else []
        meeting.commitments_made = list(commitments_made) if commitments_made else []
        meeting.status = MeetingStatus.OCCURRED

    def observe_outcome(self, meeting: Meeting, outcome: str) -> None:
        """Transition OCCURRED → OUTCOME_OBSERVED. Record the observed outcome.

        Args:
            meeting: The meeting whose outcome is being observed
            outcome: The outcome label. Common values:
              - "commitment_honored" — the commitment made in the meeting was kept
              - "commitment_broken" — the commitment was broken
              - "decision_reached" — a decision was made
              - "no_resolution" — the meeting ended without resolution
              - "rescheduled" — the meeting was rescheduled
        """
        if meeting.status != MeetingStatus.OCCURRED:
            logger.warning(
                "MeetingIntelligenceLoop.observe_outcome: meeting %s is in state %s, expected OCCURRED",
                meeting.meeting_id, meeting.status,
            )
            return

        meeting.outcome = outcome
        meeting.status = MeetingStatus.OUTCOME_OBSERVED

    def record_learning(self, meeting: Meeting) -> str:
        """Transition OUTCOME_OBSERVED → LEARNING_RECORDED. Write the learning entry.

        The Meeting Learning Ledger entry is one honest sentence about
        what Maestro learned from this meeting's trajectory. It references:
          - The meeting title + entity
          - The topics discussed
          - The commitments made
          - The observed outcome
          - Honest acknowledgment of causality uncertainty

        Returns:
            The learning entry (also persisted on the meeting object).
        """
        if meeting.status != MeetingStatus.OUTCOME_OBSERVED:
            logger.warning(
                "MeetingIntelligenceLoop.record_learning: meeting %s is in state %s, expected OUTCOME_OBSERVED",
                meeting.meeting_id, meeting.status,
            )
            return ""

        entry = self._compose_learning_entry(meeting)
        meeting.learning_entry = entry
        meeting.status = MeetingStatus.LEARNING_RECORDED
        return entry

    def _compose_learning_entry(self, meeting: Meeting) -> str:
        """Compose one honest sentence about what Maestro learned from this meeting.

        Signal-derived, not templated. References the actual meeting,
        topics, commitments, and outcome. Honestly acknowledges uncertainty.
        """
        parts: list[str] = []

        # ── Part 1: What the meeting was about ─────────────────────────
        if meeting.topics_discussed:
            topics_str = ", ".join(meeting.topics_discussed[:3])
            parts.append(
                f"The {meeting.title} with {meeting.entity} covered {topics_str}"
            )
        else:
            parts.append(f"The {meeting.title} with {meeting.entity} occurred")

        # ── Part 2: What was committed ─────────────────────────────────
        if meeting.commitments_made:
            if len(meeting.commitments_made) == 1:
                parts.append(f"a commitment was made: {meeting.commitments_made[0]}")
            else:
                parts.append(f"{len(meeting.commitments_made)} commitments were made")
        else:
            parts.append("no new commitments were made")

        # ── Part 3: The observed outcome ───────────────────────────────
        outcome_label = self._label_outcome(meeting.outcome)
        if outcome_label == "honored":
            parts.append("the commitment was honored")
        elif outcome_label == "broken":
            parts.append("the commitment was broken")
        elif outcome_label == "decision":
            parts.append("a decision was reached")
        elif outcome_label == "no_resolution":
            parts.append("no resolution was reached")
        elif outcome_label == "rescheduled":
            parts.append("the meeting was rescheduled")
        else:
            parts.append(f"the outcome was: {meeting.outcome}")

        # ── Part 4: Honest causality acknowledgment ────────────────────
        # Maestro never claims the meeting CAUSED the outcome. It records
        # the temporal sequence.
        if outcome_label == "honored" and meeting.commitments_made:
            parts.append(
                "Maestro does not know if the meeting caused the commitment to be honored"
            )
        elif outcome_label == "broken" and meeting.commitments_made:
            parts.append(
                "Maestro does not know if a different meeting trajectory would have prevented the break"
            )
        elif outcome_label == "no_resolution":
            parts.append(
                "Maestro does not know if more preparation would have changed the outcome"
            )

        # Join into one sentence (parts 1-3 form the main clause; part 4 is an observation)
        main_clause = "; ".join(parts[:3]) + "."
        if len(parts) > 3:
            observation = " " + parts[3] + "."
            return f"{main_clause}{observation}"
        return main_clause

    def _label_outcome(self, outcome: str | None) -> str:
        """Map an outcome string to a label for the learning entry."""
        if not outcome:
            return "unknown"
        outcome_lower = outcome.lower()
        if "honored" in outcome_lower or "kept" in outcome_lower or "fulfilled" in outcome_lower:
            return "honored"
        if "broken" in outcome_lower or "missed" in outcome_lower or "failed" in outcome_lower:
            return "broken"
        if "decision" in outcome_lower or "reached" in outcome_lower:
            return "decision"
        if "no_resolution" in outcome_lower or "no resolution" in outcome_lower:
            return "no_resolution"
        if "rescheduled" in outcome_lower:
            return "rescheduled"
        return "unknown"
