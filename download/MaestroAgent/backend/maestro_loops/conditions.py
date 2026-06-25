"""Exit conditions for loops.

A `Condition` is an async callable `(State, RunContext) -> ConditionResult`.
Loops check their condition after each iteration; if met, the loop exits.

Built-in conditions
-------------------
- `TestPassCondition` — run a test command in the sandbox; exit if it passes.
- `MetricThresholdCondition` — exit when a metric (e.g. test pass rate)
  crosses a threshold.
- `CriticCondition` — an LLM-as-judge scores the latest output; exit if
  the score crosses a threshold.
- `CallableCondition` — wrap a user-supplied async callable.
- `AllOf` / `AnyOf` — boolean combinators.

Conditions are *verifiers*, not *executors*: they read state but should
not mutate it. This separation is what makes MaestroAgent's autonomy
*verifiable* — the loop's exit is decided by an independent party, not
by the agent that did the work.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from maestro_core.context import RunContext
    from maestro_core.state import State


@dataclass
class ConditionResult:
    met: bool
    reason: str = ""
    score: float | None = None  # optional numeric score for UI


class Condition(abc.ABC):
    """Abstract loop exit condition."""

    @abc.abstractmethod
    async def evaluate(self, state: "State", ctx: "RunContext") -> ConditionResult: ...

    async def __call__(self, state: "State", ctx: "RunContext") -> ConditionResult:
        return await self.evaluate(state, ctx)


@dataclass
class CallableCondition(Condition):
    """Wrap a user-supplied async callable as a condition."""

    fn: Callable[["State", "RunContext"], Awaitable[ConditionResult]]
    name: str = "callable"

    async def evaluate(self, state: "State", ctx: "RunContext") -> ConditionResult:
        return await self.fn(state, ctx)


@dataclass
class TestPassCondition(Condition):
    """Exit when a shell test command succeeds in the sandbox.

    The command runs inside the configured sandbox container. If the
    sandbox is disabled, it runs locally (with a warning emitted).
    """

    command: str
    cwd: str = "/workspace"
    timeout_seconds: int = 120
    name: str = "tests"

    async def evaluate(self, state: "State", ctx: "RunContext") -> ConditionResult:
        # We delegate tool execution to the plugin/tool registry. For v0.1,
        # we run the command via the verifier's sandbox runner.
        from maestro_verify.sandbox import run_in_sandbox

        result = await run_in_sandbox(
            ctx, command=self.command, cwd=self.cwd, timeout=self.timeout_seconds
        )
        passed = result.exit_code == 0
        return ConditionResult(
            met=passed,
            reason=(
                f"tests passed ({len(result.stdout)} bytes stdout)"
                if passed
                else f"tests failed (exit {result.exit_code}): {result.stderr[:300]}"
            ),
            score=1.0 if passed else 0.0,
        )


@dataclass
class MetricThresholdCondition(Condition):
    """Exit when a numeric metric crosses a threshold.

    The metric is read from `state.metadata[metric_key]`. The loop's
    body is responsible for writing the metric each iteration.
    """

    metric_key: str
    threshold: float
    comparator: str = ">="  # one of >=, <=, >, <, ==
    name: str = "metric"

    async def evaluate(self, state: "State", ctx: "RunContext") -> ConditionResult:
        value = state.metadata.get(self.metric_key)
        if value is None:
            return ConditionResult(met=False, reason=f"metric {self.metric_key} not set")
        try:
            v = float(value)
        except (TypeError, ValueError):
            return ConditionResult(
                met=False, reason=f"metric {self.metric_key} not numeric: {value}"
            )
        ops = {
            ">=": v >= self.threshold,
            "<=": v <= self.threshold,
            ">": v > self.threshold,
            "<": v < self.threshold,
            "==": v == self.threshold,
        }
        met = ops.get(self.comparator, False)
        return ConditionResult(
            met=met,
            reason=f"{self.metric_key}={v} {self.comparator} {self.threshold}: {met}",
            score=v,
        )


@dataclass
class CriticCondition(Condition):
    """Exit when an LLM-as-judge critic scores the output above a threshold.

    The critic is an independent agent that scores the latest output
    against a rubric. This is the LangGraph evaluator-optimizer pattern,
    packaged as a reusable exit condition.
    """

    rubric: str
    threshold: float = 0.8
    agent_id: str = "critic"
    name: str = "critic"

    async def evaluate(self, state: "State", ctx: "RunContext") -> ConditionResult:
        from maestro_verify.critic import score_with_critic

        last_output = ""
        if state.messages:
            content = state.messages[-1].get("content", "")
            last_output = str(content)[:4000]

        score = await score_with_critic(
            ctx=ctx,
            rubric=self.rubric,
            output=last_output,
            agent_id=self.agent_id,
        )
        met = score >= self.threshold
        return ConditionResult(
            met=met,
            reason=f"critic score {score:.2f} {'>=' if met else '<'} {self.threshold}",
            score=score,
        )


@dataclass
class AllOf(Condition):
    """Met when ALL of the sub-conditions are met."""

    conditions: list[Condition]

    async def evaluate(self, state: "State", ctx: "RunContext") -> ConditionResult:
        results = []
        for c in self.conditions:
            results.append(await c.evaluate(state, ctx))
        met = all(r.met for r in results)
        return ConditionResult(
            met=met,
            reason="ALL: " + " | ".join(r.reason for r in results),
            score=min((r.score for r in results if r.score is not None), default=None),
        )


@dataclass
class AnyOf(Condition):
    """Met when ANY of the sub-conditions is met."""

    conditions: list[Condition]

    async def evaluate(self, state: "State", ctx: "RunContext") -> ConditionResult:
        results = []
        for c in self.conditions:
            results.append(await c.evaluate(state, ctx))
        met = any(r.met for r in results)
        return ConditionResult(
            met=met,
            reason="ANY: " + " | ".join(r.reason for r in results),
            score=max((r.score for r in results if r.score is not None), default=None),
        )
