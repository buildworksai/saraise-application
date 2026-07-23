"""Canonical API v2 routing for Human Resources."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    AttendanceViewSet,
    DepartmentViewSet,
    EmployeeViewSet,
    HumanResourcesConfigurationViewSet,
    LeaveBalanceViewSet,
    LeaveRequestViewSet,
)
from .health import health_check

app_name = "human_resources"

router = DefaultRouter()
router.register("departments", DepartmentViewSet, basename="department")
router.register("employees", EmployeeViewSet, basename="employee")
router.register("attendances", AttendanceViewSet, basename="attendance")
router.register("leave-balances", LeaveBalanceViewSet, basename="leave-balance")
router.register("leave-requests", LeaveRequestViewSet, basename="leave-request")

urlpatterns = [
    path("health/", health_check, name="health"),
    path(
        "configuration/",
        HumanResourcesConfigurationViewSet.as_view({"get": "list", "patch": "partial_update"}),
        name="configuration",
    ),
    path(
        "configuration/preview/",
        HumanResourcesConfigurationViewSet.as_view({"post": "preview"}),
        name="configuration-preview",
    ),
    path(
        "configuration/history/",
        HumanResourcesConfigurationViewSet.as_view({"get": "history"}),
        name="configuration-history",
    ),
    path(
        "configuration/audit/",
        HumanResourcesConfigurationViewSet.as_view({"get": "audit"}),
        name="configuration-audit",
    ),
    path(
        "configuration/rollback/",
        HumanResourcesConfigurationViewSet.as_view({"post": "rollback"}),
        name="configuration-rollback",
    ),
    path(
        "configuration/import/",
        HumanResourcesConfigurationViewSet.as_view({"post": "import_configuration"}),
        name="configuration-import",
    ),
    path(
        "configuration/export/",
        HumanResourcesConfigurationViewSet.as_view({"get": "export_configuration"}),
        name="configuration-export",
    ),
    path("", include(router.urls)),
]


__all__ = ["router", "urlpatterns"]
