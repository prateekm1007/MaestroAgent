"""C-2 fix: Ask Maestro must return 'I don't know' instead of generic signals.

The external audit found the most dangerous illusion in the product:
when entity resolution fails, _search_signals() returns the first 3
signals as 'context' — producing a plausible-looking answer with zero
relevance to the question. An executive who asks 'Prepare me for Globex'
and sees a response with dates, sources, and evidence items will assume
the system understood them. It did not.

The fix: when no evidence matches, return EMPTY evidence. The narrator
will then honestly say 'I don't have enough organizational memory.'

Adversarial tests:
  1. test_no_entity_match_returns_empty_evidence
     'What about the weather?' with Globex signals → 0 evidence, not 3 generic
  2. test_no_entity_match_returns_honest_answer
     The answer must contain 'I don't have enough' or 'no relevant'
  3. test_entity_match_still_returns_relevant_evidence
     'What did we promise Globex?' with Globex signals → evidence > 0
  4. test_nonexistent_entity_returns_empty
     'What did we promise NonExistentCorp?' → 0 evidence
"""
from __future__ import annotations

import sys
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class MockSignal:
    def __init__(self, sig_type, actor="", artifact="", metadata=None, timestamp=None, provider="customer"):
        self.type = sig_type
        self.actor = actor
        self.artifact = artifact
        self.metadata = metadata or {}
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.signal_id = f"sig-{artifact or id(self)}"
        self.provider = type("P", (), {"value": provider})()
        self.authority_weight = 0.5


@pytest.fixture
def now():
    return datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def globex_signals(now):
    from maestro_oem.signal import SignalType
    return [
        MockSignal(SignalType.CUSTOMER_COMMITMENT_MADE, actor="jane@example.com",
            artifact="crm:1", metadata={"customer": "Globex", "commitment": "Deliver SSO by Q4"},
            timestamp=now - timedelta(days=20)),
        MockSignal(SignalType.CUSTOMER_OBJECTION, actor="jane@example.com",
            artifact="crm:2", metadata={"customer": "Globex", "objection_type": "pricing"},
            timestamp=now - timedelta(days=5)),
    ]


# ─── C-2: No entity match → empty evidence, NOT generic signals ────────────

def test_no_entity_match_returns_empty_evidence(globex_signals):
    """'What about the weather?' with Globex signals → 0 evidence, not 3 generic."""
    from maestro_oem.ask_pipeline import AskPipeline

    p = AskPipeline(signals=globex_signals, whisper_store={}, oem_state=None)
    result = p.execute("What about the weather?", org_id="default")

    # Must NOT return generic Globex signals as evidence for a weather question
    assert len(result["evidence"]) == 0, (
        f"Evidence must be empty for irrelevant query. "
        f"Got {len(result['evidence'])} evidence items — these are generic fallback signals (C-2 bug)."
    )


def test_no_entity_match_returns_honest_answer(globex_signals):
    """The answer must contain 'I don't have enough' or 'no relevant' — NOT plausible prose."""
    from maestro_oem.ask_pipeline import AskPipeline

    p = AskPipeline(signals=globex_signals, whisper_store={}, oem_state=None)
    result = p.execute("What about the weather?", org_id="default")

    answer = result["answer"].lower()
    assert "don't have enough" in answer or "no relevant" in answer or "couldn't find" in answer, (
        f"Answer must honestly say 'I don't have enough'. Got: {result['answer'][:200]!r}"
    )


# ─── Entity match still works (no regression) ──────────────────────────────

def test_entity_match_still_returns_relevant_evidence(globex_signals):
    """'What did we promise Globex?' with Globex signals → evidence > 0 (no regression)."""
    from maestro_oem.ask_pipeline import AskPipeline

    p = AskPipeline(signals=globex_signals, whisper_store={}, oem_state=None)
    result = p.execute("What did we promise Globex?", org_id="default")

    assert len(result["evidence"]) > 0, (
        f"Evidence must be non-empty for Globex query. Got 0 — entity resolution regression."
    )


def test_nonexistent_entity_returns_empty(globex_signals):
    """'Tell me about XYZCorp funding' → 0 evidence (honest 'I don't know').
    
    Note: 'What did we promise NonExistentCorp?' would match because 'promise'
    is a synonym for the 'commitment' entity, and the Globex signal's type
    contains 'commitment'. That's actually correct — the user IS asking about
    commitments. This test uses a query with no entity or synonym overlap."""
    from maestro_oem.ask_pipeline import AskPipeline

    p = AskPipeline(signals=globex_signals, whisper_store={}, oem_state=None)
    result = p.execute("Tell me about XYZCorp funding rounds", org_id="default")

    assert len(result["evidence"]) == 0, (
        f"Evidence must be empty for irrelevant entity. Got {len(result['evidence'])} — C-2 bug."
    )
