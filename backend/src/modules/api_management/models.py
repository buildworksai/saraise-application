"""Durable, tenant-isolated state for the API management module."""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models

from src.core.tenancy.models import TenantScopedModel


def generate_uuid() -> uuid.UUID:
    """Return a native UUID for durable identifiers."""

    return uuid.uuid4()


class _TenantBaseModel(TenantScopedModel):
    """Shared ownership and timestamps for tenant data."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.tenant_id:
            raise ValidationError({"tenant_id": "Tenant ID is required."})
        super().save(*args, **kwargs)

    class Meta:
        app_label = "api_management"
        abstract = True
        indexes = [models.Index(fields=["tenant_id", "created_at"])]


class ApiManagementResource(_TenantBaseModel):
    """A tenant-owned managed API registration."""

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    # The database cap protects storage. The tenant's lower effective limit is
    # enforced by ApiManagementService from the versioned configuration.
    name = models.CharField(max_length=512, db_index=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(db_index=True)
    config = models.JSONField(default=dict)
    created_by = models.CharField(max_length=255, db_index=True)
    idempotency_key = models.UUIDField()
    version = models.PositiveIntegerField(default=1)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted_by = models.CharField(max_length=255, blank=True)

    class Meta:
        app_label = "api_management"
        db_table = "api_management_resources"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "idempotency_key"],
                name="api_mgmt_resource_idempotency_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "deleted_at", "is_active"],
                name="api_mgmt_res_tenant_state_idx",
            ),
            models.Index(fields=["tenant_id", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"


class ApiManagementConfiguration(_TenantBaseModel):
    """The current validated configuration document for one tenant."""

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    document = models.JSONField()
    version = models.PositiveIntegerField()
    updated_by = models.CharField(max_length=255)

    class Meta:
        app_label = "api_management"
        db_table = "api_management_configurations"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id"], name="api_mgmt_config_tenant_uniq"),
        ]


class _AppendOnlyQuerySet(models.QuerySet[Any]):
    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ValidationError("Append-only evidence cannot be updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Append-only evidence cannot be deleted.")


class _AppendOnlyManager(models.Manager[Any]):
    def get_queryset(self) -> _AppendOnlyQuerySet:
        return _AppendOnlyQuerySet(self.model, using=self._db)


class _AppendOnlyTenantModel(_TenantBaseModel):
    """Application-level protection complementing database triggers."""

    objects = _AppendOnlyManager()

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Append-only evidence cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Append-only evidence cannot be deleted.")

    class Meta:
        abstract = True


class ApiManagementConfigurationVersion(_AppendOnlyTenantModel):
    """Immutable snapshot enabling rollback to any prior configuration."""

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    version = models.PositiveIntegerField()
    document = models.JSONField()
    actor_id = models.CharField(max_length=255)
    correlation_id = models.CharField(max_length=255, db_index=True)
    idempotency_key = models.UUIDField()
    reason = models.CharField(max_length=64)

    class Meta:
        app_label = "api_management"
        db_table = "api_management_configuration_versions"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "version"],
                name="api_mgmt_config_version_uniq",
            ),
            models.UniqueConstraint(
                fields=["tenant_id", "idempotency_key"],
                name="api_mgmt_config_idempotency_uniq",
            ),
        ]
        ordering = ["-version"]


class ApiManagementAuditRecord(_AppendOnlyTenantModel):
    """Immutable evidence for every configuration and resource mutation."""

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    target_type = models.CharField(max_length=32)
    target_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=64)
    actor_id = models.CharField(max_length=255)
    correlation_id = models.CharField(max_length=255, db_index=True)
    idempotency_key = models.UUIDField()
    before_value = models.JSONField(null=True, blank=True)
    after_value = models.JSONField(null=True, blank=True)
    version = models.PositiveIntegerField()

    class Meta:
        app_label = "api_management"
        db_table = "api_management_audit_records"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["tenant_id", "target_type", "target_id"],
                name="api_mgmt_audit_target_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "idempotency_key"],
                name="api_mgmt_audit_idempotency_uniq",
            ),
        ]


# Backward-compatible public name retained for existing module callers.
TenantBaseModel = ApiManagementResource


__all__ = [
    "ApiManagementAuditRecord",
    "ApiManagementConfiguration",
    "ApiManagementConfigurationVersion",
    "ApiManagementResource",
    "TenantBaseModel",
    "generate_uuid",
]
