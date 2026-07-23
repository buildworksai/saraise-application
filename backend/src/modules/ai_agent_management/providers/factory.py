"""Tenant-bound provider resolution without implicit failover.

Returning another model's output as if it came from the configured provider is
forbidden.  Resolution therefore produces an explicit unavailable outcome when
configuration, credentials, or an adapter cannot be obtained.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

from src.core.api import OperationResult

from .base import LLMProvider, ProviderConfig
from .registry import ProviderRegistry, get_registry

ProviderConfigurationResolver = Callable[[UUID, UUID], Mapping[str, Any]]


class ProviderFactory:
    """Resolve one tenant-owned published provider configuration."""

    def __init__(
        self,
        resolver: ProviderConfigurationResolver | None = None,
        *,
        registry: ProviderRegistry | None = None,
    ) -> None:
        self._resolver = resolver
        self._registry = registry or get_registry()

    @property
    def is_configured(self) -> bool:
        """Whether a published tenant-first configuration resolver exists."""
        return self._resolver is not None

    def resolve(self, tenant_id: UUID, provider_config_id: UUID) -> OperationResult[LLMProvider]:
        if self._resolver is None:
            return OperationResult.unavailable(
                capability="provider_configuration",
                message="The provider configuration service is not installed.",
            )
        try:
            published = dict(self._resolver(tenant_id, provider_config_id))
        except Exception:
            return OperationResult.unavailable(
                capability="provider_configuration",
                message="The provider configuration service could not resolve this configuration.",
            )
        if str(published.get("tenant_id", tenant_id)) != str(tenant_id):
            return OperationResult.failed(
                code="PROVIDER_TENANT_MISMATCH",
                message="The provider configuration is not available.",
                http_status=404,
            )
        adapter_key = str(published.get("adapter_key", "")).strip()
        adapter = self._registry.get(adapter_key) if adapter_key else None
        if adapter is None:
            return OperationResult.unavailable(
                capability=f"provider_adapter:{adapter_key or 'unspecified'}",
                message="The configured provider adapter is unavailable.",
            )
        from ..services import ConfigurationService

        runtime_defaults = ConfigurationService.resolve(tenant_id)["provider"]
        for key in ("max_tokens", "temperature", "timeout_seconds", "max_retries"):
            published.setdefault(key, runtime_defaults[key])
        try:
            configuration = ProviderConfig.from_published(published)
            provider = adapter(configuration)
        except Exception:
            return OperationResult.unavailable(
                capability=f"provider_adapter:{adapter_key}",
                message="The provider adapter rejected the published configuration.",
            )
        return OperationResult.succeeded(
            provider,
            provider=adapter_key,
            evidence={"provider_config_id": str(provider_config_id), "adapter_key": adapter_key},
        )

    # Compatibility API: only explicitly registered, already constructed
    # instances may be returned.  There is intentionally no fallback chain.
    def register(self, provider: LLMProvider, **_: Any) -> None:
        self._registry.register(provider.name, type(provider))

    def get(self, name: str) -> LLMProvider | None:
        raise RuntimeError(f"Provider {name!r} requires tenant-bound configuration resolution")

    def call_with_failover(self, *_: Any, **__: Any) -> Any:
        raise RuntimeError("Implicit provider failover is forbidden; resolve a tenant configuration")


_factory = ProviderFactory()


def get_provider_factory() -> ProviderFactory:
    return _factory


def configure_provider_factory(resolver: ProviderConfigurationResolver) -> ProviderFactory:
    global _factory
    _factory = ProviderFactory(resolver)
    return _factory


def get_provider(name: str) -> None:
    raise RuntimeError(f"Provider {name!r} requires tenant-bound configuration resolution")


__all__ = [
    "ProviderConfigurationResolver",
    "ProviderFactory",
    "configure_provider_factory",
    "get_provider",
    "get_provider_factory",
]
