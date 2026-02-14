"""
DRF ViewSets for Inventory Management module.
"""

import uuid
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import Item, StockBalance, StockEntry, Warehouse
from .serializers import ItemSerializer, StockBalanceSerializer, StockEntrySerializer, WarehouseSerializer


class WarehouseViewSet(viewsets.ModelViewSet):
    """ViewSet for Warehouse CRUD operations."""

    serializer_class = WarehouseSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter warehouses by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return Warehouse.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Warehouse.objects.none()

        queryset = Warehouse.objects.filter(tenant_id=tenant_id, is_active=True)
        return queryset.order_by("warehouse_code")

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            raise PermissionDenied("User must belong to a tenant")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise PermissionDenied("Invalid tenant_id format")

        serializer.save(tenant_id=tenant_id)


class ItemViewSet(viewsets.ModelViewSet):
    """ViewSet for Item CRUD operations."""

    serializer_class = ItemSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter items by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return Item.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Item.objects.none()

        queryset = Item.objects.filter(tenant_id=tenant_id, is_active=True)
        return queryset.order_by("item_code")

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            raise PermissionDenied("User must belong to a tenant")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise PermissionDenied("Invalid tenant_id format")

        serializer.save(tenant_id=tenant_id)


class StockEntryViewSet(viewsets.ModelViewSet):
    """ViewSet for StockEntry CRUD operations."""

    serializer_class = StockEntrySerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter stock entries by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return StockEntry.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return StockEntry.objects.none()

        queryset = StockEntry.objects.filter(tenant_id=tenant_id)
        return queryset.order_by("-posting_date", "-entry_number")

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            raise PermissionDenied("User must belong to a tenant")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise PermissionDenied("Invalid tenant_id format")

        serializer.save(tenant_id=tenant_id)


class StockBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for StockBalance read operations."""

    serializer_class = StockBalanceSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter stock balances by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return StockBalance.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return StockBalance.objects.none()

        queryset = StockBalance.objects.filter(tenant_id=tenant_id)
        return queryset.order_by("item__item_code", "warehouse__warehouse_code")
