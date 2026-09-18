"""Unit tests for shared event schemas and models."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from shared.enums import (
    AutonomyLevel,
    DecisionAction,
    EventPriority,
    EventSource,
    EventType,
    RiskLevel,
)
from shared.events import Entity, ThiraEvent
from shared.models import (
    Decision,
    DecisionScores,
    Execution,
    Experience,
    Learning,
    Plan,
    PlanStep,
    StepResult,
    ToolAnnotation,
)


class TestThiraEvent:
    def test_create_event(self):
        event = ThiraEvent(
            source=EventSource.USER_COMMAND,
            type=EventType.USER_REQUEST,
            timestamp=datetime.utcnow(),
            content="Hello THIRA",
        )
        assert event.source == EventSource.USER_COMMAND
        assert event.priority == EventPriority.MEDIUM  # default
        assert event.confidence == 1.0  # default

    def test_event_with_entities(self):
        event = ThiraEvent(
            source=EventSource.GMAIL,
            type=EventType.MESSAGE_RECEIVED,
            timestamp=datetime.utcnow(),
            actor="client@example.com",
            content="Send the proposal",
            entities=[
                Entity(name="Proposal", type="document", confidence=0.95),
                Entity(name="Client", type="person", confidence=0.9),
            ],
        )
        assert len(event.entities) == 2
        assert event.entities[0].name == "Proposal"

    def test_event_serialization(self):
        event = ThiraEvent(
            source=EventSource.GMAIL,
            type=EventType.MESSAGE_RECEIVED,
            timestamp=datetime.utcnow(),
            content="Test",
        )
        json_str = event.model_dump_json()
        restored = ThiraEvent.model_validate_json(json_str)
        assert restored.source == event.source
        assert restored.content == event.content


class TestDecision:
    def test_create_decision(self):
        decision = Decision(
            event_id=uuid4(),
            action=DecisionAction.ACT,
            scores=DecisionScores(urgency=0.9, importance=0.8),
            reasoning="High priority client request",
        )
        assert decision.action == DecisionAction.ACT
        assert decision.scores.urgency == 0.9

    def test_default_scores(self):
        scores = DecisionScores()
        assert scores.urgency == 0.5
        assert scores.dependency == 0.0


class TestPlan:
    def test_create_plan(self):
        plan = Plan(
            decision_id=uuid4(),
            goal="Send proposal email",
            steps=[
                PlanStep(index=0, description="Read file", agent="filesystem", tool="read_file"),
                PlanStep(
                    index=1,
                    description="Send email",
                    agent="gmail",
                    tool="send_email",
                    depends_on=[0],
                ),
            ],
        )
        assert len(plan.steps) == 2
        assert plan.steps[1].depends_on == [0]


class TestExecution:
    def test_record_steps(self):
        execution = Execution(plan_id=uuid4())
        step = PlanStep(index=0, description="Test", agent="test", tool="test")
        result = StepResult(step_index=0, success=True, output={"data": "ok"})

        execution.record_step(step, result)
        assert execution.steps_completed == 1
        assert execution.steps_failed == 0


class TestToolAnnotation:
    def test_defaults(self):
        ann = ToolAnnotation()
        assert ann.autonomy_level == AutonomyLevel.L3_EXECUTE_APPROVED
        assert ann.reversible is True
        assert ann.risk == RiskLevel.LOW

    def test_high_risk(self):
        ann = ToolAnnotation(risk=RiskLevel.CRITICAL, reversible=False)
        assert ann.risk == RiskLevel.CRITICAL


class TestExperience:
    def test_create_experience(self):
        exp = Experience(
            event_id=uuid4(),
            decision_id=uuid4(),
            context_summary="Client requested proposal",
            decision_summary="Prioritize immediately",
            action_summary="Updated and sent proposal",
            outcome_summary="Client accepted",
            success=True,
            learnings=[
                Learning(
                    insight="Client values speed",
                    pattern="Urgent requests from this client",
                    recommendation="Always prioritize same-day",
                    confidence=0.9,
                ),
            ],
        )
        assert exp.success is True
        assert len(exp.learnings) == 1
