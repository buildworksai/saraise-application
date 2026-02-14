"""
URL routing for Master Data Management module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import MasterDataEntityViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"entities", MasterDataEntityViewSet, basename="entity")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
