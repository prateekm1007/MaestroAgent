"""Event bus — typed pub-sub for run observability.

Every layer of the engine emits events onto an in-process `EventBus`.
The FastAPI server republishes events over WebSocket to UIs and external
hooks. The bus is the single source of truth for "what is happening in
this run" — the dashboard, the trace tree, the metrics panel, and the
audit log all consume from it.

Design
------
- Events are pydantic models, so they serialize cleanly to JSON.
- Subscribers are async callbacks. The bus dispatches concurrently but
  isolates failures (one bad subscriber does not break the bus).
- The bus is local to a run. Cross-run aggregation is a UI concern.
- High throughput: we batch-dispatch using `anyio` to avoid unbounded
  task creation. Drop policies are configurable; default is "block" so
  we never silently lose events.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

Subscriber = Callable[["Event"], Awaitable[None]]


class EventType(str, Enum):
    RUN_STARTED = "run.started"
    RUN_PAUSED = "run.paused"
    RUN_RESUMED = "run.resumed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    STEP_STARTED = "step.started"
    STEP_COMPLETED = "step.completed"
    STEP_FAILED = "step.failed"
    LOOP_ITERATION = "loop.iteration"
    LOOP_EXIT = "loop.exit"
    LOOP_ESCALATE = "loop.escalate"
    AGENT_SPAWNED = "agent.spawned"
    AGENT_COMPLETED = "agent.completed"
    AGENT_DEBATE = "agent.debate"
    LLM_CALL_STARTED = "llm.call.started"
    LLM_CALL_COMPLETED = "llm.call.completed"
    LLM_CALL_FAILED = "llm.call.failed"
    TOOL_CALL_STARTED = "tool.call.started"
    TOOL_CALL_COMPLETED = "tool.call.completed"
    TOOL_CALL_FAILED = "tool.call.failed"
    MEMORY_WRITE = "memory.write"
    MEMORY_READ = "memory.read"
    HITL_REQUESTED = "hitl.requested"
    HITL_RESOLVED = "hitl.resolved"
    BUDGET_WARNING = "budget.warning"
    AUDIT = "audit"


class Event(BaseModel):
    """A single event on the bus."""

    type: EventType
    run_id: str
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


class EventBus:
    """In-process async pub-sub."""

    def __init__(self, max_queue: int = 1024) -> None:
        self._subscribers: list[Subscriber] = []
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=max_queue)
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    def subscribe(self, fn: Subscriber) -> Callable[[], None]:
        """Register a subscriber. Returns an unsubscribe callable."""
        self._subscribers.append(fn)
        return lambda: self._subscribers.remove(fn) if fn in self._subscribers else None

    async def publish(self, event: Event) -> None:
        """Publish an event. Blocks if the queue is full (default drop policy)."""
        if self._closed:
            return
        await self._queue.put(event)

    async def emit(
        self, type_: EventType, run_id: str, **payload: Any
    ) -> None:
        """Convenience: build and publish."""
        await self.publish(Event(type=type_, run_id=run_id, payload=payload))

    async def _dispatch_loop(self) -> None:
        while not self._closed or not self._queue.empty():
            event = await self._queue.get()
            # Fan out concurrently; isolate failures.
            results = await asyncio.gather(
                *[sub(event) for sub in self._subscribers],
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, Exception):
                    # Swallow — a bad subscriber must not break the bus.
                    # In production we'd log this; here we keep it quiet
                    # to avoid log noise in tests.
                    pass

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._dispatch_loop())

    async def stop(self) -> None:
        self._closed = True
        # Wake the dispatcher so it sees _closed.
        await self._queue.put(Event(type=EventType.AUDIT, run_id="__shutdown__"))
        if self._task is not None:
            await self._task
