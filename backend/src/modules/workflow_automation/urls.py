"""Canonical workflow automation route surface.

The project mounts these patterns at both v2 and the temporary v1 compatibility
prefix.  Controllers add deprecation headers when reached through v1.
"""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .api import (
    CatalogViewSet,
    HealthView,
    WorkflowConfigurationViewSet,
    WorkflowInstanceViewSet,
    WorkflowTaskViewSet,
    WorkflowViewSet,
)

app_name = "workflow_automation"

router = SimpleRouter()
router.register("workflows", WorkflowViewSet, basename="workflow")
router.register("instances", WorkflowInstanceViewSet, basename="workflow-instance")
router.register("tasks", WorkflowTaskViewSet, basename="workflow-task")
router.register("catalog", CatalogViewSet, basename="workflow-catalog")
router.register("configuration", WorkflowConfigurationViewSet, basename="workflow-configuration")

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("", include(router.urls)),
]
