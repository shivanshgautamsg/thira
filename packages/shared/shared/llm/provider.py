"""LLM Provider interface — the abstraction all engines use."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class LLMMessage:
    """A single message in an LLM conversation."""

    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMResponse:
    """Response from an LLM call."""

    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: int = 0
    finish_reason: str = "stop"
    raw_response: dict = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    All THIRA engines use this interface — never call OpenAI/Anthropic/etc. directly.
    """

    @abstractmethod
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
        """Generate a completion from the LLM.

        Args:
            messages: Conversation messages.
            model: Override the default model.
            temperature: Sampling temperature (0.0–2.0).
            max_tokens: Maximum tokens to generate.
            json_mode: If True, force JSON output.
            purpose: What this call is for (e.g., "entity_extraction") — for tracing.
        """
        ...

    @abstractmethod
    async def embed(
        self,
        text: str,
        *,
        model: str | None = None,
    ) -> list[float]:
        """Generate an embedding vector for the given text.

        Args:
            text: The text to embed.
            model: Override the default embedding model.

        Returns:
            A list of floats representing the embedding vector.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is accessible."""
        ...
