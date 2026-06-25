"""Test: memory manager writes and recalls across tiers."""

from __future__ import annotations

from pathlib import Path

import pytest

from maestro_memory.manager import MemoryManager
from maestro_memory.short_term import ShortTermMemory
from maestro_memory.vector import InMemoryVectorMemory
from maestro_memory.graph import NetworkXGraphMemory
from maestro_memory.long_term import LongTermMemory


@pytest.fixture
def manager(tmp_path: Path) -> MemoryManager:
    return MemoryManager(
        short_term=ShortTermMemory(),
        semantic=InMemoryVectorMemory(),
        graph=NetworkXGraphMemory(persist_path=str(tmp_path / "graph.json")),
        long_term=LongTermMemory(db_path=str(tmp_path / "test.db")),
    )


async def test_write_and_recall(manager: MemoryManager) -> None:
    """Write an entry, then recall it."""
    await manager.write(
        run_id="r1",
        agent_id="a1",
        scope="shared",
        content="The architecture is a monorepo with Next.js + Prisma + Postgres.",
        produced_artifacts=["architecture.md"],
    )
    results = await manager.recall(
        query="architecture", run_id="r1", agent_id="a1", top_k=5
    )
    assert len(results) > 0
    assert any("architecture" in r.content.lower() for r in results)


async def test_promote_to_long_term(manager: MemoryManager) -> None:
    """Promotion writes to the long-term tier."""
    await manager.write(
        run_id="r1",
        agent_id="a1",
        scope="shared",
        content="Important decision: use Postgres not MySQL.",
    )
    eid = await manager.promote(
        agent_id="a1",
        run_id="r1",
        scope="shared",
        tags=["architecture-decision"],
    )
    assert eid is not None
    long_entries = await manager.long_term.list_by_tag("architecture-decision")
    assert len(long_entries) == 1
    assert "Postgres" in long_entries[0]["content"]


async def test_graph_relationships(manager: MemoryManager) -> None:
    """Writing with produced_artifacts creates graph edges."""
    await manager.write(
        run_id="r1",
        agent_id="a1",
        scope="shared",
        content="Generated file X.",
        produced_artifacts=["file_x"],
    )
    neighbors = await manager.graph.neighbors("a1", edge_kind="produced")
    assert any(n.id == "file_x" for n in neighbors)
