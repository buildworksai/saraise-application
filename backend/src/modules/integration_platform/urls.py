"""URL contract for Integration Platform API v2."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    ConnectorViewSet,
    DataMappingViewSet,
    InboundWebhookView,
    IntegrationCredentialViewSet,
    IntegrationPlatformConfigurationViewSet,
    IntegrationViewSet,
    NestedCredentialViewSet,
    WebhookDeliveryViewSet,
    WebhookViewSet,
)
from .health import IntegrationPlatformHealthView

app_name = "integration_platform"

router = DefaultRouter()
router.register("connectors", ConnectorViewSet, basename="connector")
router.register("integrations", IntegrationViewSet, basename="integration")
router.register(
    r"integrations/(?P<integration_id>[0-9a-fA-F-]{36})/credentials",
    NestedCredentialViewSet,
    basename="integration-credential-nested",
)
router.register(
    "integration-credentials",
    IntegrationCredentialViewSet,
    basename="integration-credential",
)
router.register("webhooks", WebhookViewSet, basename="webhook")
router.register("webhook-deliveries", WebhookDeliveryViewSet, basename="webhook-delivery")
router.register("data-mappings", DataMappingViewSet, basename="data-mapping")
router.register(
    "configuration",
    IntegrationPlatformConfigurationViewSet,
    basename="configuration",
)

inbound_webhook = InboundWebhookView.as_view({"post": "create"})

urlpatterns = [
    path("", include(router.urls)),
    path("webhooks/inbound/<uuid:public_id>/", inbound_webhook, name="webhook-inbound"),
    path("health/", IntegrationPlatformHealthView.as_view(), name="health"),
]


__all__ = ["app_name", "router", "urlpatterns"]
