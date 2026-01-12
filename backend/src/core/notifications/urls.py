"""
URL routing for Notifications module.

SPDX-License-Identifier: Apache-2.0
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api import NotificationPreferenceViewSet, NotificationViewSet

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"notifications", NotificationViewSet, basename="notification")
router.register(r"preferences", NotificationPreferenceViewSet, basename="notification-preference")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
]
