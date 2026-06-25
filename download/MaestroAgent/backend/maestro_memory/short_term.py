"""Short-term memory — bounded rolling window per agent.

Each agent has its own short-term memory: a list of messages with a
token-bounded capacity. When the window overflows, the oldest messages
are summarized (via a cheap LLM call) and the summary replaces them.

This is the most performance-sensitive tier — it's consulted on every
agent call. We keep it in-memory (a dict) during a run and persist only
on demand (e.g. for crash recovery, the latest snapshot is checkpointed
alongside the graph state).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maestro_core.context import RunContext


@dataclass
class ShortTermMemory:
    """In-memory rolling window per agent."""

    # agent_id -> list of messages
    windows: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    max_messages_per_agent: int = 50
    # When the window overflows, summarize the oldest `summarize_chunk` messages.
    summarize_chunk: int = 20

    def append(self, agent_id: str, message: dict[str, Any]) -> None:
        self.windows[agent_id].append(message)

    def get(self, agent_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        msgs = self.windows[agent_id]
        if limit is None:
            return list(msgs)
        return list(msgs[-limit:])

    def needs_compaction(self, agent_id: str) -> bool:
        return len(self.windows[agent_id]) > self.max_messages_per_agent

    async def compact(self, agent_id: str, ctx: "RunContext") -> str | None:
        """Summarize the oldest chunk and replace it with a summary message.

        Returns the summary text, or None if no compaction was needed.
        """
        if not self.needs_compaction(agent_id):
            return None
        msgs = self.windows[agent_id]
        to_summarize = msgs[: self.summarize_chunk]
        rest = msgs[self.summarize_chunk :]

        # Build a transcript string.
        transcript = "\n\n".join(
            f"[{m.get('role', '?')}] {str(m.get('content', ''))[:1000]}"
            for m in to_summarize
        )

        try:
            resp = await ctx.llm.complete(
                system=(
                    "Summarize the following agent transcript in 5-10 sentences. "
                    "Preserve key decisions, facts, and open questions."
                ),
                user=transcript[:8000],
                provider=None,
                model=None,
                temperature=0.0,
                tools=[],
                run_id=ctx.config.run_id,
                agent_id=f"{agent_id}__summarizer",
            )
            ctx.cost_so_far += resp.cost_usd
            summary = resp.text
        except Exception:
            # Fallback: keep the last message of the chunk and drop the rest.
            summary = f"(compaction failed; retained last message: {str(to_summarize[-1].get('content', ''))[:300]})"

        # Replace the chunk with a summary message.
        summary_msg = {
            "role": "system",
            "content": f"[Compacted summary of {len(to_summarize)} earlier messages]\n{summary}",
            "compacted": True,
        }
        self.windows[agent_id] = [summary_msg] + list(rest)
        return summary

    def snapshot(self, agent_id: str) -> list[dict[str, Any]]:
        return list(self.windows[agent_id])

    def restore(self, agent_id: str, messages: list[dict[str, Any]]) -> None:
        self.windows[agent_id] = list(messages)
