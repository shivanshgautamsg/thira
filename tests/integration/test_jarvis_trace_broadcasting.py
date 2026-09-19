"""Integration test verifying JARVIS live trace broadcasting and scenario triggering."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from agents.filesystem import FilesystemAgent
from agents.registry import AgentBus, AgentRegistry
from echo.engine import EchoEngine
from jarvis.app import ConnectionManager, JarvisNotifier, app, set_orchestrator
from shared.enums import EventSource, EventType
from shared.events import ThiraEvent
from thira_core.context.engine import ContextEngine
from thira_core.decision.engine import DecisionEngine
from thira_core.failure.engine import FailureEngine
from thira_core.orchestrator import ThiraOrchestrator
from thira_core.perception.engine import PerceptionEngine
from thira_core.planning.engine import PlanningEngine
from thira_core.policy.engine import PolicyEngine
from thira_core.verification.engine import VerificationEngine
from thira_core.world_model.model import WorldModel


class TraceTestingLLM:
    """Mock LLM producing deterministic plans and decisions."""

    async def complete(self, messages, **kwargs):
        purpose = kwargs.get("purpose", "")
        if purpose == "decision_scoring":
            return type(
                "Resp",
                (),
                {
                    "content": json.dumps(
                        {
                            "action": "act",
                            "urgency": 0.8,
                            "importance": 0.9,
                            "risk": 0.1,
                            "opportunity": 0.5,
                            "effort": 0.2,
                            "confidence": 0.95,
                            "reversibility": 0.9,
                            "dependency": 0.0,
                            "reasoning": "Executive morning briefing requires prompt schedule review",
                        }
                    )
                },
            )()
        elif purpose == "plan_generation":
            return type(
                "Resp",
                (),
                {
                    "content": json.dumps(
                        {
                            "goal": "Generate executive briefing",
                            "requires_approval": False,
                            "steps": [
                                {
                                    "description": "List directory contents for briefing",
                                    "agent": "filesystem",
                                    "tool": "list_directory",
                                    "arguments": {"path": "."},
                                    "depends_on": [],
                                }
                            ],
                        }
                    )
                },
            )()
        elif purpose == "learning_extraction":
            return type(
                "Resp",
                (),
                {
                    "content": json.dumps(
                        [
                            {
                                "pattern": "Morning briefing pattern",
                                "insight": "Executive briefings are most useful when delivered before 9 AM",
                                "applicability": "Executive workflows",
                            }
                        ]
                    )
                },
            )()
        return type("Resp", (), {"content": "{}"})()

    async def embed(self, text: str) -> list[float]:
        return [0.05] * 1536


@pytest.mark.asyncio
async def test_trace_broadcasting_during_orchestrator_loop(test_db, in_memory_bus):
    """Verify that the orchestrator loop emits structured trace events to JarvisNotifier."""
    mock_llm = TraceTestingLLM()
    perception = PerceptionEngine(event_bus=in_memory_bus)
    context = ContextEngine(llm=mock_llm)
    world_model = WorldModel(db_session_factory=test_db)
    decision = DecisionEngine(llm=mock_llm)
    planning = PlanningEngine(llm=mock_llm)
    policy = PolicyEngine()
    verification = VerificationEngine()
    failure = FailureEngine()
    echo = EchoEngine(db_session_factory=test_db, llm=mock_llm)

    registry = AgentRegistry()
    fs_agent = FilesystemAgent()
    await registry.register(fs_agent)
    agent_bus = AgentBus(registry=registry)

    # Capture all trace events emitted by the orchestrator
    traces_captured: list[dict] = []

    class CapturingConnectionManager(ConnectionManager):
        async def broadcast(self, message: dict):
            traces_captured.append(message)

    capturing_manager = CapturingConnectionManager()
    jarvis_notifier = JarvisNotifier(connection_manager=capturing_manager)

    orchestrator = ThiraOrchestrator(
        perception=perception,
        context=context,
        world_model=world_model,
        decision=decision,
        planning=planning,
        policy=policy,
        agent_bus=agent_bus,
        verification=verification,
        failure=failure,
        echo=echo,
        jarvis=jarvis_notifier,
    )
    set_orchestrator(orchestrator)

    # 1. Run event through orchestrator
    event = ThiraEvent(
        source=EventSource.USER_COMMAND,
        type=EventType.USER_REQUEST,
        timestamp=datetime.now(UTC),
        actor="user",
        content="Prepare morning briefing",
    )

    result = await orchestrator.process_event(event)
    assert result.status == "completed"

    # 2. Verify all trace lifecycle stages were broadcasted
    stages_broadcasted = [t["stage"] for t in traces_captured if t.get("type") == "trace"]
    assert "perception" in stages_broadcasted
    assert "context" in stages_broadcasted
    assert "decision" in stages_broadcasted
    assert "plan" in stages_broadcasted
    assert "step_result" in stages_broadcasted
    assert "verification" in stages_broadcasted
    assert "echo" in stages_broadcasted

    # 3. Test triggering demo scenario endpoint via REST API
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/scenarios/demo/morning_briefing")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert "trace_id" in data
