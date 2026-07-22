"""Governed public API v2 routes for data migration."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    DataMigrationConfigurationViewSet,
    ExternalConnectionViewSet,
    MigrationJobViewSet,
    MigrationMappingViewSet,
    MigrationRollbackViewSet,
    MigrationRunViewSet,
    ValidationRuleViewSet,
)
from .health import LivenessView, ReadinessView

app_name = "data_migration"

router = DefaultRouter()
router.register("jobs", MigrationJobViewSet, basename="job")
router.register("mappings", MigrationMappingViewSet, basename="mapping")
router.register("validation-rules", ValidationRuleViewSet, basename="validation-rule")
router.register("runs", MigrationRunViewSet, basename="run")
router.register("rollbacks", MigrationRollbackViewSet, basename="rollback")
router.register("connections", ExternalConnectionViewSet, basename="connection")

urlpatterns = [
    path(
        "configuration/",
        DataMigrationConfigurationViewSet.as_view({"get": "retrieve_configuration", "patch": "update_configuration"}),
        name="configuration",
    ),
    path(
        "configuration/preview/",
        DataMigrationConfigurationViewSet.as_view({"post": "preview_configuration"}),
        name="configuration-preview",
    ),
    path(
        "configuration/versions/",
        DataMigrationConfigurationViewSet.as_view({"get": "configuration_versions"}),
        name="configuration-versions",
    ),
    path(
        "configuration/versions/<int:version>/restore/",
        DataMigrationConfigurationViewSet.as_view({"post": "restore_configuration"}),
        name="configuration-restore",
    ),
    path(
        "configuration/import/",
        DataMigrationConfigurationViewSet.as_view({"post": "import_configuration"}),
        name="configuration-import",
    ),
    path(
        "configuration/export/",
        DataMigrationConfigurationViewSet.as_view({"get": "export_configuration"}),
        name="configuration-export",
    ),
    path("", include(router.urls)),
    path("health/live/", LivenessView.as_view(), name="health-live"),
    path("health/ready/", ReadinessView.as_view(), name="health-ready"),
]
