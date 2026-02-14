"""
URL routing for Communication Hub module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import ChannelViewSet, MessageViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"channels", ChannelViewSet, basename="channel")
router.register(r"messages", MessageViewSet, basename="message")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
