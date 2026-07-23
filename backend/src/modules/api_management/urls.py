"""Governed API-management routes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    ApiManagementResourceViewSet,
    ConfigurationExportView,
    ConfigurationHistoryView,
    ConfigurationImportView,
    ConfigurationPreviewView,
    ConfigurationRollbackView,
    ConfigurationSchemaView,
    ConfigurationView,
    HealthView,
)

router = DefaultRouter()
router.register(r"resources", ApiManagementResourceViewSet, basename="resource")

urlpatterns = [
    path("", include(router.urls)),
    path("configuration/", ConfigurationView.as_view(), name="configuration"),
    path("configuration/schema/", ConfigurationSchemaView.as_view(), name="configuration-schema"),
    path("configuration/preview/", ConfigurationPreviewView.as_view(), name="configuration-preview"),
    path("configuration/history/", ConfigurationHistoryView.as_view(), name="configuration-history"),
    path("configuration/rollback/", ConfigurationRollbackView.as_view(), name="configuration-rollback"),
    path("configuration/import/", ConfigurationImportView.as_view(), name="configuration-import"),
    path("configuration/export/", ConfigurationExportView.as_view(), name="configuration-export"),
    path("health/", HealthView.as_view(), name="health-check"),
]
