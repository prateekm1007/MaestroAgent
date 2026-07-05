"""Phase A + Steps 3-5: Wire orphan modules into Ask Maestro + conversation
state + narration + citations.

Phase A: Wire 3 orphan modules into AskPipeline:
  - wisdom.py → "What should we do?" intent
  - imagination.py → "What if?" intent
  - simulation.py → "simulate" intent

Step 3: Conversation state (SQLite-backed multi-turn with pronoun resolution)
Step 4: Evidence-grounded narration (template-based, LLM-replaceable)
Step 5: Source citations (inline [1][2] linking to Evidence Spine artifacts)
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

from maestro_oem.signal import SignalType


class MockSignal:
    def __init__(self, sig_type, actor="", artifact="", metadata=None, timestamp=None, provider="customer"):
        self.type = sig_type
        self.actor = actor
        self.artifact = artifact
        self.metadata = metadata or {}
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.signal_id = f"sig-{artifact or id(self)}"
        self.provider = type("P", (), {"value": provider})()


class MockModel:
    def __init__(self):
        self.laws = {}
        self.learning_objects = {}
        self.approvals = type('A', (), {'get_bottlenecks': lambda self, min_count=2: []})()
        self.decisions = type('D', (), {'get_recommendations': lambda self: []})()


@pytest.fixture
def signals(now):
    from maestro_oem.signal import SignalType
    return [
        MockSignal(SignalType.CUSTOMER_COMMITMENT_MADE, actor="jane@example.com",
            artifact="crm:1", metadata={"customer": "TestCorp", "commitment": "Deliver SSO by Q4"},
            timestamp=now - timedelta(days=20)),
        MockSignal(SignalType.CUSTOMER_OBJECTION, actor="jane@example.com",
            artifact="crm:2", metadata={"customer": "TestCorp", "objection_type": "pricing"},
            timestamp=now - timedelta(days=5)),
        MockSignal(SignalType.CUSTOMER_MEETING, actor="jane@example.com",
            artifact="crm:3", metadata={"customer": "TestCorp"}, timestamp=now - timedelta(days=10)),
        MockSignal(SignalType.CUSTOMER_EMAIL, actor="jane@example.com",
            artifact="crm:4", metadata={"customer": "TestCorp"}, timestamp=now - timedelta(days=8)),
        MockSignal(SignalType.CUSTOMER_CHAMPION_ACTIVE, actor="jane@example.com",
            artifact="crm:5", metadata={"customer": "TestCorp"}, timestamp=now - timedelta(days=1)),
    ]


@pytest.fixture
def now():
    return datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)


# ═══ PHASE A: Wire orphan modules ═══════════════════════════════════════

# ─── 1. New intents exist ────────────────────────────────────────────────

def test_new_intents_exist():
    """AskPipeline must have 3 new intents: WISDOM, WHAT_IF, SIMULATE."""
    from maestro_oem.ask_pipeline import AskIntent

    intents = {i.name for i in AskIntent}
    assert "WISDOM" in intents, f"WISDOM intent must exist. Got: {intents}"
    assert "WHAT_IF" in intents, f"WHAT_IF intent must exist. Got: {intents}"
    assert "SIMULATE" in intents, f"SIMULATE intent must exist. Got: {intents}"


def test_classify_wisdom_intent():
    """'What should we do about...' → WISDOM intent."""
    from maestro_oem.ask_pipeline import AskPipeline, AskIntent
    p = AskPipeline(signals=[], whisper_store={}, oem_state=None)
    assert p.classify_intent("What should we do about TestCorp?") == AskIntent.WISDOM
    assert p.classify_intent("What do you recommend for the pricing issue?") == AskIntent.WISDOM


def test_classify_what_if_intent():
    """'What if...' → WHAT_IF intent."""
    from maestro_oem.ask_pipeline import AskPipeline, AskIntent
    p = AskPipeline(signals=[], whisper_store={}, oem_state=None)
    assert p.classify_intent("What if we delay the SSO launch?") == AskIntent.WHAT_IF
    assert p.classify_intent("What would happen if Legal left?") == AskIntent.WHAT_IF


def test_classify_simulate_intent():
    """'Simulate...' → SIMULATE intent."""
    from maestro_oem.ask_pipeline import AskPipeline, AskIntent
    p = AskPipeline(signals=[], whisper_store={}, oem_state=None)
    assert p.classify_intent("Simulate a 20% pricing increase") == AskIntent.SIMULATE


# ─── 2. P11: modules referenced in ask_pipeline.py ───────────────────────

def test_wisdom_referenced_in_ask_pipeline():
    """P11: wisdom module must be referenced in ask_pipeline.py."""
    import maestro_oem.ask_pipeline as ap
    import inspect
    source = inspect.getsource(ap)
    assert "WisdomEngine" in source or "wisdom" in source, \
        "ask_pipeline.py must reference WisdomEngine (P11)"


def test_imagination_referenced_in_ask_pipeline():
    """P11: imagination module must be referenced in ask_pipeline.py."""
    import maestro_oem.ask_pipeline as ap
    import inspect
    source = inspect.getsource(ap)
    assert "ImaginationEngine" in source or "imagination" in source, \
        "ask_pipeline.py must reference ImaginationEngine (P11)"


def test_simulation_referenced_in_ask_pipeline():
    """P11: simulation module must be referenced in ask_pipeline.py."""
    import maestro_oem.ask_pipeline as ap
    import inspect
    source = inspect.getsource(ap)
    assert "SimulationEngine" in source or "simulation" in source, \
        "ask_pipeline.py must reference SimulationEngine (P11)"


# ─── 3. Wisdom intent produces value-synthesis answer ────────────────────

def test_wisdom_intent_produces_synthesis(signals, now):
    """'What should we do?' must route to WisdomEngine and produce
    value-synthesis output, not keyword search results."""
    from maestro_oem.ask_pipeline import AskPipeline, AskIntent
    model = MockModel()
    p = AskPipeline(signals=signals, whisper_store={}, oem_state=None, model=model)
    result = p.execute("What should we do about TestCorp?", org_id="default")

    assert result["intent"] == "wisdom"
    answer = result.get("answer", "")
    assert answer, "Wisdom intent must produce an answer"
    # Must reference wisdom/synthesis concepts, not just signal search
    assert any(w in answer.lower() for w in ["recommend", "should", "wisdom", "value", "competing", "synthesize", "balance"]), \
        f"Wisdom answer must reference synthesis. Got: {answer[:200]!r}"


# ─── 4. What-if intent produces counterfactual ───────────────────────────

def test_what_if_intent_produces_counterfactual(signals, now):
    """'What if...' must route to ImaginationEngine and produce
    counterfactual reasoning output."""
    from maestro_oem.ask_pipeline import AskPipeline, AskIntent
    model = MockModel()
    p = AskPipeline(signals=signals, whisper_store={}, oem_state=None, model=model)
    result = p.execute("What if we delay the SSO launch?", org_id="default")

    assert result["intent"] == "what_if"
    answer = result.get("answer", "")
    assert answer, "What-if intent must produce an answer"


# ─── 5. Simulate intent produces simulation ──────────────────────────────

def test_simulate_intent_produces_simulation(signals, now):
    """'Simulate...' must route to SimulationEngine."""
    from maestro_oem.ask_pipeline import AskPipeline, AskIntent
    model = MockModel()
    p = AskPipeline(signals=signals, whisper_store={}, oem_state=None, model=model)
    result = p.execute("Simulate a pricing change", org_id="default")

    assert result["intent"] == "simulate"
    answer = result.get("answer", "")
    assert answer, "Simulate intent must produce an answer"


# ═══ STEP 3: Conversation state ═════════════════════════════════════════

# ─── 6. ConversationStore exists and persists ────────────────────────────

def test_conversation_store_exists():
    """ConversationStore must exist and be importable."""
    from maestro_oem.conversation_store import ConversationStore
    assert ConversationStore is not None


def test_conversation_store_persists_and_retrieves(tmp_path):
    """Conversation history must survive restart."""
    from maestro_oem.conversation_store import ConversationStore

    db_path = str(tmp_path / "conv.db")
    store1 = ConversationStore(db_path)
    store1.add_turn(session_id="s1", turn=1, role="user", content="Prepare me for TestCorp",
                    intent="prepare", entities=["TestCorp"])
    store1.add_turn(session_id="s1", turn=2, role="maestro", content="Here's the prep...",
                    intent="prepare", entities=["TestCorp"])
    store1.close()

    store2 = ConversationStore(db_path)
    history = store2.get_history("s1")
    assert len(history) == 2, f"Must recover 2 turns. Got: {len(history)}"
    assert history[0]["content"] == "Prepare me for TestCorp"
    assert history[1]["content"] == "Here's the prep..."
    store2.close()


# ─── 7. AskPipeline uses conversation state for pronoun resolution ───────

def test_ask_pipeline_resolves_entity_from_prior_turn(signals, now, tmp_path):
    """'What did we promise?' after a TestCorp conversation must resolve
    'we' and 'promise' in the context of TestCorp."""
    from maestro_oem.ask_pipeline import AskPipeline
    from maestro_oem.conversation_store import ConversationStore

    conv_store = ConversationStore(str(tmp_path / "conv.db"))
    # Simulate prior turn: user asked about TestCorp
    conv_store.add_turn(session_id="s1", turn=1, role="user",
                        content="What did we promise TestCorp?",
                        intent="what", entities=["TestCorp"])
    conv_store.add_turn(session_id="s1", turn=2, role="maestro",
                        content="You promised SSO by Q4",
                        intent="what", entities=["TestCorp"])

    model = MockModel()
    p = AskPipeline(signals=signals, whisper_store={}, oem_state=None,
                    model=model, conversation_store=conv_store)

    # Second question: "What about their pricing concern?"
    # Should resolve "their" = TestCorp from prior turn
    result = p.execute("What about their pricing concern?", org_id="default", session_id="s1")

    entities = result.get("entities", [])
    assert any("testcorp" in e.lower() for e in entities), \
        f"Must resolve 'their' → TestCorp from prior turn. Entities: {entities}"


# ═══ STEP 4: Evidence-grounded narration ═════════════════════════════════

# ─── 8. Narrator exists and renders evidence ─────────────────────────────

def test_narrator_exists():
    """EvidenceNarrator must exist and be importable."""
    from maestro_oem.narrator import EvidenceNarrator
    assert EvidenceNarrator is not None


def test_narrator_renders_evidence():
    """The narrator must take evidence and render prose — not a list."""
    from maestro_oem.narrator import EvidenceNarrator

    narrator = EvidenceNarrator()
    evidence = [
        {
            "source": "customer signals",
            "text": "Deliver SSO by Q4",
            "date": "2026-06-01",
            "people": ["jane@example.com"],
            "evidence_spine": {
                "claim": "A commitment was made to TestCorp",
                "observed_facts": [{"source": "customer signals", "date": "2026-06-01", "text": "Deliver SSO by Q4"}],
                "claim_type": "commitment",
            },
        }
    ]
    answer = narrator.narrate("What did we promise TestCorp?", evidence)

    assert answer, "Narrator must produce non-empty answer"
    assert isinstance(answer, str), "Answer must be a string (prose), not a list"
    # Must reference the evidence content
    assert "sso" in answer.lower() or "commitment" in answer.lower() or "promise" in answer.lower(), \
        f"Narrator must reference evidence content. Got: {answer[:200]!r}"


def test_narrator_does_not_invent_when_no_evidence():
    """When no evidence, narrator must say 'I don't have enough' — NOT hallucinate."""
    from maestro_oem.narrator import EvidenceNarrator

    narrator = EvidenceNarrator()
    answer = narrator.narrate("What about the weather?", [])

    assert "don't have enough" in answer.lower() or "no relevant" in answer.lower() or "couldn't find" in answer.lower(), \
        f"Narrator must say 'I don't have enough' when no evidence. Got: {answer!r}"


# ─── 9. AskPipeline uses narrator for synthesis ──────────────────────────

def test_ask_pipeline_uses_narrator(signals, now):
    """AskPipeline must use EvidenceNarrator for the final answer synthesis."""
    from maestro_oem.ask_pipeline import AskPipeline
    import inspect

    source = inspect.getsource(AskPipeline)
    assert "narrator" in source.lower() or "Narrator" in source or "narrate" in source, \
        "AskPipeline must reference EvidenceNarrator (P11 — wired into production path)"


# ═══ STEP 5: Source citations ═══════════════════════════════════════════

# ─── 10. Answer includes source citations ────────────────────────────────

def test_answer_includes_citations(signals, now):
    """When evidence is returned, the answer must include inline citations [1], [2], etc."""
    from maestro_oem.ask_pipeline import AskPipeline

    model = MockModel()
    p = AskPipeline(signals=signals, whisper_store={}, oem_state=None, model=model)
    result = p.execute("What did we promise TestCorp?", org_id="default")

    answer = result.get("answer", "")
    evidence = result.get("evidence", [])

    if len(evidence) > 0:
        # Answer must contain at least one citation [1]
        assert "[1]" in answer or "[1]" in str(result.get("citations", [])), \
            f"Answer with evidence must include citations. Answer: {answer[:200]!r}"

    # Citations field must exist
    assert "citations" in result, \
        f"Result must include 'citations' field. Keys: {list(result.keys())}"


def test_citations_link_to_evidence():
    """Citations must link to evidence items — each citation [1] maps to an evidence item."""
    from maestro_oem.narrator import EvidenceNarrator

    narrator = EvidenceNarrator()
    evidence = [
        {"source": "slack", "text": "We promised SSO", "date": "2026-06-01",
         "evidence_spine": {"claim": "SSO promised", "observed_facts": [{"source": "slack", "text": "We promised SSO"}]}},
        {"source": "email", "text": "Q4 deadline confirmed", "date": "2026-06-05",
         "evidence_spine": {"claim": "Q4 deadline", "observed_facts": [{"source": "email", "text": "Q4 deadline confirmed"}]}},
    ]
    answer, citations = narrator.narrate_with_citations("What did we promise?", evidence)

    assert len(citations) == 2, f"Must have 2 citations for 2 evidence items. Got: {len(citations)}"
    assert "[1]" in answer, f"Answer must contain [1]. Got: {answer[:200]!r}"
    assert "[2]" in answer, f"Answer must contain [2]. Got: {answer[:200]!r}"
    assert citations[0]["source"] == "slack"
    assert citations[1]["source"] == "email"


# ─── 11. Full end-to-end: multi-turn conversation with narration ────────

def test_full_multi_turn_conversation(signals, now, tmp_path):
    """End-to-end: multi-turn conversation with:
    - Turn 1: "What did we promise TestCorp?" → evidence + narration + citations
    - Turn 2: "What about their pricing concern?" → resolves "their" → TestCorp
    """
    from maestro_oem.ask_pipeline import AskPipeline
    from maestro_oem.conversation_store import ConversationStore

    conv_store = ConversationStore(str(tmp_path / "conv_e2e.db"))
    model = MockModel()
    p = AskPipeline(signals=signals, whisper_store={}, oem_state=None,
                    model=model, conversation_store=conv_store)

    # Turn 1
    r1 = p.execute("What did we promise TestCorp?", org_id="default", session_id="conv1")
    assert r1["answer"], "Turn 1 must produce an answer"
    assert "citations" in r1, "Turn 1 must include citations"

    # Turn 2: "their" must resolve to TestCorp from turn 1
    r2 = p.execute("What about their pricing concern?", org_id="default", session_id="conv1")
    entities = r2.get("entities", [])
    assert any("testcorp" in e.lower() for e in entities), \
        f"Turn 2 must resolve 'their' → TestCorp from conversation history. Entities: {entities}"
    assert r2["answer"], "Turn 2 must produce an answer"
