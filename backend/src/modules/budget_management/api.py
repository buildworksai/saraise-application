"""
DRF ViewSets for Budget Management module.
"""

import uuid
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import Budget, BudgetLine
from .serializers import BudgetLineSerializer, BudgetSerializer


class BudgetViewSet(viewsets.ModelViewSet):
    """ViewSet for Budget CRUD operations."""

    serializer_class = BudgetSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter budgets by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return Budget.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Budget.objects.none()

        queryset = Budget.objects.filter(tenant_id=tenant_id)
        return queryset.order_by("-fiscal_year", "budget_code")

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


class BudgetLineViewSet(viewsets.ModelViewSet):
    """ViewSet for BudgetLine CRUD operations."""

    serializer_class = BudgetLineSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter budget lines by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return BudgetLine.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return BudgetLine.objects.none()

        queryset = BudgetLine.objects.filter(tenant_id=tenant_id)
        # Filter by budget if provided
        budget_id = self.request.query_params.get("budget_id")
        if budget_id:
            queryset = queryset.filter(budget_id=budget_id)
        return queryset.order_by("account_code")

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
