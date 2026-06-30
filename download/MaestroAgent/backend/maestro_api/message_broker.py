"""Message broker abstraction for WebSocket horizontal scaling.

Supports two backends:
  - Redis pub/sub (production, multi-instance)
  - In-process pub/sub (development, single-instance)

The broker is selected by the MAESTRO_MESSAGE_BROKER env var:
  - "redis"  — use Redis (requires REDIS_URL)
  - "memory" — use in-process (default, no external dependency)

In production (MAESTRO_ENV=production), if the broker is "memory",
a warning is logged — multi-instance deployments need Redis.

Usage:
    broker = get_message_broker()
    await broker.publish("ambient:pulse", {"type": "ambient_update", ...})
    async for message in broker.subscribe("ambient:pulse"):
        handle(message)

The broker is a singleton — one instance per process. In Redis mode,
multiple processes share the same Redis pub/sub channels, so WebSocket
clients connected to different server instances all receive the same
broadcasts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


class MessageBroker:
    """Base interface for a pub/sub message broker."""

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        raise NotImplementedError

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedError
        yield  # type: ignore  # Make it an async generator

    async def close(self) -> None:
        pass


class InMemoryBroker(MessageBroker):
    """In-process pub/sub for development (single-instance only).

    Uses asyncio queues per channel. No external dependency.
    Does NOT work across multiple server instances — use RedisBroker
    for production.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        async with self._lock:
            for queue in self._subscribers.get(channel, []):
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    # Drop oldest, push newest
                    try:
                        queue.get_nowait()
                        queue.put_nowait(message)
                    except Exception:
                        pass

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1024)
        async with self._lock:
            self._subscribers.setdefault(channel, []).append(queue)
        try:
            while True:
                message = await queue.get()
                yield message
        finally:
            async with self._lock:
                if channel in self._subscribers:
                    self._subscribers[channel] = [
                        q for q in self._subscribers[channel] if q is not queue
                    ]


class RedisBroker(MessageBroker):
    """Redis pub/sub for production (multi-instance).

    Requires redis>=4.2.0 (async support). Falls back to InMemoryBroker
    if redis is not installed or the connection fails.

    Each server instance subscribes to the same Redis channels. When any
    instance publishes, all instances receive the message and forward it
    to their connected WebSocket clients.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis = None
        self._pubsub = None
        self._channels: dict[str, list[asyncio.Queue]] = {}
        self._listener_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def _ensure_connected(self) -> bool:
        if self._redis is not None:
            return True
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("Redis broker connected: %s", self._redis_url)
            return True
        except ImportError:
            logger.warning(
                "Redis broker selected but redis package not installed. "
                "Install with: pip install redis>=4.2.0. Falling back to in-memory."
            )
            return False
        except Exception as e:
            logger.warning("Redis broker connection failed: %s. Falling back to in-memory.", e)
            return False

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        if not await self._ensure_connected():
            # Fallback to in-memory
            await _fallback_broker.publish(channel, message)
            return
        await self._redis.publish(channel, json.dumps(message))

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        if not await self._ensure_connected():
            # Fallback to in-memory
            async for msg in _fallback_broker.subscribe(channel):
                yield msg
            return

        queue: asyncio.Queue = asyncio.Queue(maxsize=1024)
        async with self._lock:
            self._channels.setdefault(channel, []).append(queue)

            # If this is the first subscriber for this channel, start listening
            if len(self._channels[channel]) == 1:
                self._pubsub = self._redis.pubsub()
                await self._pubsub.subscribe(channel)
                self._listener_task = asyncio.create_task(self._listen(channel))

        try:
            while True:
                message = await queue.get()
                yield message
        finally:
            async with self._lock:
                if channel in self._channels:
                    self._channels[channel] = [
                        q for q in self._channels[channel] if q is not queue
                    ]
                    if not self._channels[channel]:
                        # No more subscribers — stop listening
                        if self._listener_task:
                            self._listener_task.cancel()
                            self._listener_task = None
                        if self._pubsub:
                            await self._pubsub.unsubscribe(channel)

    async def _listen(self, channel: str) -> None:
        """Listen for Redis pub/sub messages and forward to local queues."""
        try:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        async with self._lock:
                            for queue in self._channels.get(channel, []):
                                try:
                                    queue.put_nowait(data)
                                except asyncio.QueueFull:
                                    try:
                                        queue.get_nowait()
                                        queue.put_nowait(data)
                                    except Exception:
                                        pass
                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON on Redis channel %s", channel)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("Redis listener error: %s", e)

    async def close(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()


# ─── Singleton management ──────────────────────────────────────────────────

_fallback_broker = InMemoryBroker()
_broker_instance: MessageBroker | None = None


def get_message_broker() -> MessageBroker:
    """Get the singleton message broker.

    Selection logic:
      1. MAESTRO_MESSAGE_BROKER=redis + REDIS_URL set → RedisBroker
      2. MAESTRO_MESSAGE_BROKER=redis but no redis package/conn → fallback
      3. MAESTRO_MESSAGE_BROKER=memory (default) → InMemoryBroker
      4. In production with "memory" → log a warning
    """
    global _broker_instance
    if _broker_instance is not None:
        return _broker_instance

    broker_type = os.environ.get("MAESTRO_MESSAGE_BROKER", "memory")
    is_production = os.environ.get("MAESTRO_ENV", "development") == "production"

    if broker_type == "redis":
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        _broker_instance = RedisBroker(redis_url)
        logger.info("Message broker: Redis (%s)", redis_url)
    else:
        _broker_instance = InMemoryBroker()
        if is_production:
            logger.warning(
                "Message broker is 'memory' in production. Multi-instance "
                "deployments require MAESTRO_MESSAGE_BROKER=redis with a "
                "REDIS_URL. WebSocket broadcasts will not cross instance boundaries."
            )
        else:
            logger.info("Message broker: in-memory (development mode)")

    return _broker_instance


async def close_message_broker() -> None:
    """Close the broker on shutdown."""
    global _broker_instance
    if _broker_instance:
        await _broker_instance.close()
        _broker_instance = None
