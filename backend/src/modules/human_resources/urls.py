"""
URL routing for Human Resources module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import AttendanceViewSet, DepartmentViewSet, EmployeeViewSet, LeaveRequestViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"departments", DepartmentViewSet, basename="department")
router.register(r"employees", EmployeeViewSet, basename="employee")
router.register(r"attendances", AttendanceViewSet, basename="attendance")
router.register(r"leave-requests", LeaveRequestViewSet, basename="leave-request")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
