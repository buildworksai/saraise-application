"""
URL routing for Compliance Risk Management module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import ComplianceRiskViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"risks", ComplianceRiskViewSet, basename="compliance-risk")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
