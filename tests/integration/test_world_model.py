"""Integration tests for the World Model CRUD operations."""

from __future__ import annotations

import uuid

import pytest

from shared.enums import ExecutionStatus
from shared.models import Execution, Verification
from thira_core.world_model.model import WorldModel


@pytest.mark.asyncio
async def test_world_model_entity_lifecycle(test_db):
    """Test full CRUD lifecycle for world entities."""
    wm = WorldModel(db_session_factory=test_db)

    # 1. CREATE
    entity_id = await wm.add_entity(
        name="Project Alpha",
        type="project",
        state={"status": "in_progress", "priority": "high"},
    )
    assert isinstance(entity_id, uuid.UUID)

    # 2. READ
    entity = await wm.get_entity(entity_id)
    assert entity is not None
    assert entity["name"] == "Project Alpha"
    assert entity["type"] == "project"
    assert entity["state"]["priority"] == "high"

    # Find by name
    found = await wm.find_entity("Project Alpha")
    assert found is not None
    assert found["id"] == str(entity_id)

    # List by type
    projects = await wm.get_entities_by_type("project")
    assert len(projects) == 1
    assert projects[0]["id"] == str(entity_id)

    # 3. UPDATE
    updated = await wm.update_entity(
        entity_id,
        name="Project Alpha V2",
        state={"status": "completed"},
    )
    assert updated is True

    entity_after = await wm.get_entity(entity_id)
    assert entity_after["name"] == "Project Alpha V2"
    assert entity_after["state"]["status"] == "completed"
    assert entity_after["state"]["priority"] == "high"  # Merged state

    # 4. DELETE
    deleted = await wm.delete_entity(entity_id)
    assert deleted is True

    entity_deleted = await wm.get_entity(entity_id)
    assert entity_deleted is None


@pytest.mark.asyncio
async def test_world_model_relationships(test_db):
    """Test creating, querying, and deleting relationships between entities."""
    wm = WorldModel(db_session_factory=test_db)

    # Create two entities
    user_entity = await wm.add_entity(name="Alice", type="person", state={"role": "engineer"})
    proj_entity = await wm.add_entity(name="Compiler Project", type="project")

    # Add relationship
    rel_id = await wm.add_relationship(
        source_id=user_entity,
        target_id=proj_entity,
        relationship="contributes_to",
        weight=0.9,
    )
    assert isinstance(rel_id, uuid.UUID)

    # Query related entities
    related = await wm.get_related_entities(user_entity)
    assert len(related) == 1
    assert related[0]["name"] == "Compiler Project"
    assert related[0]["relationship"] == "contributes_to"
    assert related[0]["weight"] == 0.9

    # Delete relationship
    del_res = await wm.delete_relationship(rel_id)
    assert del_res is True

    related_after = await wm.get_related_entities(user_entity)
    assert len(related_after) == 0


@pytest.mark.asyncio
async def test_world_model_snapshot_and_execution_update(test_db):
    """Test snapshot export and applying execution results."""
    wm = WorldModel(db_session_factory=test_db)

    e1 = await wm.add_entity(name="Task 1", type="task")
    e2 = await wm.add_entity(name="Task 2", type="task")
    await wm.add_relationship(e1, e2, "depends_on")

    snapshot = await wm.get_snapshot()
    assert snapshot["entities_count"] == 2
    assert snapshot["relationships_count"] == 1

    # Apply execution
    exec_record = Execution(plan_id=uuid.uuid4(), status=ExecutionStatus.COMPLETED)
    verification = Verification(
        execution_id=exec_record.id,
        strategy="state_check",
        passed=True,
        summary="All verified",
    )
    await wm.apply_execution(exec_record, verification)
