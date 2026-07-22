"""Governed v2 routes for the multi-company domain."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    AsyncJobViewSet,
    CompanyAccessViewSet,
    CompanyV2ViewSet,
    ConfigurationExportAPIView,
    ConfigurationImportAPIView,
    ConfigurationVersionViewSet,
    ConsolidationRunViewSet,
    EliminationViewSet,
    ExtensionCatalogAPIView,
    ModuleHealthAPIView,
    ReconciliationViewSet,
    TransactionViewSet,
    TransferPriceCalculateAPIView,
    TransferPricePreviewAPIView,
    TransferPricingRuleViewSet,
)

app_name = "multi_company_v2"
router = DefaultRouter()
router.register("companies", CompanyV2ViewSet, basename="company")
router.register("company-access", CompanyAccessViewSet, basename="company-access")
router.register("transactions", TransactionViewSet, basename="transaction")
router.register("reconciliation", ReconciliationViewSet, basename="reconciliation")
router.register("consolidation-runs", ConsolidationRunViewSet, basename="consolidation-run")
router.register("eliminations", EliminationViewSet, basename="elimination")
router.register("transfer-pricing-rules", TransferPricingRuleViewSet, basename="transfer-pricing-rule")
router.register("configuration/versions", ConfigurationVersionViewSet, basename="configuration-version")
router.register("jobs", AsyncJobViewSet, basename="job")

urlpatterns = [
    path("", include(router.urls)),
    path("transfer-pricing/calculate/", TransferPriceCalculateAPIView.as_view(), name="transfer-price-calculate"),
    path("transfer-pricing/preview/", TransferPricePreviewAPIView.as_view(), name="transfer-price-preview"),
    path("configuration/export/", ConfigurationExportAPIView.as_view(), name="configuration-export"),
    path("configuration/import/", ConfigurationImportAPIView.as_view(), name="configuration-import"),
    path("extensions/catalog/", ExtensionCatalogAPIView.as_view(), name="extension-catalog"),
    path("health/", ModuleHealthAPIView.as_view(), name="health"),
]
