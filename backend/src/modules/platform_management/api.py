"""
Platform Management API ViewSets

⚠️ MODE-AWARE ARCHITECTURE:
- Self-Hosted Mode: Full CRUD operations (Control Plane not deployed)
- SaaS Mode: Read-only operations (Control Plane manages configuration)

This module provides:
- Self-Hosted: Full platform configuration management
- SaaS: Read-only access for feature flags, health, audit, metrics
  (Mutations must go through Control Plane APIs)
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import FeatureFlag, PlatformAuditEvent, PlatformMetrics, PlatformSetting, SystemHealth
from .serializers import (
    FeatureFlagCreateSerializer,
    FeatureFlagSerializer,
    PlatformAuditEventSerializer,
    PlatformMetricsRequestSerializer,
    PlatformMetricsSerializer,
    PlatformSettingCreateSerializer,
    PlatformSettingSerializer,
    SystemHealthSerializer,
)
from .services import AnalyticsService, PlatformManagementService


def _get_viewset_base():
    """
    Return the appropriate ViewSet base class based on SARAISE_MODE.

    - Self-Hosted: ModelViewSet (full CRUD)
    - SaaS: ReadOnlyModelViewSet (read-only, mutations via Control Plane)
    """
    if settings.SARAISE_MODE in ("self-hosted", "development"):
        return viewsets.ModelViewSet
    else:
        return viewsets.ReadOnlyModelViewSet


class PlatformSettingViewSet(_get_viewset_base()):
    """
    Mode-aware API endpoints for platform settings.

    Self-Hosted Mode: Full CRUD operations
    SaaS Mode: Read-only (mutations via Control Plane)
    """

    authentication_classes = [RelaxedCsrfSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def check_object_permissions(self, request, obj):
        """Override to skip object permission check for list action."""
        # For list action, we don't have an object, so skip this check
        if self.action == "list":
            return
        super().check_object_permissions(request, obj)

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return PlatformSettingCreateSerializer
        return PlatformSettingSerializer

    def get_queryset(self):
        """Filter settings by tenant_id. Platform owners can see all settings."""
        from src.core.auth_utils import get_user_platform_role

        platform_role = get_user_platform_role(self.request.user)

        # Platform owners can see all platform settings (platform-wide and tenant-specific)
        if platform_role == "platform_owner":
            return PlatformSetting.objects.all()

        # Other users only see settings for their tenant or platform-wide
        tenant_id_str = get_user_tenant_id(self.request.user)

        # Return platform-wide settings + tenant-specific settings
        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
                # Only return platform-wide OR this tenant's settings
                queryset = PlatformSetting.objects.filter(
                    models.Q(tenant_id__isnull=True) | models.Q(tenant_id=tenant_id)
                )
            except (ValueError, TypeError):
                # Invalid UUID, only return platform-wide
                queryset = PlatformSetting.objects.filter(tenant_id__isnull=True)
        else:
            # No tenant_id, only platform-wide settings
            queryset = PlatformSetting.objects.filter(tenant_id__isnull=True)

        return queryset

    def list(self, request, *args, **kwargs):
        """Override list to always return 200, even if queryset is empty."""
        # CRITICAL: Set action before permission checks
        self.action = "list"
        # Check permissions
        self.check_permissions(request)
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def get_object(self):
        """Override to ensure tenant isolation on detail view. Platform owners can access any setting."""
        from src.core.auth_utils import get_user_platform_role

        platform_role = get_user_platform_role(self.request.user)

        # Get lookup value
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs.get(lookup_url_kwarg)

        if not lookup_value:
            raise NotFound("Not found.")

        # CRITICAL: Check tenant BEFORE getting from queryset
        try:
            obj = PlatformSetting.objects.get(**{self.lookup_field: lookup_value})
        except PlatformSetting.DoesNotExist:
            raise NotFound("Not found.")

        # Platform owners can access any platform setting
        if platform_role == "platform_owner":
            return obj

        # CRITICAL: Explicit tenant isolation check for non-platform owners
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = None
        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
            except (ValueError, TypeError):
                tenant_id = None

        # If object has tenant_id, user MUST have matching tenant_id
        if obj.tenant_id is not None:
            if tenant_id is None:
                # Object is tenant-specific but user has no tenant - deny access
                raise NotFound("Not found.")
            # Compare UUIDs directly (convert to string to handle UUID comparison)
            obj_tenant_str = str(obj.tenant_id)
            user_tenant_str = str(tenant_id)
            if obj_tenant_str != user_tenant_str:
                # Object belongs to different tenant - deny access
                raise NotFound("Not found.")
        # else: object is platform-wide, accessible to all authenticated users

        return obj

    def create(self, request, *args, **kwargs):
        """Create platform setting (self-hosted only)."""
        if settings.SARAISE_MODE == "saas":
            raise PermissionDenied(
                "Platform settings can only be created via Control Plane in SaaS mode. "
                "Use saraise-platform/saraise-control-plane/ APIs."
            )
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """Update platform setting (self-hosted only)."""
        if settings.SARAISE_MODE == "saas":
            raise PermissionDenied(
                "Platform settings can only be updated via Control Plane in SaaS mode. "
                "Use saraise-platform/saraise-control-plane/ APIs."
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Delete platform setting (self-hosted only)."""
        if settings.SARAISE_MODE == "saas":
            raise PermissionDenied(
                "Platform settings can only be deleted via Control Plane in SaaS mode. "
                "Use saraise-platform/saraise-control-plane/ APIs."
            )
        return super().destroy(request, *args, **kwargs)


class FeatureFlagViewSet(_get_viewset_base()):
    """
    Mode-aware API endpoints for feature flags.

    Self-Hosted Mode: Full CRUD operations
    SaaS Mode: Read-only (mutations via Control Plane)
    """

    authentication_classes = [RelaxedCsrfSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def check_object_permissions(self, request, obj):
        """Override to skip object permission check for list action."""
        # For list action, we don't have an object, so skip this check
        if self.action == "list":
            return
        super().check_object_permissions(request, obj)

    def get_serializer_class(self):
        return FeatureFlagSerializer

    def get_queryset(self):
        """Filter flags by tenant_id. Platform owners can see all flags."""
        from src.core.auth_utils import get_user_platform_role

        platform_role = get_user_platform_role(self.request.user)

        # Platform owners can see all feature flags (platform-wide and tenant-specific)
        if platform_role == "platform_owner":
            return FeatureFlag.objects.all()

        # Other users only see flags for their tenant or platform-wide
        tenant_id_str = get_user_tenant_id(self.request.user)

        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
                queryset = FeatureFlag.objects.filter(models.Q(tenant_id__isnull=True) | models.Q(tenant_id=tenant_id))
            except (ValueError, TypeError):
                queryset = FeatureFlag.objects.filter(tenant_id__isnull=True)
        else:
            queryset = FeatureFlag.objects.filter(tenant_id__isnull=True)

        return queryset

    def list(self, request, *args, **kwargs):
        """Override list to always return 200, even if queryset is empty."""
        # CRITICAL: Set action before permission checks
        self.action = "list"
        # Check permissions
        self.check_permissions(request)
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def get_object(self):
        """Override to ensure tenant isolation on detail view. Platform owners can access any flag."""
        from src.core.auth_utils import get_user_platform_role

        platform_role = get_user_platform_role(self.request.user)

        # Get lookup value
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs.get(lookup_url_kwarg)

        if not lookup_value:
            raise NotFound("Not found.")

        # CRITICAL: Check tenant BEFORE getting from queryset
        try:
            obj = FeatureFlag.objects.get(**{self.lookup_field: lookup_value})
        except FeatureFlag.DoesNotExist:
            raise NotFound("Not found.")

        # Platform owners can access any feature flag
        if platform_role == "platform_owner":
            return obj

        # CRITICAL: Explicit tenant isolation check for non-platform owners
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = None
        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
            except (ValueError, TypeError):
                tenant_id = None

        if obj.tenant_id is not None:
            if tenant_id is None:
                raise NotFound("Not found.")
            if str(obj.tenant_id) != str(tenant_id):
                raise NotFound("Not found.")

        return obj

    def create(self, request, *args, **kwargs):
        """Create feature flag (self-hosted only)."""
        if settings.SARAISE_MODE == "saas":
            raise PermissionDenied(
                "Feature flags can only be created via Control Plane in SaaS mode. "
                "Use saraise-platform/saraise-control-plane/ APIs."
            )
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """Update feature flag (self-hosted only)."""
        if settings.SARAISE_MODE == "saas":
            raise PermissionDenied(
                "Feature flags can only be updated via Control Plane in SaaS mode. "
                "Use saraise-platform/saraise-control-plane/ APIs."
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Delete feature flag (self-hosted only)."""
        if settings.SARAISE_MODE == "saas":
            raise PermissionDenied(
                "Feature flags can only be deleted via Control Plane in SaaS mode. "
                "Use saraise-platform/saraise-control-plane/ APIs."
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def toggle(self, request, pk=None):
        """Toggle feature flag enabled state (self-hosted only)."""
        if settings.SARAISE_MODE == "saas":
            raise PermissionDenied(
                "Feature flags can only be toggled via Control Plane in SaaS mode. "
                "Use saraise-platform/saraise-control-plane/ APIs."
            )
        flag = self.get_object()
        flag.enabled = not flag.enabled
        flag.save()
        serializer = self.get_serializer(flag)
        return Response(serializer.data)


class SystemHealthViewSet(_get_viewset_base()):
    """
    Mode-aware API endpoints for system health.

    Self-Hosted Mode: Full CRUD operations
    SaaS Mode: Read-only (health managed by Control Plane)
    """

    authentication_classes = [RelaxedCsrfSessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = SystemHealthSerializer
    queryset = SystemHealth.objects.all()

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Get health summary for all services."""
        services = SystemHealth.objects.all()
        healthy = services.filter(status="healthy").count()
        degraded = services.filter(status="degraded").count()
        unhealthy = services.filter(status="unhealthy").count()

        return Response(
            {
                "status": (
                    "healthy" if unhealthy == 0 and degraded == 0 else "degraded" if unhealthy == 0 else "unhealthy"
                ),
                "healthy": healthy,
                "degraded": degraded,
                "unhealthy": unhealthy,
                "total": services.count(),
                "timestamp": timezone.now().isoformat(),
            }
        )

    def create(self, request, *args, **kwargs):
        """Create health record (self-hosted only)."""
        if settings.SARAISE_MODE == "saas":
            raise PermissionDenied("System health records can only be created via Control Plane in SaaS mode.")
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """Update health record (self-hosted only)."""
        if settings.SARAISE_MODE == "saas":
            raise PermissionDenied("System health records can only be updated via Control Plane in SaaS mode.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Delete health record (self-hosted only)."""
        if settings.SARAISE_MODE == "saas":
            raise PermissionDenied("System health records can only be deleted via Control Plane in SaaS mode.")
        return super().destroy(request, *args, **kwargs)


class PlatformAuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoints for audit events (read-only in all modes).

    Audit events are immutable - no create/update/delete allowed.
    Events are created by the system automatically.
    """

    authentication_classes = [RelaxedCsrfSessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = PlatformAuditEventSerializer

    def get_queryset(self):
        """Filter audit events by tenant_id. Platform owners can see all events."""
        from src.core.auth_utils import get_user_platform_role

        # Ensure user is authenticated
        if not self.request.user or not self.request.user.is_authenticated:
            return PlatformAuditEvent.objects.none()

        platform_role = get_user_platform_role(self.request.user)

        # Platform owners can see all audit events
        if platform_role == "platform_owner":
            return PlatformAuditEvent.objects.all().order_by("-timestamp")

        # Other users only see events for their tenant or platform-wide
        tenant_id_str = get_user_tenant_id(self.request.user)

        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
                queryset = PlatformAuditEvent.objects.filter(
                    models.Q(tenant_id__isnull=True) | models.Q(tenant_id=tenant_id)
                ).order_by("-timestamp")
            except (ValueError, TypeError):
                queryset = PlatformAuditEvent.objects.filter(tenant_id__isnull=True).order_by("-timestamp")
        else:
            queryset = PlatformAuditEvent.objects.filter(tenant_id__isnull=True).order_by("-timestamp")

        return queryset

    def get_object(self):
        """Override to ensure tenant isolation on detail view. Platform owners can access any event."""
        from src.core.auth_utils import get_user_platform_role

        platform_role = get_user_platform_role(self.request.user)

        # Get lookup value
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs.get(lookup_url_kwarg)

        if not lookup_value:
            raise NotFound("Not found.")

        # CRITICAL: Check tenant BEFORE getting from queryset
        try:
            obj = PlatformAuditEvent.objects.get(**{self.lookup_field: lookup_value})
        except PlatformAuditEvent.DoesNotExist:
            raise NotFound("Not found.")

        # Platform owners can access any audit event
        if platform_role == "platform_owner":
            return obj

        # CRITICAL: Explicit tenant isolation check for non-platform owners
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = None
        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
            except (ValueError, TypeError):
                tenant_id = None

        if obj.tenant_id is not None:
            if tenant_id is None:
                raise NotFound("Not found.")
            if str(obj.tenant_id) != str(tenant_id):
                raise NotFound("Not found.")

        return obj


class PlatformMetricsViewSet(_get_viewset_base()):
    """
    Mode-aware API endpoints for platform metrics.

    Self-Hosted Mode: Full CRUD operations
    SaaS Mode: Read-only + save action (metrics reported to Control Plane)
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PlatformMetricsSerializer

    def get_queryset(self):
        queryset = PlatformMetrics.objects.all().order_by("-recorded_at")
        metric_type = self.request.query_params.get("metric_type")
        time_range = self.request.query_params.get("time_range")
        if metric_type:
            queryset = queryset.filter(metric_type=metric_type)
        if time_range:
            queryset = queryset.filter(time_range=time_range)
        return queryset

    @action(detail=False, methods=["get"])
    def current(self, request):
        """Return current metrics snapshot without persisting."""
        metric_type = request.query_params.get("metric_type", PlatformMetrics.MetricType.COMPLETE)
        time_range = request.query_params.get("time_range", "30d")
        metrics_data = AnalyticsService().get_metrics(metric_type=metric_type, time_range=time_range)
        return Response(
            {
                "metric_type": metric_type,
                "time_range": time_range,
                "metrics_data": metrics_data,
                "recorded_at": timezone.now().isoformat(),
            }
        )

    @action(detail=False, methods=["post"])
    def save(self, request):
        """Persist a metrics snapshot."""
        serializer = PlatformMetricsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        metric_type = serializer.validated_data["metric_type"]
        time_range = serializer.validated_data["time_range"]
        metric = AnalyticsService().save_metrics(
            metric_type=metric_type,
            time_range=time_range,
            created_by=request.user.id,
        )
        return Response(PlatformMetricsSerializer(metric).data, status=status.HTTP_201_CREATED)

    def create(self, request, *args, **kwargs):
        """Create metrics record (self-hosted only)."""
        if settings.SARAISE_MODE == "saas":
            raise PermissionDenied(
                "Platform metrics can only be created via Control Plane in SaaS mode. "
                "Use the /save/ action to persist metrics snapshots."
            )
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """Update metrics record (self-hosted only)."""
        if settings.SARAISE_MODE == "saas":
            raise PermissionDenied("Platform metrics can only be updated via Control Plane in SaaS mode.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Delete metrics record (self-hosted only)."""
        if settings.SARAISE_MODE == "saas":
            raise PermissionDenied("Platform metrics can only be deleted via Control Plane in SaaS mode.")
        return super().destroy(request, *args, **kwargs)
