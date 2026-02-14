"""
URL routing for Multi-Company module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import CompanyViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"companies", CompanyViewSet, basename="company")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
