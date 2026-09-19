"""Calendar event ingestion consumer.

Monitors calendar events and publishes normalized ThiraEvents to the event bus.
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


class CalendarEventConsumer:
    """Ingests calendar updates and meetings into the THIRA perception stream."""

    def __init__(self, event_bus: EventBus, calendar_client: Any | None = None):
        self._event_bus = event_bus
        self._client = calendar_client

    async def ingest_event(
        self, event_data: dict[str, Any], event_type: EventType = EventType.CALENDAR_EVENT_UPCOMING
    ) -> ThiraEvent:
        """Normalize a raw calendar event into a ThiraEvent and publish to the bus."""
        summary = event_data.get("summary", "Untitled Meeting")
        start = event_data.get("start_time", "")
        end = event_data.get("end_time", "")
        attendees = event_data.get("attendees", [])
        description = event_data.get("description", "")

        content = (
            f"Calendar Event: {summary}\n"
            f"When: {start} to {end}\n"
            f"Attendees: {', '.join(attendees)}\n"
            f"Details: {description}"
        )

        event = ThiraEvent(
            id=uuid.uuid4(),
            source=EventSource.CALENDAR,
            type=event_type,
            timestamp=datetime.now(UTC),
            actor="calendar",
            content=content,
            priority=EventPriority.MEDIUM,
            raw_data=event_data,
        )

        entry_id = await self._event_bus.publish(event)
        logger.info(
            "calendar_consumer.ingested",
            event_id=str(event.id),
            summary=summary,
            stream_entry=entry_id,
        )
        return event

    async def poll_upcoming_events(self, max_results: int = 5) -> list[ThiraEvent]:
        """Poll Calendar for upcoming events and ingest each."""
        if not self._client:
            return []

        events = await self._client.list_events(max_results=max_results)
        ingested = []
        for ev in events:
            event = await self.ingest_event(ev)
            ingested.append(event)
        return ingested
