"""The orchestration engine — drives a run from entry to completion.

Responsibilities
----------------
1. Walk the graph: pick the next node, call it, save the checkpoint,
   emit events, repeat.
2. Honor the run budget (cost + iterations + wall-clock).
3. Honor HITL pauses: a node can request a pause by returning a state
   with `status=AWAITING_HUMAN`; the engine parks the run until
   `resume()` is called.
4. Handle failures: retry with backoff (configurable per-node), then
   escalate to the run's failure policy.
5. Stream every transition to the event bus.

The engine is intentionally stateless between calls: all persistent
state lives in the checkpoint store. This means a crashed engine can be
replaced and the run resumed from the latest checkpoint.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from maestro_core.context import BudgetExhausted, IterationCapHit, RunContext
from maestro_core.graph import (
    ConditionalEdge,
    Edge,
    Graph,
    Node,
    ParallelEdges,
    run_parallel_targets,
)
from maestro_core.state import RunStatus, State
from maestro_core.streaming import EventBus, EventType

logger = logging.getLogger(__name__)


class RunResult(BaseModel):
    run_id: str
    status: RunStatus
    final_state: State | None = None
    error: str | None = None
    steps_executed: int = 0
    cost_usd: float = 0.0
    started_at: datetime
    ended_at: datetime | None = None


class OrchestrationEngine:
    """Walks a graph to completion under budget and HITL constraints."""

    def __init__(self, ctx: RunContext, graph: Graph) -> None:
        self.ctx = ctx
        self.graph = graph
        problems = graph.validate()
        if problems:
            raise ValueError(f"Invalid graph: {problems}")

    async def run(self, initial_state: State | None = None) -> RunResult:
        """Run the graph to completion (or pause/fail)."""
        self.ctx.events.start()
        started_at = self.ctx.started_at
        await self.ctx.events.emit(
            EventType.RUN_STARTED,
            run_id=self.ctx.config.run_id,
            template=self.ctx.config.template,
            goal=self.ctx.config.goal,
            budget=self.ctx.config.max_cost_usd,
        )
        await self.ctx.checkpoints.audit(
            self.ctx.config.run_id,
            "run.start",
            {"template": self.ctx.config.template, "goal": self.ctx.config.goal},
        )

        # Resume from latest checkpoint if one exists (crash recovery).
        state = initial_state or await self.ctx.checkpoints.latest(self.ctx.config.run_id)
        if state is None:
            state = State(run_id=self.ctx.config.run_id, status=RunStatus.RUNNING)
        state = state.with_updates(status=RunStatus.RUNNING, current_node=self.graph.entry)

        steps_executed = 0
        error: str | None = None

        try:
            while state.current_node is not None:
                self._check_budget_and_caps()
                node = self.graph.nodes[state.current_node]
                steps_executed += 1
                self.ctx.iterations_so_far += 1

                await self.ctx.events.emit(
                    EventType.STEP_STARTED,
                    run_id=self.ctx.config.run_id,
                    node_id=node.id,
                    iteration=self.ctx.iterations_so_far,
                )
                await self.ctx.checkpoints.save(state, node.id, "started")

                try:
                    new_state = await self._call_node_with_retry(node, state)
                except Exception as exc:
                    logger.exception("Node %s failed", node.id)
                    await self.ctx.events.emit(
                        EventType.STEP_FAILED,
                        run_id=self.ctx.config.run_id,
                        node_id=node.id,
                        error=str(exc),
                    )
                    await self.ctx.checkpoints.save(
                        state, node.id, "failed"
                    )
                    new_state = state.with_updates(
                        status=RunStatus.FAILED, error=str(exc)
                    )
                    await self.ctx.checkpoints.save(new_state, node.id, "failed-final")
                    error = str(exc)
                    break

                # Handle parallel fan-out: if the node returned a list of
                # states, run the parallel branches and merge.
                if isinstance(new_state, list):
                    # new_state is a list of State from ParallelEdges —
                    # but actually parallel fan-out is handled in _advance.
                    # If a node returns a list, we treat it as a fan-out
                    # request and merge.
                    merged = await self._merge_states(new_state, state)
                    new_state = merged

                new_state = new_state.with_updates(
                    current_node=node.id, status=RunStatus.RUNNING
                )
                await self.ctx.events.emit(
                    EventType.STEP_COMPLETED,
                    run_id=self.ctx.config.run_id,
                    node_id=node.id,
                    revision=new_state.revision,
                )
                await self.ctx.checkpoints.save(new_state, node.id, "completed")

                # HITL pause?
                if new_state.status == RunStatus.AWAITING_HUMAN:
                    await self.ctx.events.emit(
                        EventType.HITL_REQUESTED,
                        run_id=self.ctx.config.run_id,
                        node_id=node.id,
                        reason=new_state.metadata.get("hitl_reason", "unspecified"),
                    )
                    await self.ctx.checkpoints.save(new_state, node.id, "paused-hitl")
                    return RunResult(
                        run_id=self.ctx.config.run_id,
                        status=RunStatus.AWAITING_HUMAN,
                        final_state=new_state,
                        steps_executed=steps_executed,
                        cost_usd=self.ctx.cost_so_far,
                        started_at=started_at,
                        ended_at=datetime.now(timezone.utc),
                    )

                state = new_state
                state = await self._advance(state)

            # Loop ended — either success or no more edges.
            final_status = state.status if state.status != RunStatus.RUNNING else RunStatus.SUCCEEDED
            state = state.with_updates(status=final_status)
            await self.ctx.checkpoints.save(state, None, "final")
            await self.ctx.events.emit(
                EventType.RUN_COMPLETED,
                run_id=self.ctx.config.run_id,
                status=final_status.value,
                steps=steps_executed,
                cost=self.ctx.cost_so_far,
            )
            await self.ctx.checkpoints.audit(
                self.ctx.config.run_id,
                "run.complete",
                {"status": final_status.value, "steps": steps_executed},
            )
            return RunResult(
                run_id=self.ctx.config.run_id,
                status=final_status,
                final_state=state,
                steps_executed=steps_executed,
                cost_usd=self.ctx.cost_so_far,
                started_at=started_at,
                ended_at=datetime.now(timezone.utc),
            )
        except BudgetExhausted as exc:
            await self.ctx.events.emit(
                EventType.BUDGET_WARNING,
                run_id=self.ctx.config.run_id,
                reason=str(exc),
            )
            state = state.with_updates(status=RunStatus.PAUSED, error=str(exc))
            await self.ctx.checkpoints.save(state, None, "paused-budget")
            return RunResult(
                run_id=self.ctx.config.run_id,
                status=RunStatus.PAUSED,
                final_state=state,
                error=str(exc),
                steps_executed=steps_executed,
                cost_usd=self.ctx.cost_so_far,
                started_at=started_at,
                ended_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            logger.exception("Run failed")
            await self.ctx.events.emit(
                EventType.RUN_FAILED,
                run_id=self.ctx.config.run_id,
                error=str(exc),
            )
            state = state.with_updates(status=RunStatus.FAILED, error=str(exc))
            await self.ctx.checkpoints.save(state, None, "failed")
            return RunResult(
                run_id=self.ctx.config.run_id,
                status=RunStatus.FAILED,
                final_state=state,
                error=str(exc),
                steps_executed=steps_executed,
                cost_usd=self.ctx.cost_so_far,
                started_at=started_at,
                ended_at=datetime.now(timezone.utc),
            )
        finally:
            await self.ctx.events.stop()

    async def resume(self, *, human_input: dict[str, Any] | None = None) -> RunResult:
        """Resume a paused run, optionally injecting human input."""
        state = await self.ctx.checkpoints.latest(self.ctx.config.run_id)
        if state is None:
            raise ValueError(f"No checkpoint for run {self.ctx.config.run_id}")
        if human_input:
            state = state.with_updates(
                metadata={**state.metadata, "human_input": human_input},
                status=RunStatus.RUNNING,
            )
        else:
            state = state.with_updates(status=RunStatus.RUNNING)
        return await self.run(initial_state=state)

    # --- internals ---

    def _check_budget_and_caps(self) -> None:
        if self.ctx.is_budget_exhausted:
            raise BudgetExhausted("cost cap hit")
        if self.ctx.is_iteration_capped:
            raise IterationCapHit("iteration cap hit")
        elapsed = (datetime.now(timezone.utc) - self.ctx.started_at).total_seconds()
        if elapsed > self.ctx.config.max_wall_clock_seconds:
            raise IterationCapHit("wall-clock cap hit")

    async def _call_node_with_retry(self, node: Node, state: State) -> State:
        retries = node.retries if node.retries is not None else 2
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                # Set role scope on ctx for this call.
                self.ctx.agent_role = self.ctx.config.agent_role
                return await node(state, self.ctx)
            except (BudgetExhausted, IterationCapHit):
                raise  # Don't retry budget hits.
            except Exception as exc:
                last_exc = exc
                if attempt < retries:
                    await asyncio.sleep(2**attempt)  # exponential backoff
                    continue
                raise
        assert last_exc is not None
        raise last_exc

    async def _advance(self, state: State) -> State:
        """Pick the next node based on outgoing edges."""
        outgoing = self.graph.outgoing(state.current_node or "")
        if not outgoing:
            state = state.with_updates(next_node=None, current_node=None)
            return state

        # Prefer the first matching conditional edge, else fall back to plain edges.
        for edge in outgoing:
            if isinstance(edge, ConditionalEdge):
                if edge.matches(state):
                    return state.with_updates(current_node=edge.target)
            elif isinstance(edge, Edge):
                # Plain edges: collect them; we'll take the first.
                continue

        # No conditional matched; take first plain edge.
        for edge in outgoing:
            if isinstance(edge, Edge) and not isinstance(edge, ConditionalEdge):
                return state.with_updates(current_node=edge.target)

        # Parallel edges: fan out.
        for edge in outgoing:
            if isinstance(edge, ParallelEdges):
                targets = edge.targets
                if edge.predicates:
                    targets = [
                        t for t in targets
                        if edge.predicates.get(t, lambda _s: True)(state)
                    ]
                if not targets:
                    state = state.with_updates(current_node=None)
                    return state
                # Run all targets in parallel, then merge.
                results = await run_parallel_targets(
                    self.graph.nodes[state.current_node or ""],
                    state,
                    self.ctx,
                    targets,
                    self.graph,
                )
                merged = await self._merge_states(results, state)
                # After a parallel block, follow the parallel edge's "implicit"
                # continuation: no explicit target, so end here.
                return merged.with_updates(current_node=None)

        # Nothing matched — end the run.
        return state.with_updates(current_node=None)

    async def _merge_states(self, branches: list[State], parent: State) -> State:
        """Merge parallel branch outputs into a single state.

        Merge policy:
        - artifacts: shallow merge (later branches win on conflict)
        - messages: concatenate
        - metadata: shallow merge
        - errors: collect into metadata['branch_errors']
        """
        merged = parent.bump()
        all_messages: list[dict[str, Any]] = list(parent.messages)
        all_artifacts: dict[str, Any] = dict(parent.artifacts)
        all_metadata: dict[str, Any] = dict(parent.metadata)
        branch_errors: list[str] = []

        for i, b in enumerate(branches):
            all_messages.extend(b.messages)
            all_artifacts.update(b.artifacts)
            all_metadata.update(b.metadata)
            if b.error:
                branch_errors.append(f"branch[{i}]: {b.error}")

        if branch_errors:
            all_metadata["branch_errors"] = branch_errors

        return merged.with_updates(
            messages=all_messages,
            artifacts=all_artifacts,
            metadata=all_metadata,
        )
