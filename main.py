"""THIRA — Main entry point.

Wires up all components and starts the platform.
"""

from __future__ import annotations

import asyncio
import uuid

import structlog
import uvicorn

from agents.calendar import CalendarAgent, create_calendar_client
from agents.filesystem import FilesystemAgent
from agents.gmail import GmailAgent, create_gmail_client
from agents.registry import AgentBus, AgentRegistry
from agents.terminal import TerminalAgent
from echo.engine import EchoEngine
from jarvis.app import JarvisNotifier, manager, set_orchestrator
from shared.bus.redis_bus import RedisEventBus
from shared.config import load_config
from shared.db.session import DatabaseManager
from shared.llm.openai_provider import OpenAIProvider
from shared.llm.router import LLMRouter
from shared.logging import setup_logging
from shared.security.audit import AuditTrail
from shared.security.auth import ThiraUser, set_current_user
from thira_core.context.engine import ContextEngine
from thira_core.decision.engine import DecisionEngine
from thira_core.failure.engine import FailureEngine
from thira_core.orchestrator import ThiraOrchestrator
from thira_core.perception.engine import PerceptionEngine
from thira_core.planning.engine import PlanningEngine
from thira_core.policy.engine import PolicyEngine
from thira_core.verification.engine import VerificationEngine
from thira_core.world_model.model import WorldModel

logger = structlog.get_logger()


async def create_thira() -> ThiraOrchestrator:
    """Wire up all THIRA components and return the orchestrator."""
    config = load_config()

    # ── Setup logging ─────────────────────────────────────────
    setup_logging(level=config.log_level, format=config.log_format)
    logger.info("thira.starting", version="0.1.0")

    # ── Setup user (V1: single user) ─────────────────────────
    set_current_user(
        ThiraUser(
            id=uuid.uuid4(),
            email="user@thira.local",
            name="THIRA User",
        )
    )

    # ── Infrastructure ────────────────────────────────────────
    db = DatabaseManager(config.database_url)
    event_bus = RedisEventBus(config.redis_url)

    # ── LLM Provider ─────────────────────────────────────────
    openai = OpenAIProvider(
        api_key=config.openai_api_key,
        default_model=config.openai_model,
        default_embedding_model=config.openai_embedding_model,
    )
    llm = LLMRouter(primary=openai)

    # ── Core Engines ──────────────────────────────────────────
    perception = PerceptionEngine(event_bus=event_bus)
    context = ContextEngine(llm=openai)
    world_model = WorldModel(db_session_factory=db.session)
    decision = DecisionEngine(llm=openai)
    planning = PlanningEngine(llm=openai)
    policy = PolicyEngine()
    verification = VerificationEngine()
    failure = FailureEngine()

    # ── ECHO ──────────────────────────────────────────────────
    echo = EchoEngine(db_session_factory=db.session, llm=openai)

    # ── Agents ────────────────────────────────────────────────
    registry = AgentRegistry()
    audit = AuditTrail(db_session_factory=db.session)
    agent_bus = AgentBus(registry=registry, audit=audit)

    # Register agents
    await registry.register(TerminalAgent())
    await registry.register(FilesystemAgent())
    await registry.register(GmailAgent(client=create_gmail_client(config)))
    await registry.register(CalendarAgent(client=create_calendar_client(config)))

    # Update planning engine with available tools
    tools = await registry.discover_tools()
    planning.update_available_tools(tools)

    # Register tool annotations with policy engine
    for tool in tools:
        policy.register_tool_annotations(tool.agent, tool.tool, tool.annotations)

    # ── JARVIS Notifier ───────────────────────────────────────
    jarvis_notifier = JarvisNotifier(connection_manager=manager)

    # ── Orchestrator ──────────────────────────────────────────
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

    # Inject orchestrator into JARVIS
    set_orchestrator(orchestrator)

    logger.info(
        "thira.ready",
        agents=len(registry.list_agents()),
        tools=len(tools),
    )

    return orchestrator


def main():
    """Start THIRA."""
    config = load_config()
    setup_logging(level=config.log_level, format=config.log_format)

    # Create orchestrator (this wires everything up)
    loop = asyncio.new_event_loop()
    loop.run_until_complete(create_thira())

    # Start JARVIS (FastAPI server)
    logger.info(
        "thira.serving",
        host=config.jarvis_host,
        port=config.jarvis_port,
    )

    uvicorn.run(
        "jarvis.app:app",
        host=config.jarvis_host,
        port=config.jarvis_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
