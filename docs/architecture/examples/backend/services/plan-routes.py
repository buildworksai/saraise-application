# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Subscription Plan Routes with Policy Engine
# backend/src/modules/*/views.py
# Reference: docs/architecture/policy-engine-spec.md
# Reference: docs/architecture/security-model.md

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from rest_framework.request import Request
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from src.core.audit_service import AuditService
from .services import PlanService
from .models import SubscriptionPlan
from .serializers import PlanSerializer, PlanCreateSerializer
from typing import List, Optional, Dict, Any
from decimal import Decimal
from datetime import datetime


class PlanViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing subscription plans with Policy Engine authorization.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = PlanSerializer
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.audit_service = AuditService()
        self.service = None
    
    def get_service(self) -> PlanService:
        """Initialize service with request context."""
        if not self.service:
            self.service = PlanService()
        return self.service
    
    def get_queryset(self):
        """Get plans - public plans visible to all authenticated users."""
        include_inactive = self.request.query_params.get('include_inactive', 'false').lower() == 'true'
        queryset = SubscriptionPlan.objects.all()
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
        return queryset.order_by('price')
    
    def check_policy(self, action: str, context: dict = None, tenant_id=None) -> None:
        """Authorize via Policy Engine."""
        user = get_current_user_from_session(self.request)
        decision = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=tenant_id,
            resource="billing.plans" if tenant_id else "platform.billing.plans",
            action=action,
            context=context or {}
        )
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
    
    def list(self, request, *args, **kwargs):
        """List subscription plans (public plans visible to all tenant users)."""
        user = get_current_user_from_session(request)
        self.check_policy(action="view", context={"resource_type": "subscription_plans"}, tenant_id=user.tenant_id)
        
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    def create(self, request, *args, **kwargs):
        """Create subscription plan (platform_billing_manager only)."""
        serializer = PlanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = get_current_user_from_session(request)
        self.check_policy(
            action="create",
            context={"plan_name": serializer.validated_data["name"], "resource_type": "plan"},
            tenant_id=None  # Platform-level operation
        )
        
        service = self.get_service()
        plan = service.create_plan(
            name=serializer.validated_data["name"],
            tier=serializer.validated_data["tier"],
            price=serializer.validated_data["price"],
            features=serializer.validated_data.get("features", {})
        )
        
        # Audit log
        self.audit_service.log_event(
            actor_sub=user.id,
            actor_email=user.email,
            tenant_id=None,
            resource="subscription_plans",
            action="create",
            result="success",
            metadata={"plan_id": str(plan.id), "name": plan.name},
            request=request
        )
        
        return Response(PlanSerializer(plan).data, status=status.HTTP_201_CREATED)
    
    def retrieve(self, request, pk=None, *args, **kwargs):
        """Get subscription plan."""
        user = get_current_user_from_session(request)
        self.check_policy(action="view", context={"plan_id": pk}, tenant_id=user.tenant_id)
        
        try:
            plan = self.get_queryset().get(pk=pk)
        except SubscriptionPlan.DoesNotExist:
            raise NotFound(detail="Plan not found")
        
        serializer = self.get_serializer(plan)
        return Response(serializer.data)
