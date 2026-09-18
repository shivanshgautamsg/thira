"""Audit trail — records every action THIRA takes for explainability and trust."""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from sqlalchemy import insert

from shared.db.models import AuditLogModel

logger = structlog.get_logger()


class AuditTrail:
    """Records every action for compliance, debugging, and trust.

    Every tool invocation, every policy decision, every approval
    flows through the audit trail.
    """

    def __init__(self, db_session_factory):
        self._session_factory = db_session_factory

    async def record(
        self,
        *,
        action: str,
        agent: str | None = None,
        tool: str | None = None,
        arguments: dict | None = None,
        result_summary: str | None = None,
        policy_verdict: str | None = None,
        user_id: uuid.UUID | None = None,
        approval_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Record an audit entry.

        Returns:
            The audit record ID.
        """
        record_id = uuid.uuid4()

        async with self._session_factory() as session:
            await session.execute(
                insert(AuditLogModel).values(
                    id=record_id,
                    user_id=user_id,
                    action=action,
                    agent=agent,
                    tool=tool,
                    arguments=arguments or {},
                    result_summary=result_summary,
                    policy_verdict=policy_verdict,
                    approval_id=approval_id,
                    timestamp=datetime.utcnow(),
                )
            )
            await session.commit()

        logger.info(
            "audit.recorded",
            record_id=str(record_id),
            action=action,
            agent=agent,
            tool=tool,
            verdict=policy_verdict,
        )

        return record_id
