# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# Tenant Resource Permissions via Policy Engine
# Reference: docs/architecture/policy-engine-spec.md § 4
# Reference: docs/architecture/security-model.md § 2
# Reference: docs/architecture/application-architecture.md § 2.1 (Row-Level Multitenancy)

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from .models import User, Workflow, Subscription
from .serializers import UserCreateSerializer, UserSerializer, SubscriptionUpdateSerializer
from django.db import transaction


class TenantResourceViewSet(viewsets.ViewSet):
    """
    ViewSet for tenant-scoped resource management with Policy Engine authorization.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    Multitenancy: Row-level filtering by tenant_id
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
    
    def check_policy(self, action: str, resource: str, context: dict = None) -> None:
        """Authorize via Policy Engine."""
        user = get_current_user_from_session(self.request)
        decision = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=user.tenant_id,
            resource=resource,
            action=action,
            context=context or {}
        )
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
    
    @action(detail=False, methods=['post'], url_path='users')
    def create_user(self, request):
        """
        Create user within tenant.
        
        Architecture:
        - Session provides identity only (user_id, tenant_id)
        - Policy Engine evaluates: permission "users:create" + tenant_admin role
        - Explicit tenant_id filtering for data isolation (Row-Level Multitenancy)
        """
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = get_current_user_from_session(request)
        self.check_policy(
            action="create",
            resource="users",
            context={"resource_type": "tenant_user"}
        )
        
        # CRITICAL: Explicit tenant_id assignment for Row-Level Multitenancy
        with transaction.atomic():
            new_user = User.objects.create(
                **serializer.validated_data,
                tenant_id=user.tenant_id  # Explicit tenant isolation
            )
        
        return Response(UserSerializer(new_user).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'], url_path='workflows/(?P<workflow_id>[^/.]+)/execute')
    def execute_workflow(self, request, workflow_id=None):
        """
        Execute workflow within tenant.
        
        Architecture:
        - Policy Engine checks "workflows:execute" permission
        - Explicit tenant_id filtering prevents cross-tenant data access
        """
        user = get_current_user_from_session(request)
        self.check_policy(
            action="execute",
            resource=f"workflows.{workflow_id}",
            context={"workflow_id": workflow_id}
        )
        
        # CRITICAL: Filter by tenant_id (Row-Level Multitenancy)
        try:
            workflow = Workflow.objects.get(
                id=workflow_id,
                tenant_id=user.tenant_id  # Explicit tenant filter
            )
        except Workflow.DoesNotExist:
            raise NotFound(detail="Workflow not found")
        
        # Execute workflow logic
        result = workflow.execute()
        return Response(result)
    
    @action(detail=False, methods=['patch'], url_path='billing/subscription')
    def update_subscription(self, request):
        """
        Update tenant subscription.
        
        Architecture:
        - Policy Engine checks "billing:manage" permission + billing_manager role
        - Tenant-scoped operation with explicit tenant_id filtering
        """
        serializer = SubscriptionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = get_current_user_from_session(request)
        self.check_policy(
            action="update",
            resource="billing.subscription",
            context={"resource_type": "tenant_subscription"}
        )
        
        # CRITICAL: Filter by tenant_id
        try:
            subscription = Subscription.objects.get(tenant_id=user.tenant_id)
        except Subscription.DoesNotExist:
            raise NotFound(detail="Subscription not found")
        
        # Update subscription
        for key, value in serializer.validated_data.items():
            setattr(subscription, key, value)
        
        with transaction.atomic():
            subscription.save()
        
        return Response({"status": "updated", "subscription_id": str(subscription.id)})
