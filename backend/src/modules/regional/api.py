"""
DRF ViewSets for Regional module.
Provides REST API endpoints for all models.
"""

from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import (
    AllowAny,
    BasePermission,
    IsAuthenticated,
)
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import RegionalResource
from .serializers import RegionalResourceSerializer
from .services import RegionalService


class RegionalResourceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for RegionalResource CRUD operations.

    Endpoints:
    - GET /api/v1/regional/resources/ - List all resources
    - POST /api/v1/regional/resources/ - Create resource
    - GET /api/v1/regional/resources/{id}/ - Get resource detail
    - PUT /api/v1/regional/resources/{id}/ - Update resource
    - PATCH /api/v1/regional/resources/{id}/ - Partial update resource
    - DELETE /api/v1/regional/resources/{id}/ - Delete resource
    """

    serializer_class = RegionalResourceSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_permissions(self) -> list[BasePermission]:
        """Allow an empty anonymous list only in explicit development mode."""
        if self.action == "list" and settings.SARAISE_MODE == "development":
            return [AllowAny()]
        return super().get_permissions()

    def get_queryset(self):
        """Filter resources by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return RegionalResource.objects.none()
        return RegionalResource.objects.filter(tenant_id=tenant_id)

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        created_by = str(self.request.user.id)
        serializer.save(tenant_id=tenant_id, created_by=created_by)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate resource."""
        resource = self.get_object()
        service = RegionalService()
        service.activate_resource(
            resource.id,
            get_user_tenant_id(request.user),
        )
        return Response({"status": "activated"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Deactivate resource."""
        resource = self.get_object()
        service = RegionalService()
        service.deactivate_resource(
            resource.id,
            get_user_tenant_id(request.user),
        )
        return Response({"status": "deactivated"}, status=status.HTTP_200_OK)
