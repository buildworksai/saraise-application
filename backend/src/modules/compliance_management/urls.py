"""
URL routing for Compliance Management module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import CompliancePolicyViewSet, ComplianceRequirementViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"policies", CompliancePolicyViewSet, basename="compliance-policy")
router.register(r"requirements", ComplianceRequirementViewSet, basename="compliance-requirement")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
