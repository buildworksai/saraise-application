"""
URL routing for Bank Reconciliation module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import BankAccountViewSet, BankStatementViewSet, BankTransactionViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"accounts", BankAccountViewSet, basename="bank-account")
router.register(r"statements", BankStatementViewSet, basename="bank-statement")
router.register(r"transactions", BankTransactionViewSet, basename="bank-transaction")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
