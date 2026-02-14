"""
URL routing for Notifications module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import NotificationPreferenceViewSet, NotificationViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"notifications", NotificationViewSet, basename="notification")
router.register(r"preferences", NotificationPreferenceViewSet, basename="preference")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
