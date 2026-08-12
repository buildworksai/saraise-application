"""Canonical model primitives for tenant-owned data.

Tenant ownership and record timestamps are intentionally separate concerns. A
module can adopt :class:`TenantScopedModel` without inheriting unrelated audit
columns or changing an existing timestamp contract.
"""

from __future__ import annotations

from typing import Any, TypeVar
from uuid import UUID

from django.db import models

TenantModelT = TypeVar("TenantModelT", bound=models.Model)


class TenantQuerySet(models.QuerySet[TenantModelT]):
    """QuerySet with an explicit, reusable tenant boundary."""

    def for_tenant(self, tenant_id: UUID) -> "TenantQuerySet[TenantModelT]":
        """Return records owned by ``tenant_id`` only."""
        return self.filter(tenant_id=tenant_id)


class TenantScopedModel(models.Model):
    """Abstract ownership base for every tenant-scoped model.

    The tenant UUID is deliberately non-null and indexed. It is an ownership
    boundary, not client-provided metadata.
    """

    tenant_id = models.UUIDField(db_index=True)

    objects: Any = TenantQuerySet.as_manager()

    class Meta:
        abstract = True


class TimestampedModel(models.Model):
    """Optional abstract mixin for conventional creation/update timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
