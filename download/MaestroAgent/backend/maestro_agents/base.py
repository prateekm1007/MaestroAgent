"""BaseAgent — the unit of agency in MaestroAgent.

A `BaseAgent` is defined by:
- `role` — what it is ("Senior Backend Engineer")
- `goal` — what it tries to do ("Ship a working API")
- `backstory` — context that shapes its style ("10 years at Stripe, pragmatic")
- `tools` — callable tools it may invoke
- `llm_hint` — preferred provider/model (router may override)
- `memory_scope` — private / shared / crew (RBAC on memory access)

This mirrors CrewAI's `Agent` constructor so users coming from CrewAI
feel at home, but the runtime is our own: each call goes through the
`LLMRouter` (with cost tracking + failover) and every output is written
to the memory tiers via `MemoryManager`.

The `__call__` method is the graph-node interface: `(State, RunContext) -> State`.
This means an agent IS a node — you can `graph.add_node(Node(id=..., fn=agent))`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from maestro_core.state import State
from maestro_core.streaming import EventType

if TYPE_CHECKING:
    from maestro_core.context import RunContext

Tool = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class AgentSpec:
    """Declarative agent definition. Used by templates and the UI."""

    role: str
    goal: str
    backstory: str = ""
    tools: list[str] = field(default_factory=list)  # tool names, resolved at runtime
    llm_hint: dict[str, str] = field(default_factory=dict)  # {"provider": "...", "model": "..."}
    memory_scope: str = "private"  # "private" | "shared" | "crew"
    max_consecutive_calls: int = 8
    allow_delegation: bool = False
    allow_spawning: bool = False
    temperature: float = 0.2


@dataclass
class BaseAgent:
    """An agent — a node in a graph that calls an LLM with role/goal/backstory."""

    id: str
    spec: AgentSpec

    async def __call__(self, state: State, ctx: "RunContext") -> State:
        """Node interface: read state, call LLM, write state."""
        ctx.check_budget()
        await ctx.events.emit(
            EventType.AGENT_SPAWNED,
            run_id=ctx.config.run_id,
            agent_id=self.id,
            role=self.spec.role,
            goal=self.spec.goal,
        )

        # Build the prompt from role/goal/backstory + relevant state.
        system_prompt = self._system_prompt()
        user_prompt = self._user_prompt(state, ctx)

        await ctx.events.emit(
            EventType.LLM_CALL_STARTED,
            run_id=ctx.config.run_id,
            agent_id=self.id,
            provider=self.spec.llm_hint.get("provider"),
            model=self.spec.llm_hint.get("model"),
        )

        # Route through LLMRouter for cost tracking + failover.
        response = await ctx.llm.complete(
            system=system_prompt,
            user=user_prompt,
            provider=self.spec.llm_hint.get("provider"),
            model=self.spec.llm_hint.get("model"),
            temperature=self.spec.temperature,
            tools=self.spec.tools,
            run_id=ctx.config.run_id,
            agent_id=self.id,
        )

        # Update cost accumulator.
        ctx.cost_so_far += response.cost_usd
        await ctx.events.emit(
            EventType.LLM_CALL_COMPLETED,
            run_id=ctx.config.run_id,
            agent_id=self.id,
            provider=response.provider,
            model=response.model,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            cost_usd=response.cost_usd,
        )

        # Write to memory tiers.
        await ctx.memory.write(
            run_id=ctx.config.run_id,
            agent_id=self.id,
            scope=self.spec.memory_scope,
            content=response.text,
            metadata={
                "role": self.spec.role,
                "goal": self.spec.goal,
                "step_id": state.step_id,
                "provider": response.provider,
                "model": response.model,
            },
        )
        await ctx.events.emit(
            EventType.MEMORY_WRITE,
            run_id=ctx.config.run_id,
            agent_id=self.id,
            scope=self.spec.memory_scope,
        )

        # Update state with the agent's output.
        return state.with_updates(
            messages=state.messages + [
                {
                    "role": "assistant",
                    "agent_id": self.id,
                    "role_label": self.spec.role,
                    "content": response.text,
                    "tool_calls": response.tool_calls,
                    "cost_usd": response.cost_usd,
                }
            ],
            artifacts={**state.artifacts, f"{self.id}_last_output": response.text},
            metadata={**state.metadata, "last_agent": self.id},
        )

    def _system_prompt(self) -> str:
        return (
            f"You are a {self.spec.role}.\n"
            f"Goal: {self.spec.goal}\n"
            f"Backstory: {self.spec.backstory}\n\n"
            "Work step by step. Use the tools you have when needed. "
            "When you have a final answer, return it as plain text."
        )

    def _user_prompt(self, state: State, ctx: "RunContext") -> str:
        # Include the last few messages for context.
        recent = state.messages[-6:]
        return (
            f"Run goal: {ctx.config.goal}\n\n"
            f"Recent context:\n{json.dumps(recent, indent=2, default=str)}\n\n"
            f"Current artifacts: {list(state.artifacts.keys())}\n\n"
            "What is your next step?"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "spec": {
                "role": self.spec.role,
                "goal": self.spec.goal,
                "backstory": self.spec.backstory,
                "tools": self.spec.tools,
                "llm_hint": self.spec.llm_hint,
                "memory_scope": self.spec.memory_scope,
                "allow_delegation": self.spec.allow_delegation,
                "allow_spawning": self.spec.allow_spawning,
            },
        }
