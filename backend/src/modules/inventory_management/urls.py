"""Complete governed v2 inventory route surface."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    BatchViewSet, ConfigurationViewSet, CycleCountViewSet, DashboardViewSet,
    ImportViewSet, ItemViewSet, ReservationViewSet, SerialNumberViewSet,
    StockBalanceViewSet, StockEntryViewSet, StockLedgerViewSet,
    StorageLocationViewSet, WarehouseViewSet,
)
from .health import InventoryHealthView

app_name = "inventory_management"

router = DefaultRouter()
router.register(r"warehouses", WarehouseViewSet, basename="warehouse")
router.register(r"locations", StorageLocationViewSet, basename="location")
router.register(r"items", ItemViewSet, basename="item")
router.register(r"batches", BatchViewSet, basename="batch")
router.register(r"serial-numbers", SerialNumberViewSet, basename="serial-number")
router.register(r"stock-entries", StockEntryViewSet, basename="stock-entry")
router.register(r"stock-balances", StockBalanceViewSet, basename="stock-balance")
router.register(r"stock-ledger", StockLedgerViewSet, basename="stock-ledger")
router.register(r"reservations", ReservationViewSet, basename="reservation")
router.register(r"cycle-counts", CycleCountViewSet, basename="cycle-count")
router.register(r"configurations", ConfigurationViewSet, basename="configuration")
router.register(r"dashboard", DashboardViewSet, basename="dashboard")
router.register(r"imports", ImportViewSet, basename="import")

urlpatterns = [
    path("", include(router.urls)),
    path("health/", InventoryHealthView.as_view(), name="health"),
]
