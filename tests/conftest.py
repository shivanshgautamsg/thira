"""Test configuration and shared fixtures."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.bus.memory_bus import InMemoryEventBus
from shared.db.models import Base
from shared.enums import EventPriority, EventSource, EventType
from shared.events import ThiraEvent
from shared.llm.provider import LLMMessage, LLMProvider, LLMResponse


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_event() -> ThiraEvent:
    """Create a sample ThiraEvent for testing."""
    return ThiraEvent(
        source=EventSource.USER_COMMAND,
        type=EventType.USER_REQUEST,
        timestamp=datetime.now(UTC),
        actor="test_user",
        content="List the files in the current directory",
        priority=EventPriority.MEDIUM,
    )


@pytest.fixture
def sample_email_event() -> ThiraEvent:
    """Create a sample email event for testing."""
    return ThiraEvent(
        source=EventSource.GMAIL,
        type=EventType.MESSAGE_RECEIVED,
        timestamp=datetime.now(UTC),
        actor="client@example.com",
        content="Please send the revised proposal by 5 PM.",
        priority=EventPriority.HIGH,
    )


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(self, response_content: str = '{"action": "act"}'):
        self._response_content = response_content
        self.calls: list[dict] = []

    def set_response(self, content: str):
        self._response_content = content

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
        purpose: str = "",
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "purpose": purpose,
            }
        )
        return LLMResponse(
            content=self._response_content,
            model=model or "mock",
            prompt_tokens=10,
            completion_tokens=20,
        )

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        # Generate stable mock embedding based on hash of text
        val = (hash(text) % 1000) / 1000.0
        return [val] * 1536

    async def health_check(self) -> bool:
        return True


@pytest.fixture
def mock_llm() -> MockLLMProvider:
    """Create a mock LLM provider."""
    return MockLLMProvider()


@pytest.fixture
async def test_db():
    """Create an async SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory

    await engine.dispose()


@pytest.fixture
def in_memory_bus() -> InMemoryEventBus:
    """Create an in-memory event bus."""
    return InMemoryEventBus()
