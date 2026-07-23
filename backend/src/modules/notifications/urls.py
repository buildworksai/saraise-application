"""Canonical v2 notification routes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    ConfigurationAPIView, ConfigurationExportAPIView, ConfigurationHistoryAPIView,
    ConfigurationImportAPIView, ConfigurationRollbackAPIView, ConfigurationSimulateAPIView,
    DeliveryViewSet, EndpointViewSet, InboxViewSet, LivenessAPIView,
    PreferenceAPIView, PreferenceResetAPIView, ProviderCallbackAPIView, ReadinessAPIView, TemplateViewSet,
)

app_name = "notifications"
router = DefaultRouter()
router.register("inbox", InboxViewSet, basename="inbox")
router.register("templates", TemplateViewSet, basename="template")
router.register("deliveries", DeliveryViewSet, basename="delivery")
router.register("endpoints", EndpointViewSet, basename="endpoint")

urlpatterns = [
    path("", include(router.urls)),
    path("preferences/me/", PreferenceAPIView.as_view(), name="preferences-me"),
    path("preferences/me/reset/", PreferenceResetAPIView.as_view(), name="preferences-reset"),
    path("configuration/<str:environment>/", ConfigurationAPIView.as_view(), name="configuration-detail"),
    path("configuration/<str:environment>/simulate/", ConfigurationSimulateAPIView.as_view(), name="configuration-simulate"),
    path("configuration/<str:environment>/history/", ConfigurationHistoryAPIView.as_view(), name="configuration-history"),
    path("configuration/<str:environment>/rollback/", ConfigurationRollbackAPIView.as_view(), name="configuration-rollback"),
    path("configuration/<str:environment>/import/", ConfigurationImportAPIView.as_view(), name="configuration-import"),
    path("configuration/<str:environment>/export/", ConfigurationExportAPIView.as_view(), name="configuration-export"),
    path("health/live/", LivenessAPIView.as_view(), name="health-live"),
    path("health/ready/", ReadinessAPIView.as_view(), name="health-ready"),
    path("callbacks/<slug:callback_key>/", ProviderCallbackAPIView.as_view(), name="provider-callback"),
]
