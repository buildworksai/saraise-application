"""
DRF ViewSets for Compliance Management module.
"""

import uuid
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import CompliancePolicy, ComplianceRequirement
from .serializers import CompliancePolicySerializer, ComplianceRequirementSerializer


class CompliancePolicyViewSet(viewsets.ModelViewSet):
    """ViewSet for CompliancePolicy CRUD operations."""

    serializer_class = CompliancePolicySerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter policies by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return CompliancePolicy.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return CompliancePolicy.objects.none()

        queryset = CompliancePolicy.objects.filter(tenant_id=tenant_id, is_active=True)
        return queryset.order_by("policy_code")

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


class ComplianceRequirementViewSet(viewsets.ModelViewSet):
    """ViewSet for ComplianceRequirement CRUD operations."""

    serializer_class = ComplianceRequirementSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter requirements by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return ComplianceRequirement.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return ComplianceRequirement.objects.none()

        queryset = ComplianceRequirement.objects.filter(tenant_id=tenant_id)
        # Filter by policy if provided
        policy_id = self.request.query_params.get("policy_id")
        if policy_id:
            queryset = queryset.filter(policy_id=policy_id)
        return queryset.order_by("requirement_code")

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
