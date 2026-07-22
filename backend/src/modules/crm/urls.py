"""
URL routing for CRM module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    AccountViewSet,
    ActivityViewSet,
    AsyncJobViewSet,
    ContactViewSet,
    ForecastingViewSet,
    LeadViewSet,
    OpportunityViewSet,
)
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"leads", LeadViewSet, basename="lead")
router.register(r"accounts", AccountViewSet, basename="account")
router.register(r"contacts", ContactViewSet, basename="contact")
router.register(r"opportunities", OpportunityViewSet, basename="opportunity")
router.register(r"activities", ActivityViewSet, basename="activity")
router.register(r"forecasting", ForecastingViewSet, basename="forecasting")
router.register(r"jobs", AsyncJobViewSet, basename="job")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
