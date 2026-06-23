"""Shared app state — single source of truth for the FastAPI app.

Holds the LLM router, memory manager, checkpoint store, verifier
registry, plugin registry, and a map of `run_id -> EventBus` for live
streaming.

This is constructed once at app startup (in `lifespan`) and reused
across all requests. It's the dependency injection root for the routes.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maestro_core.checkpoint import SQLiteCheckpointStore
from maestro_core.streaming import EventBus
from maestro_llm.cost import CostLedger
from maestro_llm.router import LLMRouter
from maestro_memory.graph import NetworkXGraphMemory
from maestro_memory.long_term import LongTermMemory
from maestro_memory.manager import MemoryManager
from maestro_memory.short_term import ShortTermMemory
from maestro_memory.vector import InMemoryVectorMemory
from maestro_plugins.registry import PluginRegistry
from maestro_verify.registry import VerifierRegistry

logger = logging.getLogger(__name__)


@dataclass
class AppState:
    """Shared app state. Constructed once at startup."""

    db_path: str = "maestro.db"
    chroma_path: str = ".maestro/chroma"
    graph_path: str = ".maestro/graph.json"
    # Set up at start().
    llm: LLMRouter | None = None
    memory: MemoryManager | None = None
    checkpoints: SQLiteCheckpointStore | None = None
    verifiers: VerifierRegistry | None = None
    plugins: PluginRegistry | None = None
    ledger: CostLedger | None = None
    # run_id -> EventBus (for live streaming).
    live_buses: dict[str, EventBus] = field(default_factory=dict)
    # run_id -> asyncio.Task (so we can cancel).
    run_tasks: dict[str, asyncio.Task] = field(default_factory=dict)

    async def start(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.chroma_path).parent.mkdir(parents=True, exist_ok=True)

        self.ledger = CostLedger(db_path=self.db_path)

        # Try to construct a Chroma vector memory; fall back to in-memory.
        try:
            from maestro_memory.vector import ChromaVectorMemory
            vector = ChromaVectorMemory(persist_path=self.chroma_path)
        except Exception as exc:
            logger.warning("Chroma unavailable (%s); using InMemoryVectorMemory", exc)
            vector = InMemoryVectorMemory()

        self.memory = MemoryManager(
            short_term=ShortTermMemory(),
            semantic=vector,
            graph=NetworkXGraphMemory(persist_path=self.graph_path),
            long_term=LongTermMemory(db_path=self.db_path),
        )
        self.checkpoints = SQLiteCheckpointStore(db_path=self.db_path)
        self.verifiers = VerifierRegistry()
        self.plugins = PluginRegistry()
        self.plugins.discover()

        # Build the router with auto-detection of local + cloud providers.
        # auto_detect probes Ollama + LM Studio, picks the first available
        # local provider as default (cost $0), then adds cloud providers
        # from env vars.
        try:
            self.llm = await LLMRouter.auto_detect(ledger=self.ledger)
            logger.info(
                "LLM router auto-detected: providers=%s, default=%s/%s",
                list(self.llm.providers.keys()),
                self.llm.default_provider,
                self.llm.default_model,
            )
        except Exception as exc:
            logger.warning("auto_detect failed (%s); falling back to with_defaults", exc)
            import os
            self.llm = LLMRouter.with_defaults(
                ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
                openai_api_key=os.environ.get("OPENAI_API_KEY"),
                anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY"),
            grok_api_key=os.environ.get("XAI_API_KEY"),
            ledger=self.ledger,
        )

    async def stop(self) -> None:
        # Cancel any running tasks.
        for task in self.run_tasks.values():
            task.cancel()
        for task in self.run_tasks.values():
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self.run_tasks.clear()
        self.live_buses.clear()

    def get_or_create_bus(self, run_id: str) -> EventBus:
        if run_id not in self.live_buses:
            bus = EventBus()
            bus.start()
            self.live_buses[run_id] = bus
        return self.live_buses[run_id]

    def remove_bus(self, run_id: str) -> None:
        bus = self.live_buses.pop(run_id, None)
        if bus is not None:
            asyncio.create_task(bus.stop())
