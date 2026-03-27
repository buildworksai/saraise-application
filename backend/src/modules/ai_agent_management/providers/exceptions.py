"""Provider-specific exceptions for error handling and circuit breaker integration."""

from __future__ import annotations


class ProviderError(Exception):
    """Base exception for all provider errors."""

    def __init__(self, provider: str, message: str, status_code: int | None = None) -> None:
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"[{provider}] {message}")


class ProviderTimeoutError(ProviderError):
    """Provider request timed out."""

    pass


class ProviderRateLimitError(ProviderError):
    """Provider rate limit exceeded."""

    def __init__(self, provider: str, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(provider, f"Rate limit exceeded (retry after {retry_after}s)", 429)


class ProviderAuthError(ProviderError):
    """Provider authentication failed (invalid API key)."""

    def __init__(self, provider: str) -> None:
        super().__init__(provider, "Authentication failed — check API key", 401)


class ProviderQuotaError(ProviderError):
    """Provider quota/budget exceeded."""

    def __init__(self, provider: str, message: str = "Quota exceeded") -> None:
        super().__init__(provider, message, 402)
