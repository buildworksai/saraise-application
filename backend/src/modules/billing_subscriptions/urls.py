"""
URL routing for BillingSubscriptions module.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api import (
    InvoiceViewSet,
    PaymentViewSet,
    QuotaViewSet,
    SubscriptionPlanViewSet,
    SubscriptionViewSet,
    UsageRecordViewSet,
)
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"plans", SubscriptionPlanViewSet, basename="subscription-plan")
router.register(r"subscriptions", SubscriptionViewSet, basename="subscription")
router.register(r"invoices", InvoiceViewSet, basename="invoice")
router.register(r"payments", PaymentViewSet, basename="payment")
router.register(r"usage-records", UsageRecordViewSet, basename="usage-record")
router.register(r"quotas", QuotaViewSet, basename="quota")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
