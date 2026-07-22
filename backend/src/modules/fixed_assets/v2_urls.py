"""Governed API v2 routes for fixed-assets financial lifecycle management."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    AssetCategoryViewSet,
    AssetTransactionViewSet,
    DepreciationLineViewSet,
    DepreciationScheduleViewSet,
    FixedAssetDashboardViewSet,
    FixedAssetHealthAPIView,
    FixedAssetJobViewSet,
    FixedAssetViewSet,
)

app_name = "fixed_assets_v2"

router = DefaultRouter()
router.register("categories", AssetCategoryViewSet, basename="asset-category")
router.register("assets", FixedAssetViewSet, basename="fixed-asset-v2")
router.register("depreciation-schedules", DepreciationScheduleViewSet, basename="depreciation-schedule")
router.register("depreciation-lines", DepreciationLineViewSet, basename="depreciation-line")
router.register("transactions", AssetTransactionViewSet, basename="asset-transaction")
router.register("jobs", FixedAssetJobViewSet, basename="fixed-asset-job")
router.register("dashboard", FixedAssetDashboardViewSet, basename="fixed-asset-dashboard")

urlpatterns = [
    path("", include(router.urls)),
    path("health/", FixedAssetHealthAPIView.as_view(), name="health"),
]
