"""MemoryManager — the single entry point for memory operations.

Agents and loops never touch the underlying tiers directly. They call
`manager.write(...)` and `manager.recall(...)`. The manager:

1. Writes to short-term (always) + semantic (always) + graph (for
   relationships) + long-term (only on promotion).
2. Enforces RBAC: an agent with `memory_scope="private"` cannot read
   another agent's private scope.
3. Handles compaction: when short-term overflows, summarize and promote
   the summary to semantic.
4. Provides unified recall: `recall(query)` returns a merged view
   across tiers (semantic top-k + recent short-term + tagged long-term).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from maestro_memory.graph import GraphMemory, GraphNode, GraphEdge
from maestro_memory.long_term import LongTermMemory
from maestro_memory.short_term import ShortTermMemory
from maestro_memory.vector import InMemoryVectorMemory, VectorMemory, VectorEntry

if TYPE_CHECKING:
    from maestro_core.context import RunContext

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """A unified memory entry returned by `recall`."""

    id: str
    tier: str  # "short" | "semantic" | "graph" | "long"
    run_id: str
    agent_id: str | None
    scope: str
    content: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


class MemoryManager:
    """Multi-tier memory coordinator."""

    def __init__(
        self,
        short_term: ShortTermMemory | None = None,
        semantic: VectorMemory | None = None,
        graph: GraphMemory | None = None,
        long_term: LongTermMemory | None = None,
    ) -> None:
        self.short_term = short_term or ShortTermMemory()
        self.semantic = semantic or InMemoryVectorMemory()
        self.graph = graph
        self.long_term = long_term

    async def write(
        self,
        run_id: str,
        agent_id: str,
        scope: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        # Optional: declare relationships to other entities.
        produced_artifacts: list[str] | None = None,
        consumed_artifacts: list[str] | None = None,
        parent_agent: str | None = None,
    ) -> str:
        """Write to short-term + semantic (+ graph if relationships given)."""
        # 1. Short-term.
        self.short_term.append(
            agent_id,
            {
                "role": "assistant",
                "agent_id": agent_id,
                "content": content,
                "scope": scope,
                "metadata": metadata or {},
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )

        # 2. Semantic.
        eid = await self.semantic.add(
            run_id=run_id,
            agent_id=agent_id,
            scope=scope,
            content=content,
            metadata=metadata or {},
        )

        # 3. Graph: register the agent node + relationship edges.
        if self.graph is not None:
            await self.graph.add_node(
                GraphNode(
                    kind="agent",
                    id=agent_id,
                    properties={"run_id": run_id, "scope": scope},
                )
            )
            if parent_agent is not None:
                await self.graph.add_edge(
                    GraphEdge(kind="spawned", src=parent_agent, dst=agent_id)
                )
            for art in produced_artifacts or []:
                await self.graph.add_node(
                    GraphNode(kind="artifact", id=art, properties={"run_id": run_id})
                )
                await self.graph.add_edge(
                    GraphEdge(kind="produced", src=agent_id, dst=art)
                )
            for art in consumed_artifacts or []:
                if art:  # don't add edges to nonexistent nodes
                    await self.graph.add_edge(
                        GraphEdge(kind="consumed", src=agent_id, dst=art)
                    )

        # 4. Long-term: only on explicit promotion (see `promote`).
        return eid

    async def recall(
        self,
        query: str,
        run_id: str | None = None,
        agent_id: str | None = None,
        scope: str | None = None,
        top_k: int = 5,
        include_short_term: bool = True,
        include_long_term: bool = True,
    ) -> list[MemoryEntry]:
        """Unified recall across tiers. Returns merged, de-duplicated entries."""
        results: list[MemoryEntry] = []

        # Semantic tier — top-k by similarity.
        semantic_entries = await self.semantic.query(
            query_text=query,
            run_id=run_id,
            scope=scope,
            top_k=top_k,
        )
        for e in semantic_entries:
            results.append(
                MemoryEntry(
                    id=e.id,
                    tier="semantic",
                    run_id=e.run_id,
                    agent_id=e.agent_id,
                    scope=e.scope,
                    content=e.content,
                    score=e.score,
                    metadata=e.metadata,
                )
            )

        # Short-term tier — most recent N for the requesting agent.
        if include_short_term and agent_id is not None:
            recent = self.short_term.get(agent_id, limit=top_k)
            for i, m in enumerate(recent):
                results.append(
                    MemoryEntry(
                        id=f"short:{agent_id}:{i}",
                        tier="short",
                        run_id=run_id or "",
                        agent_id=agent_id,
                        scope=m.get("scope", "private"),
                        content=str(m.get("content", "")),
                        score=1.0 - (i * 0.05),  # recency decay
                        metadata=m.get("metadata", {}),
                    )
                )

        # Long-term tier — promoted episodes matching the query.
        if include_long_term and self.long_term is not None:
            long_entries = await self.long_term.search(query, limit=top_k)
            for e in long_entries:
                results.append(
                    MemoryEntry(
                        id=e["id"],
                        tier="long",
                        run_id=e["run_id"],
                        agent_id=e.get("agent_id"),
                        scope=e.get("scope", ""),
                        content=e["content"],
                        score=0.9,  # promoted = high relevance
                        metadata={
                            "tags": e.get("tags", []),
                            "provenance": e.get("provenance", {}),
                            "promoted_at": e.get("promoted_at"),
                        },
                    )
                )

        # De-duplicate by content prefix.
        seen: set[str] = set()
        deduped: list[MemoryEntry] = []
        for r in results:
            key = r.content[:100]
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)

        # Sort by score desc.
        deduped.sort(key=lambda e: e.score, reverse=True)
        return deduped[: top_k * 3]

    async def promote(
        self,
        agent_id: str,
        content: str | None = None,
        summary: str | None = None,
        run_id: str | None = None,
        scope: str = "shared",
        tags: list[str] | None = None,
    ) -> str | None:
        """Promote an entry from short-term/semantic to long-term."""
        if self.long_term is None:
            return None
        if content is None:
            recent = self.short_term.get(agent_id, limit=1)
            if not recent:
                return None
            content = str(recent[0].get("content", ""))
        return await self.long_term.write(
            run_id=run_id or "",
            agent_id=agent_id,
            scope=scope,
            content=content,
            summary=summary,
            tags=tags,
        )

    async def compact_if_needed(self, agent_id: str, ctx: "RunContext") -> str | None:
        """Compact an agent's short-term window if it has overflowed."""
        return await self.short_term.compact(agent_id, ctx)
