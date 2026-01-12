"""
DRF ViewSets for Tenant Management module.

⚠️ ARCHITECTURAL NOTE: This module is READ-ONLY in the Application layer.
Tenant lifecycle operations (create, suspend, terminate) MUST be performed
via Control Plane services in saraise-platform/saraise-control-plane/.

This ViewSet provides read-only access for:
- Filtering tenant-scoped queries
- Reading tenant status for authorization
- Displaying tenant information in UI

CRITICAL: Only platform owners can access these endpoints.
Tenant lifecycle operations are FORBIDDEN here - use Control Plane APIs.
"""

from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_platform_role

from .models import Tenant, TenantHealthScore, TenantModule, TenantResourceUsage, TenantSettings
from .serializers import (
    TenantHealthScoreSerializer,
    TenantListSerializer,
    TenantModuleSerializer,
    TenantResourceUsageSerializer,
    TenantSerializer,
    TenantSettingsSerializer,
)


class TenantViewSet(viewsets.ReadOnlyModelViewSet):
    """
    READ-ONLY ViewSet for Tenant information.

    ⚠️ ARCHITECTURAL VIOLATION PREVENTION:
    - CREATE operations: Use Control Plane API (saraise-platform/saraise-control-plane/)
    - UPDATE operations: Use Control Plane API
    - DELETE operations: Use Control Plane API

    This ViewSet only provides:
    - LIST: Read tenant list (platform owners only)
    - RETRIEVE: Read tenant details (platform owners only)

    Tenant lifecycle operations are FORBIDDEN in Application layer.
    """

    """
    ViewSet for Tenant CRUD operations.

    CRITICAL: Platform-level operations - only platform owners can access.

    Endpoints:
    - GET /api/v1/tenant-management/tenants/ - List all tenants
    - POST /api/v1/tenant-management/tenants/ - Create tenant
    - GET /api/v1/tenant-management/tenants/{id}/ - Get tenant detail
    - PUT /api/v1/tenant-management/tenants/{id}/ - Update tenant
    - PATCH /api/v1/tenant-management/tenants/{id}/ - Partial update tenant
    - DELETE /api/v1/tenant-management/tenants/{id}/ - Delete tenant
    """

    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get all tenants (platform owners only)."""
        if get_user_platform_role(self.request.user) != "platform_owner":
            return Tenant.objects.none()

        queryset = Tenant.objects.all()

        # Filter by status
        status_filter = self.request.query_params.get("status", None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by subscription plan
        plan_filter = self.request.query_params.get("subscription_plan_id", None)
        if plan_filter:
            queryset = queryset.filter(subscription_plan_id=plan_filter)

        # Search by name, slug, or email
        search = self.request.query_params.get("search", None)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(slug__icontains=search) | Q(primary_contact_email__icontains=search)
            )

        return queryset.order_by("-created_at")

    def get_serializer_class(self):
        """Use lightweight serializer for list view."""
        if self.action == "list":
            return TenantListSerializer
        return TenantSerializer

    # ⚠️ ARCHITECTURAL ENFORCEMENT: Lifecycle operations removed
    # Tenant lifecycle (create, update, delete, suspend, activate) MUST be performed
    # via Control Plane services in saraise-platform/saraise-control-plane/
    # This ViewSet is READ-ONLY for filtering and display purposes only.

    @action(detail=True, methods=["get"])
    def modules(self, request, pk=None):
        """Get modules for a tenant."""
        tenant = self.get_object()
        modules = tenant.modules.all()
        serializer = TenantModuleSerializer(modules, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def resource_usage(self, request, pk=None):
        """Get resource usage for a tenant."""
        tenant = self.get_object()
        date_from = request.query_params.get("date_from", None)
        date_to = request.query_params.get("date_to", None)

        usage = tenant.resource_usage.all()
        if date_from:
            usage = usage.filter(date__gte=date_from)
        if date_to:
            usage = usage.filter(date__lte=date_to)

        serializer = TenantResourceUsageSerializer(usage.order_by("-date")[:30], many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def health_scores(self, request, pk=None):
        """Get health scores for a tenant."""
        tenant = self.get_object()
        date_from = request.query_params.get("date_from", None)
        date_to = request.query_params.get("date_to", None)

        scores = tenant.health_scores.all()
        if date_from:
            scores = scores.filter(date__gte=date_from)
        if date_to:
            scores = scores.filter(date__lte=date_to)

        serializer = TenantHealthScoreSerializer(scores.order_by("-date")[:30], many=True)
        return Response(serializer.data)


class TenantModuleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    READ-ONLY ViewSet for Tenant Module information.

    ⚠️ ARCHITECTURAL VIOLATION PREVENTION:
    - Module enablement/disablement: Use Control Plane API (saraise-platform/saraise-control-plane/)
    - Module installation: Use Control Plane API

    This ViewSet only provides:
    - LIST: Read tenant modules (platform owners only)
    - RETRIEVE: Read tenant module details (platform owners only)

    Module lifecycle operations are FORBIDDEN in Application layer.
    """

    serializer_class = TenantModuleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get all tenant modules (platform owners only)."""
        if get_user_platform_role(self.request.user) != "platform_owner":
            return TenantModule.objects.none()

        queryset = TenantModule.objects.select_related("tenant").all()

        # Filter by tenant
        tenant_id = self.request.query_params.get("tenant_id", None)
        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)

        # Filter by module name
        module_name = self.request.query_params.get("module_name", None)
        if module_name:
            queryset = queryset.filter(module_name=module_name)

        # Filter by enabled status
        is_enabled = self.request.query_params.get("is_enabled", None)
        if is_enabled is not None:
            queryset = queryset.filter(is_enabled=is_enabled.lower() == "true")

        return queryset.order_by("tenant__name", "module_name")

    # ⚠️ ARCHITECTURAL ENFORCEMENT: Module lifecycle operations removed
    # Module enablement/disablement MUST be performed via Control Plane services
    # in saraise-platform/saraise-control-plane/


class TenantResourceUsageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Tenant Resource Usage (read-only).

    CRITICAL: Platform-level operations - only platform owners can access.
    """

    serializer_class = TenantResourceUsageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get all tenant resource usage (platform owners only)."""
        if get_user_platform_role(self.request.user) != "platform_owner":
            return TenantResourceUsage.objects.none()

        queryset = TenantResourceUsage.objects.select_related("tenant").all()

        # Filter by tenant
        tenant_id = self.request.query_params.get("tenant_id", None)
        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)

        # Filter by date range
        date_from = self.request.query_params.get("date_from", None)
        if date_from:
            queryset = queryset.filter(date__gte=date_from)

        date_to = self.request.query_params.get("date_to", None)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        return queryset.order_by("-date", "tenant__name")


class TenantSettingsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    READ-ONLY ViewSet for Tenant Settings information.

    ⚠️ ARCHITECTURAL VIOLATION PREVENTION:
    - Setting creation/update: Use Control Plane API (saraise-platform/saraise-control-plane/)

    This ViewSet only provides:
    - LIST: Read tenant settings (platform owners only)
    - RETRIEVE: Read tenant setting details (platform owners only)

    Setting management operations are FORBIDDEN in Application layer.
    """

    serializer_class = TenantSettingsSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get all tenant settings (platform owners only)."""
        if get_user_platform_role(self.request.user) != "platform_owner":
            return TenantSettings.objects.none()

        queryset = TenantSettings.objects.select_related("tenant").all()

        # Filter by tenant
        tenant_id = self.request.query_params.get("tenant_id", None)
        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)

        # Filter by category
        category = self.request.query_params.get("category", None)
        if category:
            queryset = queryset.filter(category=category)

        return queryset.order_by("tenant__name", "category", "key")

    # ⚠️ ARCHITECTURAL ENFORCEMENT: Setting management operations removed
    # Setting creation/update MUST be performed via Control Plane services
    # in saraise-platform/saraise-control-plane/


class TenantHealthScoreViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Tenant Health Scores (read-only).

    CRITICAL: Platform-level operations - only platform owners can access.
    """

    serializer_class = TenantHealthScoreSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get all tenant health scores (platform owners only)."""
        if get_user_platform_role(self.request.user) != "platform_owner":
            return TenantHealthScore.objects.none()

        queryset = TenantHealthScore.objects.select_related("tenant").all()

        # Filter by tenant
        tenant_id = self.request.query_params.get("tenant_id", None)
        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)

        # Filter by date range
        date_from = self.request.query_params.get("date_from", None)
        if date_from:
            queryset = queryset.filter(date__gte=date_from)

        date_to = self.request.query_params.get("date_to", None)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        # Filter by churn risk threshold
        churn_risk_min = self.request.query_params.get("churn_risk_min", None)
        if churn_risk_min:
            queryset = queryset.filter(churn_risk__gte=churn_risk_min)

        return queryset.order_by("-date", "tenant__name")
