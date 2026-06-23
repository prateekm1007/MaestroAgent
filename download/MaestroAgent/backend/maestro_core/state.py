"""Typed state objects that flow through the MaestroAgent graph runtime.

A `State` is an immutable, versioned snapshot of a run's working memory.
Every node receives a `State` and returns a new `State`. This functional
style keeps the graph runtime pure and makes time-travel debugging trivial:
the checkpoint store holds the full state at every step, and any past step
can be replayed or forked from.

Design notes
------------
- We use pydantic v2 for validation and JSON serialization. State schemas
  are user-defined per template; we provide a base `State` with the fields
  the engine itself needs (run_id, step_id, parent_step_id, iteration,
  budget, status). Users subclass `State` (or supply a pydantic model) to
  add their own fields.
- States are versioned: each step bumps `revision`. This lets the
  checkpoint store detect divergent branches when a run is forked.
- States carry an `artifacts` dict for large binary-ish outputs that
  should not be inlined into the JSON state (file paths, blob refs).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T", bound=BaseModel)


class RunStatus(str, Enum):
    """Lifecycle of a run."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"  # HITL or budget pause
    AWAITING_HUMAN = "awaiting_human"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class State(BaseModel):
    """Base state model. Users subclass this to add workflow-specific fields."""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_step_id: str | None = None
    revision: int = 0
    iteration: int = 0  # bumped by each loop iteration
    status: RunStatus = RunStatus.RUNNING
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Engine-internal fields
    current_node: str | None = None
    next_node: str | None = None
    error: str | None = None

    # Free-form working memory (typed by user subclasses via extra="allow")
    artifacts: dict[str, Any] = Field(default_factory=dict)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def bump(self) -> "State":
        """Return a new state with revision+1 and a fresh step_id."""
        data = self.model_dump()
        data["revision"] = self.revision + 1
        data["step_id"] = str(uuid.uuid4())
        data["parent_step_id"] = self.step_id
        data["updated_at"] = datetime.now(timezone.utc)
        return self.__class__.model_validate(data)

    def with_updates(self, **changes: Any) -> "State":
        """Return a new state with the given fields updated, revision bumped."""
        data = self.model_dump()
        data.update(changes)
        data["revision"] = self.revision + 1
        data["step_id"] = str(uuid.uuid4())
        data["parent_step_id"] = self.step_id
        data["updated_at"] = datetime.now(timezone.utc)
        return self.__class__.model_validate(data)


class StateSchema(BaseModel, Generic[T]):
    """Describes the shape of a workflow's state.

    Used by the UI to render forms and by the verifier to validate state
    transitions. Not enforced at runtime (pydantic already does that);
    this is metadata for tooling.
    """

    model: type[T]
    description: str = ""
    required_fields: list[str] = Field(default_factory=list)
