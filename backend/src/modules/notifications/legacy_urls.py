"""Two-release v1 compatibility projection onto canonical module services."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import InboxViewSet, NotificationPreferenceViewSet

router = DefaultRouter()
router.register("notifications", InboxViewSet, basename="legacy-notification")
router.register("preferences", NotificationPreferenceViewSet, basename="legacy-preference")

urlpatterns = [path("", include(router.urls))]
