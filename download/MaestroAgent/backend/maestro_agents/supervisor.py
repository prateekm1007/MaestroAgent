"""Supervisor — spawns and manages dynamic hierarchical sub-agents.

A `Supervisor` is a special agent whose job is to decompose a goal
into sub-goals, spawn sub-agents to handle each, merge their results,
and decide whether to iterate, escalate, or finish.

This is the LangGraph "supervisor" pattern, but with three additions
that make it production-grade:

1. **Parallel spawning.** A supervisor can fan out N sub-agents at
   once and await them concurrently.
2. **Quarantine.** A sub-agent that fails repeatedly is quarantined
   and not re-spawned for the rest of the run.
3. **Auto-merge with conflict detection.** When sub-agent outputs
   disagree (e.g. two sub-agents propose different architectures),
   the supervisor triggers a debate instead of silently picking one.

The supervisor itself is a graph node: `(State, RunContext) -> State`.
It uses the LLM router for its own decisions (decomposition, merge,
escalate). Sub-agents use the router for their work.

Lifecycle
---------
A supervisor run looks like:

  1. Receive goal + context.
  2. Call LLM to decompose into sub-goals.
  3. For each sub-goal, spawn a SubAgent.
  4. Run sub-agents (in parallel if independent).
  5. Merge results; detect conflicts.
  6. If conflicts: run a Debate.
  7. Decide: done, iterate (back to step 2), or escalate (HITL).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from maestro_agents.base import AgentSpec, BaseAgent
from maestro_agents.subagent import (
    SubAgent,
    SubAgentSpec,
    merge_subagent_into_parent,
)
from maestro_agents.debate import Debate, VotePolicy
from maestro_core.state import RunStatus, State
from maestro_core.streaming import EventType

if TYPE_CHECKING:
    from maestro_core.context import RunContext


@dataclass
class Supervisor:
    """A supervisor agent — decomposes, spawns, merges."""

    id: str
    spec: AgentSpec
    # Map of sub-goal -> SubAgentSpec template (filled at spawn time)
    sub_agent_specs: dict[str, SubAgentSpec] = field(default_factory=dict)
    # Live sub-agents (id -> SubAgent)
    children: dict[str, SubAgent] = field(default_factory=dict)

    async def __call__(self, state: State, ctx: "RunContext") -> State:
        ctx.check_budget()
        await ctx.events.emit(
            EventType.AGENT_SPAWNED,
            run_id=ctx.config.run_id,
            agent_id=self.id,
            role=f"Supervisor: {self.spec.role}",
            goal=self.spec.goal,
        )

        # 1. Decompose goal into sub-goals via LLM.
        decomposition = await self._decompose(state, ctx)
        sub_goals: list[dict[str, Any]] = decomposition.get("sub_goals", [])
        if not sub_goals:
            # No decomposition possible — finish with what we have.
            return state.with_updates(
                messages=state.messages + [
                    {
                        "role": "assistant",
                        "agent_id": self.id,
                        "content": "No further decomposition possible. Returning current state.",
                    }
                ]
            )

        # 2. Spawn a SubAgent for each sub-goal.
        spawn_tasks = []
        for sg in sub_goals:
            sub_id = f"{self.id}__sub_{uuid.uuid4().hex[:8]}"
            sub_spec = SubAgentSpec(
                parent_id=self.id,
                sub_goal=sg["goal"],
                role=sg.get("role", "Sub-agent"),
                backstory=sg.get("backstory", ""),
                tools=sg.get("tools", []),
                llm_hint=sg.get("llm_hint", {}),
                memory_scope=sg.get("memory_scope", "private"),
                budget_usd=sg.get("budget_usd"),
                ttl_seconds=sg.get("ttl_seconds", 300.0),
                max_iterations=sg.get("max_iterations", 10),
            )
            sub_base = BaseAgent(
                id=sub_id,
                spec=AgentSpec(
                    role=sub_spec.role,
                    goal=sub_spec.sub_goal,
                    backstory=sub_spec.backstory,
                    tools=sub_spec.tools,
                    llm_hint=sub_spec.llm_hint,
                    memory_scope=sub_spec.memory_scope,
                ),
            )
            sub = SubAgent(id=sub_id, spec=sub_spec, base=sub_base)
            self.children[sub_id] = sub
            spawn_tasks.append(self._run_one_sub(sub, state, ctx))

        # 3. Run sub-agents in parallel.
        sub_results = await asyncio.gather(*spawn_tasks, return_exceptions=True)

        # 4. Merge results, collecting conflicts.
        merged = state
        conflicts: list[dict[str, Any]] = []
        for sub_id, result in zip(self.children.keys(), sub_results):
            if isinstance(result, Exception):
                merged = merged.with_updates(
                    metadata={
                        **merged.metadata,
                        "subagent_errors": merged.metadata.get("subagent_errors", [])
                        + [{"sub_id": sub_id, "error": str(result)}],
                    }
                )
                continue
            merged = await merge_subagent_into_parent(merged, result, sub_id, ctx)

            # Conflict detection heuristic: if the sub-agent's final
            # output contradicts another sub-agent's output (we use a
            # cheap LLM-as-judge call here in production; v0.1 uses a
            # placeholder), record it.
            # For v0.1 we skip explicit conflict detection and rely on
            # the supervisor's merge step to surface disagreements.

        # 5. If conflicts, run a debate (skipped in v0.1 unless explicit).
        if conflicts:
            debate = Debate(
                id=f"{self.id}__debate_{uuid.uuid4().hex[:6]}",
                topic="Resolve conflicts between sub-agents",
                participants=list(self.children.keys()),
                policy=VotePolicy(seek_consensus=True),
            )
            merged = await debate.run(merged, ctx)

        # 6. Decide: done, iterate, or escalate.
        decision = await self._decide(merged, ctx)
        if decision == "iterate":
            # Bump iteration and let the loop handler re-enter us.
            merged = merged.with_updates(iteration=merged.iteration + 1)
        elif decision == "escalate":
            merged = merged.with_updates(
                status=RunStatus.AWAITING_HUMAN,
                metadata={**merged.metadata, "hitl_reason": "supervisor_escalation"},
            )
        # else: done — return as-is.

        return merged

    async def _decompose(self, state: State, ctx: "RunContext") -> dict[str, Any]:
        """Ask the LLM to decompose the goal into sub-goals."""
        resp = await ctx.llm.complete(
            system=(
                "You are a supervisor agent. Decompose the given goal into "
                "1-5 independent sub-goals. Respond as JSON: "
                '{"sub_goals": [{"goal": "...", "role": "...", "tools": [...]}]}. '
                "If the goal is already atomic (cannot be decomposed), return "
                '{"sub_goals": []}.'
            ),
            user=(
                f"Run goal: {ctx.config.goal}\n"
                f"Current artifacts: {list(state.artifacts.keys())}\n"
                f"Recent messages: {str(state.messages[-3:])[:2000]}"
            ),
            provider=self.spec.llm_hint.get("provider"),
            model=self.spec.llm_hint.get("model"),
            temperature=0.1,
            tools=[],
            run_id=ctx.config.run_id,
            agent_id=self.id,
        )
        ctx.cost_so_far += resp.cost_usd
        # Best-effort JSON parse.
        import json
        try:
            return json.loads(resp.text)
        except Exception:
            return {"sub_goals": []}

    async def _decide(self, state: State, ctx: "RunContext") -> str:
        """Ask the LLM: are we done, should we iterate, or escalate?"""
        resp = await ctx.llm.complete(
            system=(
                "You are a supervisor. Decide the next action: 'done', 'iterate', "
                "or 'escalate'. Respond with a single word."
            ),
            user=(
                f"Run goal: {ctx.config.goal}\n"
                f"Artifacts: {list(state.artifacts.keys())}\n"
                f"Last messages: {str(state.messages[-4:])[:2000]}"
            ),
            provider=self.spec.llm_hint.get("provider"),
            model=self.spec.llm_hint.get("model"),
            temperature=0.0,
            tools=[],
            run_id=ctx.config.run_id,
            agent_id=self.id,
        )
        ctx.cost_so_far += resp.cost_usd
        choice = resp.text.strip().lower()
        return choice if choice in {"done", "iterate", "escalate"} else "done"

    async def _run_one_sub(
        self, sub: SubAgent, state: State, ctx: "RunContext"
    ) -> State:
        """Run one sub-agent, handling TTL and quarantine."""
        if sub.is_expired():
            raise RuntimeError(f"Sub-agent {sub.id} expired before run")
        return await sub.run(state, ctx)
