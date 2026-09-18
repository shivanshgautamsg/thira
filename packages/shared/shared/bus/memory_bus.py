"""In-memory implementation of EventBus for testing and local operation."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator

import structlog

from shared.bus.event_bus import EventBus
from shared.events import ThiraEvent

logger = structlog.get_logger()


class InMemoryEventBus(EventBus):
    """In-memory event bus backed by asyncio queues."""

    def __init__(self):
        self._queues: dict[str, list[asyncio.Queue[ThiraEvent]]] = defaultdict(list)
        self._running = True

    async def publish(self, event: ThiraEvent, stream: str = "thira:events") -> str:
        entry_id = f"mem_{event.id}"
        for q in self._queues[stream]:
            await q.put(event)
        logger.debug("event_bus.memory_published", stream=stream, event_id=str(event.id))
        return entry_id

    async def subscribe(
        self,
        stream: str = "thira:events",
        group: str = "thira-core",
        consumer: str = "worker-1",
    ) -> AsyncIterator[ThiraEvent]:
        q: asyncio.Queue[ThiraEvent] = asyncio.Queue()
        self._queues[stream].append(q)
        try:
            while self._running:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield event
                except TimeoutError:
                    continue
        finally:
            if q in self._queues[stream]:
                self._queues[stream].remove(q)

    async def acknowledge(
        self,
        stream: str,
        group: str,
        message_id: str,
    ) -> None:
        pass

    async def health_check(self) -> bool:
        return True

    def stop(self) -> None:
        self._running = False
