"""Governed v2 bank-reconciliation routes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    BankAccountViewSet,
    BankStatementViewSet,
    BankTransactionViewSet,
    MatchingRuleViewSet,
    ModuleHealthAPIView,
    ReconciliationMatchViewSet,
    ReconciliationViewSet,
    StatementImportViewSet,
)

app_name = "bank_reconciliation"

router = DefaultRouter()
router.register("accounts", BankAccountViewSet, basename="bank-account")
router.register("statements", BankStatementViewSet, basename="bank-statement")
router.register("transactions", BankTransactionViewSet, basename="bank-transaction")
router.register("imports", StatementImportViewSet, basename="statement-import")
router.register("rules", MatchingRuleViewSet, basename="matching-rule")
router.register("reconciliations", ReconciliationViewSet, basename="reconciliation")
router.register("matches", ReconciliationMatchViewSet, basename="reconciliation-match")

urlpatterns = [path("", include(router.urls)), path("health/", ModuleHealthAPIView.as_view(), name="health")]
