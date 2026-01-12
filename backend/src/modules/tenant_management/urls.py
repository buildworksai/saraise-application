"""
Tenant Management URL Configuration.

CRITICAL: Platform-level routes (NO tenant_id in URLs).
Only platform owners can access these endpoints.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    TenantHealthScoreViewSet,
    TenantModuleViewSet,
    TenantResourceUsageViewSet,
    TenantSettingsViewSet,
    TenantViewSet,
)
from .health import health_check

router = DefaultRouter()
router.register(r"tenants", TenantViewSet, basename="tenant")
router.register(r"modules", TenantModuleViewSet, basename="tenant-module")
router.register(r"resource-usage", TenantResourceUsageViewSet, basename="tenant-resource-usage")
router.register(r"settings", TenantSettingsViewSet, basename="tenant-settings")
router.register(r"health-scores", TenantHealthScoreViewSet, basename="tenant-health-score")

urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="tenant_management_health_check"),
]
