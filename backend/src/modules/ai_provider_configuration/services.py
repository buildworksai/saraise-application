"""Tenant-safe business services and resilient provider adapters."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from src.core.encryption import EncryptionService
from src.core.observability import get_correlation_id
from src.core.resilience.circuit_breaker import CircuitBreakerError
from src.core.resilience.http import ResilientHttpClient, ResilientHttpError

from .models import (
    AIModel,
    AIModelDeployment,
    AIProvider,
    AIProviderConfigurationResource,
    AIProviderCredential,
    AIProviderIdempotencyKey,
    AIProviderRuntimeConfiguration,
    AIProviderRuntimeConfigurationAudit,
    AIProviderRuntimeConfigurationVersion,
    AIUsageLog,
    CredentialStatus,
    DeploymentStatus,
    ProviderType,
)

logger = logging.getLogger("saraise.ai_provider_configuration")


DEFAULT_RUNTIME_CONFIGURATION: dict[str, object] = {
    "provider_types": ["openai", "anthropic", "google", "groq", "mistral", "huggingface", "azure", "custom"],
    "provider_defaults": {"is_active": True, "api_version_by_type": {"azure": "2024-10-21", "anthropic": "2023-06-01"}},
    "provider_endpoints": {
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "google": "https://generativelanguage.googleapis.com/v1beta",
        "groq": "https://api.groq.com/openai/v1",
        "mistral": "https://api.mistral.ai/v1",
        "huggingface": "https://api-inference.huggingface.co",
    },
    "field_limits": {
        "provider_name_max": 255,
        "provider_type_max": 50,
        "provider_base_url_max": 500,
        "provider_api_version_max": 50,
        "resource_name_max": 255,
        "resource_description_max": 100000,
        "credential_label_max": 120,
        "credential_api_key_max": 20000,
        "credential_secret_hint_length": 4,
        "credential_error_code_max": 80,
        "deployment_name_max": 255,
        "rotation_key_max": 1000,
        "prompt_max": 1000000,
        "model_identifier_max": 255,
        "provider_request_id_max": 255,
        "actor_identifier_max": 36,
        "search_provider_max": 255,
        "search_credential_max": 120,
        "search_model_max": 255,
        "search_deployment_max": 255,
    },
    "credential_policy": {
        "default_label": "Default",
        "permitted_deployment_statuses": ["valid"],
        "archive_requires_no_active_deployments": True,
    },
    "deployment_policy": {
        "default_status": "active",
        "allow_without_credential": False,
        "editable_config_fields": ["temperature", "max_tokens", "top_p", "timeout_seconds"],
        "allowed_status_transitions": {"active": ["inactive"], "inactive": ["active"], "error": ["inactive"]},
        "defaults": {"max_tokens": 1000, "temperature": 0.7},
        "limits": {"max_tokens_min": 1, "max_tokens_max": 1000000, "temperature_min": 0.0, "temperature_max": 2.0},
    },
    "resilience": {
        "connect_timeout_seconds": 5.0,
        "read_timeout_seconds": 30.0,
        "max_retries": 2,
        "retry_backoff_seconds": 0.1,
        "failure_threshold": 3,
        "reset_timeout_seconds": 60.0,
    },
    "catalog_visibility": {"providers_active_only": True, "models_active_only": True},
    "resource_policy": {
        "default_description": "",
        "default_config": {},
        "default_is_active": True,
        "editable_fields": ["name", "description", "config", "is_active"],
        "allowed_config_keys": ["owner", "purpose", "retention_days", "metadata"],
    },
    "metering": {
        "default_currency": "USD",
        "currency_allowlist": ["USD", "EUR", "GBP", "INR"],
        "currency_code_length": 3,
        "cost_max_digits": 14,
        "cost_decimal_places": 6,
    },
    "pagination": {"default_page_size": 25, "max_page_size": 100},
    "presentation": {
        "identifier_prefix_length": 8,
        "model_capability_display_limit": 4,
        "copied_indicator_timeout_ms": 2000,
        "cost_fraction_digits_min": 2,
        "cost_fraction_digits_max": 6,
    },
    "rate_limits": {"tenant_requests_per_minute": 120},
    "feature_flags": {"configuration_ui": True, "provider_catalog": True, "secret_rotation": True},
    "rollout": {"enabled": True, "roles": [], "cohorts": []},
}


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


def _deep_copy(values: Mapping[str, object]) -> dict[str, object]:
    return json.loads(json.dumps(dict(values), allow_nan=False))


def _json_fingerprint(values: Mapping[str, object]) -> str:
    serialized = json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _correlation_uuid() -> UUID:
    value = get_correlation_id()
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return uuid.uuid4()


def _environment(value: object | None = None) -> str:
    raw = value if value is not None else getattr(settings, "SARAISE_ENVIRONMENT", "default")
    normalized = str(raw).strip().lower()
    if not normalized or len(normalized) > 64 or not normalized.replace("-", "").replace("_", "").isalnum():
        raise ValidationError({"environment": "Must be a bounded slug."})
    return normalized


def _section(values: Mapping[str, object], key: str) -> dict[str, object]:
    section = values.get(key)
    if not isinstance(section, Mapping):
        raise ValidationError({key: "Configuration section is invalid."})
    return dict(section)


class AIProviderRuntimeConfigurationService:
    """Validate, version, audit, import/export and resolve tenant runtime policy."""

    @classmethod
    def runtime_values(cls, tenant_id: UUID | str | None, environment: str | None = None) -> dict[str, object]:
        if tenant_id is None:
            return cls.validate_values(DEFAULT_RUNTIME_CONFIGURATION)
        tenant_uuid = _uuid(tenant_id, "tenant_id")
        env = _environment(environment)
        stored = (
            AIProviderRuntimeConfiguration.objects.filter(tenant_id=tenant_uuid, environment=env)
            .values_list("values", flat=True)
            .first()
        )
        return cls.validate_values(stored if stored is not None else DEFAULT_RUNTIME_CONFIGURATION)

    @classmethod
    def validate_values(cls, supplied: Mapping[str, object]) -> dict[str, object]:
        if not isinstance(supplied, Mapping):
            raise ValidationError({"values": "Configuration document must be an object."})
        expected = set(DEFAULT_RUNTIME_CONFIGURATION)
        received = set(supplied)
        missing = sorted(expected - received)
        unknown = sorted(received - expected)
        if missing or unknown:
            detail: dict[str, object] = {}
            if missing:
                detail["missing_fields"] = missing
            if unknown:
                detail["unknown_fields"] = unknown
            raise ValidationError(detail)
        values = _deep_copy(supplied)
        errors: dict[str, list[str]] = {}

        provider_types = values["provider_types"]
        if (
            not isinstance(provider_types, list)
            or not provider_types
            or not all(isinstance(item, str) and item for item in provider_types)
            or len(set(provider_types)) != len(provider_types)
        ):
            errors["provider_types"] = ["Must be a unique non-empty provider allow-list."]

        endpoints = values["provider_endpoints"]
        if not isinstance(endpoints, dict):
            errors["provider_endpoints"] = ["Must be an object."]
        elif isinstance(provider_types, list):
            for provider_type, url in endpoints.items():
                if provider_type not in provider_types or not isinstance(url, str) or not url.startswith("https://"):
                    errors["provider_endpoints"] = ["Every endpoint must be HTTPS and keyed by an allowed provider."]
                    break

        numeric_bounds = {
            ("field_limits", "provider_name_max"): (1, 500),
            ("field_limits", "provider_type_max"): (1, 100),
            ("field_limits", "provider_base_url_max"): (1, 1000),
            ("field_limits", "provider_api_version_max"): (1, 100),
            ("field_limits", "resource_name_max"): (1, 500),
            ("field_limits", "resource_description_max"): (0, 200000),
            ("field_limits", "credential_label_max"): (1, 255),
            ("field_limits", "credential_api_key_max"): (8, 50000),
            ("field_limits", "credential_secret_hint_length"): (1, 16),
            ("field_limits", "credential_error_code_max"): (1, 200),
            ("field_limits", "deployment_name_max"): (1, 500),
            ("field_limits", "rotation_key_max"): (44, 5000),
            ("field_limits", "prompt_max"): (1, 2000000),
            ("field_limits", "model_identifier_max"): (1, 500),
            ("field_limits", "provider_request_id_max"): (1, 500),
            ("field_limits", "actor_identifier_max"): (1, 64),
            ("field_limits", "search_provider_max"): (1, 500),
            ("field_limits", "search_credential_max"): (1, 255),
            ("field_limits", "search_model_max"): (1, 500),
            ("field_limits", "search_deployment_max"): (1, 500),
            ("deployment_policy", "limits.max_tokens_min"): (1, 1000000),
            ("deployment_policy", "limits.max_tokens_max"): (1, 2000000),
            ("pagination", "default_page_size"): (1, 500),
            ("pagination", "max_page_size"): (1, 500),
            ("presentation", "identifier_prefix_length"): (4, 36),
            ("presentation", "model_capability_display_limit"): (1, 20),
            ("presentation", "copied_indicator_timeout_ms"): (250, 10000),
            ("presentation", "cost_fraction_digits_min"): (0, 6),
            ("presentation", "cost_fraction_digits_max"): (0, 6),
            ("rate_limits", "tenant_requests_per_minute"): (1, 10000),
        }
        for (section_name, dotted_key), (minimum, maximum) in numeric_bounds.items():
            section = _section(values, section_name)
            current: object = section
            for part in dotted_key.split("."):
                current = current.get(part) if isinstance(current, Mapping) else None
            if isinstance(current, bool) or not isinstance(current, int) or not minimum <= current <= maximum:
                errors[f"{section_name}.{dotted_key}"] = [f"Must be an integer between {minimum} and {maximum}."]

        resilience = _section(values, "resilience")
        for field, minimum, maximum in (
            ("connect_timeout_seconds", 0.1, 60.0),
            ("read_timeout_seconds", 0.1, 300.0),
            ("retry_backoff_seconds", 0.0, 30.0),
            ("reset_timeout_seconds", 1.0, 3600.0),
        ):
            number = resilience.get(field)
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not minimum <= float(number) <= maximum:
                errors[f"resilience.{field}"] = [f"Must be a number between {minimum} and {maximum}."]
        if isinstance(resilience.get("max_retries"), bool) or not isinstance(resilience.get("max_retries"), int) or not 1 <= int(resilience.get("max_retries", 0)) <= 10:
            errors["resilience.max_retries"] = ["Must be an integer from 1 to 10."]
        if isinstance(resilience.get("failure_threshold"), bool) or not isinstance(resilience.get("failure_threshold"), int) or not 1 <= int(resilience.get("failure_threshold", 0)) <= 100:
            errors["resilience.failure_threshold"] = ["Must be an integer from 1 to 100."]

        deployment = _section(values, "deployment_policy")
        limits = deployment.get("limits")
        defaults = deployment.get("defaults")
        editable_fields = deployment.get("editable_config_fields")
        if not isinstance(limits, Mapping) or not isinstance(defaults, Mapping):
            errors["deployment_policy"] = ["Must define limits and defaults."]
        else:
            if int(limits["max_tokens_min"]) > int(limits["max_tokens_max"]):
                errors["deployment_policy.limits"] = ["max_tokens_min must not exceed max_tokens_max."]
            if not int(limits["max_tokens_min"]) <= int(defaults["max_tokens"]) <= int(limits["max_tokens_max"]):
                errors["deployment_policy.defaults.max_tokens"] = ["Must be within token limits."]
            if not float(limits["temperature_min"]) <= float(defaults["temperature"]) <= float(limits["temperature_max"]):
                errors["deployment_policy.defaults.temperature"] = ["Must be within temperature limits."]
        if not isinstance(editable_fields, list) or not set(editable_fields).issubset(
            {"temperature", "max_tokens", "top_p", "timeout_seconds"}
        ):
            errors["deployment_policy.editable_config_fields"] = ["Contains unsupported deployment config fields."]
        if deployment.get("default_status") not in {choice.value for choice in DeploymentStatus}:
            errors["deployment_policy.default_status"] = ["Must be a supported deployment status."]

        credential = _section(values, "credential_policy")
        allowed_statuses = credential.get("permitted_deployment_statuses")
        if not isinstance(allowed_statuses, list) or not set(allowed_statuses).issubset(
            {choice.value for choice in CredentialStatus}
        ):
            errors["credential_policy.permitted_deployment_statuses"] = ["Must use supported credential statuses."]

        metering = _section(values, "metering")
        currencies = metering.get("currency_allowlist")
        if not isinstance(currencies, list) or not currencies or any(
            not isinstance(item, str) or len(item) != 3 or item.upper() != item for item in currencies
        ):
            errors["metering.currency_allowlist"] = ["Must contain uppercase ISO-like currency codes."]
        elif metering.get("default_currency") not in currencies:
            errors["metering.default_currency"] = ["Must be present in currency_allowlist."]

        feature_flags = values["feature_flags"]
        if not isinstance(feature_flags, dict) or set(feature_flags) != {"configuration_ui", "provider_catalog", "secret_rotation"} or not all(isinstance(enabled, bool) for enabled in feature_flags.values()):
            errors["feature_flags"] = ["Must define supported feature flags as booleans."]
        rollout = values["rollout"]
        if not isinstance(rollout, dict) or set(rollout) != {"enabled", "roles", "cohorts"}:
            errors["rollout"] = ["Must contain enabled, roles and cohorts."]

        if errors:
            raise ValidationError(errors)
        return values

    @classmethod
    def current(cls, tenant_id: UUID | str, actor_id: UUID | str, environment: str | None = None) -> AIProviderRuntimeConfiguration:
        tenant_uuid = _uuid(tenant_id, "tenant_id")
        actor_uuid = _uuid(actor_id, "actor_id")
        env = _environment(environment)
        with transaction.atomic():
            configuration = (
                AIProviderRuntimeConfiguration.objects.select_for_update()
                .filter(tenant_id=tenant_uuid, environment=env)
                .first()
            )
            if configuration is not None:
                return configuration
            values = cls.validate_values(DEFAULT_RUNTIME_CONFIGURATION)
            configuration = AIProviderRuntimeConfiguration.objects.create(
                tenant_id=tenant_uuid,
                environment=env,
                values=values,
                version=1,
                updated_by=actor_uuid,
            )
            correlation_id = _correlation_uuid()
            AIProviderRuntimeConfigurationVersion.objects.create(
                tenant_id=tenant_uuid,
                configuration=configuration,
                version=1,
                environment=env,
                values=values,
                created_by=actor_uuid,
                correlation_id=correlation_id,
            )
            AIProviderRuntimeConfigurationAudit.objects.create(
                tenant_id=tenant_uuid,
                configuration=configuration,
                action="created",
                actor_id=actor_uuid,
                correlation_id=correlation_id,
                from_version=None,
                to_version=1,
                before={},
                after=values,
            )
            return configuration

    @classmethod
    def preview(cls, tenant_id: UUID | str, actor_id: UUID | str, values: Mapping[str, object], environment: str | None = None) -> dict[str, object]:
        current = cls.current(tenant_id, actor_id, environment)
        proposed = cls.validate_values(values)
        return {
            "environment": current.environment,
            "current_version": current.version,
            "would_create_version": current.version + 1,
            "changes": {
                key: {"before": current.values.get(key), "after": proposed.get(key)}
                for key in sorted(proposed)
                if current.values.get(key) != proposed.get(key)
            },
        }

    @classmethod
    def update(cls, tenant_id: UUID | str, actor_id: UUID | str, values: Mapping[str, object], environment: str | None = None, *, action: str = "updated", rollback_of: int | None = None) -> AIProviderRuntimeConfiguration:
        tenant_uuid = _uuid(tenant_id, "tenant_id")
        actor_uuid = _uuid(actor_id, "actor_id")
        proposed = cls.validate_values(values)
        with transaction.atomic():
            configuration = cls.current(tenant_uuid, actor_uuid, environment)
            locked = AIProviderRuntimeConfiguration.objects.select_for_update().get(pk=configuration.pk)
            before = _deep_copy(locked.values)
            next_version = locked.version + 1
            locked.values = proposed
            locked.version = next_version
            locked.updated_by = actor_uuid
            locked.save(update_fields=("values", "version", "updated_by", "updated_at"))
            correlation_id = _correlation_uuid()
            AIProviderRuntimeConfigurationVersion.objects.create(
                tenant_id=tenant_uuid,
                configuration=locked,
                version=next_version,
                environment=locked.environment,
                values=proposed,
                created_by=actor_uuid,
                correlation_id=correlation_id,
                rollback_of=rollback_of,
            )
            AIProviderRuntimeConfigurationAudit.objects.create(
                tenant_id=tenant_uuid,
                configuration=locked,
                action=action,
                actor_id=actor_uuid,
                correlation_id=correlation_id,
                from_version=next_version - 1,
                to_version=next_version,
                before=before,
                after=proposed,
                rollback_of=rollback_of,
            )
            return locked

    @classmethod
    def rollback(cls, tenant_id: UUID | str, actor_id: UUID | str, version: int, environment: str | None = None) -> AIProviderRuntimeConfiguration:
        configuration = cls.current(tenant_id, actor_id, environment)
        target = configuration.versions.filter(version=version).first()
        if target is None:
            raise NotFound("Configuration version was not found.")
        return cls.update(tenant_id, actor_id, target.values, environment, action="rolled_back", rollback_of=version)

    @classmethod
    def export(cls, tenant_id: UUID | str, actor_id: UUID | str, environment: str | None = None) -> dict[str, object]:
        configuration = cls.current(tenant_id, actor_id, environment)
        return {
            "module": "ai_provider_configuration",
            "environment": configuration.environment,
            "version": configuration.version,
            "values": _deep_copy(configuration.values),
        }

    @classmethod
    def import_document(cls, tenant_id: UUID | str, actor_id: UUID | str, document: Mapping[str, object]) -> AIProviderRuntimeConfiguration:
        if document.get("module") != "ai_provider_configuration":
            raise ValidationError({"module": "Unsupported configuration document."})
        return cls.update(
            tenant_id,
            actor_id,
            cls.validate_values(document.get("values", {})),  # type: ignore[arg-type]
            str(document.get("environment", "default")),
            action="imported",
        )


class AIProviderService(ABC):
    """Provider-neutral synchronous completion contract."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        dependency: str,
        policy: Mapping[str, object] | None = None,
        http_client: ResilientHttpClient | None = None,
    ) -> None:
        if not api_key:
            raise ProviderUnavailable("Provider credential is empty.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.dependency = dependency
        self.policy = AIProviderRuntimeConfigurationService.validate_values(policy or DEFAULT_RUNTIME_CONFIGURATION)
        self.http_client = http_client or self._build_http_client()

    def _build_http_client(self) -> ResilientHttpClient:
        host = urlsplit(self.base_url).hostname
        if not host:
            raise ProviderUnavailable("Provider base URL is invalid.")
        resilience = _section(self.policy, "resilience")
        return ResilientHttpClient(
            dependency_allowlist={
                self.dependency: {
                    "base_url": self.base_url,
                    "allowed_hosts": [host],
                }
            },
            connect_timeout=float(resilience["connect_timeout_seconds"]),
            read_timeout=float(resilience["read_timeout_seconds"]),
            max_retries=int(resilience["max_retries"]),
            retry_backoff=float(resilience["retry_backoff_seconds"]),
            failure_threshold=int(resilience["failure_threshold"]),
            reset_timeout=float(resilience["reset_timeout_seconds"]),
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
                headers={**dict(headers), "Idempotency-Key": str(_correlation_uuid())},
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

    def _validate_request(self, prompt: str, model: str, max_tokens: int, temperature: float) -> tuple[str, str]:
        fields = _section(self.policy, "field_limits")
        deployment = _section(self.policy, "deployment_policy")
        limits = deployment["limits"]
        if not isinstance(limits, Mapping):
            raise ValidationError({"deployment_policy": "Deployment limits are invalid."})
        prompt = _text(prompt, "prompt", maximum=int(fields["prompt_max"]))
        model = _text(model, "model", maximum=int(fields["model_identifier_max"]))
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not int(limits["max_tokens_min"]) <= max_tokens <= int(limits["max_tokens_max"]):
            raise ValidationError({"max_tokens": "Violates tenant deployment token limits."})
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not float(limits["temperature_min"]) <= float(temperature) <= float(limits["temperature_max"]):
            raise ValidationError({"temperature": "Violates tenant deployment temperature limits."})
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
        policy = AIProviderRuntimeConfigurationService.validate_values(kwargs.get("policy") or DEFAULT_RUNTIME_CONFIGURATION)
        endpoints = _section(policy, "provider_endpoints")
        super().__init__(
            api_key,
            base_url or str(endpoints["openai"]),
            dependency=str(kwargs.pop("dependency", "ai-provider-openai")),
            **kwargs,
        )


class GroqProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, base_url: str | None = None, **kwargs: Any) -> None:
        policy = AIProviderRuntimeConfigurationService.validate_values(kwargs.get("policy") or DEFAULT_RUNTIME_CONFIGURATION)
        endpoints = _section(policy, "provider_endpoints")
        super().__init__(
            api_key,
            base_url or str(endpoints["groq"]),
            dependency=str(kwargs.pop("dependency", "ai-provider-groq")),
            **kwargs,
        )


class MistralProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, base_url: str | None = None, **kwargs: Any) -> None:
        policy = AIProviderRuntimeConfigurationService.validate_values(kwargs.get("policy") or DEFAULT_RUNTIME_CONFIGURATION)
        endpoints = _section(policy, "provider_endpoints")
        super().__init__(
            api_key,
            base_url or str(endpoints["mistral"]),
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
        api_version: str | None = None,
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
        defaults = _section(self.policy, "provider_defaults")
        versions = defaults.get("api_version_by_type", {})
        self.api_version = api_version or (str(versions.get("azure")) if isinstance(versions, Mapping) else "")

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
        policy = AIProviderRuntimeConfigurationService.validate_values(kwargs.get("policy") or DEFAULT_RUNTIME_CONFIGURATION)
        endpoints = _section(policy, "provider_endpoints")
        super().__init__(
            api_key,
            base_url or str(endpoints["anthropic"]),
            dependency=str(kwargs.pop("dependency", "ai-provider-anthropic")),
            **kwargs,
        )

    def complete(self, prompt: str, model: str, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        prompt, model = self._validate_request(prompt, model, max_tokens, temperature)
        body = self._post(
            "messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": self._anthropic_version(),
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

    def _anthropic_version(self) -> str:
        versions = _section(self.policy, "provider_defaults").get("api_version_by_type", {})
        if not isinstance(versions, Mapping) or not versions.get("anthropic"):
            raise ProviderUnavailable("Anthropic API version is not configured.")
        return str(versions["anthropic"])


class GoogleGeminiProvider(AIProviderService):
    def __init__(self, api_key: str, base_url: str | None = None, **kwargs: Any) -> None:
        policy = AIProviderRuntimeConfigurationService.validate_values(kwargs.get("policy") or DEFAULT_RUNTIME_CONFIGURATION)
        endpoints = _section(policy, "provider_endpoints")
        super().__init__(
            api_key,
            base_url or str(endpoints["google"]),
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
        policy = AIProviderRuntimeConfigurationService.validate_values(kwargs.get("policy") or DEFAULT_RUNTIME_CONFIGURATION)
        endpoints = _section(policy, "provider_endpoints")
        super().__init__(
            api_key,
            base_url or str(endpoints["huggingface"]),
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
        policy = AIProviderRuntimeConfigurationService.runtime_values(tenant_id)
        credential_policy = _section(policy, "credential_policy")
        permitted_statuses = credential_policy["permitted_deployment_statuses"]
        credential = (
            AIProviderCredential.objects.for_tenant(tenant_id)
            .select_related("provider")
            .filter(
                provider__provider_type=provider_type,
                provider__is_active=True,
                is_deleted=False,
                status__in=permitted_statuses,
            )
            .order_by("created_at")
            .first()
        )
        if credential is None:
            raise ProviderUnavailable("No active credential is configured for this provider.")
        provider = credential.provider
        adapter_type = cls.adapter_types.get(provider.provider_type)
        if adapter_type is None:
            raise ProviderUnavailable("Provider type is not supported.")
        endpoints = _section(policy, "provider_endpoints")
        base_url = provider.base_url or str(endpoints.get(provider.provider_type, ""))
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
            "policy": policy,
            "http_client": http_client,
        }
        if adapter_type is AzureOpenAIProvider:
            defaults = _section(policy, "provider_defaults")
            versions = defaults.get("api_version_by_type", {})
            kwargs["api_version"] = provider.api_version or (versions.get("azure") if isinstance(versions, Mapping) else "")
        return adapter_type(api_key, base_url, **kwargs)


@dataclass(frozen=True, slots=True)
class RotationResult:
    rotated_count: int


class AIProviderConfigurationService:
    """Authoritative mutation surface for tenant configuration."""

    @staticmethod
    def validate_resource_config(policy: Mapping[str, object], value: object) -> dict[str, object]:
        if not isinstance(value, Mapping):
            raise ValidationError({"config": "Must be an object."})
        resource_policy = _section(policy, "resource_policy")
        allowed = resource_policy.get("allowed_config_keys", [])
        if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
            raise ValidationError({"resource_policy.allowed_config_keys": "Must be a list of field names."})
        config = _deep_copy(value)
        unknown = sorted(set(config) - set(allowed))
        if unknown:
            raise ValidationError({"config": f"Unsupported fields: {', '.join(unknown)}."})
        return config

    @staticmethod
    def validate_deployment_config(policy: Mapping[str, object], value: Mapping[str, object]) -> dict[str, object]:
        if not isinstance(value, Mapping):
            raise ValidationError({"config": "Must be an object."})
        deployment = _section(policy, "deployment_policy")
        allowed = set(deployment["editable_config_fields"])
        config = _deep_copy(value)
        unknown = sorted(set(config) - allowed)
        if unknown:
            raise ValidationError({"config": f"Unsupported fields: {', '.join(unknown)}."})
        limits = deployment["limits"]
        defaults = deployment["defaults"]
        if not isinstance(limits, Mapping) or not isinstance(defaults, Mapping):
            raise ValidationError({"deployment_policy": "Deployment limits are invalid."})
        if "max_tokens" not in config:
            config["max_tokens"] = defaults["max_tokens"]
        if "temperature" not in config:
            config["temperature"] = defaults["temperature"]
        max_tokens = config.get("max_tokens")
        temperature = config.get("temperature")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not int(limits["max_tokens_min"]) <= max_tokens <= int(limits["max_tokens_max"]):
            raise ValidationError({"config.max_tokens": "Violates tenant token limits."})
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not float(limits["temperature_min"]) <= float(temperature) <= float(limits["temperature_max"]):
            raise ValidationError({"config.temperature": "Violates tenant temperature limits."})
        top_p = config.get("top_p")
        if top_p is not None and (isinstance(top_p, bool) or not isinstance(top_p, (int, float)) or not 0 <= float(top_p) <= 1):
            raise ValidationError({"config.top_p": "Must be a number from 0 to 1."})
        timeout = config.get("timeout_seconds")
        if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= float(timeout) <= 300):
            raise ValidationError({"config.timeout_seconds": "Must be a number from 0.1 to 300."})
        return config

    @staticmethod
    def _idempotency_replay(
        tenant_id: UUID,
        key: str,
        payload: Mapping[str, object],
        resource_type: str,
    ) -> UUID | None:
        digest = hashlib.sha256(_text(key, "idempotency_key", maximum=128).encode("utf-8")).hexdigest()
        fingerprint = _json_fingerprint(payload)
        existing = AIProviderIdempotencyKey.objects.for_tenant(tenant_id).filter(key_digest=digest).first()
        if existing is None:
            return None
        if existing.request_fingerprint != fingerprint or existing.resource_type != resource_type:
            raise ValidationError({"idempotency_key": "Key was already used for a different request."})
        return existing.resource_id

    @staticmethod
    def _record_idempotency(
        tenant_id: UUID,
        key: str,
        payload: Mapping[str, object],
        resource_type: str,
        resource_id: UUID,
    ) -> None:
        AIProviderIdempotencyKey.objects.create(
            tenant_id=tenant_id,
            key_digest=hashlib.sha256(_text(key, "idempotency_key", maximum=128).encode("utf-8")).hexdigest(),
            request_fingerprint=_json_fingerprint(payload),
            resource_type=resource_type,
            resource_id=resource_id,
            response={"id": str(resource_id)},
        )

    @transaction.atomic
    def create_resource(
        self,
        tenant_id: UUID | str,
        name: str,
        description: str | None = None,
        config: Mapping[str, object] | None = None,
        created_by: UUID | str = "",
        idempotency_key: str | None = None,
    ) -> AIProviderConfigurationResource:
        """Create a persisted resource for the original module contract."""

        tenant_uuid = _uuid(tenant_id, "tenant_id")
        actor_uuid = _uuid(created_by, "created_by")
        if not idempotency_key:
            raise ValidationError({"idempotency_key": "A tenant-scoped idempotency key is required."})
        policy = AIProviderRuntimeConfigurationService.runtime_values(tenant_uuid)
        fields = _section(policy, "field_limits")
        resource_policy = _section(policy, "resource_policy")
        payload = {
            "operation": "create_resource",
            "name": name,
            "description": description,
            "config": config or resource_policy["default_config"],
        }
        replay = self._idempotency_replay(tenant_uuid, idempotency_key, payload, "resource")
        if replay is not None:
            return AIProviderConfigurationResource.objects.for_tenant(tenant_uuid).get(pk=replay)
        resource = AIProviderConfigurationResource(
            tenant_id=tenant_uuid,
            name=_text(name, "name", maximum=int(fields["resource_name_max"])),
            description=_text(
                description if description is not None else str(resource_policy["default_description"]),
                "description",
                maximum=int(fields["resource_description_max"]),
                allow_blank=True,
            ),
            config=self.validate_resource_config(policy, config or resource_policy["default_config"]),
            is_active=bool(resource_policy["default_is_active"]),
            created_by=actor_uuid,
        )
        _clean(resource)
        resource.save()
        self._record_idempotency(tenant_uuid, idempotency_key, payload, "resource", resource.id)
        return resource

    def get_resource(self, resource_id: UUID | str, tenant_id: UUID | str) -> AIProviderConfigurationResource | None:
        """Return a resource only when it belongs to the requested tenant."""

        return AIProviderConfigurationResource.objects.for_tenant(_uuid(tenant_id, "tenant_id")).filter(
            pk=_uuid(resource_id, "resource_id"),
            is_deleted=False,
        ).first()

    def list_resources(
        self,
        tenant_id: UUID | str,
        is_active: bool | None = None,
    ) -> list[AIProviderConfigurationResource]:
        """List resources within one explicit tenant boundary."""

        queryset = AIProviderConfigurationResource.objects.for_tenant(_uuid(tenant_id, "tenant_id")).filter(
            is_deleted=False
        )
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return list(queryset)

    @transaction.atomic
    def update_resource(
        self,
        resource_id: str,
        tenant_id: UUID | str,
        **updates: object,
    ) -> AIProviderConfigurationResource | None:
        """Update only mutable resource fields without changing ownership."""

        tenant_uuid = _uuid(tenant_id, "tenant_id")
        policy = AIProviderRuntimeConfigurationService.runtime_values(tenant_uuid)
        fields = _section(policy, "field_limits")
        editable = set(_section(policy, "resource_policy")["editable_fields"])
        resource = AIProviderConfigurationResource.objects.for_tenant(tenant_uuid).select_for_update().filter(
            pk=_uuid(resource_id, "resource_id"),
            is_deleted=False,
        ).first()
        if resource is None:
            return None
        for field, value in updates.items():
            if field not in editable:
                continue
            if field == "name":
                value = _text(value, "name", maximum=int(fields["resource_name_max"]))  # type: ignore[arg-type]
            elif field == "description":
                value = _text(value, "description", maximum=int(fields["resource_description_max"]), allow_blank=True)  # type: ignore[arg-type]
            elif field == "config":
                value = self.validate_resource_config(policy, value)
            elif field == "is_active" and not isinstance(value, bool):
                raise ValidationError({"is_active": "Must be a boolean."})
            setattr(resource, field, value)
        _clean(resource)
        resource.save()
        return resource

    @transaction.atomic
    def delete_resource(self, resource_id: UUID | str, tenant_id: UUID | str) -> bool:
        """Reversibly archive a resource only from its owning tenant."""

        resource = AIProviderConfigurationResource.objects.for_tenant(_uuid(tenant_id, "tenant_id")).filter(
            pk=_uuid(resource_id, "resource_id"),
            is_deleted=False,
        ).first()
        if resource is None:
            return False
        resource.is_deleted = True
        resource.is_active = False
        resource.deleted_at = timezone.now()
        resource.save(update_fields=("is_deleted", "is_active", "deleted_at", "updated_at"))
        return True

    def activate_resource(
        self,
        resource_id: UUID | str,
        tenant_id: UUID | str,
    ) -> AIProviderConfigurationResource | None:
        return self.update_resource(resource_id, tenant_id, is_active=True)

    def deactivate_resource(
        self,
        resource_id: UUID | str,
        tenant_id: UUID | str,
    ) -> AIProviderConfigurationResource | None:
        return self.update_resource(resource_id, tenant_id, is_active=False)

    @transaction.atomic
    def restore_resource(self, resource_id: UUID | str, tenant_id: UUID | str) -> AIProviderConfigurationResource:
        """Restore a previously archived resource within its tenant boundary."""

        tenant_uuid = _uuid(tenant_id, "tenant_id")
        resource = AIProviderConfigurationResource.objects.for_tenant(tenant_uuid).select_for_update().filter(
            pk=_uuid(resource_id, "resource_id"),
            is_deleted=True,
        ).first()
        if resource is None:
            raise NotFound()
        resource.is_deleted = False
        resource.deleted_at = None
        resource.save(update_fields=("is_deleted", "deleted_at", "updated_at"))
        return resource

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
        label: str | None = None,
        idempotency_key: str | None = None,
    ) -> AIProviderCredential:
        tenant_id = _uuid(tenant_id, "tenant_id")
        if not idempotency_key:
            raise ValidationError({"idempotency_key": "A tenant-scoped idempotency key is required."})
        policy = AIProviderRuntimeConfigurationService.runtime_values(tenant_id)
        fields = _section(policy, "field_limits")
        credential_policy = _section(policy, "credential_policy")
        label_value = label if label is not None else str(credential_policy["default_label"])
        payload = {"operation": "create_credential", "provider_id": str(provider_id), "label": label_value}
        replay = self._idempotency_replay(tenant_id, idempotency_key, payload, "credential")
        if replay is not None:
            return AIProviderCredential.objects.for_tenant(tenant_id).get(pk=replay)
        provider = AIProvider.objects.filter(pk=_uuid(provider_id, "provider"), is_active=True).first()
        if provider is None:
            raise ValidationError({"provider": "An active provider is required."})
        secret = _text(api_key, "api_key", maximum=int(fields["credential_api_key_max"]))
        hint_length = int(fields["credential_secret_hint_length"])
        credential = AIProviderCredential(
            tenant_id=tenant_id,
            provider=provider,
            label=_text(label_value, "label", maximum=int(fields["credential_label_max"])),
            api_key_encrypted=EncryptionService.encrypt(secret),
            secret_hint=secret[-hint_length:],
        )
        _clean(credential)
        credential.save()
        self._record_idempotency(tenant_id, idempotency_key, payload, "credential", credential.id)
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
        policy = AIProviderRuntimeConfigurationService.runtime_values(tenant_id)
        fields = _section(policy, "field_limits")
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
            credential.label = _text(label, "label", maximum=int(fields["credential_label_max"]))
        if api_key is not None:
            secret = _text(api_key, "api_key", maximum=int(fields["credential_api_key_max"]))
            credential.api_key_encrypted = EncryptionService.encrypt(secret)
            credential.secret_hint = secret[-int(fields["credential_secret_hint_length"]):]
            credential.status = CredentialStatus.UNVERIFIED
            credential.last_verified_at = None
            credential.last_error_code = ""
        _clean(credential)
        credential.save()
        return credential

    @transaction.atomic
    def delete_credential(self, tenant_id: UUID | str, credential_id: UUID | str) -> None:
        tenant_id = _uuid(tenant_id, "tenant_id")
        policy = AIProviderRuntimeConfigurationService.runtime_values(tenant_id)
        credential_policy = _section(policy, "credential_policy")
        credential = (
            AIProviderCredential.objects.for_tenant(tenant_id)
            .select_for_update()
            .filter(pk=_uuid(credential_id, "credential_id"), is_deleted=False)
            .first()
        )
        if credential is None:
            raise NotFound()
        if bool(credential_policy["archive_requires_no_active_deployments"]) and AIModelDeployment.objects.for_tenant(tenant_id).filter(
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
        idempotency_key: str | None = None,
    ) -> AIModelDeployment:
        tenant_id = _uuid(tenant_id, "tenant_id")
        actor_uuid = _uuid(actor_id, "actor_id")
        if not idempotency_key:
            raise ValidationError({"idempotency_key": "A tenant-scoped idempotency key is required."})
        policy = AIProviderRuntimeConfigurationService.runtime_values(tenant_id)
        fields = _section(policy, "field_limits")
        deployment_policy = _section(policy, "deployment_policy")
        credential_policy = _section(policy, "credential_policy")
        status_value = str(deployment_policy["default_status"])
        payload = {
            "operation": "create_deployment",
            "model_id": str(model_id),
            "credential_id": str(credential_id) if credential_id else None,
            "deployment_name": deployment_name,
            "config": config or {},
            "status": status_value,
        }
        replay = self._idempotency_replay(tenant_id, idempotency_key, payload, "deployment")
        if replay is not None:
            return AIModelDeployment.objects.for_tenant(tenant_id).get(pk=replay)
        model = AIModel.objects.select_related("provider").filter(pk=_uuid(model_id, "model"), is_active=True).first()
        if model is None:
            raise ValidationError({"model": "An active model is required."})
        credential = None
        if credential_id is not None:
            credential = AIProviderCredential.objects.for_tenant(tenant_id).filter(
                pk=_uuid(credential_id, "credential"),
                provider=model.provider,
                is_deleted=False,
                status__in=credential_policy["permitted_deployment_statuses"],
            ).first()
            if credential is None:
                raise ValidationError({"credential": "A permitted, verified credential for the model provider is required."})
        elif not bool(deployment_policy["allow_without_credential"]):
            raise ValidationError({"credential": "A permitted credential is required by tenant policy."})
        deployment = AIModelDeployment(
            tenant_id=tenant_id,
            model=model,
            credential=credential,
            deployment_name=_text(deployment_name, "deployment_name", maximum=int(fields["deployment_name_max"])),
            config=self.validate_deployment_config(policy, config or {}),
            status=status_value,
            created_by=str(actor_uuid),
        )
        _clean(deployment)
        deployment.save()
        self._record_idempotency(tenant_id, idempotency_key, payload, "deployment", deployment.id)
        return deployment

    @transaction.atomic
    def update_deployment(
        self,
        tenant_id: UUID | str,
        deployment_id: UUID | str,
        **changes: object,
    ) -> AIModelDeployment:
        tenant_id = _uuid(tenant_id, "tenant_id")
        policy = AIProviderRuntimeConfigurationService.runtime_values(tenant_id)
        fields = _section(policy, "field_limits")
        deployment_policy = _section(policy, "deployment_policy")
        credential_policy = _section(policy, "credential_policy")
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
                    pk=_uuid(raw_credential, "credential"),
                    provider=deployment.model.provider,
                    is_deleted=False,
                    status__in=credential_policy["permitted_deployment_statuses"],
                ).first()
                if credential is None:
                    raise ValidationError({"credential": "A permitted, verified credential for the model provider is required."})
                deployment.credential = credential
        if "deployment_name" in changes:
            deployment.deployment_name = _text(changes["deployment_name"], "deployment_name", maximum=int(fields["deployment_name_max"]))  # type: ignore[arg-type]
        if "config" in changes:
            value = changes["config"]
            if not isinstance(value, Mapping):
                raise ValidationError({"config": "Must be an object."})
            deployment.config = self.validate_deployment_config(policy, value)
        if "status" in changes:
            requested_status = str(changes["status"])
            transitions = deployment_policy.get("allowed_status_transitions", {})
            allowed = transitions.get(deployment.status, []) if isinstance(transitions, Mapping) else []
            if requested_status != deployment.status and requested_status not in allowed:
                raise ValidationError({"status": "Status transition is not permitted by tenant policy."})
            deployment.status = requested_status
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
        fields = _section(AIProviderRuntimeConfigurationService.runtime_values(tenant_id), "field_limits")
        old_key = _text(old_key, "old_key", maximum=int(fields["rotation_key_max"]))
        new_key = _text(new_key, "new_key", maximum=int(fields["rotation_key_max"]))
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
        policy = AIProviderRuntimeConfigurationService.runtime_values(tenant_id)
        fields = _section(policy, "field_limits")
        metering = _section(policy, "metering")
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
            currency=_text(currency or str(metering["default_currency"]), "currency", maximum=int(metering["currency_code_length"])).upper(),
            provider_request_id=_text(
                provider_request_id, "provider_request_id", maximum=int(fields["provider_request_id_max"]), allow_blank=True
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
