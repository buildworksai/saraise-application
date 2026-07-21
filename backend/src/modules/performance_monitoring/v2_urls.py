"""Governed API v2 routes for performance monitoring."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    AlertRuleViewSet,
    AlertViewSet,
    ComplianceViewSet,
    DashboardViewSet,
    EnvironmentViewSet,
    ExtensionViewSet,
    LogViewSet,
    MetricDefinitionViewSet,
    MetricViewSet,
    ReportViewSet,
    ServiceViewSet,
    SLAViewSet,
    SLOViewSet,
    TelemetrySourceViewSet,
    TraceViewSet,
)
from .health import governed_health_check

router = DefaultRouter()
router.register("telemetry-sources", TelemetrySourceViewSet, basename="v2-telemetry-source")
router.register("environments", EnvironmentViewSet, basename="v2-monitoring-environment")
router.register("services", ServiceViewSet, basename="v2-monitored-service")
router.register("metric-definitions", MetricDefinitionViewSet, basename="v2-metric-definition")
router.register("metrics", MetricViewSet, basename="v2-metric")
router.register("logs", LogViewSet, basename="v2-log")
router.register("traces", TraceViewSet, basename="v2-trace")
router.register("dashboards", DashboardViewSet, basename="v2-dashboard")
router.register("alerts/rules", AlertRuleViewSet, basename="v2-alert-rule")
router.register("alerts", AlertViewSet, basename="v2-alert")
router.register("sla", SLAViewSet, basename="v2-sla")
router.register("slos", SLOViewSet, basename="v2-slo")
router.register("compliance-records", ComplianceViewSet, basename="v2-compliance-record")
router.register("reports", ReportViewSet, basename="v2-sla-report")
router.register("extensions", ExtensionViewSet, basename="v2-monitoring-extension")

urlpatterns = [
    path("", include(router.urls)),
    path("health/", governed_health_check, name="v2-performance-monitoring-health"),
]
