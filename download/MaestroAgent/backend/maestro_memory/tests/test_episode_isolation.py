"""Multi-tenant isolation tests for LongTermMemory (episodes table).

Principle 7: any fix that changes shared state into scoped state must ship
with a two-org isolation test. The episodes table historically had no
org_id column — any tenant could read any other tenant's episodic memories
via search(), list_by_run(), list_by_tag(), or get().

These tests create two LongTermMemory instances scoped to different orgs,
sharing the same DB file, and verify org A can never see org B's episodes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maestro_memory.long_term import LongTermMemory
from maestro_memory.vector import InMemoryVectorMemory


@pytest.fixture
def two_org_memories(tmp_path: Path) -> tuple[LongTermMemory, LongTermMemory]:
    """Two LongTermMemory instances scoped to different orgs, same DB."""
    db_path = str(tmp_path / "episodes.db")
    org_a = LongTermMemory(db_path=db_path, org_id="org_a", vector=InMemoryVectorMemory())
    org_b = LongTermMemory(db_path=db_path, org_id="org_b", vector=InMemoryVectorMemory())
    return org_a, org_b


async def test_episode_org_a_does_not_leak_into_org_b(
    two_org_memories: tuple[LongTermMemory, LongTermMemory],
) -> None:
    """An episode written by org A must NOT appear in org B's queries."""
    org_a, org_b = two_org_memories

    eid = await org_a.write(
        run_id="r1", agent_id="a1", scope="shared",
        content="Org A's secret architecture decision",
        summary="secret decision",
    )

    # org B must NOT see org A's episode in search()
    b_results = await org_b.search("secret", limit=10)
    assert all(e.get("org_id") != "org_a" for e in b_results), (
        f"Cross-tenant leak: org B sees org A's episode in search(). "
        f"Found: {[e['id'] for e in b_results]}"
    )

    # org B must NOT be able to fetch org A's episode by ID
    b_direct = await org_b.get(eid)
    assert b_direct is None, (
        f"Cross-tenant leak: org B fetched org A's episode by ID. "
        f"Got: {b_direct.get('content')}"
    )


async def test_episode_org_b_does_not_leak_into_org_a(
    two_org_memories: tuple[LongTermMemory, LongTermMemory],
) -> None:
    """Symmetric check: org B's episodes must not leak into org A."""
    org_a, org_b = two_org_memories

    await org_b.write(
        run_id="r1", agent_id="b1", scope="shared",
        content="Org B's confidential strategy",
    )

    a_results = await org_a.search("confidential", limit=10)
    assert all(e.get("org_id") != "org_b" for e in a_results), (
        "Cross-tenant leak: org A sees org B's episode"
    )


async def test_episode_list_by_run_filters_by_org(
    two_org_memories: tuple[LongTermMemory, LongTermMemory],
) -> None:
    """list_by_run must only return episodes for the scoped org."""
    org_a, org_b = two_org_memories

    # Both orgs write episodes with the SAME run_id — must not collide
    await org_a.write(run_id="shared_run", agent_id="a", scope="s", content="A's episode")
    await org_b.write(run_id="shared_run", agent_id="b", scope="s", content="B's episode")

    a_episodes = await org_a.list_by_run("shared_run")
    b_episodes = await org_b.list_by_run("shared_run")

    assert len(a_episodes) == 1
    assert len(b_episodes) == 1
    assert a_episodes[0]["content"] == "A's episode"
    assert b_episodes[0]["content"] == "B's episode"


async def test_episode_list_by_tag_filters_by_org(
    two_org_memories: tuple[LongTermMemory, LongTermMemory],
) -> None:
    """list_by_tag must only return episodes for the scoped org."""
    org_a, org_b = two_org_memories

    await org_a.write(
        run_id="r1", agent_id="a", scope="s",
        content="A's decision", tags=["architecture"],
    )
    await org_b.write(
        run_id="r1", agent_id="b", scope="s",
        content="B's decision", tags=["architecture"],
    )

    a_tagged = await org_a.list_by_tag("architecture")
    b_tagged = await org_b.list_by_tag("architecture")

    assert len(a_tagged) == 1
    assert len(b_tagged) == 1
    assert a_tagged[0]["content"] == "A's decision"
    assert b_tagged[0]["content"] == "B's decision"


async def test_episode_default_org_still_works(tmp_path: Path) -> None:
    """Without an explicit org_id, the default org must still function."""
    ltm = LongTermMemory(db_path=str(tmp_path / "default.db"), vector=InMemoryVectorMemory())
    eid = await ltm.write(run_id="r1", agent_id="a", scope="s", content="default org episode")
    assert await ltm.get(eid) is not None
    assert len(await ltm.list_by_run("r1")) >= 1
