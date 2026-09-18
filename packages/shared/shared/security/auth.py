"""Authentication utilities for THIRA.

V1: Simple user resolution from environment.
V2: OAuth2, JWT tokens, multi-user support.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


@dataclass
class ThiraUser:
    """Represents the authenticated user."""

    id: uuid.UUID
    email: str
    name: str


# V1: Single-user system — user is configured via environment
_current_user: ThiraUser | None = None


def set_current_user(user: ThiraUser) -> None:
    """Set the current user (V1: called at startup)."""
    global _current_user
    _current_user = user
    logger.info("auth.user_set", user_id=str(user.id), email=user.email)


def get_current_user() -> ThiraUser:
    """Get the current authenticated user."""
    if _current_user is None:
        raise RuntimeError("No user configured. Call set_current_user() at startup.")
    return _current_user
