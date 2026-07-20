"""
Tenant-scoped ViewSet base classes for SARAISE modules.

SARAISE-33001: All tenant-scoped queries MUST filter by tenant_id.
SARAISE-33004: Raw SQL MUST include tenant_id in WHERE clause.

These base classes enforce tenant isolation at the ViewSet level,
making it impossible to accidentally return cross-tenant data.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.db import models
from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied

from src.core.tenancy.models import TenantScopedModel

logger = logging.getLogger("saraise.tenant")


class _TenantContextMixin:
    """Shared fail-closed tenant behavior for mutable and read-only views."""

    request: Any

    def _scope_queryset(self, queryset: QuerySet[models.Model]) -> QuerySet[models.Model]:
        """Return only rows owned by the authenticated profile's tenant."""
        self._validate_model(queryset.model)

        tenant_id = self._get_tenant_id()
        if tenant_id is None:
            logger.warning(
                "Tenant context unavailable; denying scoped read",
                extra={
                    "user_id": str(getattr(self.request.user, "pk", "unknown")),
                    "view": self.__class__.__name__,
                },
            )
            return queryset.none()

        return queryset.filter(tenant_id=tenant_id)

    @staticmethod
    def _validate_model(model: type[models.Model]) -> None:
        """Reject accidental use with global, hybrid, or legacy model bases."""
        if not issubclass(model, TenantScopedModel):
            raise ImproperlyConfigured(
                f"{model._meta.label} must inherit TenantScopedModel before it can " "use a tenant-scoped ViewSet."
            )

    def _get_tenant_id(self) -> UUID | None:
        """Resolve tenant authority only from an authenticated user profile."""
        user = getattr(self.request, "user", None)
        if user is None or not bool(getattr(user, "is_authenticated", False)):
            return None

        try:
            raw_tenant_id = getattr(user.profile, "tenant_id", None)
        except (AttributeError, ObjectDoesNotExist):
            return None

        if not raw_tenant_id:
            return None

        try:
            return raw_tenant_id if isinstance(raw_tenant_id, UUID) else UUID(str(raw_tenant_id))
        except (AttributeError, TypeError, ValueError):
            logger.error(
                "Authenticated profile contains an invalid tenant UUID",
                extra={"user_id": str(getattr(user, "pk", "unknown"))},
            )
            return None

    def _require_tenant_id(self) -> UUID:
        tenant_id = self._get_tenant_id()
        if tenant_id is None:
            raise PermissionDenied("Authenticated tenant context is required for write operations.")
        return tenant_id


class TenantScopedModelViewSet(_TenantContextMixin, viewsets.ModelViewSet[models.Model]):
    """
    ModelViewSet that enforces tenant isolation on all queries.

    All subclasses automatically filter querysets by tenant_id from
    the authenticated user's context. Direct model access without
    tenant filtering is impossible through this base class.

    Usage:
        class InvoiceViewSet(TenantScopedModelViewSet):
            queryset = Invoice.objects.all()
            serializer_class = InvoiceSerializer
            # tenant_id is automatically filtered
    """

    def get_queryset(self) -> QuerySet[models.Model]:
        """Return only rows owned by the authenticated profile's tenant."""
        return self._scope_queryset(super().get_queryset())

    def perform_create(self, serializer: Any) -> None:
        """Inject authenticated ownership, overriding any submitted tenant."""
        self.get_queryset()  # Validate the configured model before any write.
        serializer.save(tenant_id=self._require_tenant_id())

    def perform_update(self, serializer: Any) -> None:
        """Keep ownership immutable from request data during updates."""
        self.get_queryset()
        serializer.save(tenant_id=self._require_tenant_id())


class TenantScopedReadOnlyModelViewSet(_TenantContextMixin, viewsets.ReadOnlyModelViewSet[models.Model]):
    """Read-only version of TenantScopedModelViewSet."""

    def get_queryset(self) -> QuerySet[models.Model]:
        """Return only rows owned by the authenticated profile's tenant."""
        return self._scope_queryset(super().get_queryset())
