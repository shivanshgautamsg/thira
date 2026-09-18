"""Redis Streams implementation of the Event Bus.

Uses Redis Streams with consumer groups for reliable event delivery.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime

import redis.asyncio as redis
import structlog

from shared.bus.event_bus import EventBus
from shared.events import ThiraEvent

logger = structlog.get_logger()


class RedisEventBus(EventBus):
    """Redis Streams-based event bus.

    Features:
    - Consumer groups for reliable delivery
    - Automatic stream creation
    - JSON serialization of ThiraEvents
    - Graceful reconnection
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._running = False

    async def publish(self, event: ThiraEvent, stream: str = "thira:events") -> str:
        """Publish a ThiraEvent to a Redis Stream."""
        payload = {
            "event_id": str(event.id),
            "source": event.source.value,
            "type": event.type.value,
            "payload": event.model_dump_json(),
            "ingested_at": datetime.utcnow().isoformat(),
        }

        entry_id = await self._redis.xadd(stream, payload)

        logger.info(
            "event_bus.published",
            stream=stream,
            event_id=str(event.id),
            source=event.source.value,
            type=event.type.value,
            entry_id=entry_id,
        )

        return entry_id

    async def subscribe(
        self,
        stream: str = "thira:events",
        group: str = "thira-core",
        consumer: str = "worker-1",
    ) -> AsyncIterator[ThiraEvent]:
        """Subscribe to events using Redis consumer groups.

        Creates the consumer group if it doesn't exist.
        Yields ThiraEvents as they arrive on the stream.
        """
        # Ensure stream and consumer group exist
        try:
            await self._redis.xgroup_create(stream, group, id="0", mkstream=True)
            logger.info("event_bus.group_created", stream=stream, group=group)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
            # Group already exists — that's fine

        self._running = True
        logger.info("event_bus.subscribed", stream=stream, group=group, consumer=consumer)

        while self._running:
            try:
                # Read new messages (block for up to 5 seconds)
                messages = await self._redis.xreadgroup(
                    groupname=group,
                    consumername=consumer,
                    streams={stream: ">"},
                    count=10,
                    block=5000,
                )

                if not messages:
                    continue

                for stream_name, entries in messages:
                    for entry_id, fields in entries:
                        try:
                            event = ThiraEvent.model_validate_json(fields["payload"])
                            yield event

                            # Auto-acknowledge after successful processing
                            await self.acknowledge(stream_name, group, entry_id)

                        except Exception as e:
                            logger.error(
                                "event_bus.process_error",
                                entry_id=entry_id,
                                error=str(e),
                            )

            except redis.ConnectionError:
                logger.warning("event_bus.connection_lost, reconnecting...")
                await self._reconnect()

    async def acknowledge(
        self,
        stream: str,
        group: str,
        message_id: str,
    ) -> None:
        """Acknowledge a processed message."""
        await self._redis.xack(stream, group, message_id)

    async def health_check(self) -> bool:
        """Check if Redis is accessible."""
        try:
            await self._redis.ping()
            return True
        except Exception:
            return False

    def stop(self) -> None:
        """Stop the subscriber loop."""
        self._running = False

    async def close(self) -> None:
        """Close the Redis connection."""
        self.stop()
        await self._redis.close()

    async def _reconnect(self) -> None:
        """Attempt to reconnect to Redis."""
        import asyncio

        for attempt in range(5):
            try:
                await self._redis.ping()
                logger.info("event_bus.reconnected", attempt=attempt)
                return
            except Exception:
                wait = 2**attempt
                logger.warning("event_bus.reconnect_failed", attempt=attempt, wait=wait)
                await asyncio.sleep(wait)

        raise ConnectionError("Failed to reconnect to Redis after 5 attempts")
