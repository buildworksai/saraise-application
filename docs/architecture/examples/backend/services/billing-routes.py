# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Billing API Routes with Policy Engine
# backend/src/modules/billing/views.py
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
from .services import SubscriptionService, PaymentService
from .models import Subscription, Invoice
from .serializers import SubscriptionSerializer, CancelSubscriptionRequestSerializer, PaymentRequestSerializer
from decimal import Decimal


class BillingViewSet(viewsets.ViewSet):
    """
    ViewSet for managing billing operations with Policy Engine authorization.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    Multitenancy: Row-level filtering by tenant_id
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.audit_service = AuditService()
        self.subscription_service = None
        self.payment_service = None
    
    def get_subscription_service(self) -> SubscriptionService:
        """Initialize subscription service."""
        if not self.subscription_service:
            self.subscription_service = SubscriptionService()
        return self.subscription_service
    
    def get_payment_service(self) -> PaymentService:
        """Initialize payment service."""
        if not self.payment_service:
            self.payment_service = PaymentService()
        return self.payment_service
    
    def check_policy(self, action: str, context: dict = None) -> None:
        """Authorize via Policy Engine."""
        user = get_current_user_from_session(self.request)
        decision = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=user.tenant_id,
            resource="tenant.billing.subscriptions",
            action=action,
            context=context or {}
        )
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
    
    @action(detail=False, methods=['get'], url_path='subscriptions/(?P<subscription_id>[^/.]+)')
    def get_subscription(self, request, subscription_id=None):
        """Get subscription (tenant_billing_manager only)."""
        self.check_policy(
            action="view",
            context={"subscription_id": subscription_id, "resource_type": "subscription"}
        )
        
        user = get_current_user_from_session(request)
        service = self.get_subscription_service()
        subscription = service.get_subscription(subscription_id, user.tenant_id)
        
        if not subscription:
            raise NotFound(detail="Subscription not found")
        
        return Response(SubscriptionSerializer(subscription).data)
    
    @action(detail=False, methods=['post'], url_path='subscriptions/(?P<subscription_id>[^/.]+)/cancel')
    def cancel_subscription(self, request, subscription_id=None):
        """Cancel subscription (tenant_billing_manager only)."""
        self.check_policy(
            action="update",
            context={"subscription_id": subscription_id, "action": "cancel"}
        )
        
        serializer = CancelSubscriptionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = get_current_user_from_session(request)
        service = self.get_subscription_service()
        subscription = service.cancel_subscription(
            subscription_id,
            user.tenant_id,
            serializer.validated_data.get("cancel_at_period_end", True)
        )
        
        # Audit log
        self.audit_service.log_event(
            actor_sub=user.id,
            actor_email=user.email,
            tenant_id=user.tenant_id,
            resource="subscriptions",
            action="cancel",
            result="success",
            metadata={"subscription_id": subscription_id},
            request=request
        )
        
        return Response(SubscriptionSerializer(subscription).data)
    
    @action(detail=False, methods=['post'], url_path='invoices/(?P<invoice_id>[^/.]+)/pay')
    def pay_invoice(self, request, invoice_id=None):
        """Process payment for invoice (tenant_billing_manager only)."""
        self.check_policy(
            action="update",
            context={"invoice_id": invoice_id, "action": "pay"}
        )
        
        serializer = PaymentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = get_current_user_from_session(request)
        payment_service = self.get_payment_service()
        payment = payment_service.process_payment(
            invoice_id=invoice_id,
            tenant_id=user.tenant_id,
            payment_method_id=serializer.validated_data["payment_method_id"],
            amount=serializer.validated_data["amount"]
        )
        
        # Audit log
        self.audit_service.log_event(
            actor_sub=user.id,
            actor_email=user.email,
            tenant_id=user.tenant_id,
            resource="payments",
            action="create",
            result="success",
            metadata={
                "invoice_id": invoice_id,
                "amount": str(serializer.validated_data["amount"])
            },
            request=request
        )
        
        return Response(payment)
