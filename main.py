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


import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from shared.bus.memory_bus import InMemoryEventBus
from shared.db.models import Base
from scripts.demo import DemoLLM


async def create_thira() -> ThiraOrchestrator:
    """Wire up all THIRA components and return the orchestrator."""
    config = load_config()

    # ── Setup logging ─────────────────────────────────────────
    setup_logging(level=config.log_level, format=config.log_format)
    logger.info("thira.starting", version="0.2.0")

    # ── Setup user (V1: single user) ─────────────────────────
    set_current_user(
        ThiraUser(
            id=uuid.uuid4(),
            email="user@thira.local",
            name="THIRA User",
        )
    )

    # ── Infrastructure (Postgres or SQLite Fallback) ───────────
    session_factory = None
    try:
        db = DatabaseManager(config.database_url)
        async with asyncio.timeout(1.0):
            async with db.session() as s:
                await s.execute(text("SELECT 1"))
        session_factory = db.session
        logger.info("db.connected_postgres")
    except Exception as e:
        logger.warning("db.postgres_unreachable", fallback="sqlite:///thira.db", error=str(e))
        engine = create_async_engine("sqlite+aiosqlite:///thira.db", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # ── Event Bus (Redis or In-Memory Fallback) ────────────────
    try:
        redis_bus = RedisEventBus(config.redis_url)
        async with asyncio.timeout(1.0):
            await redis_bus._redis.ping()
        event_bus = redis_bus
        logger.info("event_bus.connected_redis")
    except Exception as e:
        logger.warning("event_bus.redis_unreachable", fallback="InMemoryEventBus", error=str(e))
        event_bus = InMemoryEventBus()

    # ── LLM Provider (OpenAI or Realistic Demo Fallback) ──────
    if config.openai_api_key:
        llm_provider = OpenAIProvider(
            api_key=config.openai_api_key,
            default_model=config.openai_model,
            default_embedding_model=config.openai_embedding_model,
        )
        logger.info("llm.openai_configured")
    else:
        logger.warning("llm.api_key_absent", fallback="DemoLLM")
        llm_provider = DemoLLM()

    # ── Core Engines ──────────────────────────────────────────
    perception = PerceptionEngine(event_bus=event_bus)
    context = ContextEngine(llm=llm_provider)
    world_model = WorldModel(db_session_factory=session_factory)
    decision = DecisionEngine(llm=llm_provider)
    planning = PlanningEngine(llm=llm_provider)
    policy = PolicyEngine()
    verification = VerificationEngine()
    failure = FailureEngine()

    # ── ECHO ──────────────────────────────────────────────────
    echo = EchoEngine(db_session_factory=session_factory, llm=llm_provider)

    # ── Agents ────────────────────────────────────────────────
    registry = AgentRegistry()
    audit = AuditTrail(db_session_factory=session_factory)
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

    # Pre-initialize orchestrator
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(create_thira())
    except Exception as e:
        logger.error("thira.pre_init_error", error=str(e))

    logger.info(
        "thira.serving",
        host=config.jarvis_host,
        port=config.jarvis_port,
    )

    from jarvis.app import app
    uvicorn.run(
        app,
        host=config.jarvis_host,
        port=config.jarvis_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
