"""
URL routing for Business Intelligence module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import DashboardViewSet, ReportViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"reports", ReportViewSet, basename="report")
router.register(r"dashboards", DashboardViewSet, basename="dashboard")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
