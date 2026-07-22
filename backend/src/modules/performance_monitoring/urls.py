"""Performance-monitoring API routes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .health import health_check
from .v1_api import (
    V1AlertRuleViewSet,
    V1AlertViewSet,
    V1ComplianceViewSet,
    V1ConfigurationViewSet,
    V1DashboardViewSet,
    V1EnvironmentViewSet,
    V1ExtensionViewSet,
    V1LogViewSet,
    V1MetricDataPointViewSet,
    V1MetricDefinitionViewSet,
    V1MetricViewSet,
    V1ReportViewSet,
    V1ServiceViewSet,
    V1SLAViewSet,
    V1SLOViewSet,
    V1TelemetrySourceViewSet,
    V1TraceViewSet,
)

router = DefaultRouter()
router.register("telemetry-sources", V1TelemetrySourceViewSet, basename="telemetry-source")
router.register("environments", V1EnvironmentViewSet, basename="monitoring-environment")
router.register("services", V1ServiceViewSet, basename="monitored-service")
router.register("metric-definitions", V1MetricDefinitionViewSet, basename="metric-definition")
router.register("metrics", V1MetricViewSet, basename="metric")
router.register("metric-data-points", V1MetricDataPointViewSet, basename="metric-data-point")
router.register("logs", V1LogViewSet, basename="log")
router.register("traces", V1TraceViewSet, basename="trace")
router.register("dashboards", V1DashboardViewSet, basename="dashboard")
router.register("alerts/rules", V1AlertRuleViewSet, basename="alert-rule")
router.register("alerts", V1AlertViewSet, basename="alert")
router.register("sla", V1SLAViewSet, basename="sla")
router.register("slos", V1SLOViewSet, basename="slo")
router.register("compliance-records", V1ComplianceViewSet, basename="compliance-record")
router.register("reports", V1ReportViewSet, basename="sla-report")
router.register("extensions", V1ExtensionViewSet, basename="monitoring-extension")
router.register("configuration", V1ConfigurationViewSet, basename="monitoring-configuration")

urlpatterns = [path("", include(router.urls)), path("health/", health_check, name="performance-monitoring-health")]
