"""Canonical API v2 route surface for email marketing."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    CampaignRecipientViewSet,
    ConfigurationViewSet,
    ConsentRecordViewSet,
    DeliveryAttemptViewSet,
    EmailCampaignViewSet,
    EmailTemplateViewSet,
    ProviderEventAPIView,
    PublicUnsubscribeAPIView,
    SuppressionEntryViewSet,
    TrackingClickAPIView,
    TrackingOpenAPIView,
)
from .health import EmailMarketingHealthView

app_name = "email_marketing"

router = DefaultRouter()
router.register("campaigns", EmailCampaignViewSet, basename="email-campaign")
router.register("templates", EmailTemplateViewSet, basename="email-template")
router.register("recipients", CampaignRecipientViewSet, basename="email-recipient")
router.register("deliveries", DeliveryAttemptViewSet, basename="email-delivery")
router.register("suppressions", SuppressionEntryViewSet, basename="email-suppression")
router.register("consents", ConsentRecordViewSet, basename="email-consent")
router.register("configuration", ConfigurationViewSet, basename="email-configuration")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "provider-events/",
        ProviderEventAPIView.as_view(),
        name="provider-event",
    ),
    path(
        "public/unsubscribe/",
        PublicUnsubscribeAPIView.as_view(),
        name="public-unsubscribe",
    ),
    path(
        "t/<str:token>/open.gif",
        TrackingOpenAPIView.as_view(),
        name="tracking-open",
    ),
    path(
        "t/<str:token>/click/",
        TrackingClickAPIView.as_view(),
        name="tracking-click",
    ),
    path("health/", EmailMarketingHealthView.as_view(), name="health"),
]
