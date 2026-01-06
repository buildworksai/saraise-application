"""
DRF ViewSets for Tenant Management module.

CRITICAL: These are PLATFORM-LEVEL ViewSets (NO tenant_id).
Only platform owners can access these endpoints.
Tenant Management manages tenants themselves, which are platform-level entities.
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q

from src.core.auth_utils import get_user_platform_role

from .models import (
    Tenant,
    TenantModule,
    TenantResourceUsage,
    TenantSettings,
    TenantHealthScore,
)
from .serializers import (
    TenantSerializer,
    TenantListSerializer,
    TenantModuleSerializer,
    TenantResourceUsageSerializer,
    TenantSettingsSerializer,
    TenantHealthScoreSerializer,
)


class TenantViewSet(viewsets.ModelViewSet):
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
                Q(name__icontains=search)
                | Q(slug__icontains=search)
                | Q(primary_contact_email__icontains=search)
            )

        return queryset.order_by("-created_at")

    def get_serializer_class(self):
        """Use lightweight serializer for list view."""
        if self.action == "list":
            return TenantListSerializer
        return TenantSerializer

    def perform_create(self, serializer):
        """Set created_by from authenticated user."""
        if get_user_platform_role(self.request.user) != "platform_owner":
            raise PermissionDenied("Only platform owners can create tenants.")
        serializer.save(created_by=str(self.request.user.id))

    def perform_update(self, serializer):
        """Set updated_by from authenticated user."""
        if get_user_platform_role(self.request.user) != "platform_owner":
            raise PermissionDenied("Only platform owners can update tenants.")
        serializer.save(updated_by=str(self.request.user.id))

    def perform_destroy(self, instance):
        """Check permissions before deletion."""
        if get_user_platform_role(self.request.user) != "platform_owner":
            raise PermissionDenied("Only platform owners can delete tenants.")
        # Prevent deletion of active tenants without explicit confirmation
        if instance.status == Tenant.TenantStatus.ACTIVE:
            raise PermissionDenied(
                "Cannot delete active tenant. Suspend or cancel first."
            )
        instance.delete()

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        """Suspend a tenant."""
        tenant = self.get_object()
        if get_user_platform_role(request.user) != "platform_owner":
            raise PermissionDenied("Only platform owners can suspend tenants.")
        tenant.status = Tenant.TenantStatus.SUSPENDED
        tenant.save()
        return Response(
            {
                "status": "suspended",
                "message": f"Tenant {tenant.name} has been suspended.",
            }
        )

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate a tenant."""
        tenant = self.get_object()
        if get_user_platform_role(request.user) != "platform_owner":
            raise PermissionDenied("Only platform owners can activate tenants.")
        tenant.status = Tenant.TenantStatus.ACTIVE
        tenant.save()
        return Response(
            {"status": "active", "message": f"Tenant {tenant.name} has been activated."}
        )

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

        serializer = TenantResourceUsageSerializer(
            usage.order_by("-date")[:30], many=True
        )
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

        serializer = TenantHealthScoreSerializer(
            scores.order_by("-date")[:30], many=True
        )
        return Response(serializer.data)


class TenantModuleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Tenant Module management.

    CRITICAL: Platform-level operations - only platform owners can access.
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

    def perform_create(self, serializer):
        """Set created_by from authenticated user."""
        if get_user_platform_role(self.request.user) != "platform_owner":
            raise PermissionDenied("Only platform owners can manage tenant modules.")
        serializer.save(installed_by=str(self.request.user.id))

    @action(detail=True, methods=["post"])
    def enable(self, request, pk=None):
        """Enable a module for a tenant."""
        tenant_module = self.get_object()
        if get_user_platform_role(request.user) != "platform_owner":
            raise PermissionDenied("Only platform owners can enable modules.")
        tenant_module.is_enabled = True
        tenant_module.save()
        return Response(
            {
                "status": "enabled",
                "message": f"Module {tenant_module.module_name} enabled for {tenant_module.tenant.name}.",
            }
        )

    @action(detail=True, methods=["post"])
    def disable(self, request, pk=None):
        """Disable a module for a tenant."""
        tenant_module = self.get_object()
        if get_user_platform_role(request.user) != "platform_owner":
            raise PermissionDenied("Only platform owners can disable modules.")
        tenant_module.is_enabled = False
        tenant_module.save()
        return Response(
            {
                "status": "disabled",
                "message": f"Module {tenant_module.module_name} disabled for {tenant_module.tenant.name}.",
            }
        )


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


class TenantSettingsViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Tenant Settings management.

    CRITICAL: Platform-level operations - only platform owners can access.
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

    def perform_create(self, serializer):
        """Set created_by from authenticated user."""
        if get_user_platform_role(self.request.user) != "platform_owner":
            raise PermissionDenied("Only platform owners can manage tenant settings.")
        serializer.save(created_by=str(self.request.user.id))

    def perform_update(self, serializer):
        """Set updated_by from authenticated user."""
        if get_user_platform_role(self.request.user) != "platform_owner":
            raise PermissionDenied("Only platform owners can update tenant settings.")
        serializer.save(updated_by=str(self.request.user.id))


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
