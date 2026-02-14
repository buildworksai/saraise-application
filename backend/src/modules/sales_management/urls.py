"""
URL routing for Sales Management module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import CustomerViewSet, DeliveryNoteViewSet, QuotationViewSet, SalesOrderViewSet
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
    path("health/", health_check, name="health_check"),
]
