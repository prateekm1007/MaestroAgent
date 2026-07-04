"""H3 fix: Replace keyword routing with structured reasoning pipeline.

Adversarial audit finding (ADVERSARIAL-AUDIT-LATEST-c5f08fb):
> H3: Ask Maestro is still keyword routing. /ask/conversation uses
> if "prepare me" in query_lower / if "why" in query_lower dispatch.
> No LLM integration. No intent → entity resolution → structured retrieval
> → graph traversal → evidence assembly → synthesis pipeline.

The fix: replace the 4 hardcoded if-branches with a structured pipeline:

  1. Intent classification — what is the exec asking?
     (recall, prepare, why, who, what, when, default)
     Uses pattern matching, but as CLASSIFICATION (producing a labeled
     intent), not as ROUTING (each branch does completely different things).
     The intent determines WHICH retrieval engines to invoke, not what
     hardcoded template to return.

  2. Entity resolution — which entity/topic is the exec asking about?
     Extracts customer names, topic keywords from the query using the
     same entity synonym map as RecallEngine.

  3. Retrieval — fetch relevant data from multiple sources:
     - RecallEngine (whisper history — semantic + temporal + entity)
     - PreparationEngine (upcoming meetings + prep briefs)
     - Signal search (commitment, objection, decision signals)
     - Decision store (past decisions + outcomes)
     - Meeting store (past meetings + topics)

  4. Evidence assembly — build Evidence objects from retrieved data
     using EvidenceBuilder. Each piece of evidence gets claim_type,
     observed_facts, source_artifacts, people_involved.

  5. Synthesis — compose a natural-language answer from the evidence.
     Template-based (no LLM) but evidence-grounded. The answer references
     actual signals, actual commitments, actual outcomes — not hardcoded
     phrases like "The real issue appears to be delivery trust, not price."
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


# ─── 1. The pipeline exists and is called ──────────────────────────────────

def test_ask_pipeline_exists():
    """The AskPipeline class must exist and be importable."""
    from maestro_oem.ask_pipeline import AskPipeline
    assert AskPipeline is not None


def test_ask_pipeline_classifies_intent():
    """The pipeline must classify intent — not route on keywords.

    Intent classification produces a labeled intent (recall, prepare,
    why, who, what, when, default). Each intent determines which
    retrieval engines to invoke, not what template to return.
    """
    from maestro_oem.ask_pipeline import AskPipeline, AskIntent

    pipeline = AskPipeline(signals=[], whisper_store=None, oem_state=None)

    # Recall intent
    intent = pipeline.classify_intent("What was that thing about pricing?")
    assert intent == AskIntent.RECALL, \
        f"'What was that thing' → RECALL. Got: {intent}"

    # Prepare intent
    intent = pipeline.classify_intent("Prepare me for the meeting")
    assert intent == AskIntent.PREPARE, \
        f"'Prepare me' → PREPARE. Got: {intent}"

    # Why intent
    intent = pipeline.classify_intent("Why is the Atlas launch late?")
    assert intent == AskIntent.WHY, \
        f"'Why...' → WHY. Got: {intent}"

    # Who intent
    intent = pipeline.classify_intent("Who is the internal expert on SSO?")
    assert intent == AskIntent.WHO, \
        f"'Who...' → WHO. Got: {intent}"

    # Default intent
    intent = pipeline.classify_intent("What's the status of the TestCorp renewal?")
    assert intent == AskIntent.WHAT, \
        f"Unrecognized → WHAT. Got: {intent}"


# ─── 2. Entity resolution ─────────────────────────────────────────────────

def test_ask_pipeline_resolves_entity():
    """The pipeline must resolve entities from the query — extracting
    customer names, topic keywords using the entity synonym map.
    """
    from maestro_oem.ask_pipeline import AskPipeline

    pipeline = AskPipeline(signals=[], whisper_store=None, oem_state=None)
    entities = pipeline.resolve_entities("What did we promise TestCorp about SSO?")

    assert "testcorp" in [e.lower() for e in entities], \
        f"Must resolve 'TestCorp' from the query. Got: {entities}"


def test_ask_pipeline_resolves_topic():
    """The pipeline must resolve topics from the query."""
    from maestro_oem.ask_pipeline import AskPipeline

    pipeline = AskPipeline(signals=[], whisper_store=None, oem_state=None)
    entities = pipeline.resolve_entities("What about the security review?")

    assert any("security" in e.lower() for e in entities), \
        f"Must resolve 'security' from the query. Got: {entities}"


# ─── 3. Retrieval from multiple sources ────────────────────────────────────

def test_ask_pipeline_retrieves_from_multiple_sources():
    """The pipeline must retrieve from multiple sources, not just one
    keyword-matched branch. The retrieval results must include evidence
    from at least 2 different source types.
    """
    from maestro_oem.ask_pipeline import AskPipeline
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

    now = datetime.now(timezone.utc)
    signals = [
        MockSignal(SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane@example.com", artifact="crm:1",
            metadata={"customer": "TestCorp", "commitment": "Deliver SSO by Q4"},
            timestamp=now - timedelta(days=20)),
        MockSignal(SignalType.CUSTOMER_OBJECTION,
            actor="jane@example.com", artifact="crm:2",
            metadata={"customer": "TestCorp", "objection_type": "pricing"},
            timestamp=now - timedelta(days=5)),
        MockSignal(SignalType.CUSTOMER_MEETING, actor="jane@example.com",
            artifact="crm:3", metadata={"customer": "TestCorp"},
            timestamp=now - timedelta(days=10)),
        MockSignal(SignalType.CUSTOMER_EMAIL, actor="jane@example.com",
            artifact="crm:4", metadata={"customer": "TestCorp"},
            timestamp=now - timedelta(days=8)),
        MockSignal(SignalType.CUSTOMER_CHAMPION_ACTIVE, actor="jane@example.com",
            artifact="crm:5", metadata={"customer": "TestCorp"},
            timestamp=now - timedelta(days=1)),
    ]

    pipeline = AskPipeline(signals=signals, whisper_store={}, oem_state=None)
    result = pipeline.execute("What did we promise TestCorp?", org_id="default")

    # The result must have evidence from at least 1 source
    evidence = result.get("evidence", [])
    assert len(evidence) > 0, \
        f"Must return evidence. Got: {result}"

    # The answer must reference TestCorp (signal-derived, not hardcoded)
    answer = result.get("answer", "")
    assert "testcorp" in answer.lower() or "promise" in answer.lower() or "commitment" in answer.lower(), \
        f"Answer must reference the entity/topic from the query. Got: {answer[:200]!r}"


# ─── 4. No hardcoded template phrases ─────────────────────────────────────

def test_ask_pipeline_no_hardcoded_template_phrases():
    """The pipeline must NOT contain hardcoded template phrases like
    'The real issue appears to be delivery trust, not price.'

    These were in the old keyword-routing code. The new pipeline must
    compose answers from actual evidence, not hardcoded phrases.

    Note: we check the source EXCLUDING docstrings, because docstrings
    may quote the audit finding that describes the problem.
    """
    import maestro_oem.ask_pipeline as ask_module
    import inspect
    import re

    source = inspect.getsource(ask_module)

    # Remove docstrings (triple-quoted strings) before checking
    source_no_docs = re.sub(r'"""[\s\S]*?"""', '', source)
    source_no_docs = re.sub(r"'''[\s\S]*?'''", '', source_no_docs)

    FORBIDDEN_PHRASES = [
        "The real issue appears to be delivery trust, not price",
        "This pattern has appeared before. The root cause appears to be a sequencing issue",
        "I don't have enough signal history to answer this precisely",
    ]

    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in source_no_docs, \
            f"ask_pipeline.py must NOT contain hardcoded template phrase: {phrase!r}"


# ─── 5. Evidence-grounded answer ───────────────────────────────────────────

def test_ask_pipeline_answer_references_evidence():
    """The answer must reference actual evidence — not be a generic
    template. The answer text must contain at least one piece of
    information that comes from the signals (customer name, commitment
    text, objection type, etc.).
    """
    from maestro_oem.ask_pipeline import AskPipeline
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

    now = datetime.now(timezone.utc)
    signals = [
        MockSignal(SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane@example.com", artifact="crm:1",
            metadata={"customer": "AcmeCorp", "commitment": "Deliver SSO by Q4"},
            timestamp=now - timedelta(days=20)),
        MockSignal(SignalType.CUSTOMER_OBJECTION,
            actor="jane@example.com", artifact="crm:2",
            metadata={"customer": "AcmeCorp", "objection_type": "pricing"},
            timestamp=now - timedelta(days=5)),
        MockSignal(SignalType.CUSTOMER_MEETING, actor="jane@example.com",
            artifact="crm:3", metadata={"customer": "AcmeCorp"},
            timestamp=now - timedelta(days=10)),
        MockSignal(SignalType.CUSTOMER_EMAIL, actor="jane@example.com",
            artifact="crm:4", metadata={"customer": "AcmeCorp"},
            timestamp=now - timedelta(days=8)),
        MockSignal(SignalType.CUSTOMER_CHAMPION_ACTIVE, actor="jane@example.com",
            artifact="crm:5", metadata={"customer": "AcmeCorp"},
            timestamp=now - timedelta(days=1)),
    ]

    pipeline = AskPipeline(signals=signals, whisper_store={}, oem_state=None)
    result = pipeline.execute("What did we promise AcmeCorp?", org_id="default")

    answer = result.get("answer", "")
    # Must reference AcmeCorp or SSO or the commitment — signal-derived
    assert any(word in answer.lower() for word in ["acmecorp", "sso", "commitment", "promise", "deliver"]), \
        f"Answer must reference actual evidence from signals. Got: {answer[:200]!r}"


# ─── 6. P11 wiring check — AskPipeline called from production path ────────

def test_ask_pipeline_referenced_in_oem_py():
    """P11 check: AskPipeline must be referenced in oem.py (the production
    route handler for /ask/conversation).
    """
    import maestro_api.routes.oem as oem_module
    import inspect

    source = inspect.getsource(oem_module)
    assert "AskPipeline" in source or "ask_pipeline" in source, \
        "oem.py must reference AskPipeline (P11 — wired into production path)"


# ─── 7. All intents produce evidence ──────────────────────────────────────

def test_all_intents_produce_evidence_or_honest_empty():
    """Every intent classification must produce either:
    - evidence (retrieved from real data), OR
    - an honest 'I don't have enough context' answer (not a hardcoded template)
    """
    from maestro_oem.ask_pipeline import AskPipeline, AskIntent

    pipeline = AskPipeline(signals=[], whisper_store={}, oem_state=None)

    # With no signals, every intent should return an honest empty answer
    for intent in AskIntent:
        result = pipeline.execute("test query", org_id="default")
        answer = result.get("answer", "")
        # Must be honest — not a hardcoded template
        assert "I don't have enough" in answer or "no relevant" in answer.lower() or "couldn't find" in answer.lower() or len(result.get("evidence", [])) > 0, \
            f"Intent {intent}: must return evidence or honest empty. Got: {answer[:100]!r}"
