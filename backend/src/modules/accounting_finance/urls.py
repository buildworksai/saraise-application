"""
URL routing for Accounting & Finance module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    AccountViewSet,
    APInvoiceViewSet,
    ARInvoiceViewSet,
    JournalEntryViewSet,
    PaymentViewSet,
    PostingPeriodViewSet,
)
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"accounts", AccountViewSet, basename="account")
router.register(r"posting-periods", PostingPeriodViewSet, basename="posting-period")
router.register(r"journal-entries", JournalEntryViewSet, basename="journal-entry")
router.register(r"ap-invoices", APInvoiceViewSet, basename="ap-invoice")
router.register(r"ar-invoices", ARInvoiceViewSet, basename="ar-invoice")
router.register(r"payments", PaymentViewSet, basename="payment")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
