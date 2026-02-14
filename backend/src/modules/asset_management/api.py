"""
DRF ViewSets for Asset Management module.
"""

import uuid
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import Asset, DepreciationEntry
from .serializers import AssetSerializer, DepreciationEntrySerializer


class AssetViewSet(viewsets.ModelViewSet):
    """ViewSet for Asset CRUD operations."""

    serializer_class = AssetSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter assets by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return Asset.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Asset.objects.none()

        queryset = Asset.objects.filter(tenant_id=tenant_id, is_active=True)
        return queryset.order_by("asset_code")

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            raise PermissionDenied("User must belong to a tenant")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise PermissionDenied("Invalid tenant_id format")

        serializer.save(tenant_id=tenant_id)


class DepreciationEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for DepreciationEntry read operations."""

    serializer_class = DepreciationEntrySerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter depreciation entries by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return DepreciationEntry.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return DepreciationEntry.objects.none()

        queryset = DepreciationEntry.objects.filter(tenant_id=tenant_id)
        # Filter by asset if provided
        asset_id = self.request.query_params.get("asset_id")
        if asset_id:
            queryset = queryset.filter(asset_id=asset_id)
        return queryset.order_by("-entry_date")
