"""Integration tests for the human-in-the-loop approval flow (JARVIS <-> THIRA)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from agents.registry import AgentBus, AgentRegistry
from agents.terminal import TerminalAgent
from echo.engine import EchoEngine
from jarvis.app import ConnectionManager, JarvisNotifier, app, set_orchestrator
from shared.enums import (
    EventSource,
    EventType,
    RiskLevel,
)
from shared.events import ThiraEvent
from shared.models import (
    ToolAnnotation,
)
from thira_core.context.engine import ContextEngine
from thira_core.decision.engine import DecisionEngine
from thira_core.failure.engine import FailureEngine
from thira_core.orchestrator import ThiraOrchestrator
from thira_core.perception.engine import PerceptionEngine
from thira_core.planning.engine import PlanningEngine
from thira_core.policy.engine import PolicyEngine
from thira_core.verification.engine import VerificationEngine
from thira_core.world_model.model import WorldModel


@pytest.mark.asyncio
async def test_approval_flow_roundtrip(test_db, mock_llm, in_memory_bus):
    """Test full approval cycle: plan requires approval -> approve -> execution completes."""
    # Setup engines
    perception = PerceptionEngine(event_bus=in_memory_bus)
    context = ContextEngine(llm=mock_llm)
    world_model = WorldModel(db_session_factory=test_db)
    decision_engine = DecisionEngine(llm=mock_llm)
    planning = PlanningEngine(llm=mock_llm)
    policy = PolicyEngine()
    verification = VerificationEngine()
    failure = FailureEngine()
    echo = EchoEngine(db_session_factory=test_db, llm=mock_llm)

    registry = AgentRegistry()
    await registry.register(TerminalAgent())
    agent_bus = AgentBus(registry=registry)

    # Register high-risk annotation for a tool so policy demands approval
    policy.register_tool_annotations(
        agent="terminal",
        tool="execute_command",
        annotations=ToolAnnotation(
            risk_level=RiskLevel.HIGH,
            requires_approval=True,
            description="High risk command",
        ),
    )

    manager = ConnectionManager()
    jarvis_notifier = JarvisNotifier(connection_manager=manager)

    orchestrator = ThiraOrchestrator(
        perception=perception,
        context=context,
        world_model=world_model,
        decision=decision_engine,
        planning=planning,
        policy=policy,
        agent_bus=agent_bus,
        verification=verification,
        failure=failure,
        echo=echo,
        jarvis=jarvis_notifier,
    )
    set_orchestrator(orchestrator)

    # Setup LLM mock for planning a high-risk step
    mock_llm.set_response(
        json.dumps(
            {
                "goal": "Run high risk deployment command",
                "requires_approval": True,
                "steps": [
                    {
                        "description": "Echo deploy test",
                        "agent": "terminal",
                        "tool": "execute_command",
                        "arguments": {"command": "echo deployment_ok"},
                        "depends_on": [],
                    }
                ],
            }
        )
    )

    event = ThiraEvent(
        source=EventSource.USER_COMMAND,
        type=EventType.USER_REQUEST,
        timestamp=datetime.now(UTC),
        content="Deploy the production service",
    )

    # 1. Process event -> should halt at awaiting_approval
    result = await orchestrator.process_event(event)
    assert result.status == "awaiting_approval"
    plan_id = result.plan_id
    assert plan_id is not None
    assert plan_id in orchestrator._pending_approvals

    # 2. Test rejection flow first with another event
    rej_event = ThiraEvent(
        source=EventSource.USER_COMMAND,
        type=EventType.USER_REQUEST,
        timestamp=datetime.now(UTC),
        content="Deploy staging",
    )
    rej_result = await orchestrator.process_event(rej_event)
    rej_plan_id = rej_result.plan_id
    assert rej_plan_id in orchestrator._pending_approvals

    rej_response = await orchestrator.handle_approval(rej_plan_id, approved=False)
    assert rej_response.status == "rejected"
    assert rej_plan_id not in orchestrator._pending_approvals

    # 3. Test approval via JARVIS REST API endpoint
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/approve/{plan_id}?approved=true")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["plan_id"] == str(plan_id)

    # 4. Verify plan is no longer pending
    assert plan_id not in orchestrator._pending_approvals
