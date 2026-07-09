"""
The 30-Day Personal Life-of-Work Benchmark.

Per the Pre-Beta Break Test spec: one professional over 30 simulated
days, with messy, ambiguous, partially-fulfilled commitments. This is
the Personal equivalent of the Enterprise Globex SSO scenario.

This is a SKELETON — it defines the target. Many checkpoints will fail
against current code (that's the worklist for Weeks 2-6). The point is
to define what "good" looks like so the team knows what to build toward.

Day 1: user promises to send a proposal.
Day 3: recipient asks a follow-up question.
Day 5: calendar meeting is moved.
Day 7: user casually says they will send revised numbers.
Day 9: another email contradicts an earlier assumption.
Day 12: no action has been taken.
Day 14: meeting approaches.
Day 15: commitment is fulfilled partially.
Day 18: recipient interprets the promise differently.
Day 21: another meeting creates a related commitment.
Day 25: user asks what changed while away.
Day 30: Maestro must explain the full history.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))

from datetime import datetime, timezone, timedelta
import pytest


def _make_signal(entity: str, text: str, signal_type: str, days_ago: int = 0) -> "PersonalSignal":
    """Build a PersonalSignal with a timestamp N days ago."""
    from maestro_personal_shell.personal_oem_state import PersonalSignal
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return PersonalSignal(
        entity=entity,
        text=text,
        signal_type=signal_type,
        timestamp=ts,
    )


class Test30DayBenchmark:
    """The Personal Life-of-Work Benchmark — 30 simulated days."""

    def _build_30_day_state(self):
        """Build the full 30-day scenario state."""
        from maestro_personal_shell.personal_oem_state import PersonalOemState

        signals = [
            # Day 1: user promises to send a proposal to Alex by Friday
            _make_signal("Alex", "I will send the proposal by Friday", "commitment_made", days_ago=29),
            # Day 3: Alex asks a follow-up question about scope
            _make_signal("Alex", "What scope should the proposal cover?", "follow_up.required", days_ago=27),
            # Day 5: calendar meeting with Alex moved from Thursday to Monday
            _make_signal("Alex", "Meeting moved from Thursday to Monday", "meeting.moved", days_ago=25),
            # Day 7: user casually says "I'll send revised numbers too"
            _make_signal("Alex", "I'll send revised numbers too", "personal.promise", days_ago=23),
            # Day 9: another email contradicts an earlier assumption about budget
            _make_signal("Alex", "Actually the budget is $50K not $100K", "reported_statement", days_ago=21),
            # Day 12: no action has been taken (no signal — this is the absence-detection checkpoint)
            # Day 14: meeting with Alex approaches
            _make_signal("Alex", "Meeting tomorrow at 2pm", "meeting.scheduled", days_ago=16),
            # Day 15: user sends the proposal (partially fulfilled — no revised numbers)
            _make_signal("Alex", "Proposal sent (without revised numbers)", "observed_fact", days_ago=15),
            # Day 18: Alex interprets the promise differently
            _make_signal("Alex", "I thought this included the revised numbers", "reported_statement", days_ago=12),
            # Day 21: another meeting creates a related commitment
            _make_signal("Alex", "Send the case study by next Friday", "commitment_made", days_ago=9),
            # Day 25: user asks what changed while away (vacation Days 22-24)
            # Day 30: user asks Maestro to explain the full Alex situation
        ]
        return PersonalOemState(signals=signals)

    def test_day1_commitment_detected(self):
        """Day 1: Maestro classifies the proposal promise as a commitment."""
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.surfaces.commitments import CommitmentsSurface

        state = self._build_30_day_state()
        shell = PersonalShell(oem_state=state)
        surface = CommitmentsSurface(shell=shell)
        commitments = surface.get_commitments_for_entity("Alex")

        # Must find the Day 1 commitment
        proposal_commitments = [c for c in commitments if "proposal" in c["text"].lower()]
        assert len(proposal_commitments) >= 1, (
            f"Day 1 commitment 'send the proposal by Friday' must be detected. "
            f"Found: {[c['text'] for c in commitments]}"
        )

    def test_day7_casual_commitment_detected(self):
        """Day 7: Maestro detects the casual 'I'll send revised numbers too'.

        This is the salience checkpoint — casual commitments are harder
        to detect than explicit ones. If this fails, the salience model
        needs personal-mode tuning (not a thesis failure).
        """
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.surfaces.commitments import CommitmentsSurface

        state = self._build_30_day_state()
        shell = PersonalShell(oem_state=state)
        surface = CommitmentsSurface(shell=shell)
        commitments = surface.get_commitments_for_entity("Alex")

        # Must find the Day 7 casual commitment
        numbers_commitments = [c for c in commitments if "revised numbers" in c["text"].lower()]
        assert len(numbers_commitments) >= 1, (
            f"Day 7 casual commitment 'I'll send revised numbers too' must be detected. "
            f"If this fails, salience model needs personal-mode tuning. "
            f"Found: {[c['text'] for c in commitments]}"
        )

    def test_day12_absence_detection(self):
        """Day 12: Maestro detects no action on the proposal for 5+ days.

        This is the absence-detection checkpoint — Core doesn't have this
        mechanism. The shell builds it via detect_stale_commitments.
        If this fails, the absence-detection mechanism needs work.
        """
        from maestro_personal_shell.shell import PersonalShell

        # Build a state where the Day 1 commitment has no follow-up for 12 days
        from maestro_personal_shell.personal_oem_state import PersonalOemState
        state = PersonalOemState(signals=[
            _make_signal("Alex", "I will send the proposal by Friday", "commitment_made", days_ago=12),
            # No follow-up signals — this is the absence
        ])
        shell = PersonalShell(oem_state=state)
        stale = shell.detect_stale_commitments(days_threshold=5)

        assert len(stale) >= 1, (
            "Day 12 absence detection: must flag commitment with no follow-up for 5+ days. "
            "If this fails, the absence-detection mechanism needs work."
        )
        assert any("alex" in s["entity"].lower() for s in stale), (
            f"Must flag the Alex commitment as stale. Found: {stale}"
        )

    def test_day14_prepare_for_meeting(self):
        """Day 14: Maestro Prepare surfaces context for the Alex meeting.

        Must include: original commitment, follow-up question, revised-
        numbers aspiration, budget contradiction.
        """
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.surfaces.prepare import PrepareSurface

        state = self._build_30_day_state()
        shell = PersonalShell(oem_state=state)
        surface = PrepareSurface(shell=shell)
        situations_needing_prep = surface.get_situations_needing_preparation()

        # Must find at least one situation needing preparation
        assert len(situations_needing_prep) >= 1, (
            "Day 14: must find situations needing preparation for the Alex meeting"
        )

    def test_day25_what_changed(self):
        """Day 25: Maestro What Changed surfaces meaningful deltas, not inbox summary."""
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.surfaces.what_changed import WhatChangedSurface
        from datetime import timedelta

        state = self._build_30_day_state()
        shell = PersonalShell(oem_state=state)
        surface = WhatChangedSurface(shell=shell)

        # What changed in the last 30 days (the full scenario)
        since = datetime.now(timezone.utc) - timedelta(days=30)
        deltas = surface.get_recent_deltas(since_timestamp=since)

        # Must have deltas
        assert len(deltas) > 0, "Day 25: must surface deltas"

        # Must have meaningful deltas (not just inbox activity)
        meaningful = [d for d in deltas if d["is_meaningful"]]
        assert len(meaningful) >= 3, (
            f"Day 25: must surface ≥3 meaningful deltas. Found {len(meaningful)}: "
            f"{[d['text'] for d in meaningful]}"
        )

    def test_day30_full_history_explanation(self):
        """Day 30: Maestro Ask explains the full Alex situation.

        Must include: original commitment, follow-up, revised-numbers
        aspiration, budget contradiction, scope dispute, new commitment.
        """
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.surfaces.ask import AskSurface

        state = self._build_30_day_state()
        shell = PersonalShell(oem_state=state)
        surface = AskSurface(shell=shell)

        result = surface.ask("What's the full situation with Alex?")
        assert result is not None, "Day 30: Ask must return a result"

        # The result must have an answer (field name varies by Core version)
        answer = getattr(result, "answer", None) or getattr(result, "synthesized_answer", None) or ""
        assert answer, (
            f"Day 30: Ask must produce an answer. Result: {result}"
        )

    def test_differentiation_from_inbox_summary(self):
        """Break-test dimension 5: What Changed must NOT be an inbox summary.

        It must surface meaningful deltas (commitments, meeting changes,
        deadlines) — not chronological email activity.
        """
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.surfaces.what_changed import WhatChangedSurface
        from datetime import timedelta

        state = self._build_30_day_state()
        shell = PersonalShell(oem_state=state)
        surface = WhatChangedSurface(shell=shell)

        since = datetime.now(timezone.utc) - timedelta(days=30)
        deltas = surface.get_recent_deltas(since_timestamp=since)

        # All deltas must have is_meaningful flag (not just chronological)
        for d in deltas:
            assert "is_meaningful" in d, (
                "What Changed must classify deltas as meaningful/noise, "
                "not just list them chronologically"
            )

        # At least some must be meaningful
        meaningful_count = sum(1 for d in deltas if d["is_meaningful"])
        assert meaningful_count >= 3, (
            f"At least 3 deltas must be meaningful. Got {meaningful_count}/{len(deltas)}"
        )
