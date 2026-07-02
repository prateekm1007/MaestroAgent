"""Integration test: AppState wires the vector store into LongTermMemory.

Principle 7 (test the real scoped object graph, not a hand-wired stand-in):
the C1 fix was correct at the unit level — LongTermMemory.search() genuinely
calls .query() on an injected VectorMemory. But the fix was UNWIRED at the
integration level: AppState.start() constructed the vector store and passed
it to MemoryManager(semantic=vector) but NOT to LongTermMemory(vector=vector).
So in the real running app, long_term.vector was permanently None and search()
always fell through to SQL LIKE — silently, with no warning logged.

This test constructs the REAL AppState (not a hand-wired LongTermMemory) and
asserts the wiring is correct. It would have caught the integration bug that
the 19 unit tests missed.

DETERMINISM NOTE (Principle 1): these tests set MAESTRO_VECTOR_BACKEND=inmemory
to force InMemoryVectorMemory. Without this, AppState tries to construct
ChromaVectorMemory, which uses ChromaDB's default embedding function — that
downloads a ~90MB ONNX model from the internet on first use. The test would
then be non-deterministic: it passes when chromadb is absent (falls back to
InMemoryVectorMemory) but fails when chromadb is present and the model
download fails (air-gapped networks, egress allowlists, corrupted cache).
Setting the env var makes the test deterministic regardless of environment.

Root cause (P10): all 19 unit tests constructed LongTermMemory by hand with
vector=InMemoryVectorMemory(). None constructed the real AppState end-to-end.
Following Principle 7 here closes that gap.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def force_inmemory_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force InMemoryVectorMemory so tests don't depend on ChromaDB's model download.

    This makes the integration tests deterministic across environments — they
    pass whether or not chromadb is installed, and whether or not the ONNX
    model can be downloaded. Production deployments that want real semantic
    ranking should NOT set this env var (and should vendor the model — see
    state.py docstring).
    """
    monkeypatch.setenv("MAESTRO_VECTOR_BACKEND", "inmemory")


async def test_app_state_wires_vector_into_long_term_memory(tmp_path: Path) -> None:
    """AppState.start() must pass the vector store to LongTermMemory.

    This is the integration test that would have caught C1's integration-level
    bug. Before the fix, long_term.vector was None even though semantic (the
    same vector store) was correctly wired — because state.py constructed
    LongTermMemory(db_path=...) without vector=vector.

    Proof by negation: if you revert the one-line fix in state.py (remove
    `vector=vector` from the LongTermMemory constructor), this test FAILS
    with `assert state.memory.long_term.vector is not None → None is not None`.
    """
    from maestro_api.state import AppState

    state = AppState(
        db_path=str(tmp_path / "test.db"),
        chroma_path=str(tmp_path / "chroma"),
        graph_path=str(tmp_path / "graph.json"),
    )
    await state.start()

    # The semantic tier must have a vector store (this was already correct).
    assert state.memory.semantic is not None, "semantic vector store is None"

    # The long-term tier must ALSO have the same vector store wired in.
    # Before the C1 integration fix, this was None — search() silently
    # fell through to SQL LIKE.
    assert state.memory.long_term is not None, "long_term is None"
    assert state.memory.long_term.vector is not None, (
        "long_term.vector is None — AppState.start() did not pass the vector "
        "store to LongTermMemory. This is the C1 integration bug: the unit-level "
        "fix is correct but the real app never wires it in. search() will silently "
        "fall through to SQL LIKE in production."
    )


async def test_app_state_long_term_search_uses_vector_not_sql_like(tmp_path: Path) -> None:
    """End-to-end: writing an episode then searching with a non-substring query
    must find it via the vector layer — proving the wiring is functional, not
    just present.

    This test uses InMemoryVectorMemory (via MAESTRO_VECTOR_BACKEND=inmemory)
    so it's deterministic. The InMemoryVectorMemory uses a hash-based pseudo-
    embedding — not real semantic quality, but sufficient to prove the wiring
    is functional: a non-substring query finds an episode that SQL LIKE would
    miss. Production semantic quality depends on ChromaDB + a real embedding
    model (see state.py docstring for the offline-deployment caveat).
    """
    from maestro_api.state import AppState

    state = AppState(
        db_path=str(tmp_path / "test.db"),
        chroma_path=str(tmp_path / "chroma"),
        graph_path=str(tmp_path / "graph.json"),
    )
    await state.start()

    # Write an episode whose content shares NO substring with the query.
    await state.memory.long_term.write(
        run_id="r1",
        agent_id="architect",
        scope="shared",
        content="We chose Postgres for the system of record because it has "
                "mature streaming replication and B-tree indexes.",
        summary="Postgres chosen for replication",
    )

    # Query with no substring overlap — SQL LIKE returns [], vector returns it.
    results = await state.memory.long_term.search("database scaling and high availability", limit=5)
    assert results, (
        "Semantic search returned no results for a non-substring query. "
        "This means long_term.vector is None in the real AppState — the C1 "
        "integration bug. search() fell through to SQL LIKE, which can't match "
        "'database scaling' against 'Postgres for streaming replication'."
    )
    assert "Postgres" in results[0]["content"]
