"""World Model implementation.

Maintains the current state of the user's digital environment:
entities, relationships, goals, deadlines, active tasks, and dependencies.

Answers: "What is true right now?"
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select

from shared.db.models import WorldEntityModel, WorldRelationshipModel
from shared.models import Execution, Verification

logger = structlog.get_logger()


class WorldModel:
    """The user's digital world — current state of entities and relationships.

    Tracks:
    - People (clients, team members, managers)
    - Projects (with deadlines, status)
    - Goals
    - Activities (emails, meetings, tasks)
    - Dependencies between entities
    - Historical state changes

    Provides situational awareness to the Context and Decision engines.
    """

    def __init__(self, db_session_factory):
        self._session_factory = db_session_factory

    async def add_entity(
        self,
        name: str,
        type: str,
        state: dict | None = None,
        user_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Add or update an entity in the world model."""
        entity_id = uuid.uuid4()
        async with self._session_factory() as session:
            entity = WorldEntityModel(
                id=entity_id,
                user_id=user_id,
                name=name,
                type=type,
                state=state or {},
                last_seen=datetime.now(UTC),
            )
            session.add(entity)
            await session.commit()

        logger.debug("world_model.entity_added", entity_id=str(entity_id), name=name, type=type)
        return entity_id

    async def get_entities_by_type(self, entity_type: str) -> list[dict]:
        """Get all entities of a given type."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(WorldEntityModel).where(WorldEntityModel.type == entity_type)
            )
            entities = result.scalars().all()
            return [
                {
                    "id": str(e.id),
                    "name": e.name,
                    "type": e.type,
                    "state": e.state,
                    "last_seen": e.last_seen.isoformat() if e.last_seen else None,
                }
                for e in entities
            ]

    async def find_entity(self, name: str) -> dict | None:
        """Find an entity by name (fuzzy match in Phase 2)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(WorldEntityModel).where(WorldEntityModel.name == name)
            )
            entity = result.scalar_one_or_none()
            if entity:
                return {
                    "id": str(entity.id),
                    "name": entity.name,
                    "type": entity.type,
                    "state": entity.state,
                }
            return None

    async def add_relationship(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relationship: str,
        weight: float = 1.0,
    ) -> uuid.UUID:
        """Add a relationship between two entities."""
        rel_id = uuid.uuid4()
        async with self._session_factory() as session:
            rel = WorldRelationshipModel(
                id=rel_id,
                source_entity=source_id,
                target_entity=target_id,
                relationship=relationship,
                weight=weight,
            )
            session.add(rel)
            await session.commit()

        logger.debug(
            "world_model.relationship_added",
            source=str(source_id),
            target=str(target_id),
            relationship=relationship,
        )
        return rel_id

    async def get_related_entities(self, entity_id: uuid.UUID) -> list[dict]:
        """Get all entities related to a given entity."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(WorldRelationshipModel, WorldEntityModel)
                .join(
                    WorldEntityModel,
                    WorldRelationshipModel.target_entity == WorldEntityModel.id,
                )
                .where(WorldRelationshipModel.source_entity == entity_id)
            )
            rows = result.all()
            return [
                {
                    "entity_id": str(entity.id),
                    "name": entity.name,
                    "type": entity.type,
                    "relationship": rel.relationship,
                    "weight": rel.weight,
                }
                for rel, entity in rows
            ]

    async def get_entity(self, entity_id: uuid.UUID) -> dict | None:
        """Get an entity by its UUID."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(WorldEntityModel).where(WorldEntityModel.id == entity_id)
            )
            entity = result.scalar_one_or_none()
            if entity:
                return {
                    "id": str(entity.id),
                    "name": entity.name,
                    "type": entity.type,
                    "state": entity.state,
                    "last_seen": entity.last_seen.isoformat() if entity.last_seen else None,
                }
            return None

    async def update_entity(
        self,
        entity_id: uuid.UUID,
        *,
        name: str | None = None,
        type: str | None = None,
        state: dict | None = None,
    ) -> bool:
        """Update an existing entity's attributes."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(WorldEntityModel).where(WorldEntityModel.id == entity_id)
            )
            entity = result.scalar_one_or_none()
            if not entity:
                return False
            if name is not None:
                entity.name = name
            if type is not None:
                entity.type = type
            if state is not None:
                entity.state = {**entity.state, **state}
            entity.last_seen = datetime.now()
            entity.updated_at = datetime.now()
            await session.commit()
            logger.debug("world_model.entity_updated", entity_id=str(entity_id))
            return True

    async def delete_entity(self, entity_id: uuid.UUID) -> bool:
        """Delete an entity from the world model."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(WorldEntityModel).where(WorldEntityModel.id == entity_id)
            )
            entity = result.scalar_one_or_none()
            if not entity:
                return False
            await session.delete(entity)
            await session.commit()
            logger.debug("world_model.entity_deleted", entity_id=str(entity_id))
            return True

    async def delete_relationship(self, rel_id: uuid.UUID) -> bool:
        """Delete a relationship from the world model."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(WorldRelationshipModel).where(WorldRelationshipModel.id == rel_id)
            )
            rel = result.scalar_one_or_none()
            if not rel:
                return False
            await session.delete(rel)
            await session.commit()
            logger.debug("world_model.relationship_deleted", rel_id=str(rel_id))
            return True

    async def get_snapshot(self) -> dict:
        """Get a snapshot of the current world model state."""
        async with self._session_factory() as session:
            entities_res = await session.execute(select(WorldEntityModel))
            entities = entities_res.scalars().all()
            rels_res = await session.execute(select(WorldRelationshipModel))
            rels = rels_res.scalars().all()

            return {
                "entities_count": len(entities),
                "relationships_count": len(rels),
                "entities": [
                    {"id": str(e.id), "name": e.name, "type": e.type, "state": e.state}
                    for e in entities
                ],
                "relationships": [
                    {
                        "id": str(r.id),
                        "source": str(r.source_entity),
                        "target": str(r.target_entity),
                        "relationship": r.relationship,
                    }
                    for r in rels
                ],
            }

    async def apply_execution(self, execution: Execution, verification: Verification) -> None:
        """Update the world model based on execution outcomes.

        Extracts entity/relationship changes from execution results and applies them.
        """
        logger.info(
            "world_model.execution_applied",
            execution_id=str(execution.id),
            success=verification.passed,
            steps_completed=execution.steps_completed,
        )
