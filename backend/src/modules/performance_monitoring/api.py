"""
DRF ViewSets for PerformanceMonitoring module.
Provides REST API endpoints for all models.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import PerformanceMonitoringResource
from .serializers import PerformanceMonitoringResourceSerializer
from .services import PerformanceMonitoringService


class PerformanceMonitoringResourceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for PerformanceMonitoringResource CRUD operations.

    Endpoints:
    - GET /api/v1/performance-monitoring/resources/ - List all resources
    - POST /api/v1/performance-monitoring/resources/ - Create resource
    - GET /api/v1/performance-monitoring/resources/{id}/ - Get resource detail
    - PUT /api/v1/performance-monitoring/resources/{id}/ - Update resource
    - PATCH /api/v1/performance-monitoring/resources/{id}/ - Partial update resource
    - DELETE /api/v1/performance-monitoring/resources/{id}/ - Delete resource
    """

    serializer_class = PerformanceMonitoringResourceSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter resources by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return PerformanceMonitoringResource.objects.none()
        return PerformanceMonitoringResource.objects.filter(tenant_id=tenant_id)

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
        service = PerformanceMonitoringService()
        service.activate_resource(resource.id, get_user_tenant_id(request.user))
        return Response({"status": "activated"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate resource."""
        resource = self.get_object()
        service = PerformanceMonitoringService()
        service.deactivate_resource(resource.id, get_user_tenant_id(request.user))
        return Response({"status": "deactivated"}, status=status.HTTP_200_OK)
