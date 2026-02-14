"""
DRF ViewSets for Compliance Risk Management module.
"""

import uuid
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import ComplianceRisk
from .serializers import ComplianceRiskSerializer


class ComplianceRiskViewSet(viewsets.ModelViewSet):
    """ViewSet for ComplianceRisk CRUD operations."""

    serializer_class = ComplianceRiskSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter risks by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return ComplianceRisk.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return ComplianceRisk.objects.none()

        queryset = ComplianceRisk.objects.filter(tenant_id=tenant_id)
        # Filter by risk_level if provided
        risk_level = self.request.query_params.get("risk_level")
        if risk_level:
            queryset = queryset.filter(risk_level=risk_level)
        return queryset.order_by("-risk_level", "risk_code")

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
