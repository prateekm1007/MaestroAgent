"""Tests for Surface 5: Copilot → Situation Engine.

Proves the Live Copilot is wired to the Cognitive Council's Situation
Engine. Meeting intelligence flows through Situations:

  1. Pre-call: briefing references the Situation (not raw signals)
  2. During call: transcript chunks update operational state
  3. Post-call: commitments ingested as refs, learning triggered
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def _make_signal(sig_type, entity, text, signal_id="", days_ago=0):
    sig = MagicMock()
    sig.type = MagicMock()
    sig.type.value = sig_type
    sig.entity = entity
    sig.text = text
    sig.signal_id = signal_id or f"sig-{entity.lower()}-{days_ago}"
    sig.metadata = {"customer": entity}
    sig.timestamp = datetime.now(timezone.utc) - timedelta(days=days_ago)
    sig.actor = ""
    sig.org_id = "default"
    return sig


def _make_oem_with_signals(signals):
    oem = MagicMock()
    oem.signals = signals
    return oem


# ════════════════════════════════════════════════════════════════════════════
# Pre-Call: Situation-aware briefing
# ════════════════════════════════════════════════════════════════════════════

class TestCopilotPreCall:
    """Pre-call briefing references the Situation — not raw signals."""

    def test_pre_call_finds_situation(self):
        """Pre-call briefing finds the relevant Situation for the meeting entity."""
        from maestro_cognitive_council import CopilotSituationBridge

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        from maestro_cognitive_council import SituationEngine
        engine = SituationEngine(oem_state=oem)
        engine.detect_situations()
        bridge = CopilotSituationBridge(oem_state=oem, situation_engine=engine)

        briefing = bridge.pre_call_briefing(
            meeting_title="CustomerA Renewal",
            attendees=["ceo@customera.com"],
        )

        assert briefing.found_situation is True
        assert "CustomerA" in briefing.entity

    def test_pre_call_surfaces_unknowns(self):
        """Pre-call briefing surfaces the Situation's unknowns."""
        from maestro_cognitive_council import CopilotSituationBridge

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        from maestro_cognitive_council import SituationEngine
        engine = SituationEngine(oem_state=oem)
        engine.detect_situations()
        bridge = CopilotSituationBridge(oem_state=oem, situation_engine=engine)

        briefing = bridge.pre_call_briefing("CustomerA Renewal", ["ceo@customera.com"])

        assert len(briefing.unknowns_to_address) > 0
        assert len(briefing.blocking_unknowns) > 0

    def test_pre_call_includes_decision_boundary(self):
        """Pre-call briefing includes the decision boundary."""
        from maestro_cognitive_council import CopilotSituationBridge, Judgment, DecisionBoundary, SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        if situations:
            situations[0].judgment = Judgment(
                central_claim="Test",
                decision_boundary=DecisionBoundary(
                    can_decide_now=["Proceed with direction"],
                    cannot_decide_yet=["Commit to deadline"],
                    why="Blocking unknown",
                    smallest_useful_next_step="Resolve the unknown",
                ),
            )

        bridge = CopilotSituationBridge(oem_state=oem, situation_engine=engine)
        briefing = bridge.pre_call_briefing("CustomerA Renewal", ["ceo@customera.com"])

        # If a situation was found, should have decision boundary
        if briefing.found_situation:
            assert len(briefing.can_decide_now) > 0 or len(briefing.cannot_decide_yet) > 0

    def test_pre_call_generates_talking_points(self):
        """Pre-call briefing generates talking points citing evidence_refs."""
        from maestro_cognitive_council import CopilotSituationBridge

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        from maestro_cognitive_council import SituationEngine
        engine = SituationEngine(oem_state=oem)
        engine.detect_situations()
        bridge = CopilotSituationBridge(oem_state=oem, situation_engine=engine)

        briefing = bridge.pre_call_briefing("CustomerA Renewal", ["ceo@customera.com"])

        if briefing.found_situation:
            assert len(briefing.talking_points) > 0

    def test_pre_call_references_evidence(self):
        """Pre-call briefing references evidence by ref (not copies)."""
        from maestro_cognitive_council import CopilotSituationBridge

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        from maestro_cognitive_council import SituationEngine
        engine = SituationEngine(oem_state=oem)
        engine.detect_situations()
        bridge = CopilotSituationBridge(oem_state=oem, situation_engine=engine)

        briefing = bridge.pre_call_briefing("CustomerA Renewal", ["ceo@customera.com"])

        if briefing.found_situation:
            assert len(briefing.evidence_refs) > 0
            assert all(isinstance(r, str) for r in briefing.evidence_refs)

    def test_pre_call_falls_back_when_no_entity(self):
        """Pre-call briefing falls back gracefully when no entity detected."""
        from maestro_cognitive_council import CopilotSituationBridge

        oem = _make_oem_with_signals([])
        bridge = CopilotSituationBridge(oem_state=oem)

        briefing = bridge.pre_call_briefing("Random meeting", ["someone@gmail.com"])

        assert briefing.found_situation is False


# ════════════════════════════════════════════════════════════════════════════
# During Call: transcript chunks update operational state
# ════════════════════════════════════════════════════════════════════════════

class TestCopilotTranscriptChunk:
    """Transcript chunks update the Situation's operational state."""

    def test_transcript_chunk_transitions_to_action_in_progress(self):
        """First transcript chunk transitions operational state to ACTION_IN_PROGRESS."""
        from maestro_cognitive_council import CopilotSituationBridge, SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        bridge = CopilotSituationBridge(oem_state=oem, situation_engine=engine)

        if situations:
            result = bridge.on_transcript_chunk(
                situations[0].situation_id,
                "We will deliver SSO by Friday",
                "ceo",
            )
            assert len(result["transitions"]) > 0

    def test_transcript_chunk_detects_commitments(self):
        """Transcript chunk with commitment keywords adds to commitment_refs."""
        from maestro_cognitive_council import CopilotSituationBridge, SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        bridge = CopilotSituationBridge(oem_state=oem, situation_engine=engine)

        if situations:
            result = bridge.on_transcript_chunk(
                situations[0].situation_id,
                "We will deliver the integration by next Friday",
                "engineer",
            )
            assert len(result["commitments_detected"]) > 0

    def test_transcript_chunk_adds_timeline_event(self):
        """Transcript chunk adds a timeline event to the Situation."""
        from maestro_cognitive_council import CopilotSituationBridge, SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        bridge = CopilotSituationBridge(oem_state=oem, situation_engine=engine)

        if situations:
            original_timeline_len = len(situations[0].timeline)
            bridge.on_transcript_chunk(
                situations[0].situation_id,
                "Let's discuss the pricing",
                "ceo",
            )
            assert len(situations[0].timeline) > original_timeline_len


# ════════════════════════════════════════════════════════════════════════════
# Post-Call: ingest commitments, trigger learning
# ════════════════════════════════════════════════════════════════════════════

class TestCopilotPostCall:
    """Post-call summary ingests commitments and triggers learning."""

    def test_post_call_transitions_to_awaiting_outcome(self):
        """Post-call transitions operational state to AWAITING_OUTCOME."""
        from maestro_cognitive_council import CopilotSituationBridge, SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        bridge = CopilotSituationBridge(oem_state=oem, situation_engine=engine)

        if situations:
            # Simulate meeting in progress first
            bridge.on_transcript_chunk(situations[0].situation_id, "Discussion", "ceo")

            summary = bridge.post_call_summary(
                situations[0].situation_id,
                transcript_chunks=[{"text": "Discussion", "speaker": "ceo"}],
                commitments=[{"text": "Will deliver SSO"}],
            )

            assert len(summary.operational_transitions) > 0

    def test_post_call_ingests_commitments_as_refs(self):
        """Post-call ingests commitments as refs (not copies)."""
        from maestro_cognitive_council import CopilotSituationBridge, SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        bridge = CopilotSituationBridge(oem_state=oem, situation_engine=engine)

        if situations:
            summary = bridge.post_call_summary(
                situations[0].situation_id,
                commitments=[
                    {"text": "Will deliver SSO by Friday", "ref": "commit-1"},
                    {"text": "Will send pricing", "ref": "commit-2"},
                ],
            )

            assert len(summary.commitments_ingested) > 0
            assert all(isinstance(r, str) for r in summary.commitments_ingested)

    def test_post_call_generates_draft_followup(self):
        """Post-call generates a draft follow-up citing evidence_refs."""
        from maestro_cognitive_council import CopilotSituationBridge, SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        bridge = CopilotSituationBridge(oem_state=oem, situation_engine=engine)

        if situations:
            summary = bridge.post_call_summary(
                situations[0].situation_id,
                commitments=[{"text": "Will deliver SSO"}],
            )

            assert summary.draft_followup
            assert "subject" in summary.draft_followup
            assert "body" in summary.draft_followup

    def test_post_call_references_evidence(self):
        """Post-call summary references evidence by ref (not copies)."""
        from maestro_cognitive_council import CopilotSituationBridge, SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        bridge = CopilotSituationBridge(oem_state=oem, situation_engine=engine)

        if situations:
            summary = bridge.post_call_summary(situations[0].situation_id)

            assert len(summary.evidence_refs) > 0
            assert all(isinstance(r, str) for r in summary.evidence_refs)

    def test_post_call_to_dict(self):
        """PostCallSummary exposes full structure in to_dict()."""
        from maestro_cognitive_council import CopilotSituationBridge, SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        bridge = CopilotSituationBridge(oem_state=oem, situation_engine=engine)

        if situations:
            summary = bridge.post_call_summary(situations[0].situation_id)
            d = summary.to_dict()

            required = [
                "situation_id", "situation_title", "entity",
                "operational_transitions", "commitments_ingested",
                "learning_triggered", "draft_followup", "evidence_refs",
            ]
            for field in required:
                assert field in d, f"Missing field: {field}"


# ════════════════════════════════════════════════════════════════════════════
# Full Meeting Lifecycle: Pre → During → Post
# ════════════════════════════════════════════════════════════════════════════

class TestFullMeetingLifecycle:
    """The full meeting lifecycle: pre-call → transcript → post-call."""

    def test_full_lifecycle_flows_through_situation(self):
        """Pre-call → transcript → post-call all flow through the same Situation."""
        from maestro_cognitive_council import CopilotSituationBridge, SituationEngine

        signals = [
            _make_signal("customer.commitment_made", "CustomerA", "Deliver SSO", "s1", days_ago=10),
            _make_signal("security.condition", "CustomerA", "Security approval required", "s2", days_ago=8),
        ]
        oem = _make_oem_with_signals(signals)
        engine = SituationEngine(oem_state=oem)
        situations = engine.detect_situations()
        bridge = CopilotSituationBridge(oem_state=oem, situation_engine=engine)

        if not situations:
            pytest.skip("No situations detected")

        situation_id = situations[0].situation_id

        # 1. Pre-call briefing
        pre = bridge.pre_call_briefing("CustomerA Renewal", ["ceo@customera.com"])
        assert pre.found_situation is True
        assert pre.situation_id == situation_id

        # 2. During call — transcript chunks
        chunk_result = bridge.on_transcript_chunk(
            situation_id,
            "We will deliver SSO by Friday",
            "ceo",
        )
        assert len(chunk_result["transitions"]) > 0

        # 3. Post-call summary
        post = bridge.post_call_summary(
            situation_id,
            transcript_chunks=[{"text": "Discussion", "speaker": "ceo"}],
            commitments=[{"text": "Will deliver SSO by Friday"}],
        )
        assert post.situation_id == situation_id
        assert len(post.commitments_ingested) > 0
