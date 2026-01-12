from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import WorkflowViewSet, WorkflowInstanceViewSet, WorkflowTaskViewSet
from .health import health_check

router = DefaultRouter()
router.register(r"workflows", WorkflowViewSet, basename="workflow")
router.register(r"instances", WorkflowInstanceViewSet, basename="workflow-instance")
router.register(r"tasks", WorkflowTaskViewSet, basename="workflow-task")

urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
