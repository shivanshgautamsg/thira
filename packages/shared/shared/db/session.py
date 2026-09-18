"""Async SQLAlchemy session management.

Provides an async session factory and dependency for FastAPI injection.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = structlog.get_logger()


class DatabaseManager:
    """Manages async SQLAlchemy engine and session factory.

    Usage:
        db = DatabaseManager("postgresql+asyncpg://...")
        async with db.session() as session:
            result = await session.execute(...)
    """

    def __init__(self, database_url: str, echo: bool = False):
        self._engine = create_async_engine(
            database_url,
            echo=echo,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info("db.initialized", url=database_url.split("@")[-1])  # Log without creds

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a transactional async session scope."""
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """FastAPI dependency — yields a session for request scope."""
        async with self.session() as session:
            yield session

    async def close(self) -> None:
        """Dispose of the engine's connection pool."""
        await self._engine.dispose()
        logger.info("db.closed")

    @property
    def engine(self):
        return self._engine
