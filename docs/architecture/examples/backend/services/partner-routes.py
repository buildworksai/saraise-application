# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Partner Management Routes with Policy Engine
# backend/src/modules/*/views.py
# Reference: docs/architecture/policy-engine-spec.md
# Reference: docs/architecture/security-model.md

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.fields import Field
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from src.core.audit_service import AuditService
from .services import PartnerService
from .models import Partner
from .serializers import (
    PartnerSerializer,
    PartnerCreateSerializer,
    PartnerReferralCreateSerializer,
    PartnerReferralResponseSerializer,
    PartnerStatsResponseSerializer
)
from decimal import Decimal
from typing import Optional


class PartnerViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing partners with Policy Engine authorization.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = PartnerSerializer
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.audit_service = AuditService()
        self.service = None
    
    def get_service(self) -> PartnerService:
        """Initialize service with request context."""
        if not self.service:
            self.service = PartnerService()
        return self.service
    
    def get_queryset(self):
        """Get partners - platform-level resource."""
        return Partner.objects.all().order_by('-created_at')
    
    def check_policy(self, action: str, context: dict = None, tenant_id=None) -> None:
        """Authorize via Policy Engine."""
        user = get_current_user_from_session(self.request)
        decision = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=tenant_id,
            resource="platform.partners" if tenant_id is None else "tenant.partners",
            action=action,
            context=context or {}
        )
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
    
    def create(self, request, *args, **kwargs):
        """Create partner (platform_billing_manager only)."""
        serializer = PartnerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = get_current_user_from_session(request)
        self.check_policy(
            action="create",
            context={"partner_type": serializer.validated_data["partner_type"], "resource_type": "partner"},
            tenant_id=None  # Platform-level operation
        )
        
        service = self.get_service()
        partner = service.create_partner(
            name=serializer.validated_data["name"],
            email=serializer.validated_data["email"],
            partner_type=serializer.validated_data["partner_type"],
            commission_type=serializer.validated_data["commission_type"],
            commission_rate=serializer.validated_data["commission_rate"],
            created_by=user.id
        )
        
        # Audit log
        self.audit_service.log_event(
            actor_sub=user.id,
            actor_email=user.email,
            tenant_id=None,
            resource="partner",
            action="create",
            result="success",
            metadata={"partner_id": str(partner.id), "name": partner.name},
            request=request
        )
        
        return Response(PartnerSerializer(partner).data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'], url_path='referrals')
    def create_referral(self, request):
        """Create a partner referral (tenant admin only)."""
        serializer = PartnerReferralCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = get_current_user_from_session(request)
        # Policy check for tenant admin
        self.check_policy(
            action="create",
            context={"resource_type": "partner_referral"},
            tenant_id=user.tenant_id
        )
        
        service = self.get_service()
        referral = service.create_referral(
            referral_code=serializer.validated_data["referral_code"],
            tenant_id=user.tenant_id
        )
        
        # Audit log
        self.audit_service.log_event(
            actor_sub=user.id,
            actor_email=user.email,
            tenant_id=user.tenant_id,
            resource="partner_referral",
            action="CREATE",
            result="success",
            metadata={
                "referral_id": str(referral.id),
                "referral_code": referral.referral_code,
                "partner_id": str(referral.partner_id)
            },
            request=request
        )
        
        return Response(PartnerReferralResponseSerializer(referral).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['get'], url_path='stats')
    def get_partner_stats(self, request, pk=None):
        """Get partner statistics (platform billing manager only)."""
        self.check_policy(
            action="view",
            context={"partner_id": pk, "resource_type": "partner_stats"},
            tenant_id=None  # Platform-level operation
        )
        
        try:
            partner = Partner.objects.get(pk=pk)
        except Partner.DoesNotExist:
            raise NotFound(detail="Partner not found")
        
        return Response({
            "total_referrals": partner.total_referrals,
            "active_referrals": partner.active_referrals,
            "total_commission_earned": str(partner.total_commission_earned),
            "total_commission_paid": str(partner.total_commission_paid),
            "total_commission_pending": str(partner.total_commission_pending)
        })
