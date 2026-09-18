"""Integration tests for ECHO Experience and Learning Engine."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from echo.engine import EchoEngine
from shared.enums import DecisionAction, EventSource, EventType, ExecutionStatus, PlanStatus
from shared.events import EnrichedEvent, ThiraEvent
from shared.models import (
    Decision,
    DecisionScores,
    Execution,
    Plan,
    PlanStep,
    StepResult,
    Verification,
)


@pytest.mark.asyncio
async def test_echo_record_and_retrieve(test_db, mock_llm):
    """Test recording an experience with learning extraction and semantic retrieval."""
    # Set mock LLM response for learning extraction
    mock_llm.set_response(
        json.dumps(
            [
                {
                    "insight": "Filesystem operations require path verification",
                    "pattern": "Permission errors occur when directory does not exist",
                    "recommendation": "Check path existence before executing write_file",
                    "confidence": 0.95,
                }
            ]
        )
    )

    echo = EchoEngine(db_session_factory=test_db, llm=mock_llm)

    event = ThiraEvent(
        source=EventSource.USER_COMMAND,
        type=EventType.USER_REQUEST,
        timestamp=datetime.now(UTC),
        content="Create a temporary report file at /tmp/report.txt",
    )
    enriched = EnrichedEvent(
        event=event,
        interpretation="User wants to create a new report file in the filesystem",
    )
    decision = Decision(
        event_id=event.id,
        action=DecisionAction.ACT,
        scores=DecisionScores(urgency=0.7, importance=0.8, confidence=0.9),
        reasoning="User command is actionable and safe",
    )
    plan = Plan(
        decision_id=decision.id,
        goal="Create report file",
        status=PlanStatus.COMPLETED,
        steps=[
            PlanStep(
                index=0,
                description="Write report file",
                agent="filesystem",
                tool="write_file",
                arguments={"path": "/tmp/report.txt", "content": "Sample report"},
            )
        ],
    )
    execution = Execution(
        plan_id=plan.id,
        status=ExecutionStatus.COMPLETED,
        steps_total=1,
        steps_completed=1,
    )
    execution.record_step(
        plan.steps[0],
        StepResult(step_index=0, success=True, output={"message": "File written successfully"}),
    )
    verification = Verification(
        execution_id=execution.id,
        strategy="file_check",
        passed=True,
        summary="Report file created and verified",
    )

    # Record experience
    experience = await echo.record(
        event=event,
        enriched=enriched,
        decision=decision,
        plan=plan,
        execution=execution,
        verification=verification,
    )

    assert experience is not None
    assert experience.event_id == event.id
    assert experience.decision_id == decision.id
    assert experience.success is True
    assert len(experience.learnings) == 1
    assert experience.learnings[0].confidence == 0.95

    # Retrieve similar experiences
    similar = await echo.retrieve_similar(query="Create temporary file in filesystem", k=3)
    assert len(similar) >= 1
    retrieved = similar[0]
    assert retrieved.id == experience.id
    assert retrieved.action_summary == experience.action_summary
    assert retrieved.outcome_summary == experience.outcome_summary
    assert len(retrieved.learnings) == 1
    assert retrieved.learnings[0].insight == "Filesystem operations require path verification"
