"""ThiraEvent — The universal event schema.

Every input to THIRA, regardless of source, is normalized into a ThiraEvent.
This is the single data contract between the Perception Engine and the rest of the system.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from shared.enums import EventPriority, EventSource, EventType


class Entity(BaseModel):
    """An entity extracted from an event (person, project, deadline, document, etc.)."""

    name: str
    type: str  # "person", "project", "deadline", "document", "organization", etc.
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    metadata: dict = Field(default_factory=dict)


class ThiraEvent(BaseModel):
    """The universal event schema — all inputs normalize to this.

    This is the fundamental data unit that flows through the THIRA loop.
    The Perception Engine produces ThiraEvents; every downstream engine consumes them.
    """

    id: UUID = Field(default_factory=uuid4)
    source: EventSource
    type: EventType
    timestamp: datetime
    actor: str | None = None  # Who/what triggered this event
    content: str  # Human-readable content
    raw_data: dict = Field(default_factory=dict)  # Original payload from source
    entities: list[Entity] = Field(default_factory=list)
    related_events: list[UUID] = Field(default_factory=list)
    priority: EventPriority = EventPriority.MEDIUM
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict = Field(default_factory=dict)

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "source": "gmail",
                "type": "message_received",
                "timestamp": "2026-09-18T10:30:00Z",
                "actor": "client@example.com",
                "content": "Please send the revised proposal by 5 PM.",
                "entities": [
                    {"name": "Proposal", "type": "document", "confidence": 0.95},
                    {"name": "5 PM deadline", "type": "deadline", "confidence": 0.92},
                ],
                "priority": "high",
                "confidence": 0.94,
            }
        }
    }


class ContextItem(BaseModel):
    """A piece of contextual information retrieved by the Context Engine."""

    source: str  # "calendar", "email_thread", "world_model", "echo"
    content: str
    relevance: float = Field(ge=0.0, le=1.0, default=1.0)
    timestamp: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class ResolvedEntity(BaseModel):
    """An entity that has been resolved against the World Model."""

    entity: Entity
    world_entity_id: UUID | None = None  # Link to world_entities table
    resolution_confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    related_entities: list[UUID] = Field(default_factory=list)


class WorldSnapshot(BaseModel):
    """A relevant slice of the World Model state at a point in time."""

    entities: list[dict] = Field(default_factory=list)
    relationships: list[dict] = Field(default_factory=list)
    active_tasks: list[dict] = Field(default_factory=list)
    upcoming_deadlines: list[dict] = Field(default_factory=list)


class ExperienceSummary(BaseModel):
    """Summary of a past experience from ECHO, used during context enrichment."""

    experience_id: UUID
    context_summary: str
    decision_summary: str
    outcome_summary: str
    success: bool
    similarity: float = Field(ge=0.0, le=1.0)
    learnings: list[str] = Field(default_factory=list)


class EnrichedEvent(BaseModel):
    """Event after context enrichment — the full picture THIRA uses to decide.

    Produced by the Context Engine, consumed by the Decision Engine.
    """

    event: ThiraEvent
    resolved_entities: list[ResolvedEntity] = Field(default_factory=list)
    related_context: list[ContextItem] = Field(default_factory=list)
    world_model_snapshot: WorldSnapshot = Field(default_factory=WorldSnapshot)
    echo_matches: list[ExperienceSummary] = Field(default_factory=list)
    suggested_priority: EventPriority = EventPriority.MEDIUM
    interpretation: str = ""  # LLM-generated natural language interpretation
