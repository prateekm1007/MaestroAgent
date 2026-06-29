"""maestro_core — stateful graph runtime, checkpoints, streaming, orchestration engine.

This package contains the pure-Python core of MaestroAgent. It has no UI
dependencies and no provider SDK dependencies; it talks to LLMs and storage
through injectable interfaces. This keeps the core testable headlessly and
makes it usable as a library outside the desktop app.
"""

from maestro_core.engine import OrchestrationEngine
from maestro_core.graph import Graph, Node, Edge, ConditionalEdge
from maestro_core.state import State, StateSchema
from maestro_core.checkpoint import CheckpointStore, SQLiteCheckpointStore
from maestro_core.streaming import EventBus, Event, EventType
from maestro_core.context import RunContext, RunConfig
from maestro_core.state import RunStatus

__all__ = [
    "OrchestrationEngine",
    "Graph",
    "Node",
    "Edge",
    "ConditionalEdge",
    "State",
    "StateSchema",
    "CheckpointStore",
    "SQLiteCheckpointStore",
    "EventBus",
    "Event",
    "EventType",
    "RunContext",
    "RunConfig",
    "RunStatus",
]

__version__ = "0.1.0"
