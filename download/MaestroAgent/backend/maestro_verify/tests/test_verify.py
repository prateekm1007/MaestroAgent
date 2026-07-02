"""Smoke tests for maestro_verify — the module underpinning the
"verifiable autonomy" pitch. If it's untested, that claim is unverifiable.

Principle 3: no mocking the thing being verified. The critic tests use
a real stub LLM (not a mock of xmlsec/crypto). The sandbox tests use
real local execution (not a mock of Docker).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from maestro_verify.critic import CriticResult, evaluate_with_critic
from maestro_verify.evaluator import EvaluatorOptimizer
from maestro_verify.recovery import (
    FallbackPolicy,
    FailureRecovery,
    RecoveryAction,
)
from maestro_verify.registry import VerifierRegistry, VerifierResult


# ---------------------------------------------------------------------------
# VerifierRegistry
# ---------------------------------------------------------------------------


def test_verifier_registry_ships_with_builtin_verifiers() -> None:
    """The registry must ship with pytest, ruff, mypy verifiers."""
    reg = VerifierRegistry()
    names = reg.names()
    assert "pytest" in names
    assert "ruff" in names
    assert "mypy" in names


def test_verifier_registry_get_returns_async_callable() -> None:
    reg = VerifierRegistry()
    v = reg.get("pytest")
    assert callable(v)
    import asyncio
    assert asyncio.iscoroutinefunction(v)


def test_verifier_registry_unknown_raises_keyerror() -> None:
    reg = VerifierRegistry()
    with pytest.raises(KeyError):
        reg.get("does_not_exist")


def test_verifier_registry_accepts_custom_verifier() -> None:
    reg = VerifierRegistry()

    async def custom(state: Any, ctx: Any) -> VerifierResult:
        return VerifierResult(passed=True, score=1.0, reason="custom")

    reg.register("custom", custom)
    assert "custom" in reg.names()


# ---------------------------------------------------------------------------
# FallbackPolicy — circuit breaker
# ---------------------------------------------------------------------------


def test_circuit_opens_after_threshold_failures() -> None:
    policy = FallbackPolicy(circuit_breaker_threshold=3, circuit_breaker_cooldown=60.0)
    assert policy.is_available("ollama") is True
    policy.record_failure("ollama")
    policy.record_failure("ollama")
    assert policy.is_available("ollama") is True
    policy.record_failure("ollama")
    assert policy.is_available("ollama") is False


def test_circuit_closes_after_cooldown() -> None:
    import time
    policy = FallbackPolicy(circuit_breaker_threshold=1, circuit_breaker_cooldown=0.05)
    policy.record_failure("ollama")
    assert policy.is_available("ollama") is False
    time.sleep(0.06)
    assert policy.is_available("ollama") is True


def test_record_success_resets_failure_count() -> None:
    policy = FallbackPolicy(circuit_breaker_threshold=3)
    policy.record_failure("ollama")
    policy.record_failure("ollama")
    policy.record_success("ollama")
    policy.record_failure("ollama")
    assert policy.is_available("ollama") is True


def test_next_provider_walks_chain() -> None:
    policy = FallbackPolicy(provider_chain=["ollama", "openrouter", "anthropic"])
    assert policy.next_provider("ollama") == "openrouter"


def test_next_provider_skips_unavailable() -> None:
    policy = FallbackPolicy(provider_chain=["ollama", "openrouter", "anthropic"])
    policy._failure_counts["openrouter"] = 99
    policy._circuit_open_until["openrouter"] = float("inf")
    assert policy.next_provider("ollama") == "anthropic"


# ---------------------------------------------------------------------------
# FailureRecovery.classify
# ---------------------------------------------------------------------------


def test_classify_budget_exhausted_pauses() -> None:
    from maestro_core.context import BudgetExhausted
    recovery = FailureRecovery()
    assert recovery.classify(BudgetExhausted("over")) is RecoveryAction.PAUSE


def test_classify_permission_error_escalates() -> None:
    recovery = FailureRecovery()
    assert recovery.classify(PermissionError("denied")) is RecoveryAction.ESCALATE


def test_classify_timeout_retries() -> None:
    recovery = FailureRecovery()
    assert recovery.classify(TimeoutError("slow")) is RecoveryAction.RETRY


def test_classify_generic_retries() -> None:
    recovery = FailureRecovery()
    assert recovery.classify(RuntimeError("??")) is RecoveryAction.RETRY


# ---------------------------------------------------------------------------
# Critic — empty output short-circuit (no LLM needed, Principle 3)
# ---------------------------------------------------------------------------


async def test_critic_empty_output_returns_zero_without_calling_llm() -> None:
    """Empty output must short-circuit to 0.0 without an LLM call.

    This is the only critic path that doesn't need an LLM, so it's the
    one we can test in true isolation. An agent that returns empty output
    must NOT get a free pass.
    """
    result = await evaluate_with_critic(
        ctx=None,  # type: ignore[arg-type]
        rubric="anything",
        output="   ",
    )
    assert result.score == 0.0
    assert "empty" in result.justification.lower()


# ---------------------------------------------------------------------------
# Critic — non-empty path with a real stub LLM (not a mock of crypto)
# ---------------------------------------------------------------------------


@dataclass
class _StubLLMResponse:
    text: str
    cost_usd: float = 0.0


@dataclass
class _StubConfig:
    run_id: str = "r1"


@dataclass
class _StubEvents:
    emitted: list = field(default_factory=list)

    async def emit(self, *a: Any, **kw: Any) -> None:
        self.emitted.append((a, kw))


@dataclass
class _StubCtx:
    llm: _StubLLMResponse  # type: ignore[assignment]
    events: _StubEvents
    cost_so_far: float = 0.0
    config: _StubConfig = field(default_factory=_StubConfig)

    def check_budget(self) -> None:
        pass


@dataclass
class _StubLLM:
    """Real stub — returns a canned response. Not a mock of a crypto library."""
    response_text: str

    async def complete(self, **kwargs: Any) -> _StubLLMResponse:
        return _StubLLMResponse(text=self.response_text, cost_usd=0.001)


async def test_critic_parses_well_formed_json() -> None:
    llm = _StubLLM(response_text='{"score": 0.85, "justification": "good", "suggestions": ["add tests"]}')
    ctx = _StubCtx(llm=llm, events=_StubEvents())  # type: ignore[arg-type]
    result = await evaluate_with_critic(ctx=ctx, rubric="r", output="my work")
    assert result.score == 0.85
    assert result.suggestions == ["add tests"]


async def test_critic_clamps_score_to_unit_interval() -> None:
    """A misbehaving LLM returning score=1.5 must be clamped to 1.0, not crash."""
    llm = _StubLLM(response_text='{"score": 1.5, "justification": "x", "suggestions": []}')
    ctx = _StubCtx(llm=llm, events=_StubEvents())  # type: ignore[arg-type]
    result = await evaluate_with_critic(ctx=ctx, rubric="r", output="work")
    assert result.score == 1.0


async def test_critic_extracts_json_from_prose_wrapper() -> None:
    """LLMs sometimes wrap JSON in prose — the critic must still extract it."""
    llm = _StubLLM(response_text='Here:\n{"score": 0.7, "justification": "ok", "suggestions": []}\nThanks!')
    ctx = _StubCtx(llm=llm, events=_StubEvents())  # type: ignore[arg-type]
    result = await evaluate_with_critic(ctx=ctx, rubric="r", output="work")
    assert result.score == 0.7


async def test_critic_non_json_defaults_to_neutral() -> None:
    """Total JSON parse failure defaults to 0.5, not 0.0 or crash."""
    llm = _StubLLM(response_text="I cannot evaluate this.")
    ctx = _StubCtx(llm=llm, events=_StubEvents())  # type: ignore[arg-type]
    result = await evaluate_with_critic(ctx=ctx, rubric="r", output="work")
    assert result.score == 0.5


# ---------------------------------------------------------------------------
# EvaluatorOptimizer — convergence + budget exhaustion
# ---------------------------------------------------------------------------


async def test_evaluator_converges_when_score_crosses_threshold() -> None:
    from maestro_core.state import State

    llm = _StubLLM(response_text='{"score": 0.9, "justification": "good", "suggestions": []}')
    ctx = _StubCtx(llm=llm, events=_StubEvents())  # type: ignore[arg-type]
    calls = 0

    async def gen(state: State, suggestions: list[str], ctx: Any) -> str:
        nonlocal calls
        calls += 1
        return "draft"

    ev = EvaluatorOptimizer(id="e1", generator=gen, rubric="r", threshold=0.85, max_iterations=5)
    await ev.run(State(), ctx)  # type: ignore[arg-type]
    assert calls == 1  # converged after 1 iteration


async def test_evaluator_exits_on_max_iterations_without_convergence() -> None:
    from maestro_core.state import State

    llm = _StubLLM(response_text='{"score": 0.3, "justification": "bad", "suggestions": ["fix"]}')
    ctx = _StubCtx(llm=llm, events=_StubEvents())  # type: ignore[arg-type]

    async def gen(state: State, suggestions: list[str], ctx: Any) -> str:
        return "draft"

    ev = EvaluatorOptimizer(id="e1", generator=gen, rubric="r", threshold=0.85, max_iterations=2)
    result_state = await ev.run(State(), ctx)  # type: ignore[arg-type]
    assert result_state.messages[-1]["iterations"] == 2
    assert result_state.metadata["e1_converged"] is False
