"""Persistence contract for tenant AI-provider configuration.

Provider and model catalog rows are platform-owned reference data. Credentials,
deployments, and usage evidence are tenant owned and inherit the canonical
tenant primitive so ORM and PostgreSQL RLS enforcement agree.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from src.core.tenancy import TenantScopedModel, TimestampedModel


def generate_uuid() -> str:
    """Compatibility callable retained for already-recorded migration imports."""

    return str(uuid.uuid4())


class ProviderType(models.TextChoices):
    OPENAI = "openai", "OpenAI"
    ANTHROPIC = "anthropic", "Anthropic"
    GOOGLE = "google", "Google Gemini"
    GROQ = "groq", "Groq"
    MISTRAL = "mistral", "Mistral"
    HUGGINGFACE = "huggingface", "Hugging Face"
    AZURE = "azure", "Azure OpenAI"
    CUSTOM = "custom", "Custom OpenAI-compatible"


class CredentialStatus(models.TextChoices):
    UNVERIFIED = "unverified", "Unverified"
    VALID = "valid", "Valid"
    INVALID = "invalid", "Invalid"


class DeploymentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    ERROR = "error", "Error"


class AIProvider(TimestampedModel):
    """Platform provider catalog entry; it never stores a credential."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    provider_type = models.CharField(max_length=50, choices=ProviderType.choices, db_index=True)
    base_url = models.URLField(max_length=500, blank=True)
    api_version = models.CharField(max_length=50, blank=True)
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "ai_provider_configuration_providers"
        constraints = [
            models.UniqueConstraint(Lower("name"), name="aiprov_provider_name_ci_uniq"),
        ]
        indexes = [
            models.Index(fields=["provider_type", "is_active"], name="aiprov_type_active_idx"),
        ]
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.provider_type})"


class TenantDomainModel(TenantScopedModel, TimestampedModel):
    """Common native UUID identity and archival fields for tenant data."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class _LegacyTenantResourceBase(models.Model):
    """Persistence base for the module's original public resource contract.

    The first module API accepted string tenant identifiers, so this narrow
    compatibility surface retains that storage type. New domain models use the
    canonical UUID-backed :class:`TenantScopedModel` above.
    """

    tenant_id = models.CharField(max_length=36, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.tenant_id:
            raise ValidationError({"tenant_id": "Tenant ID is required."})
        super().save(*args, **kwargs)


class AIProviderConfigurationResource(_LegacyTenantResourceBase):
    """Concrete tenant resource retained for the original module API."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    config = models.JSONField(default=dict, blank=True)
    created_by = models.CharField(max_length=36, db_index=True)

    class Meta:
        db_table = "ai_provider_configuration_resources"
        indexes = [
            models.Index(fields=["tenant_id", "is_active"], name="aiprov_res_tenant_active_idx"),
            models.Index(fields=["tenant_id", "name"], name="aiprov_res_tenant_name_idx"),
        ]
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"


# The generated module contract exposed this name even though the intended
# object was the concrete resource rather than an abstract Django base model.
TenantBaseModel = AIProviderConfigurationResource


class AIProviderCredential(TenantDomainModel):
    """Encrypted provider credential owned by exactly one tenant.

    ``api_key_encrypted`` is intentionally internal. API serializers expose
    only ``has_secret`` and the non-sensitive final four characters.
    """

    provider = models.ForeignKey(AIProvider, on_delete=models.PROTECT, related_name="credentials")
    label = models.CharField(max_length=120, default="Default")
    api_key_encrypted = models.TextField(editable=False)
    secret_hint = models.CharField(max_length=4, blank=True, editable=False)
    status = models.CharField(
        max_length=20,
        choices=CredentialStatus.choices,
        default=CredentialStatus.UNVERIFIED,
        db_index=True,
    )
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=80, blank=True, editable=False)

    class Meta:
        db_table = "ai_provider_configuration_credentials"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "provider", "label"],
                condition=models.Q(is_deleted=False),
                name="aiprov_credential_tenant_provider_label_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "provider", "status"], name="aiprov_cred_tenant_provider_idx"),
            models.Index(fields=["tenant_id", "is_deleted", "created_at"], name="aiprov_cred_tenant_created_idx"),
        ]
        ordering = ("-created_at",)

    @property
    def has_secret(self) -> bool:
        return bool(self.api_key_encrypted)

    def __str__(self) -> str:
        return f"{self.label} credential for {self.provider.name}"


class AIModel(TimestampedModel):
    """Platform model catalog entry associated with a provider adapter."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(AIProvider, on_delete=models.CASCADE, related_name="models")
    model_id = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    capabilities = models.JSONField(default=list, blank=True)
    pricing = models.JSONField(default=dict, blank=True)
    max_tokens = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "ai_provider_configuration_models"
        constraints = [
            models.UniqueConstraint(fields=["provider", "model_id"], name="aiprov_model_provider_id_uniq"),
        ]
        indexes = [
            models.Index(fields=["provider", "is_active", "display_name"], name="aiprov_model_provider_idx"),
        ]
        ordering = ("display_name",)

    @property
    def name(self) -> str:
        return self.display_name

    def __str__(self) -> str:
        return f"{self.provider.name} - {self.display_name}"


class AIModelDeployment(TenantDomainModel):
    """Tenant-specific, provider-neutral model runtime configuration."""

    model = models.ForeignKey(AIModel, on_delete=models.PROTECT, related_name="deployments")
    credential = models.ForeignKey(
        AIProviderCredential,
        on_delete=models.PROTECT,
        related_name="deployments",
        null=True,
        blank=True,
    )
    deployment_name = models.CharField(max_length=255)
    config = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=DeploymentStatus.choices,
        default=DeploymentStatus.ACTIVE,
        db_index=True,
    )
    created_by = models.CharField(max_length=36, editable=False)

    class Meta:
        db_table = "ai_provider_configuration_deployments"
        constraints = [
            models.UniqueConstraint(
                Lower("deployment_name"),
                models.F("tenant_id"),
                condition=models.Q(is_deleted=False),
                name="aiprov_deploy_tenant_name_ci_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "status", "created_at"], name="aiprov_deploy_tenant_status_idx"),
            models.Index(fields=["tenant_id", "model"], name="aiprov_deploy_tenant_model_idx"),
            models.Index(fields=["tenant_id", "is_deleted"], name="aiprov_deploy_tenant_deleted_idx"),
        ]
        ordering = ("-created_at",)

    @property
    def is_active(self) -> bool:
        return self.status == DeploymentStatus.ACTIVE

    def clean(self) -> None:
        super().clean()
        if self.credential_id is not None:
            if self.credential.tenant_id != self.tenant_id:
                raise ValidationError({"credential": "Credential must belong to the deployment tenant."})
            if self.credential.provider_id != self.model.provider_id:
                raise ValidationError({"credential": "Credential provider must match the model provider."})
            if self.credential.is_deleted:
                raise ValidationError({"credential": "Archived credentials cannot be deployed."})

    def __str__(self) -> str:
        return self.deployment_name


class AIUsageLog(TenantScopedModel):
    """Append-only provider usage and cost evidence."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    deployment = models.ForeignKey(
        AIModelDeployment,
        on_delete=models.PROTECT,
        related_name="usage_logs",
    )
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    cost = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        default=Decimal("0.000000"),
        validators=[MinValueValidator(Decimal("0.000000"))],
    )
    currency = models.CharField(max_length=3, default="USD")
    provider_request_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "ai_provider_configuration_usage_logs"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(total_tokens=models.F("prompt_tokens") + models.F("completion_tokens")),
                name="aiprov_usage_total_tokens_match",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "deployment", "created_at"], name="aiprov_usage_tenant_deploy_idx"),
            models.Index(fields=["tenant_id", "created_at"], name="aiprov_usage_tenant_created_idx"),
        ]
        ordering = ("-created_at",)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Normalize the original aggregate-token inputs without losing data."""

        tokens_used = kwargs.pop("tokens_used", None)
        input_tokens = kwargs.pop("input_tokens", None)
        output_tokens = kwargs.pop("output_tokens", None)
        if not args and any(value is not None for value in (tokens_used, input_tokens, output_tokens)):
            prompt_tokens = input_tokens
            completion_tokens = output_tokens
            if prompt_tokens is None and completion_tokens is None and tokens_used is not None:
                prompt_tokens, completion_tokens = tokens_used, 0
            prompt_tokens = 0 if prompt_tokens is None else prompt_tokens
            completion_tokens = 0 if completion_tokens is None else completion_tokens
            kwargs.setdefault("prompt_tokens", prompt_tokens)
            kwargs.setdefault("completion_tokens", completion_tokens)
            kwargs.setdefault(
                "total_tokens",
                tokens_used if tokens_used is not None else prompt_tokens + completion_tokens,
            )
        super().__init__(*args, **kwargs)

    @property
    def tokens_used(self) -> int:
        return self.total_tokens

    @property
    def input_tokens(self) -> int:
        return self.prompt_tokens

    @property
    def output_tokens(self) -> int:
        return self.completion_tokens

    def clean(self) -> None:
        super().clean()
        if self.deployment_id and self.deployment.tenant_id != self.tenant_id:
            raise ValidationError({"deployment": "Deployment must belong to the usage-log tenant."})
        expected = self.prompt_tokens + self.completion_tokens
        if self.total_tokens != expected:
            raise ValidationError({"total_tokens": "Total tokens must equal prompt plus completion tokens."})
        self.currency = self.currency.upper()

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Usage logs are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Usage logs are append-only.")

    def __str__(self) -> str:
        return f"{self.total_tokens} tokens on {self.deployment_id}"


__all__ = [
    "AIModel",
    "AIModelDeployment",
    "AIProvider",
    "AIProviderConfigurationResource",
    "AIProviderCredential",
    "AIUsageLog",
    "CredentialStatus",
    "DeploymentStatus",
    "ProviderType",
    "TenantBaseModel",
]
