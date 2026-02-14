"""
URL routing for Email Marketing module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import EmailCampaignViewSet, EmailTemplateViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"campaigns", EmailCampaignViewSet, basename="email-campaign")
router.register(r"templates", EmailTemplateViewSet, basename="email-template")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
