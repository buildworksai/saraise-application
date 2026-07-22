"""Governed DMS API v2 routing."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    DmsHealthAPIView,
    DocumentPermissionViewSet,
    DocumentShareViewSet,
    DocumentVersionViewSet,
    DocumentViewSet,
    FolderViewSet,
    PrincipalSearchAPIView,
    PublicShareDownloadAPIView,
)

app_name = "dms"

router = DefaultRouter()
router.register("folders", FolderViewSet, basename="folder")
router.register("documents", DocumentViewSet, basename="document")
router.register("document-versions", DocumentVersionViewSet, basename="document-version")
router.register("document-permissions", DocumentPermissionViewSet, basename="document-permission")
router.register("document-shares", DocumentShareViewSet, basename="document-share")

urlpatterns = [
    path("", include(router.urls)),
    path("principals/", PrincipalSearchAPIView.as_view(), name="principal-search"),
    path("public/shares/<str:token>/download/", PublicShareDownloadAPIView.as_view(), name="public-share-download"),
    path("health/", DmsHealthAPIView.as_view(), name="health"),
]
