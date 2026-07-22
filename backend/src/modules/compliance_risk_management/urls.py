"""Governed API v2 routes for compliance risk management."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    CalendarViewSet,
    ConfigurationViewSet,
    ControlTestViewSet,
    ControlViewSet,
    DashboardViewSet,
    HealthAPIView,
    HeatmapViewSet,
    JobViewSet,
    RemediationViewSet,
    RequirementViewSet,
    RiskAssessmentViewSet,
)

router = DefaultRouter()
router.register(r"risks", RiskAssessmentViewSet, basename="compliance-risk")
router.register(r"controls", ControlViewSet, basename="compliance-control")
router.register(r"tests", ControlTestViewSet, basename="compliance-control-test")
router.register(r"requirements", RequirementViewSet, basename="compliance-requirement")
router.register(r"calendar", CalendarViewSet, basename="compliance-calendar")
router.register(r"remediations", RemediationViewSet, basename="compliance-remediation")
router.register(r"dashboard", DashboardViewSet, basename="compliance-dashboard")
router.register(r"heatmap", HeatmapViewSet, basename="compliance-heatmap")
router.register(r"configuration", ConfigurationViewSet, basename="compliance-configuration")
router.register(r"jobs", JobViewSet, basename="compliance-job")

configuration = ConfigurationViewSet.as_view({"get": "list", "put": "update"})

urlpatterns = [
    path("configuration/", configuration, name="compliance-configuration-active"),
    path("health/live/", HealthAPIView.as_view(), {"probe": "live"}, name="compliance-health-live"),
    path("health/ready/", HealthAPIView.as_view(), {"probe": "ready"}, name="compliance-health-ready"),
    path("", include(router.urls)),
]
