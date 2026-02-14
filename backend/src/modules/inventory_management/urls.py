"""
URL routing for Inventory Management module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import ItemViewSet, StockBalanceViewSet, StockEntryViewSet, WarehouseViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"warehouses", WarehouseViewSet, basename="warehouse")
router.register(r"items", ItemViewSet, basename="item")
router.register(r"stock-entries", StockEntryViewSet, basename="stock-entry")
router.register(r"stock-balances", StockBalanceViewSet, basename="stock-balance")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
