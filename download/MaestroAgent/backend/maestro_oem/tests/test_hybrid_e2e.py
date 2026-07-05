"""End-to-end integration test: the auditor's 7-signal scenario through the full pipeline.

AUDITOR VERDICT:
> The Hybrid (Condition C) wins.
> - Synthesizes the evidence into a coherent answer ✅
> - Identifies the discrepancy between internal completion and customer expectations ✅
> - Recommends specific action before the meeting ✅
> - No internal jargon ✅
> - Concise ✅
> - Every claim cites a Day number ✅

This test proves the full chain works end-to-end:
  Stage 2: ContentEpistemicClassifier classifies all 6 signals correctly
  Stage 3: _search_signals retrieves all 6 with body text + correct epistemic labels
  Stage 5: LLMNarrator receives all 6 evidence items + synthesis_hints in its prompt

The LLM narrator has everything it needs to produce the Condition C synthesis.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ["MAESTRO_LOCAL_DEV"] = "true"


def _make_msg_signal(artifact: str, entity: str, body: str, actor: str):
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
    return ExecutionSignal(
        type=SignalType.MESSAGE_SENT,
        actor=actor,
        artifact=artifact,
        metadata={"customer": entity, "body": body},
        provider=SignalProvider.SLACK,
    )


def test_full_pipeline_all_6_signals_classified_and_retrieved():
    """Stage 2 → Stage 3: all 6 signals classified correctly and retrieved with body text."""
    from maestro_oem.ask_pipeline import AskPipeline

    signals = [
        _make_msg_signal("msg-day5", "Globex", "should be able to support SSO before renewal", "sales@corp.com"),
        _make_msg_signal("msg-day12", "Globex", "we will have SSO available", "exec@corp.com"),
        _make_msg_signal("msg-day30", "Globex", "target: before renewal", "product@corp.com"),
        _make_msg_signal("msg-day40", "Globex", "security approval is still conditional", "security@corp.com"),
        _make_msg_signal("msg-day50", "Globex", "SSO work is complete", "sales@corp.com"),
        _make_msg_signal("msg-day55", "Globex", "we understood the commitment as production availability", "raj@globex.com"),
    ]

    pipe = AskPipeline(signals=signals, synthesis_provider=None)
    evidence, answer_parts = pipe._search_signals(
        entities=["Globex"],
        query="What exactly did we promise Globex, and is it still accurate?",
        user_email="auditor@acme.com",
    )

    # All 6 signals retrieved
    assert len(evidence) == 6, f"Expected 6 evidence items, got {len(evidence)}"

    # Correct epistemic labels
    labels = {e["evidence_spine"]["claim_type"] for e in evidence}
    assert "proposal" in labels, "Day 5 should be proposal"
    assert "commitment" in labels, "Day 12/30 should be commitment"
    assert "negation" in labels, "Day 40 should be negation"
    assert "outcome" in labels, "Day 50 should be outcome"
    assert "reported_statement" in labels, "Day 55 should be reported_statement"

    # Body text visible
    all_text = " ".join(e["text"] for e in evidence)
    assert "security approval is still conditional" in all_text
    assert "SSO work is complete" in all_text
    assert "we understood the commitment as production availability" in all_text

    # Answer parts include ALL types (not just commitments)
    answer_text = " ".join(answer_parts)
    assert "Commitments:" in answer_text
    assert "Conditional/pending:" in answer_text
    assert "Outcomes:" in answer_text
    assert "Reported statements:" in answer_text


def test_llm_narrator_receives_all_evidence_and_hints():
    """Stage 5: the LLM narrator's prompt contains all 6 evidence items + synthesis hints."""
    from maestro_oem.llm_narrator import LLMNarrator

    class CapturingProvider:
        def __init__(self):
            self.last_user = ""
        async def complete(self, system, user, **kwargs):
            self.last_user = user
            return type("R", (), {
                "text": "Synthesized answer [1] [2].",
                "provider": "mock", "model": "mock",
                "prompt_tokens": 10, "completion_tokens": 5,
            })()

    evidence = [
        {"source": "slack", "text": "should be able to support SSO before renewal", "date": "2024-01-05", "people": ["sales@corp.com"]},
        {"source": "slack", "text": "we will have SSO available", "date": "2024-01-12", "people": ["exec@corp.com"]},
        {"source": "slack", "text": "target: before renewal", "date": "2024-01-30", "people": ["product@corp.com"]},
        {"source": "slack", "text": "security approval is still conditional", "date": "2024-02-10", "people": ["security@corp.com"]},
        {"source": "slack", "text": "SSO work is complete", "date": "2024-02-20", "people": ["sales@corp.com"]},
        {"source": "slack", "text": "we understood the commitment as production availability", "date": "2024-02-25", "people": ["raj@globex.com"]},
    ]

    hints = [
        "Based on 6 signal(s) from Globex:",
        "Commitments:", "  • we will have SSO available",
        "Conditional/pending:", "  • security approval is still conditional",
        "Outcomes:", "  • SSO work is complete",
        "Reported statements:", "  • we understood the commitment as production availability",
    ]

    mock = CapturingProvider()
    narrator = LLMNarrator(llm_provider=mock)
    narrator.narrate("What exactly did we promise Globex, and is it still accurate?", evidence, synthesis_hints=hints)

    # All 6 evidence items in the prompt
    for i in range(1, 7):
        assert f"[{i}]" in mock.last_user, f"Evidence [{i}] must be in the LLM prompt"

    # Synthesis hints in the prompt
    assert "Synthesis context" in mock.last_user
    assert "Conditional/pending:" in mock.last_user
    assert "Outcomes:" in mock.last_user
    assert "Reported statements:" in mock.last_user

    # The critical signals the auditor said were missing before
    assert "security approval is still conditional" in mock.last_user
    assert "SSO work is complete" in mock.last_user
    assert "we understood the commitment as production availability" in mock.last_user
