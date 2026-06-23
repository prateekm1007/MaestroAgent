"""Nested, parallel, and meta loops.

These are loop combinators — loops whose bodies contain other loops.

- `NestedLoop` — a loop whose body is itself a `LoopHandler`. The outer
  loop runs the inner loop to completion each iteration.
- `ParallelLoop` — runs N independent `LoopHandler`s concurrently and
  merges their results.
- `MetaLoop` — a supervisor-driven loop that, each iteration, decides
  which child loop to run next based on the current state.

These are exposed as graph nodes just like `LoopHandler`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from maestro_loops.handler import LoopHandler, LoopOutcome
from maestro_loops.conditions import Condition
from maestro_loops.types import BackoffPolicy, LoopKind, OnExceedAction
from maestro_core.state import State
from maestro_core.streaming import EventType

if TYPE_CHECKING:
    from maestro_core.context import RunContext

logger = logging.getLogger(__name__)


@dataclass
class NestedLoop(LoopHandler):
    """A loop whose body is an inner LoopHandler.

    Each outer iteration runs the inner loop to completion (or its own
    exit), then the outer condition is evaluated.
    """

    inner: LoopHandler | None = None

    async def __call__(self, state: State, ctx: "RunContext") -> State:
        if self.inner is None:
            raise ValueError("NestedLoop requires an inner LoopHandler")
        # Wrap the inner loop as the body.
        original_body = self.spec.body
        self.spec.body = lambda s, c: self.inner(s, c)  # type: ignore
        try:
            return await super().__call__(state, ctx)
        finally:
            self.spec.body = original_body


@dataclass
class ParallelLoop:
    """Run N independent LoopHandlers concurrently, merge results.

    Each child loop runs against a *fork* of the state (so they don't
    clobber each other). After all complete, results are merged:
    - messages: concatenated
    - artifacts: shallow-merged (later children win on conflicts)
    - metadata: merged; per-child outcomes stored under loop:<id>:outcome
    """

    id: str
    children: list[LoopHandler]
    merge_condition: Condition | None = None  # if set, also evaluated after merge

    async def __call__(self, state: State, ctx: "RunContext") -> State:
        await ctx.events.emit(
            EventType.LOOP_ITERATION,
            run_id=ctx.config.run_id,
            loop_id=self.id,
            kind=LoopKind.PARALLEL.value,
            children=[c.spec.id for c in self.children],
        )

        async def _run_one(child: LoopHandler, fork: State) -> State:
            return await child(fork, ctx)

        forks = [state.bump() for _ in self.children]
        results = await asyncio.gather(
            *[_run_one(c, f) for c, f in zip(self.children, forks)],
            return_exceptions=True,
        )

        merged = state.bump()
        all_messages = list(state.messages)
        all_artifacts = dict(state.artifacts)
        all_metadata = dict(state.metadata)
        for child, r in zip(self.children, results):
            if isinstance(r, Exception):
                all_metadata[f"loop:{child.spec.id}:error"] = str(r)
                continue
            all_messages.extend(r.messages)
            all_artifacts.update(r.artifacts)
            all_metadata.update(r.metadata)

        merged = merged.with_updates(
            messages=all_messages,
            artifacts=all_artifacts,
            metadata=all_metadata,
        )

        if self.merge_condition is not None:
            res = await self.merge_condition.evaluate(merged, ctx)
            await ctx.events.emit(
                EventType.LOOP_EXIT,
                run_id=ctx.config.run_id,
                loop_id=self.id,
                outcome="merge_condition_evaluated",
                met=res.met,
                reason=res.reason,
            )
        return merged


@dataclass
class MetaLoop:
    """A supervisor-driven meta-loop that picks which child loop to run next.

    Each iteration:
    1. Ask the LLM: given the current state, which child loop should run next?
    2. Run that child loop for one iteration.
    3. Re-evaluate the meta-condition.
    4. If met, exit; else repeat.

    This is the highest-level loop primitive — it lets a supervisor
    dynamically choose between "fix bugs", "add tests", "refactor",
    "improve docs", etc. based on what the run needs most.
    """

    id: str
    children: dict[str, LoopHandler]
    meta_condition: Condition
    max_iterations: int = 10
    # The selector LLM call: returns a child id.
    selector_prompt: str = "Given the current state, which sub-loop should run next?"

    async def __call__(self, state: State, ctx: "RunContext") -> State:
        await ctx.events.emit(
            EventType.LOOP_ITERATION,
            run_id=ctx.config.run_id,
            loop_id=self.id,
            kind=LoopKind.META.value,
        )

        current = state
        for i in range(1, self.max_iterations + 1):
            ctx.check_budget()

            # 1. Pick a child.
            child_id = await self._select_child(current, ctx)
            if child_id is None or child_id not in self.children:
                # No selection — exit.
                break
            child = self.children[child_id]

            await ctx.events.emit(
                EventType.LOOP_ITERATION,
                run_id=ctx.config.run_id,
                loop_id=self.id,
                iteration=i,
                selected_child=child_id,
            )

            # 2. Run the child for one iteration (we trick it by setting
            #    its max_iterations to 1 temporarily).
            original_max = child.spec.max_iterations
            child.spec.max_iterations = 1
            try:
                current = await child(current, ctx)
            finally:
                child.spec.max_iterations = original_max

            # 3. Evaluate the meta-condition.
            result = await self.meta_condition.evaluate(current, ctx)
            await ctx.events.emit(
                EventType.LOOP_ITERATION,
                run_id=ctx.config.run_id,
                loop_id=self.id,
                iteration=i,
                meta_condition_met=result.met,
                reason=result.reason,
            )
            if result.met:
                await ctx.events.emit(
                    EventType.LOOP_EXIT,
                    run_id=ctx.config.run_id,
                    loop_id=self.id,
                    outcome="meta_condition_met",
                    iterations=i,
                )
                break

        return current

    async def _select_child(self, state: State, ctx: "RunContext") -> str | None:
        """Ask the LLM which child to run next. Returns a child id or None."""
        child_list = "\n".join(f"- {cid}: {c.spec.id}" for cid, c in self.children.items())
        resp = await ctx.llm.complete(
            system=(
                "You are a meta-supervisor. Pick which sub-loop should run next. "
                "Respond with EXACTLY ONE child id from the list, or 'none' to stop. "
                "No other text."
            ),
            user=(
                f"{self.selector_prompt}\n\n"
                f"Available children:\n{child_list}\n\n"
                f"Current artifacts: {list(state.artifacts.keys())}\n"
                f"Recent: {str(state.messages[-3:])[:1500]}"
            ),
            provider=None,
            model=None,
            temperature=0.0,
            tools=[],
            run_id=ctx.config.run_id,
            agent_id=f"{self.id}__selector",
        )
        ctx.cost_so_far += resp.cost_usd
        text = resp.text.strip().lower()
        if text == "none" or text not in self.children:
            return None
        return text
