"""
URL routing for Asset Management module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import AssetConfigurationViewSet, AssetViewSet, DepreciationEntryViewSet, ModuleHealthAPIView

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"assets", AssetViewSet, basename="asset")
router.register(r"depreciation-entries", DepreciationEntryViewSet, basename="depreciation-entry")
router.register(r"configuration", AssetConfigurationViewSet, basename="asset-configuration")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", ModuleHealthAPIView.as_view(), name="health_check"),
]
