"""Event bus interface.

Defines the abstract contract for event publishing and consuming.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from shared.events import ThiraEvent


class EventBus(ABC):
    """Abstract event bus for THIRA.

    Provides pub/sub semantics for ThiraEvents.
    V1 implementation uses Redis Streams.
    """

    @abstractmethod
    async def publish(self, event: ThiraEvent, stream: str = "thira:events") -> str:
        """Publish an event to a stream.

        Args:
            event: The event to publish.
            stream: The stream name to publish to.

        Returns:
            The stream entry ID.
        """
        ...

    @abstractmethod
    async def subscribe(
        self,
        stream: str = "thira:events",
        group: str = "thira-core",
        consumer: str = "worker-1",
    ) -> AsyncIterator[ThiraEvent]:
        """Subscribe to events from a stream using consumer groups.

        Args:
            stream: The stream name to subscribe to.
            group: The consumer group name.
            consumer: The consumer name within the group.

        Yields:
            ThiraEvent objects as they arrive.
        """
        ...

    @abstractmethod
    async def acknowledge(
        self,
        stream: str,
        group: str,
        message_id: str,
    ) -> None:
        """Acknowledge that an event has been processed.

        Args:
            stream: The stream name.
            group: The consumer group name.
            message_id: The message ID to acknowledge.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the event bus is accessible."""
        ...
