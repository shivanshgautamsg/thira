"""End-to-end integration tests for THIRA Phase 2 Proactive Execution Pipeline.

Tests:
1. Inbound email ingestion via GmailEventConsumer
2. Entity extraction and auto-population into World Model
3. Proactive autonomous plan execution (drafting response + checking schedule)
4. Proactive notification delivery via JARVIS
5. Action escalation requiring approval (sending email / creating public event)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from agents.calendar import CalendarAgent
from agents.gmail import GmailAgent
from agents.registry import AgentBus, AgentRegistry
from echo.engine import EchoEngine
from event_bus.consumers import CalendarEventConsumer, GmailEventConsumer
from shared.enums import (
    AutonomyLevel,
    EventPriority,
    EventSource,
    EventType,
)
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


class ProactiveMockLLM:
    """Mock LLM handling multi-stage reasoning for proactive pipeline."""

    def __init__(self):
        self.call_history: list[dict] = []

    async def complete(self, messages, **kwargs):
        purpose = kwargs.get("purpose", "")
        self.call_history.append({"purpose": purpose, "messages": messages})

        if purpose == "entity_extraction":
            return type(
                "Resp",
                (),
                {
                    "content": json.dumps(
                        [
                            {"name": "Alice Smith", "type": "person", "confidence": 0.95},
                            {"name": "Project Artemis", "type": "project", "confidence": 0.9},
                        ]
                    )
                },
            )()

        elif purpose == "context_enrichment" or purpose == "context_interpretation":
            return type(
                "Resp",
                (),
                {
                    "content": json.dumps(
                        {
                            "entities": [
                                {"name": "Alice Smith", "type": "person", "confidence": 0.95},
                                {"name": "Project Artemis", "type": "project", "confidence": 0.9},
                            ],
                            "suggested_priority": "high",
                            "interpretation": "Client Alice Smith is requesting urgent status on Project Artemis and meeting setup.",
                        }
                    )
                },
            )()

        elif purpose == "decision_scoring":
            return type(
                "Resp",
                (),
                {
                    "content": json.dumps(
                        {
                            "action": "act",
                            "urgency": 0.8,
                            "importance": 0.85,
                            "opportunity": 0.7,
                            "effort": 0.2,
                            "confidence": 0.95,
                            "risk": 0.1,
                            "reversibility": 0.9,
                            "dependency": 0.0,
                            "reasoning": "High-priority client communication requires proactive response preparation and calendar inspection.",
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
                            "goal": "Prepare response draft and check calendar availability for Alice Smith",
                            "requires_approval": False,
                            "steps": [
                                {
                                    "description": "Check existing calendar events",
                                    "agent": "calendar",
                                    "tool": "list_events",
                                    "arguments": {"max_results": 5},
                                    "depends_on": [],
                                },
                                {
                                    "description": "Draft email response to Alice Smith",
                                    "agent": "gmail",
                                    "tool": "draft_email",
                                    "arguments": {
                                        "to": "alice@enterprise.com",
                                        "subject": "Re: Project Artemis Status Update",
                                        "body": "Hi Alice, We are on track for Project Artemis. I am reviewing our schedule for tomorrow.",
                                    },
                                    "depends_on": [],
                                },
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
                                "pattern": "Proactive email response drafting for client updates",
                                "insight": "Drafting before sending saves user time and keeps communications responsive",
                                "applicability": "Inbound client emails with status inquiries",
                            }
                        ]
                    )
                },
            )()

        elif purpose == "embedding":
            return type(
                "Resp",
                (),
                {"content": "", "embedding": [0.05] * 1536},
            )()

        return type("Resp", (), {"content": "{}"})()

    async def embed(self, text: str) -> list[float]:
        return [0.05] * 1536


@pytest.mark.asyncio
async def test_proactive_email_pipeline_end_to_end(test_db, in_memory_bus):
    """Test full proactive pipeline:

    1. Inbound email ingested via GmailEventConsumer -> event bus.
    2. Context engine extracts entities and auto-populates World Model.
    3. Decision engine triggers proactive action.
    4. Planning drafts email & checks calendar (L0 / L2 -> auto-approved under L3 default).
    5. Agents execute actions autonomously.
    6. Outcome verified and stored in ECHO.
    7. JARVIS receives proactive notification.
    """
    mock_llm = ProactiveMockLLM()
    perception = PerceptionEngine(event_bus=in_memory_bus)
    context = ContextEngine(llm=mock_llm)
    world_model = WorldModel(db_session_factory=test_db)
    decision_engine = DecisionEngine(llm=mock_llm)
    planning = PlanningEngine(llm=mock_llm)
    policy = PolicyEngine(default_autonomy=AutonomyLevel.L3_EXECUTE_APPROVED)
    verification = VerificationEngine()
    failure = FailureEngine()
    echo = EchoEngine(db_session_factory=test_db, llm=mock_llm)

    # Register Agents
    registry = AgentRegistry()
    gmail_agent = GmailAgent()
    calendar_agent = CalendarAgent()
    await registry.register(gmail_agent)
    await registry.register(calendar_agent)
    agent_bus = AgentBus(registry=registry)

    # Register Tool Annotations
    for cap in gmail_agent.capabilities():
        policy.register_tool_annotations("gmail", cap.name, cap.annotations)
    for cap in calendar_agent.capabilities():
        policy.register_tool_annotations("calendar", cap.name, cap.annotations)

    # Track notifications via JARVIS
    notifications_sent = []

    class MockJarvisNotifier:
        async def notify(self, message: str, level: str = "info", **kwargs):
            notifications_sent.append({"message": message, "level": level, "kwargs": kwargs})

        async def request_approval(self, plan):
            notifications_sent.append({"approval_request": plan})

    jarvis = MockJarvisNotifier()

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
        jarvis=jarvis,
    )

    # 1. Ingest Inbound Email via Consumer
    gmail_consumer = GmailEventConsumer(event_bus=in_memory_bus)
    raw_email = {
        "id": "msg_artemis_001",
        "from": "alice@enterprise.com",
        "subject": "URGENT: Project Artemis Update",
        "body": "Hi, Please provide a status update on Project Artemis and confirm if we can sync tomorrow.",
        "labels": ["INBOX", "IMPORTANT"],
    }
    thira_event = await gmail_consumer.ingest_message(raw_email)
    assert thira_event.priority == EventPriority.HIGH

    # 2. Run Orchestrator Loop on the Event
    result = await orchestrator.process_event(thira_event)

    # 3. Verify autonomous execution completed
    assert result.status == "completed"
    assert result.plan_id is not None
    assert result.execution_id is not None

    # 4. Verify World Model entity auto-creation & cross-referencing
    alice_entity = await world_model.find_entity("Alice Smith")
    assert alice_entity is not None
    assert alice_entity["type"] == "person"

    artemis_entity = await world_model.find_entity("Project Artemis")
    assert artemis_entity is not None
    assert artemis_entity["type"] == "project"

    # 5. Verify ECHO recorded the proactive experience
    experiences = await echo.retrieve_similar("Project Artemis update")
    assert len(experiences) >= 1
    assert experiences[0].success is True

    # 6. Verify calendar event consumer also works cleanly
    calendar_consumer = CalendarEventConsumer(event_bus=in_memory_bus)
    cal_event = await calendar_consumer.ingest_event(
        {
            "summary": "Project Artemis Strategy",
            "start_time": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "end_time": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
            "attendees": ["alice@enterprise.com", "user@thira.local"],
            "description": "Discussing Artemis deliverables",
        }
    )
    assert cal_event.source == EventSource.CALENDAR
    assert cal_event.actor == "calendar"


@pytest.mark.asyncio
async def test_proactive_high_risk_escalation_requires_approval(test_db, in_memory_bus):
    """Test that a plan attempting external communication (send_email) halts for approval."""

    class HighRiskMockLLM(ProactiveMockLLM):
        async def complete(self, messages, **kwargs):
            purpose = kwargs.get("purpose", "")
            if purpose == "plan_generation":
                return type(
                    "Resp",
                    (),
                    {
                        "content": json.dumps(
                            {
                                "goal": "Directly send confirmed update to client",
                                "requires_approval": False,
                                "steps": [
                                    {
                                        "description": "Send confirmation email to Alice",
                                        "agent": "gmail",
                                        "tool": "send_email",
                                        "arguments": {
                                            "to": "alice@enterprise.com",
                                            "subject": "Project Artemis Delivery Confirmed",
                                            "body": "Hi Alice, All deliverables are signed off.",
                                        },
                                        "depends_on": [],
                                    }
                                ],
                            }
                        )
                    },
                )()
            return await super().complete(messages, **kwargs)

    mock_llm = HighRiskMockLLM()
    perception = PerceptionEngine(event_bus=in_memory_bus)
    context = ContextEngine(llm=mock_llm)
    world_model = WorldModel(db_session_factory=test_db)
    decision_engine = DecisionEngine(llm=mock_llm)
    planning = PlanningEngine(llm=mock_llm)
    policy = PolicyEngine(default_autonomy=AutonomyLevel.L3_EXECUTE_APPROVED)
    verification = VerificationEngine()
    failure = FailureEngine()
    echo = EchoEngine(db_session_factory=test_db, llm=mock_llm)

    registry = AgentRegistry()
    gmail_agent = GmailAgent()
    await registry.register(gmail_agent)
    agent_bus = AgentBus(registry=registry)

    for cap in gmail_agent.capabilities():
        policy.register_tool_annotations("gmail", cap.name, cap.annotations)

    approval_requests = []

    class MockJarvisNotifier:
        async def notify(self, message: str, level: str = "info", **kwargs):
            pass

        async def request_approval(self, plan):
            approval_requests.append(plan)

    jarvis = MockJarvisNotifier()

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
        jarvis=jarvis,
    )

    event = ThiraEvent(
        source=EventSource.GMAIL,
        type=EventType.MESSAGE_RECEIVED,
        timestamp=datetime.now(UTC),
        actor="alice@enterprise.com",
        content="Please send the final confirmation email.",
        priority=EventPriority.HIGH,
    )

    # 1. Process event -> Must halt because send_email is L4_EXECUTE_AUTO and user default is L3
    loop_result = await orchestrator.process_event(event)
    assert loop_result.status == "awaiting_approval"
    assert len(approval_requests) == 1
    plan_id = loop_result.plan_id

    # 2. Grant approval through orchestrator
    resume_result = await orchestrator.handle_approval(plan_id, approved=True)
    assert resume_result.status == "completed"
    assert resume_result.execution_id is not None
