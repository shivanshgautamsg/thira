"""LLM Router — provider routing and fallback logic."""

from __future__ import annotations

import structlog

from shared.llm.provider import LLMMessage, LLMProvider, LLMResponse

logger = structlog.get_logger()


class LLMRouter:
    """Routes LLM calls to the appropriate provider.

    V1: Single provider (OpenAI).
    V2: Multi-provider with fallback, cost-based routing, model-per-engine config.
    """

    def __init__(self, primary: LLMProvider):
        self._primary = primary
        self._fallbacks: list[LLMProvider] = []

    def add_fallback(self, provider: LLMProvider) -> None:
        """Add a fallback provider used when the primary fails."""
        self._fallbacks.append(provider)

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
        """Route a completion request to the appropriate provider."""
        providers = [self._primary, *self._fallbacks]

        last_error: Exception | None = None
        for provider in providers:
            try:
                return await provider.complete(
                    messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    purpose=purpose,
                )
            except Exception as e:
                logger.warning(
                    "llm.router.fallback",
                    provider=type(provider).__name__,
                    purpose=purpose,
                    error=str(e),
                )
                last_error = e

        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        """Route an embedding request."""
        return await self._primary.embed(text, model=model)

    async def health_check(self) -> bool:
        """Check if the primary provider is healthy."""
        return await self._primary.health_check()
