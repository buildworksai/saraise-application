"""Compatibility routes for the existing fixed-assets API v1."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import LegacyFixedAssetViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"assets", LegacyFixedAssetViewSet, basename="fixed-asset")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
