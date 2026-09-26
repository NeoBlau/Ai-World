"""Provider-agnostic LLM interface.

Every provider speaks the same internal protocol: an ``LLMRequest`` goes in,
an ``LLMResponse`` comes out. The engine never talks to vendor SDKs directly.
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["user", "assistant"]


class ProviderError(Exception):
    """Raised when a provider call fails (network, auth, quota, bad output)."""

    def __init__(self, provider: str, message: str, *, retryable: bool = True, status: int | None = None) -> None:
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.retryable = retryable
        self.status = status


class ProviderNotConfigured(ProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(provider, "provider is not configured", retryable=False)


@dataclass
class ChatMessage:
    role: Role
    content: str


@dataclass
class LLMRequest:
    system: str
    messages: list[ChatMessage]
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int = 400
    json_mode: bool = True
    purpose: str = "decide"
    # Structured context. Real providers ignore it (they read the prompt);
    # the offline simulation provider reasons over it directly.
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    fallback_used: bool = False

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class ProviderHealth:
    name: str
    configured: bool
    healthy: bool | None
    detail: str = ""
    default_model: str = ""


class LLMProvider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def is_configured(self) -> bool: ...

    @property
    @abc.abstractmethod
    def default_model(self) -> str: ...

    @abc.abstractmethod
    async def _generate(self, request: LLMRequest, model: str) -> LLMResponse: ...

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if not self.is_configured():
            raise ProviderNotConfigured(self.name)
        model = request.model or self.default_model
        started = time.perf_counter()
        response = await self._generate(request, model)
        response.latency_ms = int((time.perf_counter() - started) * 1000)
        return response

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Return embeddings or ``None`` if the provider has no embedding API."""
        return None

    async def health(self) -> ProviderHealth:
        return ProviderHealth(self.name, self.is_configured(), None, "", self.default_model)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
