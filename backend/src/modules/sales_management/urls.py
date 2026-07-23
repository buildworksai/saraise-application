"""
URL routing for Sales Management module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    ConfigurationViewSet,
    CustomerViewSet,
    DeliveryNoteViewSet,
    QuotationViewSet,
    SalesInsightsViewSet,
    SalesOrderViewSet,
)
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"customers", CustomerViewSet, basename="customer")
router.register(r"quotations", QuotationViewSet, basename="quotation")
router.register(r"sales-orders", SalesOrderViewSet, basename="sales-order")
router.register(r"delivery-notes", DeliveryNoteViewSet, basename="delivery-note")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("summary/", SalesInsightsViewSet.as_view({"get": "summary"}), name="sales-summary"),
    path("capabilities/", SalesInsightsViewSet.as_view({"get": "capabilities"}), name="sales-capabilities"),
    path(
        "configuration/", ConfigurationViewSet.as_view({"get": "current", "put": "apply"}), name="sales-configuration"
    ),
    path(
        "configuration/preview/", ConfigurationViewSet.as_view({"post": "preview"}), name="sales-configuration-preview"
    ),
    path(
        "configuration/versions/",
        ConfigurationViewSet.as_view({"get": "versions"}),
        name="sales-configuration-versions",
    ),
    path(
        "configuration/versions/<int:version>/",
        ConfigurationViewSet.as_view({"get": "version_detail"}),
        name="sales-configuration-version",
    ),
    path(
        "configuration/rollback/",
        ConfigurationViewSet.as_view({"post": "rollback"}),
        name="sales-configuration-rollback",
    ),
    path("configuration/export/", ConfigurationViewSet.as_view({"get": "export"}), name="sales-configuration-export"),
    path(
        "configuration/import/",
        ConfigurationViewSet.as_view({"post": "import_configuration"}),
        name="sales-configuration-import",
    ),
    path("health/", health_check, name="health_check"),
]
