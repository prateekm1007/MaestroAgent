"""Semantic vector memory — Chroma / PGVector / in-memory.

The semantic tier embeds every memory entry and retrieves top-k by
similarity. This is the workhorse for "recall relevant context":

- Before an agent call, the supervisor queries the semantic tier for
  context relevant to the current sub-goal.
- After an agent produces output, the output is embedded and stored.
- On recall, we embed the query and return top-k entries.

Backends
--------
- `InMemoryVectorMemory` — default for tests / no-Chroma environments.
  Cosine similarity over numpy arrays.
- `ChromaVectorMemory` — default for production. Uses ChromaDB locally.
- `PGVectorMemory` — placeholder for v0.2, when running on Postgres.

Embeddings
----------
We use the LLM router's `embed()` method, which routes to the
configured embedding provider (Ollama, OpenAI, etc.). For v0.1, the
default is a small local model via Ollama (`nomic-embed-text`).
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maestro_core.context import RunContext


@dataclass
class VectorEntry:
    id: str
    run_id: str
    agent_id: str | None
    scope: str
    content: str
    metadata: dict[str, Any]
    score: float = 0.0


class VectorMemory(ABC):
    """Abstract semantic vector memory."""

    @abstractmethod
    async def add(
        self,
        run_id: str,
        agent_id: str | None,
        scope: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> str: ...

    @abstractmethod
    async def query(
        self,
        query_text: str,
        run_id: str | None = None,
        scope: str | None = None,
        top_k: int = 5,
        embedding: list[float] | None = None,
    ) -> list[VectorEntry]: ...

    @abstractmethod
    async def list_by_run(self, run_id: str) -> list[VectorEntry]: ...


class InMemoryVectorMemory(VectorMemory):
    """Pure-Python in-memory vector store. Default for tests."""

    def __init__(self) -> None:
        self._entries: list[VectorEntry] = []
        self._embeddings: list[list[float]] = []
        # Cache for embeddings to avoid recomputing.
        self._embed_cache: dict[str, list[float]] = {}

    async def add(
        self,
        run_id: str,
        agent_id: str | None,
        scope: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> str:
        eid = str(uuid.uuid4())
        if embedding is None:
            # Trivially hash content to a fixed-size vector. This is NOT a
            # real embedding — it's only for tests. Production uses Chroma
            # with a real embedding model.
            embedding = self._hash_embedding(content)
        entry = VectorEntry(
            id=eid,
            run_id=run_id,
            agent_id=agent_id,
            scope=scope,
            content=content,
            metadata=metadata or {},
        )
        self._entries.append(entry)
        self._embeddings.append(embedding)
        return eid

    async def query(
        self,
        query_text: str,
        run_id: str | None = None,
        scope: str | None = None,
        top_k: int = 5,
        embedding: list[float] | None = None,
    ) -> list[VectorEntry]:
        if not self._entries:
            return []
        q = embedding or self._hash_embedding(query_text)
        # Cosine similarity.
        scored: list[tuple[float, VectorEntry]] = []
        for entry, emb in zip(self._entries, self._embeddings):
            if run_id is not None and entry.run_id != run_id:
                continue
            if scope is not None and entry.scope != scope:
                continue
            score = self._cosine(q, emb)
            scored.append((score, entry))
        scored.sort(key=lambda t: t[0], reverse=True)
        results: list[VectorEntry] = []
        for score, entry in scored[:top_k]:
            results.append(
                VectorEntry(
                    id=entry.id,
                    run_id=entry.run_id,
                    agent_id=entry.agent_id,
                    scope=entry.scope,
                    content=entry.content,
                    metadata=entry.metadata,
                    score=score,
                )
            )
        return results

    async def list_by_run(self, run_id: str) -> list[VectorEntry]:
        return [e for e in self._entries if e.run_id == run_id]

    def _hash_embedding(self, text: str, dim: int = 256) -> list[float]:
        """Deterministic hash-based pseudo-embedding. Tests only."""
        cache_key = hashlib.md5(text.encode()).hexdigest()
        if cache_key in self._embed_cache:
            return self._embed_cache[cache_key]
        # Split text into chars; hash each chunk.
        vec = [0.0] * dim
        for i, ch in enumerate(text[:1024]):
            h = int(hashlib.md5(ch.encode()).hexdigest(), 16)
            vec[i % dim] += (h % 1000) / 1000.0
        # Normalize.
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        self._embed_cache[cache_key] = vec
        return vec

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)


class ChromaVectorMemory(VectorMemory):
    """ChromaDB-backed vector memory. Default for production."""

    def __init__(
        self,
        collection_name: str = "maestro_memory",
        persist_path: str = ".maestro/chroma",
        embedding_fn: Any | None = None,
    ) -> None:
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as e:
            raise ImportError(
                "ChromaVectorMemory requires `pip install chromadb`. "
                "Alternatively, use InMemoryVectorMemory."
            ) from e

        self._client = chromadb.PersistentClient(
            path=persist_path, settings=Settings(anonymized_telemetry=False)
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        # The embedding function: callable[str] -> list[float].
        # If None, Chroma uses its default sentence-transformer.
        self._embedding_fn = embedding_fn

    async def add(
        self,
        run_id: str,
        agent_id: str | None,
        scope: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> str:
        eid = str(uuid.uuid4())
        meta = {"run_id": run_id, "agent_id": agent_id or "", "scope": scope}
        if metadata:
            # Chroma metadata values must be primitives.
            meta.update({k: v for k, v in metadata.items() if isinstance(v, (str, int, float, bool))})
        # Chroma's add is sync; run in a thread.
        import anyio

        def _add() -> None:
            self._collection.add(
                ids=[eid],
                documents=[content],
                metadatas=[meta],
                embeddings=[embedding] if embedding is not None else None,
            )

        await anyio.to_thread.run_sync(_add)
        return eid

    async def query(
        self,
        query_text: str,
        run_id: str | None = None,
        scope: str | None = None,
        top_k: int = 5,
        embedding: list[float] | None = None,
    ) -> list[VectorEntry]:
        where: dict[str, Any] = {}
        if run_id is not None:
            where["run_id"] = run_id
        if scope is not None:
            where["scope"] = scope

        import anyio

        def _query() -> Any:
            return self._collection.query(
                query_embeddings=[embedding] if embedding is not None else None,
                query_texts=None if embedding is not None else [query_text],
                n_results=top_k,
                where=where or None,
            )

        result = await anyio.to_thread.run_sync(_query)
        entries: list[VectorEntry] = []
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        for i in range(len(ids)):
            score = 1.0 - float(distances[i]) if i < len(distances) else 0.0
            entries.append(
                VectorEntry(
                    id=ids[i],
                    run_id=metadatas[i].get("run_id", ""),
                    agent_id=metadatas[i].get("agent_id") or None,
                    scope=metadatas[i].get("scope", ""),
                    content=documents[i],
                    metadata=metadatas[i],
                    score=score,
                )
            )
        return entries

    async def list_by_run(self, run_id: str) -> list[VectorEntry]:
        # Chroma doesn't have a direct "list" — we query with a broad query.
        return await self.query("", run_id=run_id, top_k=1000)
