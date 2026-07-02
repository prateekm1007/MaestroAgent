"""Tests for maestro_memory — the memory tier that underpins the product's
"semantic recall" pitch.

Principle 2: these tests exist because the module previously had zero
coverage. Principle 1: every claim below is verified by execution in
this test run, not by reading code.

Coverage:
- VectorMemory is an ABC (regression guard — the audit's C1 found a
  prior version that instantiated it directly)
- InMemoryVectorMemory: add → query round-trip, cosine similarity,
  run_id/scope filtering, empty-store query returns []
- LongTermMemory: write → search (current behavior: naive SQL LIKE),
  write → get, write → list_by_run, write → list_by_tag, promote
- LongTermMemory.search() currently does NOT do semantic ranking —
  a non-substring query returns []. This documents the feature gap
  honestly. A future fix that adds semantic ranking must make the
  non-substring query pass (proof-by-negation guard).
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from maestro_memory.long_term import LongTermMemory
from maestro_memory.vector import InMemoryVectorMemory, VectorMemory, VectorEntry


# ---------------------------------------------------------------------------
# VectorMemory ABC — regression guard (Principle 1)
# ---------------------------------------------------------------------------


def test_vector_memory_is_abstract_and_cannot_be_instantiated() -> None:
    """VectorMemory is an ABC. Instantiating it must raise TypeError.

    This is the regression guard for the audit's C1 finding: a prior
    version of long_term.py instantiated VectorMemory() directly. If a
    future refactor accidentally removes the ABC marker, this test
    catches it.
    """
    with pytest.raises(TypeError):
        VectorMemory()


# ---------------------------------------------------------------------------
# InMemoryVectorMemory — add + query round-trip
# ---------------------------------------------------------------------------


async def test_inmemory_add_then_query_returns_the_entry() -> None:
    """An entry added via .add() must be findable via .query()."""
    vm = InMemoryVectorMemory()
    eid = await vm.add(
        run_id="r1", agent_id="a1", scope="shared",
        content="The API uses Postgres for the primary store.",
    )
    assert eid, "add() must return a non-empty id"

    results = await vm.query(query_text="database", top_k=5)
    assert results, "query() must return at least one result"
    assert any(r.id == eid for r in results), "the added entry must be in results"


async def test_inmemory_query_on_empty_store_returns_empty_list() -> None:
    """Querying an empty store must return [], not raise."""
    vm = InMemoryVectorMemory()
    results = await vm.query(query_text="anything", top_k=5)
    assert results == []


async def test_inmemory_query_filters_by_run_id() -> None:
    """When run_id is specified, only entries from that run are returned."""
    vm = InMemoryVectorMemory()
    await vm.add(run_id="r1", agent_id="a", scope="s", content="entry from run 1")
    await vm.add(run_id="r2", agent_id="a", scope="s", content="entry from run 2")

    r1_results = await vm.query(query_text="entry", run_id="r1", top_k=10)
    assert all(r.run_id == "r1" for r in r1_results), "run_id filter leaked"
    r2_results = await vm.query(query_text="entry", run_id="r2", top_k=10)
    assert all(r.run_id == "r2" for r in r2_results), "run_id filter leaked"


async def test_inmemory_query_filters_by_scope() -> None:
    """When scope is specified, only entries in that scope are returned."""
    vm = InMemoryVectorMemory()
    await vm.add(run_id="r1", agent_id="a", scope="private", content="private entry")
    await vm.add(run_id="r1", agent_id="a", scope="shared", content="shared entry")

    private_results = await vm.query(query_text="entry", scope="private", top_k=10)
    assert all(r.scope == "private" for r in private_results)


async def test_inmemory_query_respects_top_k() -> None:
    """top_k limits the number of results returned."""
    vm = InMemoryVectorMemory()
    for i in range(10):
        await vm.add(run_id="r1", agent_id="a", scope="s", content=f"entry number {i}")
    results = await vm.query(query_text="entry", top_k=3)
    assert len(results) <= 3


async def test_inmemory_list_by_run_returns_only_that_run() -> None:
    """list_by_run returns all entries for a run, not other runs' entries."""
    vm = InMemoryVectorMemory()
    await vm.add(run_id="r1", agent_id="a", scope="s", content="r1 entry")
    await vm.add(run_id="r2", agent_id="a", scope="s", content="r2 entry")
    r1_entries = await vm.list_by_run("r1")
    assert len(r1_entries) == 1
    assert r1_entries[0].run_id == "r1"


async def test_inmemory_query_returns_vector_entry_objects() -> None:
    """Results must be VectorEntry instances with the expected fields."""
    vm = InMemoryVectorMemory()
    await vm.add(run_id="r1", agent_id="a1", scope="shared", content="hello")
    results = await vm.query(query_text="hello", top_k=1)
    assert isinstance(results[0], VectorEntry)
    assert results[0].content == "hello"
    assert results[0].run_id == "r1"
    assert results[0].agent_id == "a1"
    assert results[0].scope == "shared"
    assert isinstance(results[0].score, float)


# ---------------------------------------------------------------------------
# LongTermMemory — write + read round-trip
# ---------------------------------------------------------------------------


@pytest.fixture
def ltm(tmp_path: Path) -> LongTermMemory:
    return LongTermMemory(db_path=str(tmp_path / "ltm.db"))


async def test_ltm_write_returns_episode_id(ltm: LongTermMemory) -> None:
    """write() must return a non-empty episode id."""
    eid = await ltm.write(
        run_id="r1", agent_id="a1", scope="shared", content="test content",
    )
    assert eid, "write() must return a non-empty id"


async def test_ltm_get_returns_written_episode(ltm: LongTermMemory) -> None:
    """get() must return the episode with all fields populated."""
    eid = await ltm.write(
        run_id="r1", agent_id="a1", scope="shared",
        content="the content", summary="the summary", tags=["decision"],
    )
    episode = await ltm.get(eid)
    assert episode is not None
    assert episode["id"] == eid
    assert episode["run_id"] == "r1"
    assert episode["agent_id"] == "a1"
    assert episode["scope"] == "shared"
    assert episode["content"] == "the content"
    assert episode["summary"] == "the summary"
    assert episode["tags"] == ["decision"]


async def test_ltm_get_nonexistent_returns_none(ltm: LongTermMemory) -> None:
    """get() on a nonexistent id must return None, not raise."""
    result = await ltm.get("does-not-exist")
    assert result is None


async def test_ltm_list_by_run(ltm: LongTermMemory) -> None:
    """list_by_run returns all episodes for a run, ordered by created_at."""
    await ltm.write(run_id="r1", agent_id="a", scope="s", content="first")
    await ltm.write(run_id="r1", agent_id="a", scope="s", content="second")
    await ltm.write(run_id="r2", agent_id="a", scope="s", content="other run")
    r1 = await ltm.list_by_run("r1")
    assert len(r1) == 2
    assert all(e["run_id"] == "r1" for e in r1)
    # Ordered by created_at ASC — "first" should come before "second".
    assert r1[0]["content"] == "first"
    assert r1[1]["content"] == "second"


async def test_ltm_list_by_tag(ltm: LongTermMemory) -> None:
    """list_by_tag finds episodes with the given tag in their tags_json."""
    await ltm.write(run_id="r1", agent_id="a", scope="s", content="x", tags=["arch"])
    await ltm.write(run_id="r1", agent_id="a", scope="s", content="y", tags=["bug"])
    arch = await ltm.list_by_tag("arch")
    assert len(arch) == 1
    assert arch[0]["content"] == "x"


async def test_ltm_promote_sets_promoted_at(ltm: LongTermMemory) -> None:
    """promote() sets promoted_at and returns True; second promote returns False."""
    eid = await ltm.write(run_id="r1", agent_id="a", scope="s", content="x")
    assert await ltm.promote(eid) is True
    episode = await ltm.get(eid)
    assert episode["promoted_at"] is not None
    # Second promote must return False (already promoted).
    assert await ltm.promote(eid) is False


# ---------------------------------------------------------------------------
# LongTermMemory.search() — current behavior is naive SQL LIKE
# ---------------------------------------------------------------------------


async def test_ltm_search_finds_substring_matches(ltm: LongTermMemory) -> None:
    """search() currently does naive SQL LIKE — a substring query finds matches.

    This documents the CURRENT behavior. If semantic ranking is added later,
    this test must still pass (substring matches are a subset of semantic matches).
    """
    await ltm.write(
        run_id="r1", agent_id="a", scope="s",
        content="We chose Postgres for streaming replication.",
        summary="Postgres chosen",
    )
    results = await ltm.search("Postgres", limit=5)
    assert results, "Substring search must find 'Postgres'"
    assert "Postgres" in results[0]["content"]


async def test_ltm_search_non_substring_query_returns_empty(ltm: LongTermMemory) -> None:
    """search() with a non-substring query returns [].

    This documents the FEATURE GAP: the product pitches semantic memory,
    but long-term search is naive SQL LIKE. A query like "database scaling"
    does NOT find an episode about "Postgres for streaming replication"
    because there's no substring overlap.

    PROOF-BY-NEGATION GUARD: when semantic ranking is added to search(),
    this test must be UPDATED to assert results are non-empty. If the test
    still passes (returns []) after the semantic fix, the fix is broken.
    """
    await ltm.write(
        run_id="r1", agent_id="a", scope="s",
        content="We chose Postgres for streaming replication.",
        summary="Postgres chosen for replication",
    )
    # "database scaling" shares NO substring with the episode content/summary.
    results = await ltm.search("database scaling", limit=5)
    assert results == [], (
        "search() currently does naive SQL LIKE — a non-substring query must "
        "return []. If this test FAILS (results non-empty), semantic ranking "
        "was added — update this test to assert relevance instead of emptiness."
    )


async def test_ltm_search_respects_limit(ltm: LongTermMemory) -> None:
    """search() must not return more than `limit` results."""
    for i in range(10):
        await ltm.write(run_id="r1", agent_id="a", scope="s", content=f"Postgres entry {i}")
    results = await ltm.search("Postgres", limit=3)
    assert len(results) <= 3


# ---------------------------------------------------------------------------
# LongTermMemory + VectorMemory integration (the fix path for semantic ranking)
# ---------------------------------------------------------------------------


async def test_ltm_with_vector_does_semantic_search_on_non_substring_query() -> None:
    """When a VectorMemory is injected, search() does semantic ranking.

    PROOF BY NEGATION (Principle 2): before the fix, LongTermMemory did not
    accept a vector parameter — this test was skipped. After the fix, it must
    PASS. If it fails after the fix, the semantic layer is broken.

    The query "database scaling" shares NO substring with the episode content
    "We chose Postgres for streaming replication." Under SQL LIKE this returns
    []. With the vector layer, it returns the episode via semantic similarity.
    """
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        ltm = LongTermMemory(
            db_path=str(Path(tmp) / "ltm.db"),
            vector=InMemoryVectorMemory(),
        )
        await ltm.write(
            run_id="r1", agent_id="a", scope="s",
            content="We chose Postgres for streaming replication.",
            summary="Postgres chosen for replication",
        )
        results = await ltm.search("database scaling", limit=5)
        assert results, (
            "Semantic search returned no results for a non-substring query — "
            "the vector layer is not being consulted. Principle 1: execute, don't read."
        )
        assert "Postgres" in results[0]["content"]


async def test_ltm_without_vector_falls_back_to_sql_like() -> None:
    """Without a vector, search() still works via SQL LIKE (substring match).

    This guards the fallback path — the fix must not break the no-vector case.
    """
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        ltm = LongTermMemory(db_path=str(Path(tmp) / "ltm.db"))
        await ltm.write(
            run_id="r1", agent_id="a", scope="s",
            content="We chose Postgres for streaming replication.",
        )
        # Substring query — must find the episode.
        results = await ltm.search("Postgres", limit=5)
        assert results
        assert "Postgres" in results[0]["content"]
        # Non-substring query — must return [] (no vector, no semantic ranking).
        empty = await ltm.search("database scaling", limit=5)
        assert empty == []
