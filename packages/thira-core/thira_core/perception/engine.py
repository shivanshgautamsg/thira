"""Perception Engine implementation.

Streams events from multiple sources and normalizes them into ThiraEvents.
V1: Accepts user commands directly + Redis event bus subscription.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import structlog

from shared.bus.event_bus import EventBus
from shared.events import ThiraEvent

logger = structlog.get_logger()


class PerceptionEngine:
    """Perceives the digital environment by streaming normalized events.

    V1 sources:
    - Direct user commands (pushed via inject_event)
    - Redis event bus (external event consumers push events here)

    V2+ sources:
    - Gmail webhook consumer
    - Calendar push notifications
    - GitHub webhooks
    - File system watchers
    - Android event streams
    """

    def __init__(self, event_bus: EventBus | None = None):
        self._event_bus = event_bus
        self._queue: asyncio.Queue[ThiraEvent] = asyncio.Queue()
        self._running = False

    async def inject_event(self, event: ThiraEvent) -> None:
        """Inject an event directly into the perception stream.

        Used for user commands from JARVIS and testing.
        """
        await self._queue.put(event)
        logger.debug(
            "perception.event_injected",
            event_id=str(event.id),
            source=event.source.value,
            type=event.type.value,
        )

    async def stream(self) -> AsyncIterator[ThiraEvent]:
        """Stream normalized events to the orchestrator.

        Merges events from the direct queue and the event bus.
        """
        self._running = True
        logger.info("perception.streaming_started")

        # If we have an event bus, start consuming from it in the background
        if self._event_bus:
            asyncio.create_task(self._consume_event_bus())

        while self._running:
            try:
                # Wait for events with a timeout so we can check _running
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)

                logger.info(
                    "perception.event_received",
                    event_id=str(event.id),
                    source=event.source.value,
                    type=event.type.value,
                    priority=event.priority.value,
                )

                yield event

            except TimeoutError:
                continue

        logger.info("perception.streaming_stopped")

    async def _consume_event_bus(self) -> None:
        """Background task that reads from the Redis event bus and queues events."""
        if not self._event_bus:
            return

        try:
            async for event in self._event_bus.subscribe():
                if not self._running:
                    break
                await self._queue.put(event)
        except Exception as e:
            logger.error("perception.event_bus_error", error=str(e), exc_info=True)

    def stop(self) -> None:
        """Stop the perception engine."""
        self._running = False
