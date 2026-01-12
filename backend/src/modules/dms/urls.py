"""
URL routing for Dms module.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api import (
    DocumentPermissionViewSet,
    DocumentShareViewSet,
    DocumentVersionViewSet,
    DocumentViewSet,
    FolderViewSet,
)
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"folders", FolderViewSet, basename="folder")
router.register(r"documents", DocumentViewSet, basename="document")
router.register(r"document-versions", DocumentVersionViewSet, basename="document-version")
router.register(r"document-permissions", DocumentPermissionViewSet, basename="document-permission")
router.register(r"document-shares", DocumentShareViewSet, basename="document-share")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
