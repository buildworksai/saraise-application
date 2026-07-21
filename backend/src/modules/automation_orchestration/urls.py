"""API v2 routes for the orchestration DAG domain."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    DefinitionViewSet,
    EdgeViewSet,
    NodeTypeViewSet,
    NodeViewSet,
    OrchestrationHealthView,
    RunViewSet,
    ScheduleViewSet,
    TaskRunViewSet,
)

app_name = "automation_orchestration"

router = DefaultRouter()
router.register("definitions", DefinitionViewSet, basename="definition")
router.register("nodes", NodeViewSet, basename="node")
router.register("edges", EdgeViewSet, basename="edge")
router.register("schedules", ScheduleViewSet, basename="schedule")
router.register("runs", RunViewSet, basename="run")
router.register("task-runs", TaskRunViewSet, basename="task-run")
router.register("node-types", NodeTypeViewSet, basename="node-type")

urlpatterns = [
    path("health/", OrchestrationHealthView.as_view(), name="health"),
    path("", include(router.urls)),
]
