"""Authoritative purchase-management API v2 routes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    ConfigurationViewSet,
    JobViewSet,
    PurchaseOrderViewSet,
    QuoteViewSet,
    ReceiptViewSet,
    RequisitionViewSet,
    RFQViewSet,
    SupplierViewSet,
)
from .health import ModuleHealthView

app_name = "purchase_management"
router = DefaultRouter()
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("requisitions", RequisitionViewSet, basename="requisition")
router.register("rfqs", RFQViewSet, basename="rfq")
router.register("quotes", QuoteViewSet, basename="quote")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchase-order")
router.register("receipts", ReceiptViewSet, basename="receipt")
router.register("configurations", ConfigurationViewSet, basename="configuration")
router.register("jobs", JobViewSet, basename="job")
urlpatterns = [path("", include(router.urls)), path("health/", ModuleHealthView.as_view(), name="health")]
