"""P22 verification tests: production fallback path + CircuitBreaker trip.

AUDITOR DIRECTIVE:
> Fix 2: Verify the rule-based synthesizer fires in the production fallback path.
> Fix 3: Verify the CircuitBreaker trips on 3 failures.

Per P22: "Regression test must execute the production path — unit tests don't prove wiring."
Per P1: "A claim is not true until it has been executed."
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


def _make_signals():
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
    return [
        ExecutionSignal(type=SignalType.MESSAGE_SENT, actor="sales@corp.com",
            artifact="msg-day5", metadata={"customer": "Globex", "body": "should be able to support SSO before renewal"},
            provider=SignalProvider.SLACK),
        ExecutionSignal(type=SignalType.MESSAGE_SENT, actor="exec@corp.com",
            artifact="msg-day12", metadata={"customer": "Globex", "body": "we will have SSO available"},
            provider=SignalProvider.SLACK),
        ExecutionSignal(type=SignalType.MESSAGE_SENT, actor="security@corp.com",
            artifact="msg-day40", metadata={"customer": "Globex", "body": "security approval is still conditional"},
            provider=SignalProvider.SLACK),
        ExecutionSignal(type=SignalType.MESSAGE_SENT, actor="sales@corp.com",
            artifact="msg-day50", metadata={"customer": "Globex", "body": "SSO work is complete"},
            provider=SignalProvider.SLACK),
        ExecutionSignal(type=SignalType.MESSAGE_SENT, actor="raj@globex.com",
            artifact="msg-day55", metadata={"customer": "Globex", "body": "we understood the commitment as production availability"},
            provider=SignalProvider.SLACK),
    ]


# ═══════════════════════════════════════════════════════════════════════════
# FIX 2: Rule-based synthesizer fires in production fallback (P22)
# ═══════════════════════════════════════════════════════════════════════════

def test_rule_based_synthesizer_fires_when_no_llm():
    """P22: When synthesis_provider=None, the rule-based synthesizer fires.

    NOT the old EvidenceNarrator data dump. The output must contain
    WHAT WE PROMISED / STATUS / RISK / RECOMMENDED ACTION.
    """
    from maestro_oem.ask_pipeline import AskPipeline

    pipe = AskPipeline(signals=_make_signals(), synthesis_provider=None)
    result = asyncio.run(pipe.execute_async(
        "What exactly did we promise Globex, and is it still accurate?",
        user_email="auditor@acme.com",
    ))

    answer = result["answer"]
    trace = result["synthesis_trace"]

    # reasoning_mode must be template_only (no LLM)
    assert trace["reasoning_mode"] == "template_only"

    # The answer must be SYNTHESIS, not a data dump
    assert "WHAT WE PROMISED" in answer, "Rule-based synthesizer must fire — WHAT WE PROMISED missing"
    assert "STATUS" in answer, "STATUS section missing"
    assert "RISK" in answer, "RISK section missing"
    assert "RECOMMENDED ACTION" in answer, "RECOMMENDED ACTION section missing"

    # Must NOT be the old data dump format
    assert "Based on" not in answer or "signal(s)" not in answer, \
        "Old data dump format detected — rule-based synthesizer did not fire"

    # All 3 critical signals must be mentioned
    answer_lower = answer.lower()
    assert "conditional" in answer_lower, "Security caveat missing"
    assert "complete" in answer_lower, "Complete claim missing"
    assert "understood" in answer_lower, "Customer disagreement missing"


def test_rule_based_synthesizer_fires_on_llm_fallback():
    """P22: When the LLM fails, the rule-based synthesizer fires (not the data dump).

    AUDITOR-FIX (Round 4): The LLM escalation trigger now routes known-category
    evidence directly to the rule-based synthesizer WITHOUT attempting the LLM.
    This means the reasoning_mode is TEMPLATE_ONLY (not deterministic_fallback)
    because the system correctly determined that the LLM wasn't needed — all
    evidence fit known categories. The LLM is only attempted for novel signals.

    To test the actual LLM-failure path, we need evidence with unclassified
    signals so the escalation trigger fires.
    """
    from maestro_oem.ask_pipeline import AskPipeline
    from maestro_oem.synthesis_provider import SynthesisProvider

    class AlwaysFailProvider:
        available = True
        async def synthesize(self, system, user):
            raise RuntimeError("simulated API failure")

    # Wrap in SynthesisProvider to get CircuitBreaker protection
    provider = SynthesisProvider.wrap_provider(AlwaysFailProvider(), timeout_seconds=2)

    # Use signals that will produce unclassified evidence → triggers LLM escalation
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
    novel_signals = [
        ExecutionSignal(type=SignalType.MESSAGE_SENT, actor="ceo@corp.com",
            artifact="msg-novel", metadata={"customer": "Globex", "body": "gut feeling renewal at risk"},
            provider=SignalProvider.SLACK),
    ]

    pipe = AskPipeline(signals=novel_signals, synthesis_provider=provider)
    result = asyncio.run(pipe.execute_async(
        "What is the status of Globex?",
        user_email="auditor@acme.com",
    ))

    answer = result["answer"]
    trace = result["synthesis_trace"]

    # Must fall back (LLM failed after escalation trigger fired)
    assert trace["reasoning_mode"] == "deterministic_fallback"
    assert trace["fallback_triggered"] is True
    assert "error" in trace["fallback_reason"].lower() or "circuit" in trace["fallback_reason"].lower()

    # The fallback must include the novel signal (NOT silently dropped)
    assert "gut feeling" in answer.lower(), "Novel signal must be surfaced in fallback"


# ═══════════════════════════════════════════════════════════════════════════
# FIX 3: CircuitBreaker trips on 3 failures (P22)
# ═══════════════════════════════════════════════════════════════════════════

def test_circuit_breaker_trips_after_3_failures():
    """P22: CircuitBreaker trips to OPEN after 3 consecutive failures.

    After trip, no further API calls are made. The system falls back
    to the rule-based synthesizer.

    AUDITOR-FIX (Round 4): Uses novel signals (unclassified) so the LLM
    escalation trigger fires. Known-category signals now bypass the LLM
    entirely (correct behavior), so the CircuitBreaker wouldn't be exercised.
    """
    from maestro_oem.synthesis_provider import SynthesisProvider, ProviderState
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider

    call_count = 0

    class CountingFailProvider:
        available = True
        async def synthesize(self, system, user):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("simulated failure")

    provider = SynthesisProvider.wrap_provider(
        CountingFailProvider(),
        timeout_seconds=2,
        max_concurrent=1,
    )

    # Use novel signals so the LLM escalation trigger fires
    novel_signals = [
        ExecutionSignal(type=SignalType.MESSAGE_SENT, actor="ceo@corp.com",
            artifact="msg-novel", metadata={"customer": "Globex", "body": "gut feeling renewal at risk"},
            provider=SignalProvider.SLACK),
    ]

    async def run_5_calls():
        from maestro_oem.ask_pipeline import AskPipeline
        results = []
        for i in range(5):
            pipe = AskPipeline(signals=novel_signals, synthesis_provider=provider)
            r = await pipe.execute_async(
                "What is the status of Globex?", user_email="auditor@acme.com",
            )
            results.append(r)
        return results

    results = asyncio.run(run_5_calls())

    # First 3 calls should fail (CircuitBreaker CLOSED → records failures)
    # After 3 failures, CircuitBreaker trips to OPEN
    # Calls 4 and 5 should fail-fast (no API call made)
    assert call_count == 3, \
        f"CircuitBreaker should have allowed exactly 3 calls before tripping. Got {call_count}"

    # CircuitBreaker should be OPEN
    assert provider.circuit_state == ProviderState.OPEN, \
        f"CircuitBreaker should be OPEN after 3 failures. Got {provider.circuit_state}"

    # All 5 results should have fallen back to rule-based synthesizer
    for i, r in enumerate(results):
        trace = r["synthesis_trace"]
        assert trace["reasoning_mode"] in ("deterministic_fallback", "template_only"), \
            f"Iteration {i}: should be fallback, got {trace['reasoning_mode']}"

    # Calls 4 and 5 should have fallback_reason="circuit_open"
    assert "circuit_open" in results[3]["synthesis_trace"]["fallback_reason"], \
        f"Call 4 should be circuit_open. Got: {results[3]['synthesis_trace']['fallback_reason']}"
    assert "circuit_open" in results[4]["synthesis_trace"]["fallback_reason"], \
        f"Call 5 should be circuit_open. Got: {results[4]['synthesis_trace']['fallback_reason']}"

    # All 5 should surface the novel signal (not silently dropped)
    for i, r in enumerate(results):
        assert "gut feeling" in r["answer"].lower(), \
            f"Iteration {i}: novel signal must be surfaced even on circuit_open"
