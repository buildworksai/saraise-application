"""
Platform Management URL Configuration
"""

from rest_framework.routers import DefaultRouter

from .api import (
    FeatureFlagViewSet,
    PlatformAuditEventViewSet,
    PlatformMetricsViewSet,
    PlatformSettingViewSet,
    SystemHealthViewSet,
)

router = DefaultRouter()
router.register(r"settings", PlatformSettingViewSet, basename="platform-settings")
router.register(r"feature-flags", FeatureFlagViewSet, basename="feature-flags")
router.register(r"health", SystemHealthViewSet, basename="system-health")
router.register(r"audit-events", PlatformAuditEventViewSet, basename="audit-events")
router.register(r"metrics", PlatformMetricsViewSet, basename="metrics")

urlpatterns = router.urls
