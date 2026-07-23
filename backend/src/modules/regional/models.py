"""Tenant-isolated persistence for the Regional module."""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.deletion import ProtectedError

from src.core.tenancy import TenantScopedModel as CoreTenantScopedModel
from src.core.tenancy import TimestampedModel


def generate_uuid() -> uuid.UUID:
    """Return a UUID suitable for model primary keys and historical migrations."""

    return uuid.uuid4()


def empty_resource_configuration() -> dict[str, Any]:
    """Return the typed resource configuration's empty representation."""

    return {}


class TenantScopedModel(CoreTenantScopedModel):
    """Base for Regional tenant data."""

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.tenant_id:
            raise ValidationError({"tenant_id": "Tenant ID is required."})
        super().save(*args, **kwargs)


class TimestampedTenantModel(TenantScopedModel, TimestampedModel):
    """Tenant data with creation and modification evidence."""

    class Meta:
        abstract = True


class RegionalResourceQuerySet(models.QuerySet["RegionalResource"]):
    """Prevent bulk hard deletion from bypassing the service workflow."""

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ProtectedError("Regional resources must be soft-deleted through RegionalService.", list(self[:1]))


class RegionalResource(TimestampedTenantModel):
    """A tenant-owned regional policy resource."""

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    # 512 is a structural storage ceiling. The effective tenant limit is read
    # from RegionalConfiguration and enforced by RegionalService.
    name = models.CharField(max_length=512, db_index=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(db_index=True)
    config = models.JSONField(
        default=empty_resource_configuration,
        help_text="Typed regional resource configuration validated by RegionalService.",
    )
    created_by = models.CharField(max_length=128, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted_by = models.CharField(max_length=128, blank=True)

    objects = RegionalResourceQuerySet.as_manager()

    class Meta:
        app_label = "regional"
        db_table = "regional_resources"
        indexes = [
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["tenant_id", "name"]),
            models.Index(
                fields=["tenant_id", "deleted_at"],
                name="regional_re_tenant__deleted_idx",
            ),
        ]

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ProtectedError("Regional resources must be soft-deleted through RegionalService.", [self])

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"


class RegionalConfiguration(TimestampedTenantModel):
    """Current validated configuration for one tenant and environment."""

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    environment = models.CharField(max_length=32)
    version = models.PositiveIntegerField()
    document = models.JSONField()
    updated_by = models.CharField(max_length=128)
    correlation_id = models.UUIDField()

    class Meta:
        app_label = "regional"
        db_table = "regional_configurations"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "environment"],
                name="regional_config_tenant_environment_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "environment"],
                name="regional_co_tenant__env_idx",
            )
        ]


class AppendOnlyQuerySet(models.QuerySet[Any]):
    """Block bulk mutation of compliance evidence."""

    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ValidationError("Regional audit and version records are immutable.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ProtectedError("Regional audit and version records are immutable.", list(self[:1]))


class AppendOnlyTenantModel(TenantScopedModel):
    """Base class that permits evidence creation only."""

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Regional audit and version records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ProtectedError("Regional audit and version records are immutable.", [self])


class RegionalConfigurationVersion(AppendOnlyTenantModel):
    """Immutable configuration snapshot; rollback creates a new snapshot."""

    environment = models.CharField(max_length=32)
    version = models.PositiveIntegerField()
    document = models.JSONField()
    operation = models.CharField(max_length=32)
    actor_id = models.CharField(max_length=128)
    correlation_id = models.UUIDField()
    previous_version = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        app_label = "regional"
        db_table = "regional_configuration_versions"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "environment", "version"],
                name="regional_config_version_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "environment", "-version"],
                name="regional_cv_tenant__version_idx",
            ),
            models.Index(
                fields=["tenant_id", "correlation_id"],
                name="regional_cv_tenant__corr_idx",
            ),
        ]


class RegionalAuditRecord(AppendOnlyTenantModel):
    """Immutable before/after evidence for every Regional mutation."""

    actor_id = models.CharField(max_length=128)
    correlation_id = models.UUIDField()
    operation = models.CharField(max_length=64)
    entity_type = models.CharField(max_length=64)
    entity_id = models.UUIDField(null=True, blank=True)
    before_value = models.JSONField()
    after_value = models.JSONField()

    class Meta:
        app_label = "regional"
        db_table = "regional_audit_records"
        indexes = [
            models.Index(
                fields=["tenant_id", "entity_type", "entity_id"],
                name="regional_ar_tenant__entity_idx",
            ),
            models.Index(
                fields=["tenant_id", "correlation_id"],
                name="regional_ar_tenant__corr_idx",
            ),
            models.Index(
                fields=["tenant_id", "-created_at"],
                name="regional_ar_tenant__created_idx",
            ),
        ]


class RegionalIdempotencyRecord(TenantScopedModel):
    """Tenant-scoped replay protection for state-changing commands."""

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    operation = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=255)
    resource = models.ForeignKey(
        RegionalResource,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="idempotency_records",
    )
    request_fingerprint = models.CharField(max_length=64)
    correlation_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "regional"
        db_table = "regional_idempotency_records"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "operation", "idempotency_key"],
                name="regional_idempotency_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "operation", "idempotency_key"],
                name="regional_idem_tenant__key_idx",
            )
        ]


# Historical public alias retained for callers while pointing at the concrete model.
TenantBaseModel = RegionalResource
