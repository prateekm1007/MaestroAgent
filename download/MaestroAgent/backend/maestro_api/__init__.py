"""maestro_api — FastAPI server + WebSocket streaming.

This is the HTTP boundary between the desktop UI (or any external
client) and the Python core. It exposes:

- REST routes for runs, agents, loops, memory, templates, costs.
- A WebSocket endpoint that streams events from a run's event bus.
- HITL endpoints to pause/resume runs and inject human input.

The server is stateless across runs — all persistent state lives in
SQLite + Chroma. The server keeps an in-process map of `run_id ->
EventBus` so WebSocket clients can subscribe to live events.
"""

from maestro_api.main import create_app

__all__ = ["create_app"]
