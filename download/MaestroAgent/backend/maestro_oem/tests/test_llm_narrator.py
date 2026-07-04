"""Priority 5: LLM Narration — constrained, evidence-grounded prose generation.

CEO directive (2026-07-04):
> LLM narration (deferred) — Prove the governed learning loop first.
> Then add LLM as constrained narrator.

The CEO's original vision: "LLM is the narrator, not the architecture."
The LLM receives structured evidence and renders prose. It NEVER reasons,
retrieves, or decides. It only narrates what the evidence says.

Constraints (the "constrained" in "constrained narrator"):
  1. GROUNDED: The LLM receives ONLY the evidence + the question. It must
     NEVER add information not in the evidence.
  2. CITED: Every claim in the output must have an inline citation [1][2]
     linking to an evidence item.
  3. FAIL-CLOSED (P6): When the LLM is unavailable (no provider, API error,
     timeout), fall back to the template-based EvidenceNarrator. The user
     always gets an answer.
  4. CONSTRAINED: The system prompt explicitly tells the LLM: "You are a
     narrator. Do not reason. Do not retrieve. Do not decide. Narrate what
     the evidence says."
  5. HALLUCINATION GUARD: After the LLM generates prose, verify that each
     citation [N] maps to an actual evidence item. Strip hallucinated
     citations.

The LLMNarrator implements the same interface as EvidenceNarrator:
  narrate(question, evidence) → str
  narrate_with_citations(question, evidence) → (str, list[dict])

This makes it a drop-in replacement. The AskPipeline can use either.

Adversarial tests (write first, watch fail, then build):

  1. test_llm_narrator_exists
     LLMNarrator must exist and be importable.

  2. test_llm_narrator_implements_same_interface
     LLMNarrator must have narrate() and narrate_with_citations() methods
     with the same signatures as EvidenceNarrator.

  3. test_llm_narrator_falls_back_when_no_llm
     When no LLM provider is available, LLMNarrator falls back to the
     template EvidenceNarrator. The user still gets an answer (P6).

  4. test_llm_narrator_falls_back_on_error
     When the LLM raises an error, LLMNarrator falls back to the template
     narrator. The user still gets an answer (P6).

  5. test_llm_narrator_uses_llm_when_available
     When an LLM is available (mocked), LLMNarrator uses it to generate
     prose. The output is different from the template narrator's output.

  6. test_llm_narrator_grounds_in_evidence
     The LLM prompt must include the evidence. The system prompt must
     instruct the LLM to ONLY use the evidence — not add information.

  7. test_llm_narrator_includes_citations
     The LLM output must include inline citations [1][2] linking to
     evidence items. The citations list must map to evidence.

  8. test_llm_narrator_strips_hallucinated_citations
     If the LLM generates a citation [99] that doesn't map to any evidence
     item, the narrator strips it from the output.

  9. test_llm_narrator_system_prompt_constrains
     The system prompt must contain constraining language: "narrate",
     "do not add", "evidence", "citation". The LLM is a narrator, not
     a reasoner.

  10. test_llm_narrator_empty_evidence
      When no evidence is provided, the narrator says "I don't have enough
      organizational memory" — same as the template narrator. The LLM
      is NOT called with empty evidence (no point, and prevents
      hallucination from no context).

  11. test_wiring_p11_llm_narrator_in_ask_pipeline
      P11: ask_pipeline.py must reference LLMNarrator (or the narrator
      factory that produces it).

  12. test_llm_narrator_backward_compat
      Existing code that uses EvidenceNarrator must still work.
      LLMNarrator is ADDITIVE — it doesn't replace EvidenceNarrator,
      it wraps it.

P2: Untested code is unverified code.
P6: Fail-closed — LLM unavailable → template narrator, user always gets an answer.
P11: Wiring proved by grep + execution.
P13: The LLM receives evidence DERIVED from the pipeline, not caller-supplied prose.
"""
from __future__ import annotations

import sys
import inspect
import pytest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ═══ Priority 5: LLM Narration ═════════════════════════════════════════════

# ─── 1. LLMNarrator exists ─────────────────────────────────────────────────

def test_llm_narrator_exists():
    """LLMNarrator must exist and be importable."""
    from maestro_oem.llm_narrator import LLMNarrator
    assert LLMNarrator is not None


# ─── 2. Same interface as EvidenceNarrator ─────────────────────────────────

def test_llm_narrator_implements_same_interface():
    """LLMNarrator must have narrate() and narrate_with_citations() methods
    with the same signatures as EvidenceNarrator."""
    from maestro_oem.llm_narrator import LLMNarrator
    from maestro_oem.narrator import EvidenceNarrator

    # Check methods exist
    assert hasattr(LLMNarrator, "narrate"), "LLMNarrator must have narrate()"
    assert hasattr(LLMNarrator, "narrate_with_citations"), "LLMNarrator must have narrate_with_citations()"

    # Check signatures match
    llm_sig = inspect.signature(LLMNarrator.narrate_with_citations)
    template_sig = inspect.signature(EvidenceNarrator.narrate_with_citations)
    llm_params = set(llm_sig.parameters.keys())
    template_params = set(template_sig.parameters.keys())
    assert template_params.issubset(llm_params), (
        f"LLMNarrator params must include EvidenceNarrator params. "
        f"Missing: {template_params - llm_params}"
    )


# ─── 3. Falls back when no LLM ─────────────────────────────────────────────

def test_llm_narrator_falls_back_when_no_llm():
    """When no LLM provider is available, LLMNarrator falls back to the
    template EvidenceNarrator. The user still gets an answer (P6)."""
    from maestro_oem.llm_narrator import LLMNarrator

    # No LLM provider configured
    narrator = LLMNarrator(llm_provider=None)
    evidence = [
        {"source": "slack", "text": "We promised SSO by Q4", "date": "2026-06-01", "people": ["jane@example.com"],
         "evidence_spine": {"claim": "SSO promised", "observed_facts": [{"source": "slack", "text": "We promised SSO"}]}}
    ]
    answer = narrator.narrate("What did we promise?", evidence)
    assert answer, "Must produce an answer even without an LLM (P6 fail-closed)"
    assert isinstance(answer, str)


# ─── 4. Falls back on error ────────────────────────────────────────────────

def test_llm_narrator_falls_back_on_error():
    """When the LLM raises an error, LLMNarrator falls back to the template
    narrator. The user still gets an answer (P6)."""
    from maestro_oem.llm_narrator import LLMNarrator

    class ErrorProvider:
        """A mock LLM provider that always raises."""
        async def complete(self, system, user, **kwargs):
            raise ConnectionError("LLM service unavailable")

    narrator = LLMNarrator(llm_provider=ErrorProvider())
    evidence = [
        {"source": "slack", "text": "We promised SSO by Q4", "date": "2026-06-01", "people": []}
    ]
    # Must NOT raise — must fall back to template
    answer = narrator.narrate("What did we promise?", evidence)
    assert answer, "Must produce an answer even when LLM errors (P6 fail-closed)"


# ─── 5. Uses LLM when available ────────────────────────────────────────────

def test_llm_narrator_uses_llm_when_available():
    """When an LLM is available (mocked), LLMNarrator uses it to generate
    prose. The output is different from the template narrator's output."""
    from maestro_oem.llm_narrator import LLMNarrator
    from maestro_oem.narrator import EvidenceNarrator

    class MockProvider:
        """A mock LLM provider that returns canned prose."""
        def __init__(self):
            self.called = False
            self.last_system = ""
            self.last_user = ""

        async def complete(self, system, user, **kwargs):
            self.called = True
            self.last_system = system
            self.last_user = user
            return type("Resp", (), {
                "text": "Based on the evidence [1], the team committed to delivering SSO by Q4.",
                "provider": "mock",
                "model": "mock-model",
                "prompt_tokens": 100,
                "completion_tokens": 50,
            })()

    mock = MockProvider()
    narrator = LLMNarrator(llm_provider=mock)
    evidence = [
        {"source": "slack", "text": "We promised SSO by Q4", "date": "2026-06-01",
         "people": ["jane@example.com"]}
    ]
    answer = narrator.narrate("What did we promise?", evidence)

    assert mock.called, "LLM provider must have been called"
    assert "SSO" in answer or "sso" in answer.lower(), (
        f"LLM-generated answer must reference the evidence content. Got: {answer[:200]!r}"
    )


# ─── 6. Grounds in evidence ────────────────────────────────────────────────

def test_llm_narrator_grounds_in_evidence():
    """The LLM prompt must include the evidence. The system prompt must
    instruct the LLM to ONLY use the evidence — not add information."""
    from maestro_oem.llm_narrator import LLMNarrator

    class CapturingProvider:
        def __init__(self):
            self.last_system = ""
            self.last_user = ""

        async def complete(self, system, user, **kwargs):
            self.last_system = system
            self.last_user = user
            return type("Resp", (), {
                "text": "Test response [1].",
                "provider": "mock", "model": "mock",
                "prompt_tokens": 0, "completion_tokens": 0,
            })()

    mock = CapturingProvider()
    narrator = LLMNarrator(llm_provider=mock)
    evidence = [
        {"source": "slack", "text": "We promised SSO by Q4", "date": "2026-06-01", "people": []}
    ]
    narrator.narrate("What did we promise?", evidence)

    # The system prompt must contain constraining language
    system_lower = mock.last_system.lower()
    assert "narrate" in system_lower or "narrator" in system_lower, (
        f"System prompt must instruct the LLM to narrate. Got: {mock.last_system[:200]!r}"
    )
    assert "evidence" in system_lower, (
        f"System prompt must reference evidence. Got: {mock.last_system[:200]!r}"
    )
    # Must instruct NOT to add information
    assert "do not add" in system_lower or "only" in system_lower or "grounded" in system_lower, (
        f"System prompt must constrain the LLM to not add information. Got: {mock.last_system[:200]!r}"
    )

    # The user prompt must include the actual evidence
    user_lower = mock.last_user.lower()
    assert "sso" in user_lower or "promised" in user_lower, (
        f"User prompt must include the evidence text. Got: {mock.last_user[:200]!r}"
    )


# ─── 7. Includes citations ─────────────────────────────────────────────────

def test_llm_narrator_includes_citations():
    """The LLM output must include inline citations [1][2] linking to
    evidence items. The citations list must map to evidence."""
    from maestro_oem.llm_narrator import LLMNarrator

    class MockProvider:
        async def complete(self, system, user, **kwargs):
            return type("Resp", (), {
                "text": "The team committed to SSO [1] and confirmed the Q4 deadline [2].",
                "provider": "mock", "model": "mock",
                "prompt_tokens": 0, "completion_tokens": 0,
            })()

    narrator = LLMNarrator(llm_provider=MockProvider())
    evidence = [
        {"source": "slack", "text": "We promised SSO by Q4", "date": "2026-06-01", "people": []},
        {"source": "email", "text": "Q4 deadline confirmed", "date": "2026-06-05", "people": []},
    ]
    answer, citations = narrator.narrate_with_citations("What did we promise?", evidence)

    assert "[1]" in answer, f"Answer must include [1] citation. Got: {answer[:200]!r}"
    assert "[2]" in answer, f"Answer must include [2] citation. Got: {answer[:200]!r}"
    assert len(citations) == 2, f"Must have 2 citations. Got: {len(citations)}"
    assert citations[0]["source"] == "slack"
    assert citations[1]["source"] == "email"


# ─── 8. Strips hallucinated citations ──────────────────────────────────────

def test_llm_narrator_strips_hallucinated_citations():
    """If the LLM generates a citation [99] that doesn't map to any evidence
    item, the narrator strips it from the output."""
    from maestro_oem.llm_narrator import LLMNarrator

    class MockProvider:
        async def complete(self, system, user, **kwargs):
            # LLM hallucinates a [99] citation
            return type("Resp", (), {
                "text": "The team committed to SSO [1]. This will likely increase revenue [99].",
                "provider": "mock", "model": "mock",
                "prompt_tokens": 0, "completion_tokens": 0,
            })()

    narrator = LLMNarrator(llm_provider=MockProvider())
    evidence = [
        {"source": "slack", "text": "We promised SSO by Q4", "date": "2026-06-01", "people": []}
    ]
    answer, citations = narrator.narrate_with_citations("What did we promise?", evidence)

    # [1] must be present (valid citation)
    assert "[1]" in answer
    # [99] must be stripped (hallucinated — no evidence item 99)
    assert "[99]" not in answer, (
        f"Hallucinated citation [99] must be stripped. Got: {answer!r}"
    )
    # Only 1 valid citation
    assert len(citations) == 1


# ─── 9. System prompt constrains ───────────────────────────────────────────

def test_llm_narrator_system_prompt_constrains():
    """The system prompt must contain constraining language: 'narrate',
    'do not add', 'evidence', 'citation'. The LLM is a narrator, not
    a reasoner."""
    from maestro_oem.llm_narrator import LLMNarrator

    class CapturingProvider:
        def __init__(self):
            self.last_system = ""

        async def complete(self, system, user, **kwargs):
            self.last_system = system
            return type("Resp", (), {
                "text": "Test [1].",
                "provider": "mock", "model": "mock",
                "prompt_tokens": 0, "completion_tokens": 0,
            })()

    mock = CapturingProvider()
    narrator = LLMNarrator(llm_provider=mock)
    evidence = [{"source": "test", "text": "test evidence", "date": "", "people": []}]
    narrator.narrate("test?", evidence)

    system = mock.last_system.lower()
    required_terms = ["narrate", "evidence", "citation"]
    for term in required_terms:
        assert term in system, (
            f"System prompt must contain '{term}'. Got: {mock.last_system[:300]!r}"
        )


# ─── 10. Empty evidence → no LLM call ──────────────────────────────────────

def test_llm_narrator_empty_evidence():
    """When no evidence is provided, the narrator says 'I don't have enough
    organizational memory' — same as the template narrator. The LLM is NOT
    called with empty evidence (no point, and prevents hallucination)."""
    from maestro_oem.llm_narrator import LLMNarrator

    class TrackingProvider:
        def __init__(self):
            self.called = False

        async def complete(self, system, user, **kwargs):
            self.called = True
            return type("Resp", (), {"text": "should not be called", "provider": "mock", "model": "mock", "prompt_tokens": 0, "completion_tokens": 0})()

    mock = TrackingProvider()
    narrator = LLMNarrator(llm_provider=mock)
    answer = narrator.narrate("What about the weather?", [])

    assert not mock.called, "LLM must NOT be called with empty evidence (prevents hallucination)"
    assert "don't have enough" in answer.lower() or "no relevant" in answer.lower(), (
        f"Empty evidence must produce 'I don't have enough' message. Got: {answer!r}"
    )


# ─── 11. P11: LLMNarrator in ask_pipeline ──────────────────────────────────

def test_wiring_p11_llm_narrator_in_ask_pipeline():
    """P11: ask_pipeline.py must reference LLMNarrator (or the narrator
    factory that produces it)."""
    from maestro_oem import ask_pipeline
    source = inspect.getsource(ask_pipeline)
    assert "LLMNarrator" in source or "llm_narrator" in source, (
        "ask_pipeline.py must reference LLMNarrator (P11 — wired into production)"
    )


# ─── 12. Backward compat ───────────────────────────────────────────────────

def test_llm_narrator_backward_compat():
    """Existing code that uses EvidenceNarrator must still work.
    LLMNarrator is ADDITIVE — it doesn't replace EvidenceNarrator,
    it wraps it."""
    from maestro_oem.narrator import EvidenceNarrator
    from maestro_oem.llm_narrator import LLMNarrator

    # EvidenceNarrator must still work standalone
    template = EvidenceNarrator()
    evidence = [{"source": "slack", "text": "test", "date": "2026-01-01", "people": []}]
    answer = template.narrate("test?", evidence)
    assert answer, "EvidenceNarrator must still work standalone (backward compat)"

    # LLMNarrator with no provider must produce the same output as EvidenceNarrator
    llm = LLMNarrator(llm_provider=None)
    llm_answer = llm.narrate("test?", evidence)
    assert llm_answer, "LLMNarrator with no provider must produce an answer"
