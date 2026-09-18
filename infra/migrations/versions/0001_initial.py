"""Initial migration creating all THIRA tables.

Revision ID: 0001
Revises:
Create Date: 2026-09-18 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # 1. users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("preferences", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 2. events
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("raw_data", postgresql.JSONB(), server_default="{}"),
        sa.Column("entities", postgresql.JSONB(), server_default="[]"),
        sa.Column("priority", sa.String(), server_default="medium"),
        sa.Column("confidence", sa.Float(), server_default="1.0"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
    )
    op.create_index("idx_events_source", "events", ["source"])
    op.create_index("idx_events_type", "events", ["type"])
    op.create_index("idx_events_timestamp", "events", ["timestamp"])
    op.create_index("idx_events_priority", "events", ["priority"])

    # 3. world_entities
    op.create_table(
        "world_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("state", postgresql.JSONB(), server_default="{}"),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_world_entities_type", "world_entities", ["type"])
    op.create_index("idx_world_entities_user", "world_entities", ["user_id"])

    # 4. world_relationships
    op.create_table(
        "world_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_entity", postgresql.UUID(as_uuid=True), sa.ForeignKey("world_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_entity", postgresql.UUID(as_uuid=True), sa.ForeignKey("world_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship", sa.String(), nullable=False),
        sa.Column("weight", sa.Float(), server_default="1.0"),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_entity", "target_entity", "relationship"),
    )
    op.create_index("idx_relationships_source", "world_relationships", ["source_entity"])
    op.create_index("idx_relationships_target", "world_relationships", ["target_entity"])

    # 5. decisions
    op.create_table(
        "decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("urgency", sa.Float(), nullable=True),
        sa.Column("importance", sa.Float(), nullable=True),
        sa.Column("opportunity", sa.Float(), nullable=True),
        sa.Column("effort", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("risk", sa.Float(), nullable=True),
        sa.Column("reversibility", sa.Float(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 6. plans
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("decisions.id"), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), server_default="pending"),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 7. executions
    op.create_table(
        "executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("status", sa.String(), server_default="running"),
        sa.Column("steps_completed", sa.Integer(), server_default="0"),
        sa.Column("steps_total", sa.Integer(), nullable=False),
        sa.Column("results", postgresql.JSONB(), server_default="[]"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )

    # 8. execution_steps
    op.create_table(
        "execution_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("agent", sa.String(), nullable=False),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("arguments", postgresql.JSONB(), server_default="{}"),
        sa.Column("result", postgresql.JSONB(), server_default="{}"),
        sa.Column("status", sa.String(), server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )

    # 9. autonomy_policies
    op.create_table(
        "autonomy_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("agent", sa.String(), nullable=False),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("autonomy_level", sa.Integer(), nullable=False),
        sa.Column("conditions", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 10. audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("agent", sa.String(), nullable=True),
        sa.Column("tool", sa.String(), nullable=True),
        sa.Column("arguments", postgresql.JSONB(), server_default="{}"),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("policy_verdict", sa.String(), nullable=True),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_audit_log_user", "audit_log", ["user_id"])
    op.create_index("idx_audit_log_timestamp", "audit_log", ["timestamp"])

    # 11. experiences
    op.create_table(
        "experiences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=True),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("decisions.id"), nullable=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plans.id"), nullable=True),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("executions.id"), nullable=True),
        sa.Column("context_summary", sa.Text(), nullable=False),
        sa.Column("decision_summary", sa.Text(), nullable=False),
        sa.Column("action_summary", sa.Text(), nullable=False),
        sa.Column("outcome_summary", sa.Text(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("learnings", postgresql.JSONB(), server_default="[]"),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_experiences_user", "experiences", ["user_id"])

    # 12. verifications
    op.create_table(
        "verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("executions.id"), nullable=False),
        sa.Column("strategy", sa.String(), nullable=False),
        sa.Column("expected", postgresql.JSONB(), nullable=True),
        sa.Column("actual", postgresql.JSONB(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("evidence_path", sa.String(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("verifications")
    op.drop_table("experiences")
    op.drop_table("audit_log")
    op.drop_table("autonomy_policies")
    op.drop_table("execution_steps")
    op.drop_table("executions")
    op.drop_table("plans")
    op.drop_table("decisions")
    op.drop_table("world_relationships")
    op.drop_table("world_entities")
    op.drop_table("events")
    op.drop_table("users")
