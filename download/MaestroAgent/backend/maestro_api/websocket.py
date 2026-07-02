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

Scaling: for multi-instance deployments, the message broker (Redis or
in-process) handles cross-instance broadcast. See message_broker.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from maestro_api.security.policy import auth_policy, AuthPolicy

from maestro_api.message_broker import get_message_broker

logger = logging.getLogger(__name__)

ws_router = APIRouter()

# Connection limit for graceful degradation. When exceeded, new connections
# receive a 1013 (try again later) close code instead of crashing the server.
MAX_WS_CONNECTIONS = 1000
_active_connections = 0


def register_ws_routes(app: FastAPI) -> None:
    @app.websocket("/ws/{run_id}")
    @auth_policy(AuthPolicy.USER)
    async def stream_events(websocket: WebSocket, run_id: str) -> None:
        global _active_connections
        if _active_connections >= MAX_WS_CONNECTIONS:
            await websocket.close(code=1013, reason="Server overloaded — try again later")
            return

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
        _active_connections += 1
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
            _active_connections -= 1

    # ─── Ambient live pulse WebSocket (with message broker) ─────────────
    # Layer 3 of the ambient prompt: "maintain a continuously updating
    # model, nothing waits for refresh." This endpoint pushes the
    # organizational pulse + executive feed to connected clients every
    # 30 seconds, so the dashboard feels alive without polling.
    #
    # Uses the message broker for cross-instance broadcast: if multiple
    # server instances are running (with Redis), a pulse computed on
    # instance A is received by WebSocket clients on instance B.
    @app.websocket("/ws/ambient/pulse")
    @auth_policy(AuthPolicy.USER)
    async def stream_ambient_pulse(websocket: WebSocket) -> None:
        global _active_connections
        if _active_connections >= MAX_WS_CONNECTIONS:
            await websocket.close(code=1013, reason="Server overloaded — try again later")
            return

        # Round 49 C3 fix: authenticate the WebSocket.
        # The old code accepted any connection with no auth check. Now we
        # require a valid token via query param or Authorization header.
        # In dev mode (MAESTRO_AUTH_ENABLED not set), auth is skipped.
        from maestro_auth.permissions import is_auth_enabled
        if is_auth_enabled():
            token = (
                websocket.query_params.get("token")
                or websocket.headers.get("Authorization", "").replace("Bearer ", "")
            )
            if not token:
                await websocket.close(code=4401, reason="Authentication required")
                return
            try:
                # Round 65 CTO Blocker 3: verify_session_token never existed.
                # Use SessionManager.validate_session which is the real function.
                from maestro_auth.sessions import SessionManager
                from maestro_auth.models import AuthStore
                import os as _os
                _auth_db = _os.environ.get("MAESTRO_AUTH_DB", "auth.db")
                _store = AuthStore(_auth_db)
                _sm = SessionManager(_store)
                user = _sm.validate_session(token)
                if not user:
                    await websocket.close(code=4401, reason="Invalid token")
                    return
            except Exception:
                # If auth module is broken, fail closed in production
                await websocket.close(code=4401, reason="Authentication failed")
                return

        await websocket.accept()
        _active_connections += 1
        broker = get_message_broker()
        logger.info("Ambient pulse WS connected (total: %d)", _active_connections)

        try:
            # Send an initial pulse immediately
            await _send_ambient_update(websocket)

            # Subscribe to the broker for cross-instance updates
            async for message in broker.subscribe("ambient:pulse"):
                await websocket.send_json(message)
        except WebSocketDisconnect:
            logger.info("Ambient pulse WS disconnected")
        except Exception as exc:
            logger.exception("Ambient pulse WS error: %s", exc)
        finally:
            _active_connections -= 1
            logger.info("Ambient pulse WS closed (total: %d)", _active_connections)

    # ─── Background task: publish pulse every 30 seconds ────────────────
    @app.on_event("startup")
    async def start_pulse_publisher() -> None:
        """Background task that computes the pulse every 30 seconds and
        publishes it to the message broker. All WebSocket subscribers
        across all instances receive the update.
        """
        async def _publish_loop():
            broker = get_message_broker()
            while True:
                await asyncio.sleep(30)
                try:
                    message = await _compute_ambient_message()
                    if message:
                        await broker.publish("ambient:pulse", message)
                except Exception as e:
                    logger.warning("Pulse publish failed: %s", e)

        asyncio.create_task(_publish_loop())


async def _send_ambient_update(websocket: WebSocket) -> None:
    """Compute and send the current pulse + feed summary directly to a client."""
    try:
        message = await _compute_ambient_message()
        if message:
            await websocket.send_json(message)
    except Exception as exc:
        logger.warning("Ambient update failed: %s", exc)


async def _compute_ambient_message() -> dict[str, Any] | None:
    """Compute the ambient pulse message (shared between direct send and broker publish)."""
    try:
        from maestro_api.oem_state import oem_state
        from maestro_oem.pulse import OrganizationalPulse
        from maestro_oem.feed import ExecutiveFeed

        oem_state.initialize()
        model = oem_state.model
        signals = oem_state.signals

        pulse = OrganizationalPulse(model, signals)
        pulse_state = pulse.compute()

        feed = ExecutiveFeed(model, signals)
        events = feed.generate(limit=5)

        return {
            "type": "ambient_update",
            "timestamp": pulse_state["timestamp"],
            "pulse": {
                "state": pulse_state["state"],
                "temperature": pulse_state["temperature"],
                "momentum": pulse_state["momentum"],
                "alignment": pulse_state["alignment"],
                "trust": pulse_state["trust"],
                "knowledge_mobility": pulse_state["knowledge_mobility"],
                "decision_speed": pulse_state["decision_speed"],
                "narrative": pulse_state["narrative"],
            },
            "feed_events": [
                {
                    "event_type": e["event_type"],
                    "title": e["title"],
                    "priority": e.get("confidence", 0),
                }
                for e in events
            ],
        }
    except Exception as exc:
        logger.warning("Ambient computation failed: %s", exc)
        return None
