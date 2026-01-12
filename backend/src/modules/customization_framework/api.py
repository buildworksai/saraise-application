"""
DRF ViewSets for CustomizationFramework module.
Provides REST API endpoints for all models.
"""

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import CustomizationFrameworkResource
from .serializers import CustomizationFrameworkResourceSerializer
from .services import CustomizationFrameworkService


class CustomizationFrameworkResourceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CustomizationFrameworkResource CRUD operations.

    Endpoints:
    - GET /api/v1/customization-framework/resources/ - List all resources
    - POST /api/v1/customization-framework/resources/ - Create resource
    - GET /api/v1/customization-framework/resources/{id}/ - Get resource detail
    - PUT /api/v1/customization-framework/resources/{id}/ - Update resource
    - PATCH /api/v1/customization-framework/resources/{id}/ - Partial update resource
    - DELETE /api/v1/customization-framework/resources/{id}/ - Delete resource
    """

    serializer_class = CustomizationFrameworkResourceSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter resources by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return CustomizationFrameworkResource.objects.none()
        return CustomizationFrameworkResource.objects.filter(tenant_id=tenant_id)

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(
            tenant_id=tenant_id,
            created_by=str(self.request.user.id)
        )

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate resource."""
        resource = self.get_object()
        service = CustomizationFrameworkService()
        service.activate_resource(resource.id, get_user_tenant_id(request.user))
        return Response({"status": "activated"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate resource."""
        resource = self.get_object()
        service = CustomizationFrameworkService()
        service.deactivate_resource(resource.id, get_user_tenant_id(request.user))
        return Response({"status": "deactivated"}, status=status.HTTP_200_OK)
