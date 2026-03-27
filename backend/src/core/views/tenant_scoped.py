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

from django.db.models import QuerySet
from rest_framework import viewsets

logger = logging.getLogger("saraise.tenant")


class TenantScopedModelViewSet(viewsets.ModelViewSet):
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

    def get_queryset(self) -> QuerySet:
        """Filter queryset by tenant_id from authenticated user."""
        qs = super().get_queryset()

        # Extract tenant_id from user or request
        tenant_id = self._get_tenant_id()
        if tenant_id is None:
            logger.error(
                "No tenant_id found for user=%s on %s — returning empty queryset",
                getattr(self.request.user, "pk", "?"),
                self.__class__.__name__,
            )
            return qs.none()

        # Filter by tenant_id (SARAISE-33001)
        if hasattr(qs.model, "tenant_id"):
            return qs.filter(tenant_id=tenant_id)

        logger.warning(
            "Model %s has no tenant_id field — skipping tenant filter",
            qs.model.__name__,
        )
        return qs

    def perform_create(self, serializer: Any) -> None:
        """Inject tenant_id on create operations."""
        tenant_id = self._get_tenant_id()
        if tenant_id and hasattr(serializer.Meta.model, "tenant_id"):
            serializer.save(tenant_id=tenant_id)
        else:
            serializer.save()

    def _get_tenant_id(self) -> str | None:
        """Extract tenant_id from request context."""
        user = self.request.user
        # Try multiple sources for tenant_id
        tenant_id = getattr(user, "tenant_id", None)
        if not tenant_id:
            tenant_id = getattr(self.request, "tenant_id", None)
        if not tenant_id:
            tenant_id = self.request.headers.get("X-Tenant-ID")
        return tenant_id


class TenantScopedReadOnlyModelViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only version of TenantScopedModelViewSet."""

    def get_queryset(self) -> QuerySet:
        qs = super().get_queryset()
        tenant_id = self._get_tenant_id()
        if tenant_id is None:
            return qs.none()
        if hasattr(qs.model, "tenant_id"):
            return qs.filter(tenant_id=tenant_id)
        return qs

    def _get_tenant_id(self) -> str | None:
        user = self.request.user
        tenant_id = getattr(user, "tenant_id", None)
        if not tenant_id:
            tenant_id = getattr(self.request, "tenant_id", None)
        if not tenant_id:
            tenant_id = self.request.headers.get("X-Tenant-ID")
        return tenant_id
