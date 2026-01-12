"""
URL routing for DataMigration module.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api import (
    MigrationJobViewSet,
    MigrationLogViewSet,
    MigrationMappingViewSet,
    MigrationValidationViewSet,
)
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"jobs", MigrationJobViewSet, basename="migration-job")
router.register(r"mappings", MigrationMappingViewSet, basename="migration-mapping")
router.register(r"logs", MigrationLogViewSet, basename="migration-log")
router.register(r"validations", MigrationValidationViewSet, basename="migration-validation")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
