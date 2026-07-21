"""Governed v2 process-mining routes; the generic v1 surface is removed."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import BottleneckViewSet, ConformanceViewSet, DiscoveryViewSet, EventExportViewSet, ModuleHealthAPIView, ProcessEventViewSet, ProcessModelVersionViewSet, ProcessModelViewSet, ProcessOverviewViewSet

app_name = "process_mining"
router = DefaultRouter()
router.register("processes", ProcessOverviewViewSet, basename="process")
router.register("events", ProcessEventViewSet, basename="event")
router.register("exports", EventExportViewSet, basename="export")
router.register("discoveries", DiscoveryViewSet, basename="discovery")
router.register("models", ProcessModelViewSet, basename="model")
router.register("model-versions", ProcessModelVersionViewSet, basename="model-version")
router.register("conformance-checks", ConformanceViewSet, basename="conformance-check")
router.register("bottleneck-analyses", BottleneckViewSet, basename="bottleneck-analysis")

urlpatterns = [path("", include(router.urls)), path("health/", ModuleHealthAPIView.as_view(), name="health")]
