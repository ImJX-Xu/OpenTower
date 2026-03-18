"""LLM Client — OpenAI-compatible chat completions wrapper.

Supports LM Studio, Ollama, OpenAI, or any server exposing the
``/v1/chat/completions`` endpoint.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("opentower.llm")

_DEFAULT_BASE_URL = "http://ai-5090:8000/v1"  # llama.cpp server


@dataclass
class LLMUsage:
    """Token usage for a single completion."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLMClient:
    """Async wrapper for OpenAI-compatible chat completions.

    Attributes:
        base_url: API base URL (e.g. ``http://localhost:1234/v1``).
        api_key: Bearer token (default reads ``OPENAI_API_KEY`` env var).
        model: Model identifier for the ``model`` field.
        max_retries: Number of retries with exponential back-off.
        timeout: HTTP request timeout in seconds.
    """

    base_url: str = ""
    api_key: str = ""
    model: str = "qwen35"
    max_retries: int = 3
    timeout: float = 60.0
    _total_usage: LLMUsage = field(default_factory=LLMUsage, repr=False)

    def __post_init__(self) -> None:
        if not self.base_url:
            self.base_url = os.getenv("OPENAI_BASE_URL", _DEFAULT_BASE_URL)
        if not self.api_key:
            self.api_key = os.getenv("OPENAI_API_KEY", "no-key")

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> tuple[str, LLMUsage]:
        """Send a chat completion request.

        Returns:
            A tuple of (response_text, usage).

        Raises:
            httpx.HTTPStatusError: After exhausting retries.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()

                text = data["choices"][0]["message"]["content"]
                usage_raw = data.get("usage", {})
                usage = LLMUsage(
                    prompt_tokens=usage_raw.get("prompt_tokens", 0),
                    completion_tokens=usage_raw.get("completion_tokens", 0),
                )
                self._total_usage.prompt_tokens += usage.prompt_tokens
                self._total_usage.completion_tokens += usage.completion_tokens

                logger.debug(
                    "LLM response (%d tokens): %.80s…",
                    usage.total,
                    text.replace("\n", " "),
                )
                return text, usage

            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_exc = exc
                wait = 2**attempt
                logger.warning("LLM attempt %d/%d failed (%s), retrying in %ds", attempt, self.max_retries, exc, wait)
                await asyncio.sleep(wait)

        raise RuntimeError(f"LLM call failed after {self.max_retries} retries") from last_exc

    @property
    def total_usage(self) -> LLMUsage:
        """Cumulative token usage across all calls."""
        return self._total_usage
