"""
Platform Management API ViewSets

⚠️ ARCHITECTURAL NOTE: These ViewSets are READ-ONLY in the Application layer.
Platform configuration management (create, update, delete) MUST be performed
via Control Plane services in saraise-platform/saraise-control-plane/.

This module provides read-only access for:
- Reading platform settings for feature flags
- Reading system health status
- Reading audit events
- Reading platform metrics

CRITICAL: Platform configuration mutations are FORBIDDEN here - use Control Plane APIs.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound
from django.db import models
from django.utils import timezone
import uuid

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import (
    PlatformSetting,
    FeatureFlag,
    SystemHealth,
    PlatformAuditEvent,
    PlatformMetrics,
)
from .serializers import (
    PlatformSettingSerializer,
    PlatformSettingCreateSerializer,
    FeatureFlagSerializer,
    FeatureFlagCreateSerializer,
    SystemHealthSerializer,
    PlatformAuditEventSerializer,
    PlatformMetricsSerializer,
    PlatformMetricsRequestSerializer,
)
from .services import PlatformManagementService, AnalyticsService


class PlatformSettingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    READ-ONLY API endpoints for platform settings.
    
    ⚠️ ARCHITECTURAL VIOLATION PREVENTION:
    - CREATE operations: Use Control Plane API (saraise-platform/saraise-control-plane/)
    - UPDATE operations: Use Control Plane API
    - DELETE operations: Use Control Plane API
    
    This ViewSet only provides:
    - LIST: Read platform settings (filtered by tenant if applicable)
    - RETRIEVE: Read platform setting details
    
    Platform configuration management is FORBIDDEN in Application layer.
    """

    authentication_classes = [RelaxedCsrfSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return PlatformSettingCreateSerializer
        return PlatformSettingSerializer

    def get_queryset(self):
        """Filter settings by tenant_id. Platform owners can see all settings."""
        from src.core.auth_utils import get_user_platform_role
        
        platform_role = get_user_platform_role(self.request.user)
        
        # Platform owners can see all platform settings (platform-wide and tenant-specific)
        if platform_role == 'platform_owner':
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
        if platform_role == 'platform_owner':
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

    # ⚠️ ARCHITECTURAL ENFORCEMENT: Platform setting management operations removed
    # Platform setting creation/update MUST be performed via Control Plane services
    # in saraise-platform/saraise-control-plane/


class FeatureFlagViewSet(viewsets.ReadOnlyModelViewSet):
    """
    READ-ONLY API endpoints for feature flags.
    
    ⚠️ ARCHITECTURAL VIOLATION PREVENTION:
    - CREATE operations: Use Control Plane API (saraise-platform/saraise-control-plane/)
    - UPDATE operations: Use Control Plane API
    - TOGGLE operations: Use Control Plane API
    
    This ViewSet only provides:
    - LIST: Read feature flags (filtered by tenant if applicable)
    - RETRIEVE: Read feature flag details
    
    Feature flag management is FORBIDDEN in Application layer.
    """

    authentication_classes = [RelaxedCsrfSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        return FeatureFlagSerializer

    def get_queryset(self):
        """Filter flags by tenant_id. Platform owners can see all flags."""
        from src.core.auth_utils import get_user_platform_role
        
        platform_role = get_user_platform_role(self.request.user)
        
        # Platform owners can see all feature flags (platform-wide and tenant-specific)
        if platform_role == 'platform_owner':
            return FeatureFlag.objects.all()
        
        # Other users only see flags for their tenant or platform-wide
        tenant_id_str = get_user_tenant_id(self.request.user)

        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
                queryset = FeatureFlag.objects.filter(
                    models.Q(tenant_id__isnull=True) | models.Q(tenant_id=tenant_id)
                )
            except (ValueError, TypeError):
                queryset = FeatureFlag.objects.filter(tenant_id__isnull=True)
        else:
            queryset = FeatureFlag.objects.filter(tenant_id__isnull=True)

        return queryset

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
        if platform_role == 'platform_owner':
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

    # ⚠️ ARCHITECTURAL ENFORCEMENT: Feature flag management operations removed
    # Feature flag creation/update/toggle MUST be performed via Control Plane services
    # in saraise-platform/saraise-control-plane/


class SystemHealthViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoints for system health (read-only)."""

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
                    "healthy"
                    if unhealthy == 0 and degraded == 0
                    else "degraded" if unhealthy == 0 else "unhealthy"
                ),
                "healthy": healthy,
                "degraded": degraded,
                "unhealthy": unhealthy,
                "total": services.count(),
                "timestamp": timezone.now().isoformat(),
            }
        )


class PlatformAuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoints for audit events (read-only).

    CRITICAL: No create/update/delete allowed.
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
        if platform_role == 'platform_owner':
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
                queryset = PlatformAuditEvent.objects.filter(
                    tenant_id__isnull=True
                ).order_by("-timestamp")
        else:
            queryset = PlatformAuditEvent.objects.filter(
                tenant_id__isnull=True
            ).order_by("-timestamp")

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
        if platform_role == 'platform_owner':
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


class PlatformMetricsViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoints for platform metrics (read-only + save action)."""

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
        metric_type = request.query_params.get(
            "metric_type", PlatformMetrics.MetricType.COMPLETE
        )
        time_range = request.query_params.get("time_range", "30d")
        metrics_data = AnalyticsService().get_metrics(
            metric_type=metric_type, time_range=time_range
        )
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
