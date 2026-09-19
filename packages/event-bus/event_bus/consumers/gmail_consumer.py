"""Gmail event ingestion consumer.

Monitors incoming emails and publishes normalized ThiraEvents to the event bus.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from shared.bus.event_bus import EventBus
from shared.enums import EventPriority, EventSource, EventType
from shared.events import ThiraEvent

logger = structlog.get_logger()


class GmailEventConsumer:
    """Ingests email messages from Gmail and feeds them into the THIRA perception stream."""

    def __init__(self, event_bus: EventBus, gmail_client: Any | None = None):
        self._event_bus = event_bus
        self._client = gmail_client

    async def ingest_message(self, message_data: dict[str, Any]) -> ThiraEvent:
        """Normalize a raw message payload into a ThiraEvent and publish to the bus."""
        subject = message_data.get("subject", "")
        body = message_data.get("body", "")
        sender = message_data.get("from", "unknown")
        labels = message_data.get("labels", [])

        # Infer priority based on labels and content
        priority = EventPriority.MEDIUM
        if "IMPORTANT" in labels or any(
            w in subject.lower() for w in ("urgent", "asap", "deadline", "emergency")
        ):
            priority = EventPriority.HIGH

        content = f"Subject: {subject}\nFrom: {sender}\n\n{body}"

        event = ThiraEvent(
            id=uuid.uuid4(),
            source=EventSource.GMAIL,
            type=EventType.MESSAGE_RECEIVED,
            timestamp=datetime.now(UTC),
            actor=sender,
            content=content,
            priority=priority,
            raw_data=message_data,
        )

        entry_id = await self._event_bus.publish(event)
        logger.info(
            "gmail_consumer.ingested",
            event_id=str(event.id),
            sender=sender,
            subject=subject,
            stream_entry=entry_id,
        )
        return event

    async def poll_new_messages(
        self, query: str = "is:unread", max_results: int = 5
    ) -> list[ThiraEvent]:
        """Poll Gmail for new messages and ingest each."""
        if not self._client:
            return []

        messages = await self._client.list_messages(query=query, max_results=max_results)
        ingested = []
        for msg_summary in messages:
            full_msg = await self._client.get_message(msg_summary["id"])
            if full_msg:
                event = await self.ingest_message(full_msg)
                ingested.append(event)
        return ingested
