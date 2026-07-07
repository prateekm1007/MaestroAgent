"""P22 test: Coverage Assessor through the PRODUCTION path, not hardcoded evidence.

AUDITOR FINDING:
> The coder's test constructs evidence directly with hardcoded claim_type.
> This bypasses the production pipeline. In production, the pipeline calls
> the classifier, then the override at line 1113 may fire.
>
> The coder should re-run their tests using evidence constructed through
> _search_signals() (the production path), not hardcoded evidence dicts.

This test does exactly what the auditor asked: builds signals, runs them
through _search_signals() (the production path), then feeds the resulting
evidence to the CoverageAssessor. This catches any production-path
artifacts (overrides, classifier behavior, etc.) that hardcoded tests miss.
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


def _make_pricing_signals():
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
    return [
        ExecutionSignal(type=SignalType.MESSAGE_SENT, actor="cfo@corp.com",
            artifact="msg-day1", metadata={"customer": "AcmeCorp", "body": "finance approves 8% price increase"},
            provider=SignalProvider.SLACK),
        ExecutionSignal(type=SignalType.MESSAGE_SENT, actor="vp_sales@corp.com",
            artifact="msg-day8", metadata={"customer": "AcmeCorp", "body": "existing strategic accounts will be protected from the increase"},
            provider=SignalProvider.SLACK),
        ExecutionSignal(type=SignalType.MESSAGE_SENT, actor="billing@corp.com",
            artifact="msg-day20", metadata={"customer": "AcmeCorp", "body": "new price table deployed to billing system"},
            provider=SignalProvider.SLACK),
        ExecutionSignal(type=SignalType.MESSAGE_SENT, actor="cs@corp.com",
            artifact="msg-day40", metadata={"customer": "AcmeCorp", "body": "three strategic accounts were charged the new rate"},
            provider=SignalProvider.SLACK),
        ExecutionSignal(type=SignalType.MESSAGE_SENT, actor="vp_sales@corp.com",
            artifact="msg-day45", metadata={"customer": "AcmeCorp", "body": "the pricing rollout is complete"},
            provider=SignalProvider.SLACK),
        ExecutionSignal(type=SignalType.MESSAGE_SENT, actor="customer@acmecorp.com",
            artifact="msg-day50", metadata={"customer": "AcmeCorp", "body": "we were told our existing contract terms were protected"},
            provider=SignalProvider.SLACK),
    ]


def _make_sso_signals():
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
    return [
        ExecutionSignal(type=SignalType.MESSAGE_SENT, actor="sales@corp.com",
            artifact="msg-day5", metadata={"customer": "Globex", "body": "should be able to support SSO before renewal"},
            provider=SignalProvider.SLACK),
        ExecutionSignal(type=SignalType.MESSAGE_SENT, actor="exec@corp.com",
            artifact="msg-day12", metadata={"customer": "Globex", "body": "we will have SSO available"},
            provider=SignalProvider.SLACK),
        ExecutionSignal(type=SignalType.MESSAGE_SENT, actor="product@corp.com",
            artifact="msg-day30", metadata={"customer": "Globex", "body": "target: before renewal"},
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


def test_pricing_scenario_escalates_through_production_path():
    """P22: Pricing scenario escalates to LLM when run through _search_signals().

    AUDITOR DIRECTIVE:
    > Re-run tests using evidence constructed through _search_signals()
    > (the production path), not hardcoded evidence dicts.

    This test builds signals, runs them through the REAL _search_signals()
    (which calls ContentEpistemicClassifier on body text), then feeds the
    production evidence to CoverageAssessor.
    """
    from maestro_oem.ask_pipeline import AskPipeline
    from maestro_oem.coverage_assessor import CoverageAssessor

    pipe = AskPipeline(signals=_make_pricing_signals(), synthesis_provider=None)
    evidence, _ = pipe._search_signals(
        entities=["AcmeCorp"], query="What happened with the pricing rollout?",
        user_email="auditor@acme.com",
    )

    # Show what the production pipeline actually produced
    print(f"\nProduction evidence: {len(evidence)} items")
    for i, e in enumerate(evidence):
        ct = e["evidence_spine"]["claim_type"]
        print(f"  [{i}] {ct:25s}  {e['text'][:60]}")

    assessor = CoverageAssessor()
    result = assessor.assess("What happened with the pricing rollout?", evidence)

    print(f"\nCoverage score: {result.coverage_score}")
    print(f"Should escalate: {result.should_escalate}")
    print(f"Gaps: {result.gaps}")

    # The pricing scenario MUST escalate — novel vocabulary
    assert result.should_escalate is True, \
        f"Pricing scenario must escalate through production path. " \
        f"Coverage={result.coverage_score}, gaps={result.gaps}"


def test_sso_scenario_does_not_escalate_through_production_path():
    """P22: SSO scenario does NOT escalate when run through _search_signals()."""
    from maestro_oem.ask_pipeline import AskPipeline
    from maestro_oem.coverage_assessor import CoverageAssessor

    pipe = AskPipeline(signals=_make_sso_signals(), synthesis_provider=None)
    evidence, _ = pipe._search_signals(
        entities=["Globex"], query="What exactly did we promise Globex?",
        user_email="auditor@acme.com",
    )

    print(f"\nProduction evidence: {len(evidence)} items")
    for i, e in enumerate(evidence):
        ct = e["evidence_spine"]["claim_type"]
        print(f"  [{i}] {ct:25s}  {e['text'][:60]}")

    assessor = CoverageAssessor()
    result = assessor.assess("What exactly did we promise Globex?", evidence)

    print(f"\nCoverage score: {result.coverage_score}")
    print(f"Should escalate: {result.should_escalate}")
    print(f"Gaps: {result.gaps}")

    # SSO should have high coverage (known categories + known relationships)
    assert result.coverage_score >= 0.8, \
        f"SSO should have high coverage. Got {result.coverage_score}"


def test_pricing_executes_llm_through_production_path():
    """P22: Full production path — pricing scenario escalates to LLM in execute_async."""
    from maestro_oem.ask_pipeline import AskPipeline
    from maestro_oem.synthesis_provider import SynthesisProvider

    class MockProvider:
        available = True
        circuit_state = type("S", (), {"value": "closed"})()
        async def synthesize(self, system, user):
            return type("R", (), {
                "text": "LLM synthesized the pricing scenario",
                "model_used": "test", "provider_name": "test",
                "mode": "model", "fallback_reason": "",
                "latency_ms": 10, "prompt_tokens": 10, "completion_tokens": 5,
            })()

    provider = SynthesisProvider.wrap_provider(MockProvider(), timeout_seconds=5)
    pipe = AskPipeline(signals=_make_pricing_signals(), synthesis_provider=provider)

    result = asyncio.run(pipe.execute_async(
        "What happened with the AcmeCorp pricing rollout?",
        user_email="auditor@acme.com",
    ))

    trace = result["synthesis_trace"]
    print(f"\nReasoning mode: {trace['reasoning_mode']}")
    print(f"Fallback: {trace['fallback_triggered']}")

    # The pricing scenario should escalate to the LLM
    assert trace["reasoning_mode"] == "model", \
        f"Pricing should escalate to LLM. Got {trace['reasoning_mode']}"


def test_sso_does_not_call_llm_through_production_path():
    """P22: Full production path — SSO scenario does NOT call the LLM."""
    from maestro_oem.ask_pipeline import AskPipeline
    from maestro_oem.synthesis_provider import SynthesisProvider

    call_count = 0

    class TrackingProvider:
        available = True
        circuit_state = type("S", (), {"value": "closed"})()
        async def synthesize(self, system, user):
            nonlocal call_count
            call_count += 1
            return type("R", (), {
                "text": "should not be called", "model_used": "test",
                "provider_name": "test", "mode": "model", "fallback_reason": "",
                "latency_ms": 10, "prompt_tokens": 10, "completion_tokens": 5,
            })()

    provider = SynthesisProvider.wrap_provider(TrackingProvider(), timeout_seconds=5)
    pipe = AskPipeline(signals=_make_sso_signals(), synthesis_provider=provider)

    result = asyncio.run(pipe.execute_async(
        "What exactly did we promise Globex?",
        user_email="auditor@acme.com",
    ))

    trace = result["synthesis_trace"]
    print(f"\nReasoning mode: {trace['reasoning_mode']}")
    print(f"LLM calls: {call_count}")

    # SSO should NOT escalate — coverage is sufficient
    assert trace["reasoning_mode"] == "template_only", \
        f"SSO should NOT escalate to LLM. Got {trace['reasoning_mode']}"
    assert call_count == 0, \
        f"SSO should not call LLM. Got {call_count} calls"
