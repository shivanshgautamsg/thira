"""SQLAlchemy ORM models for the THIRA database.

These map to the PostgreSQL tables defined in the database schema.
Used by Alembic for migrations and by engines for data access.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")
UUID_TYPE = Uuid().with_variant(UUID(as_uuid=True), "postgresql")
VECTOR_TYPE = JSON().with_variant(Vector(1536), "postgresql")


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class EventModel(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[str | None] = mapped_column(String, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSON_TYPE, default=dict)
    entities: Mapped[list] = mapped_column(JSON_TYPE, default=list)
    priority: Mapped[str] = mapped_column(String, default="medium")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON_TYPE, default=dict)

    __table_args__ = (
        Index("idx_events_source", "source"),
        Index("idx_events_type", "type"),
        Index("idx_events_timestamp", "timestamp"),
        Index("idx_events_priority", "priority"),
    )


class WorldEntityModel(Base):
    __tablename__ = "world_entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID_TYPE, ForeignKey("users.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[dict] = mapped_column(JSON_TYPE, default=dict)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_world_entities_type", "type"),
        Index("idx_world_entities_user", "user_id"),
    )


class WorldRelationshipModel(Base):
    __tablename__ = "world_relationships"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    source_entity: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("world_entities.id", ondelete="CASCADE"), nullable=False
    )
    target_entity: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("world_entities.id", ondelete="CASCADE"), nullable=False
    )
    relationship: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("source_entity", "target_entity", "relationship"),
        Index("idx_relationships_source", "source_entity"),
        Index("idx_relationships_target", "target_entity"),
    )


class DecisionModel(Base):
    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, ForeignKey("events.id"), nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    urgency: Mapped[float | None] = mapped_column(Float, nullable=True)
    importance: Mapped[float | None] = mapped_column(Float, nullable=True)
    opportunity: Mapped[float | None] = mapped_column(Float, nullable=True)
    effort: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk: Mapped[float | None] = mapped_column(Float, nullable=True)
    reversibility: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class PlanModel(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("decisions.id"), nullable=False
    )
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    steps: Mapped[list] = mapped_column(JSON_TYPE, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ExecutionModel(Base):
    __tablename__ = "executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, ForeignKey("plans.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, default="running")
    steps_completed: Mapped[int] = mapped_column(Integer, default=0)
    steps_total: Mapped[int] = mapped_column(Integer, nullable=False)
    results: Mapped[list] = mapped_column(JSON_TYPE, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExecutionStepModel(Base):
    __tablename__ = "execution_steps"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("executions.id", ondelete="CASCADE"), nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    agent: Mapped[str] = mapped_column(String, nullable=False)
    tool: Mapped[str] = mapped_column(String, nullable=False)
    arguments: Mapped[dict] = mapped_column(JSON_TYPE, default=dict)
    result: Mapped[dict] = mapped_column(JSON_TYPE, default=dict)
    status: Mapped[str] = mapped_column(String, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AutonomyPolicyModel(Base):
    __tablename__ = "autonomy_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, ForeignKey("users.id"), nullable=False)
    agent: Mapped[str] = mapped_column(String, nullable=False)
    tool: Mapped[str] = mapped_column(String, nullable=False)
    autonomy_level: Mapped[int] = mapped_column(Integer, nullable=False)
    conditions: Mapped[dict] = mapped_column(JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class AuditLogModel(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID_TYPE, ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    agent: Mapped[str | None] = mapped_column(String, nullable=True)
    tool: Mapped[str | None] = mapped_column(String, nullable=True)
    arguments: Mapped[dict] = mapped_column(JSON_TYPE, default=dict)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_verdict: Mapped[str | None] = mapped_column(String, nullable=True)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID_TYPE, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_audit_log_user", "user_id"),
        Index("idx_audit_log_timestamp", timestamp.desc()),
    )


class ExperienceModel(Base):
    __tablename__ = "experiences"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID_TYPE, ForeignKey("users.id"), nullable=True
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID_TYPE, ForeignKey("events.id"), nullable=True
    )
    decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID_TYPE, ForeignKey("decisions.id"), nullable=True
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID_TYPE, ForeignKey("plans.id"), nullable=True
    )
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID_TYPE, ForeignKey("executions.id"), nullable=True
    )

    context_summary: Mapped[str] = mapped_column(Text, nullable=False)
    decision_summary: Mapped[str] = mapped_column(Text, nullable=False)
    action_summary: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_summary: Mapped[str] = mapped_column(Text, nullable=False)
    success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    learnings: Mapped[list] = mapped_column(JSON_TYPE, default=list)

    # pgvector embedding for semantic retrieval (1536 = OpenAI text-embedding-3-small)
    embedding = mapped_column(VECTOR_TYPE, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (Index("idx_experiences_user", "user_id"),)


class VerificationModel(Base):
    __tablename__ = "verifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("executions.id"), nullable=False
    )
    strategy: Mapped[str] = mapped_column(String, nullable=False)
    expected: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    actual: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evidence_path: Mapped[str | None] = mapped_column(String, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
