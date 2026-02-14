"""
URL routing for Purchase Management module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    PurchaseOrderViewSet,
    PurchaseReceiptViewSet,
    PurchaseRequisitionViewSet,
    SupplierViewSet,
)
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"suppliers", SupplierViewSet, basename="supplier")
router.register(r"requisitions", PurchaseRequisitionViewSet, basename="requisition")
router.register(r"purchase-orders", PurchaseOrderViewSet, basename="purchase-order")
router.register(r"receipts", PurchaseReceiptViewSet, basename="receipt")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
