# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Future Authorization Enhancements with Policy Engine
# Reference: docs/architecture/policy-engine-spec.md
# All authorization evaluated by Policy Engine at request time

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from .services import WorkflowService, SensitiveDataService
from .models import Workflow
from typing import Dict, Any


class FutureEnhancementsViewSet(viewsets.ViewSet):
    """
    ViewSet demonstrating future authorization enhancements with Policy Engine.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    Multitenancy: Row-level filtering by tenant_id
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.workflow_service = None
        self.data_service = None
    
    def get_workflow_service(self):
        if not self.workflow_service:
            self.workflow_service = WorkflowService()
        return self.workflow_service
    
    def get_data_service(self):
        if not self.data_service:
            self.data_service = SensitiveDataService()
        return self.data_service
    
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
    
    @action(detail=True, methods=['get'], url_path='workflows/(?P<workflow_id>[^/.]+)')
    def get_workflow(self, request, workflow_id=None):
        """Get workflow with access control via Policy Engine."""
        user = get_current_user_from_session(request)
        
        # Evaluate access to this specific workflow
        self.check_policy(
            action="view",
            resource="workflows.item",
            context={
                "workflow_id": workflow_id,
                "resource_type": "workflow"
            }
        )
        
        service = self.get_workflow_service()
        # CRITICAL: Filter by tenant_id - explicit Row-Level Multitenancy
        workflow = service.get_workflow(
            workflow_id=workflow_id,
            tenant_id=user.tenant_id
        )
        
        if not workflow:
            raise NotFound(detail="Workflow not found")
        
        return Response(workflow)
    
    @action(detail=False, methods=['get'], url_path='auth/my-permissions')
    def get_my_permissions(self, request):
        """Get current user's permissions (evaluated at request time)."""
        user = get_current_user_from_session(request)
        
        # CRITICAL: No caching in session - Policy Engine evaluates per-request
        # This endpoint shows what permissions the user currently has
        
        can_create_users = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=user.tenant_id,
            resource="users",
            action="create",
            context={"resource_type": "user"}
        )
        
        can_view_billing = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=user.tenant_id,
            resource="billing",
            action="view",
            context={"resource_type": "billing"}
        )
        
        return Response({
            "can_create_users": can_create_users.allowed,
            "can_view_billing": can_view_billing.allowed,
            # Note: Session only contains identity (user_id, email, tenant_id)
            # All authorization evaluated by Policy Engine per-request
        })
    
    @action(detail=False, methods=['get'], url_path='sensitive-data')
    def get_sensitive_data(self, request):
        """Get sensitive data with ABAC evaluation by Policy Engine."""
        user = get_current_user_from_session(request)
        
        # Policy Engine evaluates ABAC attributes:
        # - Time-of-day
        # - IP allowlist
        # - Data classification clearance
        # - Device trust level
        
        self.check_policy(
            action="view",
            resource="data.sensitive",
            context={
                "resource_type": "sensitive_data",
                "data_classification": "confidential"
            }
        )
        
        # Fetch sensitive data with tenant_id filtering
        # CRITICAL: Explicit tenant_id filtering - NOT schema context
        service = self.get_data_service()
        data = service.get_sensitive_data(tenant_id=user.tenant_id)
        
        return Response(data)
