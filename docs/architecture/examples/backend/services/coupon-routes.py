# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Coupon Routes with Policy Engine
# backend/src/modules/*/views.py
# Reference: docs/architecture/policy-engine-spec.md

from rest_framework import viewsets, status
from rest_framework.decorators import action, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.fields import Field
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from src.core.audit_service import AuditService
from .services import CouponService
from .models import Coupon, Subscription, CouponApplication
from .serializers import (
    CouponSerializer,
    CouponCreateSerializer,
    CouponApplySerializer,
    CouponApplicationResponseSerializer,
    CouponValidationResponseSerializer
)
from typing import Optional
from decimal import Decimal
from datetime import datetime


class CouponViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing coupons with Policy Engine authorization.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = CouponSerializer
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.audit_service = AuditService()
        self.service = None
    
    def get_service(self) -> CouponService:
        """Initialize service with request context."""
        if not self.service:
            self.service = CouponService()
        return self.service
    
    def get_queryset(self):
        """Get coupons - platform-level resource."""
        return Coupon.objects.all().order_by('-created_at')
    
    def check_policy(self, action: str, context: dict = None, tenant_id=None) -> None:
        """Authorize via Policy Engine."""
        user = get_current_user_from_session(self.request)
        decision = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=tenant_id,
            resource="platform.billing.coupons" if tenant_id is None else "tenant.billing.coupons",
            action=action,
            context=context or {}
        )
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
    
    def create(self, request, *args, **kwargs):
        """Create coupon (platform_billing_manager only)."""
        serializer = CouponCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = get_current_user_from_session(request)
        self.check_policy(
            action="create",
            context={"coupon_code": serializer.validated_data["code"], "resource_type": "coupon"},
            tenant_id=None  # Platform-level operation
        )
        
        service = self.get_service()
        coupon = service.create_coupon(
            code=serializer.validated_data["code"],
            name=serializer.validated_data["name"],
            description=serializer.validated_data.get("description"),
            coupon_type=serializer.validated_data["coupon_type"],
            discount_value=serializer.validated_data.get("discount_value"),
            valid_from=serializer.validated_data["valid_from"],
            valid_until=serializer.validated_data.get("valid_until")
        )
        
        # Audit log
        self.audit_service.log_event(
            actor_sub=user.id,
            actor_email=user.email,
            tenant_id=None,
            resource="coupons",
            action="create",
            result="success",
            metadata={"coupon_id": str(coupon.id), "code": coupon.code},
            request=request
        )
        
        return Response(CouponSerializer(coupon).data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'], url_path='apply')
    def apply_coupon(self, request):
        """Apply coupon to subscription (tenant user)."""
        serializer = CouponApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = get_current_user_from_session(request)
        service = self.get_service()
        
        # Get subscription to get amount
        subscription_id = serializer.validated_data["subscription_id"]
        try:
            subscription = Subscription.objects.get(
                id=subscription_id,
                tenant_id=user.tenant_id
            )
        except Subscription.DoesNotExist:
            raise NotFound(detail="Subscription not found")
        
        if subscription.tenant_id != user.tenant_id:
            raise PermissionDenied(detail="Access denied")
        
        subscription_amount = subscription.amount
        
        application = service.apply_coupon(
            coupon_code=serializer.validated_data["coupon_code"],
            tenant_id=user.tenant_id,
            subscription_id=subscription_id,
            subscription_amount=subscription_amount,
            user_id=user.id
        )
        
        # Audit log
        self.audit_service.log_event(
            actor_sub=user.id,
            actor_email=user.email,
            tenant_id=user.tenant_id,
            resource="coupon_application",
            action="CREATE",
            result="success",
            metadata={
                "coupon_id": str(application.coupon_id),
                "coupon_code": application.coupon_code,
                "subscription_id": str(application.subscription_id),
                "applied_amount": str(application.applied_amount)
            },
            request=request
        )
        
        return Response(CouponApplicationResponseSerializer(application).data)
    
    @action(detail=False, methods=['get'], url_path='validate/(?P<coupon_code>[^/.]+)', permission_classes=[AllowAny])
    def validate_coupon(self, request, coupon_code=None):
        """Validate coupon without applying (public)."""
        subscription_plan_id = request.query_params.get('subscription_plan_id', None)
        subscription_amount = request.query_params.get('subscription_amount', None)
        
        user = get_current_user_from_session(request) if request.user.is_authenticated else None
        
        service = self.get_service()
        coupon = service.get_coupon_by_code(coupon_code)
        
        if not coupon:
            raise NotFound(detail="Coupon not found")
        
        tenant_id = user.tenant_id if user else None
        user_id = user.id if user else None
        
        is_valid, error_message = service.validate_coupon(
            coupon=coupon,
            tenant_id=tenant_id or "",
            subscription_plan_id=subscription_plan_id,
            subscription_amount=Decimal(subscription_amount) if subscription_amount else None,
            user_id=user_id
        )
        
        return Response({
            "valid": is_valid,
            "error": error_message,
            "coupon": CouponSerializer(coupon).data if is_valid else None
        })
