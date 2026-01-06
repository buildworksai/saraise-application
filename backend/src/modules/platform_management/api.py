"""
Platform Management API ViewSets
DRF ViewSets with tenant isolation and Policy Engine authorization
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


class PlatformSettingViewSet(viewsets.ModelViewSet):
    """
    API endpoints for platform settings.

    Architecture Compliance:
    - ✅ Tenant filtering in get_queryset
    - ✅ tenant_id set on create
    - ✅ Audit logging on mutations
    """

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return PlatformSettingCreateSerializer
        return PlatformSettingSerializer

    def get_queryset(self):
        """Filter settings by tenant_id for tenant-specific settings."""
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
        """Override to ensure tenant isolation on detail view."""
        # Get tenant_id first for explicit check
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = None
        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
            except (ValueError, TypeError):
                tenant_id = None

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

        # CRITICAL: Explicit tenant isolation check
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

    def perform_create(self, serializer):
        """Set tenant_id and audit on create."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else None

        instance = serializer.save(tenant_id=tenant_id, created_by=self.request.user.id)
        # Audit logging
        PlatformManagementService.log_audit_event(
            action="platform.setting.created",
            actor_id=self.request.user.id,
            resource_type="PlatformSetting",
            resource_id=instance.id,
            tenant_id=tenant_id,
            details={"key": instance.key},
        )

    def perform_update(self, serializer):
        """Audit on update."""
        instance = serializer.save(updated_by=self.request.user.id)
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else None
        PlatformManagementService.log_audit_event(
            action="platform.setting.updated",
            actor_id=self.request.user.id,
            resource_type="PlatformSetting",
            resource_id=instance.id,
            tenant_id=tenant_id,
            details={"key": instance.key},
        )


class FeatureFlagViewSet(viewsets.ModelViewSet):
    """API endpoints for feature flags."""

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return FeatureFlagCreateSerializer
        return FeatureFlagSerializer

    def get_queryset(self):
        """Filter flags by tenant_id."""
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
        """Override to ensure tenant isolation on detail view."""
        # Get tenant_id first for explicit check
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = None
        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
            except (ValueError, TypeError):
                tenant_id = None

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

        # CRITICAL: Explicit tenant isolation check
        if obj.tenant_id is not None:
            if tenant_id is None:
                raise NotFound("Not found.")
            if str(obj.tenant_id) != str(tenant_id):
                raise NotFound("Not found.")

        return obj

    def perform_create(self, serializer):
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else None
        serializer.save(tenant_id=tenant_id)

    @action(detail=True, methods=["post"])
    def toggle(self, request, pk=None):
        """Toggle feature flag on/off."""
        flag = self.get_object()
        flag.enabled = not flag.enabled
        flag.save()

        tenant_id_str = get_user_tenant_id(request.user)
        tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else None
        PlatformManagementService.log_audit_event(
            action="platform.feature_flag.toggled",
            actor_id=request.user.id,
            resource_type="FeatureFlag",
            resource_id=flag.id,
            tenant_id=tenant_id,
            details={"name": flag.name, "enabled": flag.enabled},
        )

        return Response(FeatureFlagSerializer(flag).data)


class SystemHealthViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoints for system health (read-only)."""

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

    permission_classes = [IsAuthenticated]
    serializer_class = PlatformAuditEventSerializer

    def get_queryset(self):
        """Filter audit events by tenant_id."""
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
        """Override to ensure tenant isolation on detail view."""
        # Get tenant_id first for explicit check
        tenant_id_str = get_user_tenant_id(self.request.user)
        tenant_id = None
        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
            except (ValueError, TypeError):
                tenant_id = None

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

        # CRITICAL: Explicit tenant isolation check
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
