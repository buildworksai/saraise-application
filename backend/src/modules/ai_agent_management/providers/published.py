"""Production bridge to the tenant-owned provider configuration module.

The provider configuration module owns deployments and encrypted credentials.
This bridge resolves exactly one active deployment for the requesting tenant;
it never selects a substitute deployment or credential.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any
from uuid import UUID

from src.core.encryption import EncryptionService
from src.modules.ai_provider_configuration.models import AIModelDeployment, DeploymentStatus
from src.modules.ai_provider_configuration.services import (
    AIProviderFactory as ConfigurationProviderFactory,
)
from src.modules.ai_provider_configuration.services import (
    ProviderUnavailable as ConfigurationProviderUnavailable,
)

from ..services import ConfigurationService
from .base import (
    EmbeddingResponse,
    LLMProvider,
    LLMResponse,
    ProviderConfig,
    ProviderStatus,
    TokenUsage,
)

ADAPTER_KEY = "tenant_provider_configuration"


class PublishedProviderUnavailable(RuntimeError):
    """The selected published deployment cannot safely execute."""


def resolve_published_deployment(tenant_id: UUID, deployment_id: UUID) -> Mapping[str, Any]:
    """Return a sanitized runtime projection for one tenant deployment."""

    deployment = (
        AIModelDeployment.objects.for_tenant(tenant_id)
        .select_related("model__provider", "credential")
        .filter(
            id=deployment_id,
            tenant_id=tenant_id,
            status=DeploymentStatus.ACTIVE,
            is_deleted=False,
            model__is_active=True,
            model__provider__is_active=True,
            credential__is_deleted=False,
        )
        .first()
    )
    if deployment is None or deployment.credential_id is None:
        raise PublishedProviderUnavailable("The tenant provider deployment is unavailable.")
    if (
        deployment.credential.tenant_id != tenant_id
        or deployment.credential.provider_id != deployment.model.provider_id
    ):
        raise PublishedProviderUnavailable("The provider deployment credential boundary is invalid.")

    pricing = deployment.model.pricing if isinstance(deployment.model.pricing, Mapping) else {}
    return {
        "tenant_id": str(tenant_id),
        "adapter_key": ADAPTER_KEY,
        "provider_name": deployment.model.provider.provider_type,
        "model": deployment.model.model_id,
        "credential_reference": f"{tenant_id}:{deployment.id}",
        "dependency_key": f"ai-provider-{deployment.model.provider_id}",
        "pricing_version": str(pricing.get("version", "")).strip() or None,
        "cost_per_1k_input_tokens": pricing.get("input_per_1k"),
        "cost_per_1k_output_tokens": pricing.get("output_per_1k"),
    }


class TenantConfiguredProvider(LLMProvider):
    """Adapter over the exact credential referenced by a published deployment."""

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        try:
            tenant_text, deployment_text = config.credential_reference.split(":", 1)
            self._tenant_id = UUID(tenant_text)
            self._deployment_id = UUID(deployment_text)
        except (AttributeError, ValueError) as exc:
            raise PublishedProviderUnavailable("The credential reference is invalid.") from exc

    def _provider(self):
        deployment = (
            AIModelDeployment.objects.for_tenant(self._tenant_id)
            .select_related("model__provider", "credential")
            .filter(
                id=self._deployment_id,
                tenant_id=self._tenant_id,
                status=DeploymentStatus.ACTIVE,
                is_deleted=False,
                credential__is_deleted=False,
            )
            .first()
        )
        if deployment is None or deployment.credential_id is None:
            raise PublishedProviderUnavailable("The tenant provider deployment is unavailable.")
        if (
            deployment.model.model_id != self.config.model
            or deployment.model.provider.provider_type != self.config.provider_name
            or deployment.credential.tenant_id != self._tenant_id
            or deployment.credential.provider_id != deployment.model.provider_id
        ):
            raise PublishedProviderUnavailable("The published provider projection is stale or invalid.")
        adapter_type = ConfigurationProviderFactory.adapter_types.get(deployment.model.provider.provider_type)
        if adapter_type is None:
            raise PublishedProviderUnavailable("The provider type has no production adapter.")
        try:
            secret = EncryptionService.decrypt(deployment.credential.api_key_encrypted)
            return adapter_type(
                secret,
                deployment.model.provider.base_url or None,
                dependency=self.config.dependency_key,
            )
        except Exception as exc:
            raise PublishedProviderUnavailable("The provider credential cannot be used.") from exc

    def call(
        self,
        messages: Sequence[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
    ) -> LLMResponse:
        if tools or stop_sequences:
            raise PublishedProviderUnavailable(
                "The published completion boundary does not support tools or stop sequences."
            )
        prompt = "\n".join(f"{message['role']}: {message['content']}" for message in messages)
        try:
            content = self._provider().complete(
                prompt,
                self.config.model,
                max_tokens=max_tokens if max_tokens is not None else self.config.max_tokens,
                temperature=temperature if temperature is not None else self.config.temperature,
            )
        except ConfigurationProviderUnavailable as exc:
            self._status = ProviderStatus.UNAVAILABLE
            raise PublishedProviderUnavailable("The configured provider is unavailable.") from exc

        evaluation = ConfigurationService.resolve(self._tenant_id)["evaluation"]
        characters_per_token = int(evaluation["characters_per_estimated_token"])
        input_tokens = max(1, len(prompt) // characters_per_token)
        output_tokens = max(1, len(content) // characters_per_token)
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )
        return LLMResponse(
            content=content,
            model=self.config.model,
            provider=self.config.provider_name,
            usage=usage,
            metadata={"usage_evidence": "estimated_from_configured_character_ratio"},
        )

    async def call_async(
        self,
        messages: Sequence[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        return await asyncio.to_thread(
            self.call,
            messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def stream(
        self,
        messages: Sequence[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        raise PublishedProviderUnavailable("Streaming is not implemented by this adapter.")
        yield ""  # pragma: no cover - preserves the async iterator contract

    def embed(self, texts: Sequence[str], *, model: str | None = None) -> EmbeddingResponse:
        raise PublishedProviderUnavailable("Embedding is not implemented by this adapter.")

    def health_check(self) -> ProviderStatus:
        try:
            self._provider()
        except PublishedProviderUnavailable:
            self._status = ProviderStatus.UNAVAILABLE
        else:
            self._status = ProviderStatus.HEALTHY
        return self._status


__all__ = [
    "ADAPTER_KEY",
    "PublishedProviderUnavailable",
    "TenantConfiguredProvider",
    "resolve_published_deployment",
]
