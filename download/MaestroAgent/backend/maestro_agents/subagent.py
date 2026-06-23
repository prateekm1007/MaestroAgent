"""SubAgent — a dynamically spawned child agent with isolated context.

A `SubAgent` is created at runtime by a `Supervisor` to handle a
delegated sub-goal. It has:

- Its own short-term memory (does not see the parent's transcript by
  default; the parent passes a *summary* of relevant context).
- Its own tool allowlist.
- Its own budget slice (carved out of the parent's run budget).
- A TTL — idle sub-agents are garbage-collected.

When a sub-agent finishes, its output is summarized (via a cheap LLM
call) and merged back into the parent's context. The full transcript
stays in the long-term memory tier for later recall but does not bloat
the parent's working memory.

This is the key primitive that lets MaestroAgent handle open-ended
goals: a supervisor can spawn N sub-agents in parallel, each working on
an isolated slice, without any one agent drowning in context.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from maestro_core.state import State
from maestro_core.streaming import EventType

if TYPE_CHECKING:
    from maestro_core.context import RunContext
    from maestro_agents.base import BaseAgent


@dataclass
class SubAgentSpec:
    """Spec for a sub-agent to be spawned."""

    parent_id: str
    sub_goal: str
    role: str = "Sub-agent"
    backstory: str = ""
    tools: list[str] = field(default_factory=list)
    llm_hint: dict[str, str] = field(default_factory=dict)
    memory_scope: str = "private"
    budget_usd: float | None = None  # None = inherit from run
    ttl_seconds: float = 300.0
    max_iterations: int = 10


@dataclass
class SubAgent:
    """A runtime sub-agent instance."""

    id: str
    spec: SubAgentSpec
    base: "BaseAgent"
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    status: str = "idle"  # idle | running | done | failed | quarantined
    failure_count: int = 0
    _consecutive_failures_threshold: int = 3

    def is_expired(self) -> bool:
        return (time.time() - self.last_active_at) > self.spec.ttl_seconds

    def quarantine_if_needed(self) -> bool:
        """Return True if the sub-agent was just quarantined."""
        if self.failure_count >= self._consecutive_failures_threshold:
            self.status = "quarantined"
            return True
        return False

    async def run(self, parent_state: State, ctx: "RunContext") -> State:
        """Run the sub-agent's task. Returns the sub-agent's resulting state.

        The parent state is NOT passed directly; we pass a summary.
        """
        if self.status == "quarantined":
            raise RuntimeError(f"Sub-agent {self.id} is quarantined")

        self.status = "running"
        self.last_active_at = time.time()

        await ctx.events.emit(
            EventType.AGENT_SPAWNED,
            run_id=ctx.config.run_id,
            agent_id=self.id,
            parent_id=self.spec.parent_id,
            role=self.spec.role,
            goal=self.spec.sub_goal,
        )

        # Build the sub-agent's isolated state: fresh state, but with a
        # summary of the parent's context and the sub-goal.
        child_state = State(
            run_id=ctx.config.run_id,
            status="running",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a delegated sub-agent. "
                        f"Your specific goal: {self.spec.sub_goal}\n"
                        f"Parent agent: {self.spec.parent_id} ({self.spec.role}).\n"
                        "Stay focused on your sub-goal. Return a clear, "
                        "concise result when done."
                    ),
                },
                {
                    "role": "user",
                    "content": self._parent_summary(parent_state),
                },
            ],
            metadata={"parent_agent": self.spec.parent_id, "sub_goal": self.spec.sub_goal},
        )

        # Run the underlying BaseAgent for up to max_iterations.
        try:
            current = child_state
            for _ in range(self.spec.max_iterations):
                current = await self.base(current, ctx)
                # If the agent signaled completion (heuristic: output
                # contains "DONE:" or final answer marker), stop.
                last = current.messages[-1]["content"] if current.messages else ""
                if isinstance(last, str) and "DONE:" in last:
                    break
                # Single-iteration sub-agents are common — break by default
                # unless the agent explicitly asks for another turn via
                # a tool call. For simplicity in v0.1, we run one turn.
                break
            self.status = "done"
            self.last_active_at = time.time()
            await ctx.events.emit(
                EventType.AGENT_COMPLETED,
                run_id=ctx.config.run_id,
                agent_id=self.id,
                status="done",
            )
            return current
        except Exception as exc:
            self.failure_count += 1
            self.status = "failed"
            self.last_active_at = time.time()
            self.quarantine_if_needed()
            await ctx.events.emit(
                EventType.AGENT_COMPLETED,
                run_id=ctx.config.run_id,
                agent_id=self.id,
                status="failed",
                error=str(exc),
            )
            raise

    def _parent_summary(self, parent_state: State) -> str:
        """Produce a compact summary of the parent's state for the child.

        In production this would call a cheap summarizer model. For v0.1
        we use a simple heuristic: list artifact keys, include the last
        3 messages, and the parent's current goal.
        """
        recent = parent_state.messages[-3:]
        return (
            f"Parent's artifacts: {list(parent_state.artifacts.keys())}\n"
            f"Parent's recent messages (last 3):\n"
            + "\n".join(
                f"- [{m.get('role')}] {str(m.get('content', ''))[:200]}"
                for m in recent
            )
        )


async def summarize_subagent_output(
    sub_state: State, ctx: "RunContext", parent_id: str
) -> str:
    """Summarize a sub-agent's output for merging into the parent.

    Uses a cheap model via the router. Falls back to a truncation
    heuristic if the LLM call fails.
    """
    last = sub_state.messages[-1]["content"] if sub_state.messages else ""
    if not isinstance(last, str) or not last:
        return "(no output)"
    try:
        resp = await ctx.llm.complete(
            system="Summarize the following agent output in 3-5 sentences. "
            "Focus on what was accomplished and any key decisions.",
            user=last[:8000],
            provider=None,
            model=None,
            temperature=0.0,
            tools=[],
            run_id=ctx.config.run_id,
            agent_id=f"{parent_id}__summarizer",
        )
        ctx.cost_so_far += resp.cost_usd
        return resp.text
    except Exception:
        return last[:500] + ("..." if len(last) > 500 else "")


async def merge_subagent_into_parent(
    parent_state: State, sub_state: State, sub_id: str, ctx: "RunContext"
) -> State:
    """Merge a finished sub-agent's output into the parent's state.

    Merge policy:
    - Append a summary message tagged with the sub-agent's id.
    - Add the sub-agent's artifacts under a namespaced key.
    - Do NOT copy the sub-agent's full message transcript (token efficiency).
    """
    summary = await summarize_subagent_output(sub_state, ctx, parent_id=str(parent_state.current_node))
    return parent_state.with_updates(
        messages=parent_state.messages + [
            {
                "role": "assistant",
                "agent_id": sub_id,
                "role_label": "sub-agent-summary",
                "content": summary,
            }
        ],
        artifacts={
            **parent_state.artifacts,
            f"subagent:{sub_id}:summary": summary,
            f"subagent:{sub_id}:final": sub_state.messages[-1]["content"]
            if sub_state.messages
            else "",
        },
    )
