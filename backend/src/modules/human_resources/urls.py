"""Canonical API v2 routing for Human Resources."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import AttendanceViewSet, DepartmentViewSet, EmployeeViewSet, LeaveBalanceViewSet, LeaveRequestViewSet
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
    path("", include(router.urls)),
]


__all__ = ["router", "urlpatterns"]
