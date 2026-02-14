"""
DRF ViewSets for Master Data Management module.
"""

import uuid
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import MasterDataEntity
from .serializers import MasterDataEntitySerializer


class MasterDataEntityViewSet(viewsets.ModelViewSet):
    """ViewSet for MasterDataEntity CRUD operations."""

    serializer_class = MasterDataEntitySerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter entities by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return MasterDataEntity.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return MasterDataEntity.objects.none()

        queryset = MasterDataEntity.objects.filter(tenant_id=tenant_id, is_active=True)
        # Filter by entity_type if provided
        entity_type = self.request.query_params.get("entity_type")
        if entity_type:
            queryset = queryset.filter(entity_type=entity_type)
        return queryset.order_by("entity_type", "entity_code")

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
