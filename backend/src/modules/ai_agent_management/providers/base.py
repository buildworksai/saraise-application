"""
Abstract base classes for LLM provider integration.

All provider implementations MUST inherit from LLMProvider and implement
all abstract methods. No direct API calls to LLM providers are permitted
outside of provider implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Optional, Sequence


class ProviderStatus(Enum):
    """Provider health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ProviderConfig:
    """Immutable provider configuration."""

    provider_name: str
    api_key: str
    model: str
    base_url: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout_seconds: int = 30
    max_retries: int = 3
    # Cost tracking (per 1K tokens)
    cost_per_1k_input_tokens: float = 0.0
    cost_per_1k_output_tokens: float = 0.0
    # Circuit breaker settings
    circuit_breaker_threshold: int = 5
    circuit_breaker_reset_seconds: int = 60


@dataclass
class TokenUsage:
    """Token usage for a single request."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    @property
    def cost(self) -> float:
        """Placeholder — actual cost computed by provider with its rates."""
        return 0.0


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""

    content: str
    model: str
    provider: str
    usage: TokenUsage
    finish_reason: str = "stop"
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    raw_response: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingResponse:
    """Standardized embedding response."""

    embeddings: list[list[float]]
    model: str
    provider: str
    usage: TokenUsage
    dimensions: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0


class LLMProvider(ABC):
    """
    Abstract base class for all LLM provider implementations.

    Every provider MUST implement:
    - call(): Synchronous completion
    - call_async(): Asynchronous completion
    - embed(): Generate embeddings
    - health_check(): Verify provider availability
    - get_cost(): Calculate cost for token usage

    Providers MUST NOT:
    - Cache authorization tokens beyond their TTL
    - Store conversation history (handled by memory layer)
    - Retry indefinitely (respect max_retries from config)
    """

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._status = ProviderStatus.HEALTHY

    @property
    def name(self) -> str:
        return self.config.provider_name

    @property
    def status(self) -> ProviderStatus:
        return self._status

    @abstractmethod
    def call(
        self,
        messages: Sequence[dict[str, str]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop_sequences: Optional[list[str]] = None,
    ) -> LLMResponse:
        """
        Synchronous completion call.

        Args:
            messages: List of {"role": "...", "content": "..."} dicts
            tools: Optional tool definitions for function calling
            temperature: Override default temperature
            max_tokens: Override default max_tokens
            stop_sequences: Stop generation at these sequences

        Returns:
            Standardized LLMResponse

        Raises:
            ProviderError: On API errors
            ProviderTimeoutError: On timeout
            ProviderRateLimitError: On rate limit exceeded
        """
        ...

    @abstractmethod
    async def call_async(
        self,
        messages: Sequence[dict[str, str]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Asynchronous completion call."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: Sequence[dict[str, str]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Streaming completion call. Yields content chunks."""
        ...

    @abstractmethod
    def embed(
        self,
        texts: Sequence[str],
        *,
        model: Optional[str] = None,
    ) -> EmbeddingResponse:
        """Generate embeddings for one or more texts."""
        ...

    @abstractmethod
    def health_check(self) -> ProviderStatus:
        """Check provider availability. Updates internal status."""
        ...

    def get_cost(self, usage: TokenUsage) -> float:
        """Calculate cost in USD for token usage."""
        input_cost = (usage.input_tokens / 1000) * self.config.cost_per_1k_input_tokens
        output_cost = (usage.output_tokens / 1000) * self.config.cost_per_1k_output_tokens
        return round(input_cost + output_cost, 6)
