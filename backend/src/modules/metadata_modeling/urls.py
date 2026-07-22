from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import (
    DynamicResourceViewSet, EntityDefinitionViewSet, MetadataConfigurationViewSet,
    MetadataHealthView, NamingSequenceViewSet,
)

router = DefaultRouter()
router.register(r"entity-definitions", EntityDefinitionViewSet, basename="entity-definition")
router.register(r"resources", DynamicResourceViewSet, basename="dynamic-resource")
router.register(r"naming-sequences", NamingSequenceViewSet, basename="naming-sequence")

urlpatterns = [
    path("health/", MetadataHealthView.as_view(), name="metadata-modeling-health"),
    path(
        "configuration/",
        MetadataConfigurationViewSet.as_view({"get": "list", "put": "update"}),
        name="metadata-configuration",
    ),
    path(
        "configuration/preview/",
        MetadataConfigurationViewSet.as_view({"post": "preview"}),
        name="metadata-configuration-preview",
    ),
    path(
        "configuration/versions/",
        MetadataConfigurationViewSet.as_view({"get": "versions"}),
        name="metadata-configuration-versions",
    ),
    path(
        "configuration/versions/<int:version>/rollback/",
        MetadataConfigurationViewSet.as_view({"post": "rollback"}),
        name="metadata-configuration-rollback",
    ),
    path(
        "configuration/import/",
        MetadataConfigurationViewSet.as_view({"post": "import_config"}),
        name="metadata-configuration-import",
    ),
    path(
        "configuration/export/",
        MetadataConfigurationViewSet.as_view({"get": "export_config"}),
        name="metadata-configuration-export",
    ),
    path("", include(router.urls)),
]
