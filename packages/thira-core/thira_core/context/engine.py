"""Context Engine implementation.

Enriches ThiraEvents with world model context, entity resolution,
past experience matches, and LLM-generated interpretation.
"""

from __future__ import annotations

import json

import structlog

from shared.enums import EventPriority
from shared.events import (
    ContextItem,
    EnrichedEvent,
    Entity,
    ExperienceSummary,
    ResolvedEntity,
    ThiraEvent,
    WorldSnapshot,
)
from shared.llm.provider import LLMMessage, LLMProvider

logger = structlog.get_logger()


class ContextEngine:
    """Builds contextual understanding from raw events.

    For every incoming event, the Context Engine answers:
    - Who is involved? (entity resolution)
    - What is this about? (topic/project linking)
    - What else is relevant? (related emails, calendar events, tasks)
    - What happened before in similar situations? (ECHO retrieval)
    - What does this mean? (LLM interpretation)
    """

    def __init__(self, llm: LLMProvider, echo: object | None = None):
        self._llm = llm
        self._echo = echo

    async def enrich(self, event: ThiraEvent, world_model: object) -> EnrichedEvent:
        """Enrich a raw event with full context.

        This is the main method called by the orchestrator.
        """
        # 1. Extract and resolve entities via LLM
        extracted_entities = await self._extract_entities(event)

        # 2. Resolve entities against the world model
        resolved = await self._resolve_entities(extracted_entities, world_model)

        # 3. Gather related context from the world model
        related_context = await self._gather_context(event, resolved, world_model)

        # 4. Retrieve similar past experiences from ECHO
        echo_matches = await self._retrieve_experiences(event)

        # 5. Generate LLM interpretation
        interpretation = await self._interpret(event, resolved, related_context)

        # 6. Suggest priority
        suggested_priority = await self._suggest_priority(event, related_context)

        return EnrichedEvent(
            event=event,
            resolved_entities=resolved,
            related_context=related_context,
            world_model_snapshot=WorldSnapshot(),  # TODO: populate in Phase 1
            echo_matches=echo_matches,
            suggested_priority=suggested_priority,
            interpretation=interpretation,
        )

    async def _extract_entities(self, event: ThiraEvent) -> list[Entity]:
        """Use LLM to extract entities from event content."""
        response = await self._llm.complete(
            messages=[
                LLMMessage(
                    role="system",
                    content=(
                        "You are an entity extraction engine. Extract entities from the given text. "
                        "Return a JSON array of objects with 'name', 'type', and 'confidence' fields. "
                        "Types can be: person, project, organization, deadline, document, task, "
                        "location, technology, financial, other. "
                        "Return ONLY the JSON array, no other text."
                    ),
                ),
                LLMMessage(
                    role="user",
                    content=f"Extract entities from:\n\n{event.content}",
                ),
            ],
            json_mode=True,
            temperature=0.1,
            purpose="entity_extraction",
        )

        try:
            raw = json.loads(response.content)
            # Handle both {"entities": [...]} and direct [...] formats
            entities_data = raw if isinstance(raw, list) else raw.get("entities", [])
            return [
                Entity(
                    name=e.get("name", ""),
                    type=e.get("type", "other"),
                    confidence=e.get("confidence", 0.8),
                )
                for e in entities_data
                if e.get("name")
            ]
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("context.entity_extraction_failed", error=str(e))
            return list(event.entities)  # Fall back to any pre-existing entities

    async def _resolve_entities(
        self, entities: list[Entity], world_model: object
    ) -> list[ResolvedEntity]:
        """Resolve extracted entities against the world model.

        V1: Simple wrapping — no actual resolution against world model yet.
        Phase 1 will implement full resolution with fuzzy matching.
        """
        return [
            ResolvedEntity(entity=entity, resolution_confidence=entity.confidence)
            for entity in entities
        ]

    async def _gather_context(
        self,
        event: ThiraEvent,
        resolved: list[ResolvedEntity],
        world_model: object,
    ) -> list[ContextItem]:
        """Gather related context from the world model.

        V1: Returns empty list — Phase 1 will query world model for related items.
        """
        return []

    async def _retrieve_experiences(self, event: ThiraEvent) -> list[ExperienceSummary]:
        """Retrieve similar past experiences from ECHO.

        V1: Returns empty list — Phase 1 will implement semantic search.
        """
        return []

    async def _interpret(
        self,
        event: ThiraEvent,
        entities: list[ResolvedEntity],
        context: list[ContextItem],
    ) -> str:
        """Generate a natural language interpretation of the event."""
        entity_names = [e.entity.name for e in entities]

        response = await self._llm.complete(
            messages=[
                LLMMessage(
                    role="system",
                    content=(
                        "You are a contextual analysis engine. Given an event and extracted entities, "
                        "provide a concise interpretation of what this event means and what action "
                        "might be needed. Be specific and actionable. 2-3 sentences max."
                    ),
                ),
                LLMMessage(
                    role="user",
                    content=(
                        f"Event source: {event.source.value}\n"
                        f"Event type: {event.type.value}\n"
                        f"Content: {event.content}\n"
                        f"Entities: {', '.join(entity_names)}\n"
                        f"Actor: {event.actor or 'unknown'}"
                    ),
                ),
            ],
            temperature=0.3,
            max_tokens=200,
            purpose="event_interpretation",
        )

        return response.content.strip()

    async def _suggest_priority(
        self, event: ThiraEvent, context: list[ContextItem]
    ) -> EventPriority:
        """Suggest priority based on event content and context.

        V1: Use the event's existing priority. Phase 1 will use LLM + context.
        """
        return event.priority
