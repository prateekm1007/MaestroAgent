"""WebSocket endpoint — streams events from a run's event bus to clients.

The desktop UI subscribes to `/ws/{run_id}` to receive live events
(trace, log, metric, audit) as the run progresses. The server fans
out events from the in-process `EventBus` to all connected WebSocket
clients for that run.

For v0.1, we use a simple pub-sub: each WebSocket client registers a
subscriber on the run's bus; when the bus publishes an event, the
subscriber pushes it to the WebSocket.

Backpressure: if a client is slow, events queue up in memory. v0.2 will
add a bounded queue + drop policy. For now, we warn and keep going.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

ws_router = APIRouter()


def register_ws_routes(app: FastAPI) -> None:
    @app.websocket("/ws/{run_id}")
    async def stream_events(websocket: WebSocket, run_id: str) -> None:
        # Auth: if enabled, check the token query param (browsers can't
        # set custom headers on WS connections).
        state: Any = app.state.maestro
        auth_config = getattr(state, "auth_config", None)
        if auth_config and auth_config.enabled:
            token = websocket.query_params.get("token", "")
            if not token:
                await websocket.close(code=4401, reason="Unauthorized: missing token")
                return
            # Verify via the key store.
            if state.api_key_store:
                ok, _ = await state.api_key_store.verify(token)
                if not ok:
                    await websocket.close(code=4401, reason="Unauthorized: invalid token")
                    return

        await websocket.accept()
        bus = state.get_or_create_bus(run_id)

        # Queue to push events to this client.
        queue: asyncio.Queue = asyncio.Queue(maxsize=1024)

        async def _on_event(event) -> None:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest — never block the bus.
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except Exception:
                    pass

        unsub = bus.subscribe(_on_event)

        # Send a connection-ack.
        await websocket.send_json({"type": "connected", "run_id": run_id})

        try:
            while True:
                event = await queue.get()
                await websocket.send_json(event.model_dump(mode="json"))
        except WebSocketDisconnect:
            logger.info("WS client disconnected from run %s", run_id)
        except Exception as exc:
            logger.exception("WS error for run %s: %s", run_id, exc)
        finally:
            unsub()
