"""Tenant-safe business services and resilient provider adapters."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from src.core.encryption import EncryptionService
from src.core.resilience.circuit_breaker import CircuitBreakerError
from src.core.resilience.http import ResilientHttpClient, ResilientHttpError

from .models import (
    AIModel,
    AIModelDeployment,
    AIProvider,
    AIProviderConfigurationResource,
    AIProviderCredential,
    AIUsageLog,
    CredentialStatus,
    DeploymentStatus,
    ProviderType,
)

logger = logging.getLogger("saraise.ai_provider_configuration")


class ProviderUnavailable(RuntimeError):
    """The configured provider cannot currently fulfil a request."""


class InvalidProviderResponse(RuntimeError):
    """The provider returned a successful but unusable response."""


def _uuid(value: UUID | str, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({field: "A valid UUID is required."}) from exc


def _clean(instance: Any) -> None:
    try:
        instance.full_clean()
    except DjangoValidationError as exc:
        detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or ["Invalid value."]
        raise ValidationError(detail) from exc


def _text(value: object, field: str, *, maximum: int, allow_blank: bool = False) -> str:
    if not isinstance(value, str):
        raise ValidationError({field: "Must be text."})
    normalized = value.strip()
    if not normalized and not allow_blank:
        raise ValidationError({field: "Must not be blank."})
    if len(normalized) > maximum:
        raise ValidationError({field: f"Must contain at most {maximum} characters."})
    return normalized


class AIProviderService(ABC):
    """Provider-neutral synchronous completion contract."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        dependency: str,
        http_client: ResilientHttpClient | None = None,
    ) -> None:
        if not api_key:
            raise ProviderUnavailable("Provider credential is empty.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.dependency = dependency
        self.http_client = http_client or self._build_http_client()

    def _build_http_client(self) -> ResilientHttpClient:
        host = urlsplit(self.base_url).hostname
        if not host:
            raise ProviderUnavailable("Provider base URL is invalid.")
        return ResilientHttpClient(
            dependency_allowlist={
                self.dependency: {
                    "base_url": self.base_url,
                    "allowed_hosts": [host],
                }
            },
            connect_timeout=5.0,
            read_timeout=30.0,
            max_retries=0,
            failure_threshold=3,
            reset_timeout=60.0,
        )

    @abstractmethod
    def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Return provider output or raise an explicit typed failure."""

    def _post(self, path: str, *, headers: Mapping[str, str], payload: Mapping[str, object]) -> object:
        try:
            response = self.http_client.post(
                f"{self.base_url}/{path.lstrip('/')}",
                dependency=self.dependency,
                headers=dict(headers),
                json=dict(payload),
            )
            if response.status_code < 200 or response.status_code >= 300:
                raise ProviderUnavailable(f"Provider rejected the request with HTTP {response.status_code}.")
            return response.json()
        except (CircuitBreakerError, ResilientHttpError, httpx.HTTPError) as exc:
            logger.warning(
                "AI provider request unavailable",
                extra={"dependency": self.dependency, "error_type": type(exc).__name__},
            )
            raise ProviderUnavailable("AI provider is unavailable.") from exc
        except ValueError as exc:
            raise InvalidProviderResponse("Provider response is not valid JSON.") from exc

    @staticmethod
    def _validate_request(prompt: str, model: str, max_tokens: int, temperature: float) -> tuple[str, str]:
        prompt = _text(prompt, "prompt", maximum=1_000_000)
        model = _text(model, "model", maximum=255)
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 1 <= max_tokens <= 1_000_000:
            raise ValidationError({"max_tokens": "Must be an integer from 1 to 1000000."})
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not 0 <= temperature <= 2:
            raise ValidationError({"temperature": "Must be a number from 0 to 2."})
        return prompt, model


class OpenAICompatibleProvider(AIProviderService):
    """Adapter for OpenAI, Groq, Mistral, and compatible endpoints."""

    def complete(self, prompt: str, model: str, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        prompt, model = self._validate_request(prompt, model, max_tokens, temperature)
        body = self._post(
            "chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            payload={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        try:
            text = body["choices"][0]["message"]["content"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise InvalidProviderResponse("Provider response omitted completion text.") from exc
        if not isinstance(text, str) or not text:
            raise InvalidProviderResponse("Provider completion text is empty.")
        return text


class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, base_url: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            api_key,
            base_url or "https://api.openai.com/v1",
            dependency=str(kwargs.pop("dependency", "ai-provider-openai")),
            **kwargs,
        )


class GroqProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, base_url: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            api_key,
            base_url or "https://api.groq.com/openai/v1",
            dependency=str(kwargs.pop("dependency", "ai-provider-groq")),
            **kwargs,
        )


class MistralProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, base_url: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            api_key,
            base_url or "https://api.mistral.ai/v1",
            dependency=str(kwargs.pop("dependency", "ai-provider-mistral")),
            **kwargs,
        )


class CustomProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, base_url: str | None = None, **kwargs: Any) -> None:
        if not base_url:
            raise ProviderUnavailable("A custom provider base URL is required.")
        super().__init__(
            api_key,
            base_url,
            dependency=str(kwargs.pop("dependency", "ai-provider-custom")),
            **kwargs,
        )


class AzureOpenAIProvider(AIProviderService):
    """Azure deployment adapter; model is the Azure deployment name."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        *,
        api_version: str = "2024-10-21",
        **kwargs: Any,
    ) -> None:
        if not base_url:
            raise ProviderUnavailable("An Azure OpenAI endpoint is required.")
        super().__init__(
            api_key,
            base_url,
            dependency=str(kwargs.pop("dependency", "ai-provider-azure")),
            **kwargs,
        )
        self.api_version = api_version

    def complete(self, prompt: str, model: str, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        prompt, model = self._validate_request(prompt, model, max_tokens, temperature)
        path = f"openai/deployments/{model}/chat/completions?api-version={self.api_version}"
        body = self._post(
            path,
            headers={"api-key": self.api_key, "Content-Type": "application/json"},
            payload={
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        try:
            text = body["choices"][0]["message"]["content"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise InvalidProviderResponse("Azure response omitted completion text.") from exc
        if not isinstance(text, str) or not text:
            raise InvalidProviderResponse("Azure completion text is empty.")
        return text


class AnthropicProvider(AIProviderService):
    def __init__(self, api_key: str, base_url: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            api_key,
            base_url or "https://api.anthropic.com/v1",
            dependency=str(kwargs.pop("dependency", "ai-provider-anthropic")),
            **kwargs,
        )

    def complete(self, prompt: str, model: str, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        prompt, model = self._validate_request(prompt, model, max_tokens, temperature)
        body = self._post(
            "messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            payload={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        try:
            text = body["content"][0]["text"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise InvalidProviderResponse("Anthropic response omitted completion text.") from exc
        if not isinstance(text, str) or not text:
            raise InvalidProviderResponse("Anthropic completion text is empty.")
        return text


class GoogleGeminiProvider(AIProviderService):
    def __init__(self, api_key: str, base_url: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            api_key,
            base_url or "https://generativelanguage.googleapis.com/v1beta",
            dependency=str(kwargs.pop("dependency", "ai-provider-google")),
            **kwargs,
        )

    def complete(self, prompt: str, model: str, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        prompt, model = self._validate_request(prompt, model, max_tokens, temperature)
        body = self._post(
            f"models/{model}:generateContent",
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            payload={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
            },
        )
        try:
            text = body["candidates"][0]["content"]["parts"][0]["text"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise InvalidProviderResponse("Gemini response omitted completion text.") from exc
        if not isinstance(text, str) or not text:
            raise InvalidProviderResponse("Gemini completion text is empty.")
        return text


class HuggingFaceProvider(AIProviderService):
    def __init__(self, api_key: str, base_url: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            api_key,
            base_url or "https://api-inference.huggingface.co",
            dependency=str(kwargs.pop("dependency", "ai-provider-huggingface")),
            **kwargs,
        )

    def complete(self, prompt: str, model: str, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        prompt, model = self._validate_request(prompt, model, max_tokens, temperature)
        body = self._post(
            f"models/{model}",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            payload={"inputs": prompt, "parameters": {"max_new_tokens": max_tokens, "temperature": temperature}},
        )
        candidate: object
        if isinstance(body, list) and body:
            candidate = body[0]
        else:
            candidate = body
        if not isinstance(candidate, dict) or not isinstance(candidate.get("generated_text"), str):
            raise InvalidProviderResponse("Hugging Face response omitted generated text.")
        text = candidate["generated_text"]
        if not text:
            raise InvalidProviderResponse("Hugging Face generated text is empty.")
        return text


DEFAULT_BASE_URLS: dict[str, str] = {
    ProviderType.OPENAI: "https://api.openai.com/v1",
    ProviderType.ANTHROPIC: "https://api.anthropic.com/v1",
    ProviderType.GOOGLE: "https://generativelanguage.googleapis.com/v1beta",
    ProviderType.GROQ: "https://api.groq.com/openai/v1",
    ProviderType.MISTRAL: "https://api.mistral.ai/v1",
    ProviderType.HUGGINGFACE: "https://api-inference.huggingface.co",
}


class AIProviderFactory:
    """Resolve an adapter only from an active tenant credential."""

    adapter_types: dict[str, type[AIProviderService]] = {
        ProviderType.OPENAI: OpenAIProvider,
        ProviderType.ANTHROPIC: AnthropicProvider,
        ProviderType.GOOGLE: GoogleGeminiProvider,
        ProviderType.GROQ: GroqProvider,
        ProviderType.MISTRAL: MistralProvider,
        ProviderType.HUGGINGFACE: HuggingFaceProvider,
        ProviderType.AZURE: AzureOpenAIProvider,
        ProviderType.CUSTOM: CustomProvider,
    }

    @classmethod
    def get_provider(
        cls,
        provider_type: str,
        tenant_id: UUID | str,
        *,
        http_client: ResilientHttpClient | None = None,
    ) -> AIProviderService:
        tenant_id = _uuid(tenant_id, "tenant_id")
        credential = (
            AIProviderCredential.objects.for_tenant(tenant_id)
            .select_related("provider")
            .filter(provider__provider_type=provider_type, provider__is_active=True, is_deleted=False)
            .order_by("created_at")
            .first()
        )
        if credential is None:
            raise ProviderUnavailable("No active credential is configured for this provider.")
        provider = credential.provider
        adapter_type = cls.adapter_types.get(provider.provider_type)
        if adapter_type is None:
            raise ProviderUnavailable("Provider type is not supported.")
        base_url = provider.base_url or DEFAULT_BASE_URLS.get(provider.provider_type)
        if not base_url:
            raise ProviderUnavailable("Provider base URL is not configured.")
        try:
            api_key = EncryptionService.decrypt(credential.api_key_encrypted)
        except Exception as exc:
            logger.error(
                "AI credential decryption failed",
                extra={"credential_id": str(credential.id), "provider_id": str(provider.id)},
            )
            raise ProviderUnavailable("Provider credential is unavailable.") from exc
        kwargs: dict[str, object] = {
            "dependency": f"ai-provider-{provider.id}",
            "http_client": http_client,
        }
        if adapter_type is AzureOpenAIProvider:
            kwargs["api_version"] = provider.api_version or "2024-10-21"
        return adapter_type(api_key, base_url, **kwargs)


@dataclass(frozen=True, slots=True)
class RotationResult:
    rotated_count: int


class AIProviderConfigurationService:
    """Authoritative mutation surface for tenant configuration."""

    @transaction.atomic
    def create_resource(
        self,
        tenant_id: str,
        name: str,
        description: str = "",
        config: Mapping[str, object] | None = None,
        created_by: str = "",
    ) -> AIProviderConfigurationResource:
        """Create a persisted resource for the original module contract."""

        resource = AIProviderConfigurationResource(
            tenant_id=_text(tenant_id, "tenant_id", maximum=36),
            name=_text(name, "name", maximum=255),
            description=_text(description, "description", maximum=100_000, allow_blank=True),
            config=dict(config or {}),
            created_by=_text(created_by, "created_by", maximum=36),
        )
        _clean(resource)
        resource.save()
        return resource

    def get_resource(self, resource_id: str, tenant_id: str) -> AIProviderConfigurationResource | None:
        """Return a resource only when it belongs to the requested tenant."""

        return AIProviderConfigurationResource.objects.filter(
            pk=resource_id,
            tenant_id=tenant_id,
        ).first()

    def list_resources(
        self,
        tenant_id: str,
        is_active: bool | None = None,
    ) -> list[AIProviderConfigurationResource]:
        """List resources within one explicit tenant boundary."""

        queryset = AIProviderConfigurationResource.objects.filter(tenant_id=tenant_id)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return list(queryset)

    @transaction.atomic
    def update_resource(
        self,
        resource_id: str,
        tenant_id: str,
        **updates: object,
    ) -> AIProviderConfigurationResource | None:
        """Update only mutable resource fields without changing ownership."""

        resource = AIProviderConfigurationResource.objects.select_for_update().filter(
            pk=resource_id,
            tenant_id=tenant_id,
        ).first()
        if resource is None:
            return None
        editable = {"name", "description", "config", "is_active"}
        for field, value in updates.items():
            if field not in editable:
                continue
            if field == "name":
                value = _text(value, "name", maximum=255)  # type: ignore[arg-type]
            elif field == "description":
                value = _text(value, "description", maximum=100_000, allow_blank=True)  # type: ignore[arg-type]
            elif field == "config":
                if not isinstance(value, Mapping):
                    raise ValidationError({"config": "Must be an object."})
                value = dict(value)
            elif field == "is_active" and not isinstance(value, bool):
                raise ValidationError({"is_active": "Must be a boolean."})
            setattr(resource, field, value)
        _clean(resource)
        resource.save()
        return resource

    @transaction.atomic
    def delete_resource(self, resource_id: str, tenant_id: str) -> bool:
        """Delete a resource only from its owning tenant."""

        deleted, _ = AIProviderConfigurationResource.objects.filter(
            pk=resource_id,
            tenant_id=tenant_id,
        ).delete()
        return deleted == 1

    def activate_resource(
        self,
        resource_id: str,
        tenant_id: str,
    ) -> AIProviderConfigurationResource | None:
        return self.update_resource(resource_id, tenant_id, is_active=True)

    def deactivate_resource(
        self,
        resource_id: str,
        tenant_id: str,
    ) -> AIProviderConfigurationResource | None:
        return self.update_resource(resource_id, tenant_id, is_active=False)

    @staticmethod
    def generate_rotation_key() -> str:
        """Generate real Fernet key material for an operator-led rotation."""

        return EncryptionService.rotate_key()

    @transaction.atomic
    def create_credential(
        self,
        tenant_id: UUID | str,
        *,
        provider_id: UUID | str,
        api_key: str,
        label: str = "Default",
    ) -> AIProviderCredential:
        tenant_id = _uuid(tenant_id, "tenant_id")
        provider = AIProvider.objects.filter(pk=_uuid(provider_id, "provider"), is_active=True).first()
        if provider is None:
            raise ValidationError({"provider": "An active provider is required."})
        secret = _text(api_key, "api_key", maximum=20_000)
        credential = AIProviderCredential(
            tenant_id=tenant_id,
            provider=provider,
            label=_text(label, "label", maximum=120),
            api_key_encrypted=EncryptionService.encrypt(secret),
            secret_hint=secret[-4:],
        )
        _clean(credential)
        credential.save()
        return credential

    @transaction.atomic
    def update_credential(
        self,
        tenant_id: UUID | str,
        credential_id: UUID | str,
        *,
        provider_id: UUID | str | None = None,
        api_key: str | None = None,
        label: str | None = None,
    ) -> AIProviderCredential:
        tenant_id = _uuid(tenant_id, "tenant_id")
        credential = (
            AIProviderCredential.objects.for_tenant(tenant_id)
            .select_for_update()
            .filter(pk=_uuid(credential_id, "credential_id"), is_deleted=False)
            .first()
        )
        if credential is None:
            raise NotFound()
        if provider_id is not None:
            provider = AIProvider.objects.filter(pk=_uuid(provider_id, "provider"), is_active=True).first()
            if provider is None:
                raise ValidationError({"provider": "An active provider is required."})
            if AIModelDeployment.objects.for_tenant(tenant_id).filter(
                credential=credential, is_deleted=False
            ).exclude(model__provider=provider).exists():
                raise ValidationError({"provider": "Provider cannot change while incompatible deployments use it."})
            credential.provider = provider
        if label is not None:
            credential.label = _text(label, "label", maximum=120)
        if api_key is not None:
            secret = _text(api_key, "api_key", maximum=20_000)
            credential.api_key_encrypted = EncryptionService.encrypt(secret)
            credential.secret_hint = secret[-4:]
            credential.status = CredentialStatus.UNVERIFIED
            credential.last_verified_at = None
            credential.last_error_code = ""
        _clean(credential)
        credential.save()
        return credential

    @transaction.atomic
    def delete_credential(self, tenant_id: UUID | str, credential_id: UUID | str) -> None:
        tenant_id = _uuid(tenant_id, "tenant_id")
        credential = (
            AIProviderCredential.objects.for_tenant(tenant_id)
            .select_for_update()
            .filter(pk=_uuid(credential_id, "credential_id"), is_deleted=False)
            .first()
        )
        if credential is None:
            raise NotFound()
        if AIModelDeployment.objects.for_tenant(tenant_id).filter(
            credential=credential, is_deleted=False, status=DeploymentStatus.ACTIVE
        ).exists():
            raise ValidationError({"credential": "Deactivate dependent deployments before archiving this credential."})
        credential.is_deleted = True
        credential.deleted_at = timezone.now()
        credential.save(update_fields=("is_deleted", "deleted_at", "updated_at"))

    @transaction.atomic
    def create_deployment(
        self,
        tenant_id: UUID | str,
        actor_id: UUID | str,
        *,
        model_id: UUID | str,
        deployment_name: str,
        config: Mapping[str, object] | None = None,
        credential_id: UUID | str | None = None,
        status: str = DeploymentStatus.ACTIVE,
    ) -> AIModelDeployment:
        tenant_id = _uuid(tenant_id, "tenant_id")
        actor_id = _text(str(actor_id), "actor_id", maximum=36)
        model = AIModel.objects.select_related("provider").filter(pk=_uuid(model_id, "model"), is_active=True).first()
        if model is None:
            raise ValidationError({"model": "An active model is required."})
        credential = None
        if credential_id is not None:
            credential = AIProviderCredential.objects.for_tenant(tenant_id).filter(
                pk=_uuid(credential_id, "credential"), provider=model.provider, is_deleted=False
            ).first()
            if credential is None:
                raise ValidationError({"credential": "A credential for the model provider is required."})
        deployment = AIModelDeployment(
            tenant_id=tenant_id,
            model=model,
            credential=credential,
            deployment_name=_text(deployment_name, "deployment_name", maximum=255),
            config=dict(config or {}),
            status=status,
            created_by=actor_id,
        )
        _clean(deployment)
        deployment.save()
        return deployment

    @transaction.atomic
    def update_deployment(
        self,
        tenant_id: UUID | str,
        deployment_id: UUID | str,
        **changes: object,
    ) -> AIModelDeployment:
        tenant_id = _uuid(tenant_id, "tenant_id")
        deployment = (
            AIModelDeployment.objects.for_tenant(tenant_id)
            .select_for_update()
            .select_related("model__provider", "credential")
            .filter(pk=_uuid(deployment_id, "deployment_id"), is_deleted=False)
            .first()
        )
        if deployment is None:
            raise NotFound()
        if "model_id" in changes:
            model = AIModel.objects.select_related("provider").filter(
                pk=_uuid(changes["model_id"], "model"), is_active=True
            ).first()
            if model is None:
                raise ValidationError({"model": "An active model is required."})
            deployment.model = model
        if "credential_id" in changes:
            raw_credential = changes["credential_id"]
            if raw_credential is None:
                deployment.credential = None
            else:
                credential = AIProviderCredential.objects.for_tenant(tenant_id).filter(
                    pk=_uuid(raw_credential, "credential"), provider=deployment.model.provider, is_deleted=False
                ).first()
                if credential is None:
                    raise ValidationError({"credential": "A credential for the model provider is required."})
                deployment.credential = credential
        if "deployment_name" in changes:
            deployment.deployment_name = _text(changes["deployment_name"], "deployment_name", maximum=255)  # type: ignore[arg-type]
        if "config" in changes:
            value = changes["config"]
            if not isinstance(value, Mapping):
                raise ValidationError({"config": "Must be an object."})
            deployment.config = dict(value)
        if "status" in changes:
            deployment.status = str(changes["status"])
        _clean(deployment)
        deployment.save()
        return deployment

    @transaction.atomic
    def delete_deployment(self, tenant_id: UUID | str, deployment_id: UUID | str) -> None:
        tenant_id = _uuid(tenant_id, "tenant_id")
        deployment = AIModelDeployment.objects.for_tenant(tenant_id).select_for_update().filter(
            pk=_uuid(deployment_id, "deployment_id"), is_deleted=False
        ).first()
        if deployment is None:
            raise NotFound()
        deployment.status = DeploymentStatus.INACTIVE
        deployment.is_deleted = True
        deployment.deleted_at = timezone.now()
        deployment.save(update_fields=("status", "is_deleted", "deleted_at", "updated_at"))

    @transaction.atomic
    def re_encrypt_credentials(self, tenant_id: UUID | str, *, old_key: str, new_key: str) -> RotationResult:
        tenant_id = _uuid(tenant_id, "tenant_id")
        old_key = _text(old_key, "old_key", maximum=1_000)
        new_key = _text(new_key, "new_key", maximum=1_000)
        credentials = list(
            AIProviderCredential.objects.for_tenant(tenant_id).select_for_update().filter(is_deleted=False)
        )
        for credential in credentials:
            credential.api_key_encrypted = EncryptionService.re_encrypt(
                credential.api_key_encrypted,
                old_key,
                new_key,
            )
            credential.save(update_fields=("api_key_encrypted", "updated_at"))
        return RotationResult(rotated_count=len(credentials))


class AIUsageService:
    """Append verified provider-metering evidence."""

    @transaction.atomic
    def record_usage(
        self,
        tenant_id: UUID | str,
        *,
        deployment_id: UUID | str,
        prompt_tokens: int,
        completion_tokens: int,
        cost: Decimal | str,
        currency: str = "USD",
        provider_request_id: str = "",
    ) -> AIUsageLog:
        tenant_id = _uuid(tenant_id, "tenant_id")
        deployment = AIModelDeployment.objects.for_tenant(tenant_id).filter(
            pk=_uuid(deployment_id, "deployment_id"), is_deleted=False
        ).first()
        if deployment is None:
            raise NotFound()
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in (prompt_tokens, completion_tokens)):
            raise ValidationError({"tokens": "Token counts must be non-negative integers."})
        try:
            normalized_cost = Decimal(str(cost))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError({"cost": "A valid decimal amount is required."}) from exc
        usage = AIUsageLog(
            tenant_id=tenant_id,
            deployment=deployment,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost=normalized_cost,
            currency=_text(currency, "currency", maximum=3).upper(),
            provider_request_id=_text(
                provider_request_id, "provider_request_id", maximum=255, allow_blank=True
            ),
        )
        _clean(usage)
        usage.save()
        return usage


# Compatibility alias for callers that used the old service spelling.
AiProviderConfigurationService = AIProviderConfigurationService


__all__ = [
    "AIProviderConfigurationService",
    "AIProviderFactory",
    "AIProviderService",
    "AIUsageService",
    "AiProviderConfigurationService",
    "AnthropicProvider",
    "GoogleGeminiProvider",
    "GroqProvider",
    "HuggingFaceProvider",
    "InvalidProviderResponse",
    "OpenAIProvider",
    "ProviderUnavailable",
]
