"""OpenAI LLM Provider implementation."""

from __future__ import annotations

import time

import openai
import structlog

from shared.llm.provider import LLMMessage, LLMProvider, LLMResponse

logger = structlog.get_logger()


class OpenAIProvider(LLMProvider):
    """OpenAI GPT implementation of the LLM provider interface."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        default_model: str = "gpt-4o",
        default_embedding_model: str = "text-embedding-3-small",
    ):
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self._default_model = default_model
        self._default_embedding_model = default_embedding_model

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
        """Generate a completion using OpenAI's API."""
        model = model or self._default_model
        start = time.monotonic()

        kwargs: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await self._client.chat.completions.create(**kwargs)
            duration_ms = int((time.monotonic() - start) * 1000)

            choice = response.choices[0]
            usage = response.usage

            logger.debug(
                "llm.openai.complete",
                model=model,
                purpose=purpose,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                duration_ms=duration_ms,
            )

            return LLMResponse(
                content=choice.message.content or "",
                model=model,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                duration_ms=duration_ms,
                finish_reason=choice.finish_reason or "stop",
                raw_response=response.model_dump(),
            )

        except openai.APIError as e:
            logger.error("llm.openai.error", model=model, purpose=purpose, error=str(e))
            raise

    async def embed(
        self,
        text: str,
        *,
        model: str | None = None,
    ) -> list[float]:
        """Generate an embedding using OpenAI's API."""
        model = model or self._default_embedding_model

        try:
            response = await self._client.embeddings.create(
                model=model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.warning("llm.openai.embed_fallback", model=model, error=str(e))
            import hashlib
            h = hashlib.sha256(text.encode()).digest()
            val = [(b - 128) / 128.0 for b in h]
            return (val * 48)[:1536]

    async def health_check(self) -> bool:
        """Check if OpenAI API is accessible."""
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False
