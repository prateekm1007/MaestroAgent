"""Evaluator-optimizer loop — generate → evaluate → optimize → regenerate.

This is the LangGraph evaluator-optimizer pattern: a generator produces
an output, an evaluator scores it, an optimizer proposes improvements,
and the generator regenerates with the improvements. Repeat until the
evaluator's score crosses a threshold or the budget is exhausted.

Use cases
---------
- Improving code quality before declaring "done".
- Refining a design document against a spec.
- Polishing a research summary for clarity.

This is implemented as a self-contained loop (NOT a `LoopHandler`
condition) because it has its own internal state: the current draft,
the score history, and the list of suggestions applied.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from maestro_core.state import State
from maestro_core.streaming import EventType
from maestro_verify.critic import evaluate_with_critic

if TYPE_CHECKING:
    from maestro_core.context import RunContext

logger = logging.getLogger(__name__)


# A generator: takes a state + optional suggestions, returns new output text.
Generator = Callable[["State", list[str], "RunContext"], Awaitable[str]]
# An optimizer: takes output + critic result, returns suggestions for next iteration.
Optimizer = Callable[[str, Any, "RunContext"], Awaitable[list[str]]]


@dataclass
class EvalResult:
    """Outcome of an evaluator-optimizer run."""

    final_output: str
    final_score: float
    iterations: int
    score_history: list[float] = field(default_factory=list)
    converged: bool = False


@dataclass
class EvaluatorOptimizer:
    """Generate → evaluate → optimize → regenerate loop."""

    id: str
    generator: Generator
    rubric: str
    threshold: float = 0.85
    max_iterations: int = 5
    # If None, a default optimizer is used that just passes critic suggestions through.
    optimizer: Optimizer | None = None

    async def run(self, state: State, ctx: "RunContext") -> State:
        """Run the loop and return the state with the final output merged in."""
        result = await self._run_loop(state, ctx)

        await ctx.events.emit(
            EventType.STEP_COMPLETED,
            run_id=ctx.config.run_id,
            node_id=self.id,
            kind="evaluator_optimizer",
            final_score=result.final_score,
            iterations=result.iterations,
            converged=result.converged,
        )

        return state.with_updates(
            messages=state.messages + [
                {
                    "role": "assistant",
                    "agent_id": self.id,
                    "role_label": "evaluator_optimizer",
                    "content": result.final_output,
                    "score": result.final_score,
                    "iterations": result.iterations,
                }
            ],
            artifacts={
                **state.artifacts,
                f"{self.id}_output": result.final_output,
                f"{self.id}_score": result.final_score,
            },
            metadata={
                **state.metadata,
                f"{self.id}_score_history": result.score_history,
                f"{self.id}_converged": result.converged,
            },
        )

    async def _run_loop(self, state: State, ctx: "RunContext") -> EvalResult:
        current_output = ""
        suggestions: list[str] = []
        score_history: list[float] = []

        for i in range(1, self.max_iterations + 1):
            ctx.check_budget()

            # 1. Generate (or regenerate with suggestions).
            current_output = await self.generator(state, suggestions, ctx)

            # 2. Evaluate.
            critic = await evaluate_with_critic(
                ctx=ctx,
                rubric=self.rubric,
                output=current_output,
                agent_id=f"{self.id}__critic",
            )
            score_history.append(critic.score)

            await ctx.events.emit(
                EventType.STEP_COMPLETED,
                run_id=ctx.config.run_id,
                node_id=self.id,
                iteration=i,
                score=critic.score,
                threshold=self.threshold,
            )

            # 3. Converged?
            if critic.score >= self.threshold:
                return EvalResult(
                    final_output=current_output,
                    final_score=critic.score,
                    iterations=i,
                    score_history=score_history,
                    converged=True,
                )

            # 4. Optimize: produce suggestions for next iteration.
            if self.optimizer is not None:
                suggestions = await self.optimizer(current_output, critic, ctx)
            else:
                # Default optimizer: pass through critic suggestions + justification.
                suggestions = list(critic.suggestions)
                if critic.justification:
                    suggestions.append(f"Justification: {critic.justification}")

            # 5. If no suggestions, we cannot improve further — exit.
            if not suggestions:
                return EvalResult(
                    final_output=current_output,
                    final_score=critic.score,
                    iterations=i,
                    score_history=score_history,
                    converged=False,
                )

        # Budget exhausted.
        return EvalResult(
            final_output=current_output,
            final_score=score_history[-1] if score_history else 0.0,
            iterations=self.max_iterations,
            score_history=score_history,
            converged=False,
        )
