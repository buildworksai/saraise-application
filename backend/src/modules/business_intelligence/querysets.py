"""Tenant-safe query helpers for the Business Intelligence domain."""

from __future__ import annotations

from uuid import UUID

from django.db import models

from src.core.tenancy import TenantQuerySet


class BIQuerySet(TenantQuerySet):
    """Common query surface which never weakens the explicit tenant boundary."""

    def for_tenant(self, tenant_id: UUID) -> "BIQuerySet":
        return self.filter(tenant_id=tenant_id)

    def not_deleted(self) -> "BIQuerySet":
        """Return definitions which have not been soft-deleted."""

        return self.filter(deleted_at__isnull=True)

    def in_state(self, state: str) -> "BIQuerySet":
        """Filter lifecycle-aware definitions by their explicit state."""

        return self.filter(state=state)


class ShareQuerySet(TenantQuerySet):
    """Query helpers for durable dashboard sharing records."""

    def for_tenant(self, tenant_id: UUID) -> "ShareQuerySet":
        return self.filter(tenant_id=tenant_id)

    def active(self, *, at=None) -> "ShareQuerySet":
        """Return non-revoked shares whose optional expiry remains in the future."""

        from django.utils import timezone

        instant = at or timezone.now()
        return self.filter(revoked_at__isnull=True).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=instant)
        )


class ExecutionQuerySet(TenantQuerySet):
    """Tenant-aware helpers for durable execution history."""

    def for_tenant(self, tenant_id: UUID) -> "ExecutionQuerySet":
        return self.filter(tenant_id=tenant_id)

    def terminal(self) -> "ExecutionQuerySet":
        return self.filter(status__in=("succeeded", "failed", "cancelled", "timed_out"))

    def pending(self) -> "ExecutionQuerySet":
        return self.filter(status__in=("queued", "running"))
