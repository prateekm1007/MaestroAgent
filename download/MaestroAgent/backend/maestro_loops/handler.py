"""LoopHandler — the engine that drives a loop to verifiable completion.

A `LoopHandler` wraps a "body" (a callable that produces a new state
from the current one) and runs it repeatedly until the exit condition
is met or the budget is exhausted.

This is the single biggest reliability primitive in MaestroAgent.
Without it, "until tests pass" is a hand-rolled `while` loop hidden
inside a node — bug-prone and unobservable. With it, every iteration
is checkpointed, every condition evaluation is logged, and every
exit decision is auditable.

Usage as a graph node
---------------------
A `LoopHandler` is itself a node: `(State, RunContext) -> State`.
Embed it in a graph like any other node:

    graph.add_node(Node(id="fix_until_tests_pass", fn=loop_handler))

Or use the convenience constructor:

    graph.add_node(loop_until("fix", body=fix_agent, condition=TestPassCondition("pytest")))
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from maestro_loops.conditions import Condition, ConditionResult
from maestro_loops.types import BackoffPolicy, LoopKind, OnExceedAction
from maestro_core.state import RunStatus, State
from maestro_core.streaming import EventType

if TYPE_CHECKING:
    from maestro_core.context import RunContext

logger = logging.getLogger(__name__)

# A loop body: takes a state, returns a new state. Same shape as a Node fn.
LoopBody = Callable[["State", "RunContext"], Awaitable["State"]]


class LoopOutcome(str, Enum):
    EXIT_CONDITION_MET = "exit_condition_met"
    BUDGET_EXHAUSTED = "budget_exhausted"
    MAX_ITERATIONS = "max_iterations"
    STAGNANT = "stagnant"
    ERROR = "error"
    HITL_PAUSED = "hitl_paused"


@dataclass
class LoopSpec:
    """Declarative spec for a loop — used by templates and the UI."""

    id: str
    kind: LoopKind = LoopKind.RECURSIVE
    body: LoopBody | None = None
    exit_condition: Condition | None = None
    max_iterations: int = 20
    max_cost_usd: float | None = None
    max_wall_clock_seconds: float | None = None
    backoff: BackoffPolicy = field(default_factory=BackoffPolicy)
    on_exceed: OnExceedAction = OnExceedAction.ESCALATE
    # Stagnation detector: if score does not improve by this much over
    # `stagnation_window` iterations, exit with STAGNANT.
    stagnation_window: int = 3
    stagnation_min_improvement: float = 0.0


@dataclass
class LoopHandler:
    """Runs a loop body until the exit condition is met or budget exhausted.

    This is itself a graph node — `__call__(state, ctx) -> state`.
    """

    spec: LoopSpec

    async def __call__(self, state: State, ctx: "RunContext") -> State:
        if self.spec.body is None:
            raise ValueError(f"Loop {self.spec.id} has no body")
        if self.spec.exit_condition is None:
            raise ValueError(f"Loop {self.spec.id} has no exit condition")

        await ctx.events.emit(
            EventType.LOOP_ITERATION,
            run_id=ctx.config.run_id,
            loop_id=self.spec.id,
            iteration=0,
            kind=self.spec.kind.value,
        )

        current = state
        last_score: float | None = None
        score_history: list[float | None] = []
        body_cost_at_start = ctx.cost_so_far
        body_started_at = asyncio.get_event_loop().time()

        for i in range(1, self.spec.max_iterations + 1):
            # Budget checks.
            if self.spec.max_cost_usd is not None:
                spent_in_loop = ctx.cost_so_far - body_cost_at_start
                if spent_in_loop >= self.spec.max_cost_usd:
                    return await self._exit(
                        current, ctx, LoopOutcome.BUDGET_EXHAUSTED, i,
                        reason=f"loop cost {spent_in_loop:.4f} >= {self.spec.max_cost_usd}",
                    )
            if self.spec.max_wall_clock_seconds is not None:
                elapsed = asyncio.get_event_loop().time() - body_started_at
                if elapsed >= self.spec.max_wall_clock_seconds:
                    return await self._exit(
                        current, ctx, LoopOutcome.BUDGET_EXHAUSTED, i,
                        reason=f"loop wall-clock {elapsed:.1f}s >= {self.spec.max_wall_clock_seconds}",
                    )

            # Run the body.
            current = current.with_updates(iteration=i, current_node=self.spec.id)
            await ctx.events.emit(
                EventType.LOOP_ITERATION,
                run_id=ctx.config.run_id,
                loop_id=self.spec.id,
                iteration=i,
            )
            try:
                current = await self.spec.body(current, ctx)
            except Exception as exc:
                logger.exception("Loop %s body failed on iter %d", self.spec.id, i)
                await ctx.events.emit(
                    EventType.LOOP_ITERATION,
                    run_id=ctx.config.run_id,
                    loop_id=self.spec.id,
                    iteration=i,
                    error=str(exc),
                )
                # Backoff and retry next iteration unless we hit max.
                if i >= self.spec.max_iterations:
                    return await self._exit(
                        current, ctx, LoopOutcome.ERROR, i, reason=str(exc)
                    )
                await self._backoff(i)
                continue

            # Check exit condition.
            try:
                result: ConditionResult = await self.spec.exit_condition.evaluate(current, ctx)
            except Exception as exc:
                logger.exception("Loop %s condition failed on iter %d", self.spec.id, i)
                return await self._exit(
                    current, ctx, LoopOutcome.ERROR, i,
                    reason=f"condition error: {exc}",
                )

            score_history.append(result.score)
            await ctx.events.emit(
                EventType.LOOP_ITERATION,
                run_id=ctx.config.run_id,
                loop_id=self.spec.id,
                iteration=i,
                condition_met=result.met,
                condition_reason=result.reason,
                score=result.score,
            )

            if result.met:
                return await self._exit(
                    current, ctx, LoopOutcome.EXIT_CONDITION_MET, i,
                    reason=result.reason, score=result.score,
                )

            # Stagnation check.
            if (
                len(score_history) >= self.spec.stagnation_window
                and result.score is not None
                and last_score is not None
            ):
                window = score_history[-self.spec.stagnation_window:]
                if all(s is not None for s in window):
                    improvement = max(window) - min(window)
                    if improvement < self.spec.stagnation_min_improvement:
                        return await self._exit(
                            current, ctx, LoopOutcome.STAGNANT, i,
                            reason=f"score stagnated over last {self.spec.stagnation_window} iters",
                            score=result.score,
                        )

            last_score = result.score
            await self._backoff(i)

        return await self._exit(
            current, ctx, LoopOutcome.MAX_ITERATIONS, self.spec.max_iterations,
            reason=f"hit max_iterations={self.spec.max_iterations}",
        )

    async def _exit(
        self,
        state: State,
        ctx: "RunContext",
        outcome: LoopOutcome,
        iterations: int,
        reason: str = "",
        score: float | None = None,
    ) -> State:
        """Apply the on_exceed policy and return the final state."""
        await ctx.events.emit(
            EventType.LOOP_EXIT,
            run_id=ctx.config.run_id,
            loop_id=self.spec.id,
            outcome=outcome.value,
            iterations=iterations,
            reason=reason,
            score=score,
        )

        if outcome == LoopOutcome.EXIT_CONDITION_MET:
            return state.with_updates(
                metadata={**state.metadata, f"loop:{self.spec.id}:outcome": outcome.value, f"loop:{self.spec.id}:iterations": iterations}
            )

        # Non-success outcomes: apply on_exceed policy.
        action = self.spec.on_exceed
        if action == OnExceedAction.ESCALATE:
            return state.with_updates(
                status=RunStatus.AWAITING_HUMAN,
                metadata={
                    **state.metadata,
                    f"loop:{self.spec.id}:outcome": outcome.value,
                    f"loop:{self.spec.id}:iterations": iterations,
                    "hitl_reason": f"loop_{self.spec.id}_{outcome.value}: {reason}",
                },
            )
        elif action == OnExceedAction.PAUSE:
            return state.with_updates(
                status=RunStatus.PAUSED,
                metadata={**state.metadata, f"loop:{self.spec.id}:outcome": outcome.value},
            )
        elif action == OnExceedAction.FAIL:
            return state.with_updates(
                status=RunStatus.FAILED,
                error=f"loop {self.spec.id} {outcome.value}: {reason}",
                metadata={**state.metadata, f"loop:{self.spec.id}:outcome": outcome.value},
            )
        else:  # CONTINUE
            return state.with_updates(
                metadata={**state.metadata, f"loop:{self.spec.id}:outcome": outcome.value}
            )

    async def _backoff(self, iteration: int) -> None:
        b = self.spec.backoff
        delay = min(
            b.initial_seconds * (b.multiplier ** (iteration - 1)),
            b.max_seconds,
        )
        # Jitter.
        import random
        jitter = delay * b.jitter * (2 * random.random() - 1)
        await asyncio.sleep(max(0.0, delay + jitter))


def loop_until(
    id: str,
    body: LoopBody,
    condition: Condition,
    *,
    max_iterations: int = 20,
    on_exceed: OnExceedAction = OnExceedAction.ESCALATE,
    kind: LoopKind = LoopKind.RECURSIVE,
) -> LoopHandler:
    """Convenience: build a LoopHandler as a graph node."""
    return LoopHandler(
        spec=LoopSpec(
            id=id,
            kind=kind,
            body=body,
            exit_condition=condition,
            max_iterations=max_iterations,
            on_exceed=on_exceed,
        )
    )
