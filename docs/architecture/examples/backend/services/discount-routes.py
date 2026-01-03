# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Discount Routes with Policy Engine
# backend/src/modules/*/views.py
# Reference: docs/architecture/policy-engine-spec.md

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
from .services import DiscountService
from .models import Discount
from .serializers import DiscountSerializer, DiscountCreateSerializer
from typing import Optional
from decimal import Decimal
from datetime import datetime


class DiscountViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing discounts with Policy Engine authorization.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = DiscountSerializer
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.audit_service = AuditService()
        self.service = None
    
    def get_service(self) -> DiscountService:
        """Initialize service with request context."""
        if not self.service:
            self.service = DiscountService()
        return self.service
    
    def get_queryset(self):
        """Get discounts - platform-level resource."""
        return Discount.objects.all().order_by('-created_at')
    
    def check_policy(self, action: str, context: dict = None) -> None:
        """Authorize via Policy Engine for platform-level operations."""
        user = get_current_user_from_session(self.request)
        decision = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=None,  # Platform-level operations have no tenant_id
            resource="platform.billing.discounts",
            action=action,
            context=context or {}
        )
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
    
    def create(self, request, *args, **kwargs):
        """Create discount (platform_billing_manager only)."""
        serializer = DiscountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = get_current_user_from_session(request)
        self.check_policy(
            action="create",
            context={"discount_name": serializer.validated_data["name"], "resource_type": "discount"}
        )
        
        service = self.get_service()
        discount = service.create_discount(
            name=serializer.validated_data["name"],
            code=serializer.validated_data.get("code"),
            discount_type=serializer.validated_data["discount_type"],
            discount_value=serializer.validated_data["discount_value"],
            valid_from=serializer.validated_data["valid_from"],
            valid_until=serializer.validated_data.get("valid_until")
        )
        
        # Audit log
        self.audit_service.log_event(
            actor_sub=user.id,
            actor_email=user.email,
            tenant_id=None,
            resource="discounts",
            action="create",
            result="success",
            metadata={"discount_id": str(discount.id), "name": discount.name},
            request=request
        )
        
        return Response(DiscountSerializer(discount).data, status=status.HTTP_201_CREATED)
    
    def list(self, request, *args, **kwargs):
        """List discounts."""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    def retrieve(self, request, pk=None, *args, **kwargs):
        """Retrieve single discount."""
        try:
            discount = self.get_queryset().get(pk=pk)
        except Discount.DoesNotExist:
            raise NotFound(detail="Discount not found")
        
        serializer = self.get_serializer(discount)
        return Response(serializer.data)
