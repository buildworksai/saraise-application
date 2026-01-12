"""
URL routing for IntegrationPlatform module.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api import (
    ConnectorViewSet,
    DataMappingViewSet,
    IntegrationCredentialViewSet,
    IntegrationViewSet,
    WebhookDeliveryViewSet,
    WebhookReceiveView,
    WebhookViewSet,
)
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"integrations", IntegrationViewSet, basename="integration")
router.register(r"integration-credentials", IntegrationCredentialViewSet, basename="integration-credential")
router.register(r"webhooks", WebhookViewSet, basename="webhook")
router.register(r"webhook-deliveries", WebhookDeliveryViewSet, basename="webhook-delivery")
router.register(r"connectors", ConnectorViewSet, basename="connector")
router.register(r"data-mappings", DataMappingViewSet, basename="data-mapping")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("webhooks/receive/<str:webhook_id>/", WebhookReceiveView.as_view(), name="webhook-receive"),
    path("health/", health_check, name="health_check"),
]
