"""
DRF ViewSets for Bank Reconciliation module.
"""

import uuid
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import BankAccount, BankStatement, BankTransaction
from .serializers import BankAccountSerializer, BankStatementSerializer, BankTransactionSerializer


class BankAccountViewSet(viewsets.ModelViewSet):
    """ViewSet for BankAccount CRUD operations."""

    serializer_class = BankAccountSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter bank accounts by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return BankAccount.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return BankAccount.objects.none()

        queryset = BankAccount.objects.filter(tenant_id=tenant_id, is_active=True)
        return queryset.order_by("bank_name", "account_number")

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


class BankStatementViewSet(viewsets.ModelViewSet):
    """ViewSet for BankStatement CRUD operations."""

    serializer_class = BankStatementSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter bank statements by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return BankStatement.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return BankStatement.objects.none()

        queryset = BankStatement.objects.filter(tenant_id=tenant_id)
        return queryset.order_by("-statement_date")

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


class BankTransactionViewSet(viewsets.ModelViewSet):
    """ViewSet for BankTransaction CRUD operations."""

    serializer_class = BankTransactionSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter bank transactions by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return BankTransaction.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return BankTransaction.objects.none()

        queryset = BankTransaction.objects.filter(tenant_id=tenant_id)
        # Filter by statement if provided
        statement_id = self.request.query_params.get("statement_id")
        if statement_id:
            queryset = queryset.filter(bank_statement_id=statement_id)
        return queryset.order_by("-transaction_date")

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
