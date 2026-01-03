# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Platform Resource Permissions via Policy Engine
# backend/src/modules/*/views.py
# Reference: docs/architecture/policy-engine-spec.md
# Reference: docs/architecture/security-model.md § 3

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from .services import TenantService, BillingService, AuditService
from typing import Dict, Any


class PlatformResourceViewSet(viewsets.ViewSet):
    """
    ViewSet for platform-level resource management with Policy Engine authorization.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    Scope: Platform-level operations (no tenant_id)
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.tenant_service = None
        self.billing_service = None
        self.audit_service = None
    
    def get_tenant_service(self):
        if not self.tenant_service:
            self.tenant_service = TenantService()
        return self.tenant_service
    
    def get_billing_service(self):
        if not self.billing_service:
            self.billing_service = BillingService()
        return self.billing_service
    
    def get_audit_service(self):
        if not self.audit_service:
            self.audit_service = AuditService()
        return self.audit_service
    
    def check_policy(self, action: str, resource: str, context: dict = None) -> None:
        """Authorize via Policy Engine for platform-level operations."""
        user = get_current_user_from_session(self.request)
        decision = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=None,  # Platform-level operations have no tenant_id
            resource=resource,
            action=action,
            context=context or {}
        )
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
    
    @action(detail=False, methods=['post'], url_path='tenants')
    def create_tenant(self, request):
        """Create tenant (platform_owner only)."""
        self.check_policy(
            action="create",
            resource="platform.tenants",
            context={"resource_type": "tenants"}
        )
        
        service = self.get_tenant_service()
        tenant = service.create_tenant(request.data)
        
        return Response({"message": "Tenant created", "tenant_id": tenant.id}, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'], url_path='tenants')
    def list_tenants(self, request):
        """List tenants (platform_owner only)."""
        self.check_policy(
            action="view",
            resource="platform.tenants",
            context={"resource_type": "tenants"}
        )
        
        service = self.get_tenant_service()
        tenants = service.list_tenants()
        
        return Response({"tenants": tenants})
    
    @action(detail=False, methods=['post'], url_path='billing/invoices')
    def create_invoice(self, request):
        """Create invoice (platform_billing_manager only)."""
        self.check_policy(
            action="create",
            resource="platform.billing.invoices",
            context={"resource_type": "invoices"}
        )
        
        service = self.get_billing_service()
        invoice = service.create_invoice(request.data)
        
        return Response({"message": "Invoice created", "invoice_id": invoice.id}, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'], url_path='audit-logs')
    def get_audit_logs(self, request):
        """Get audit logs (platform_auditor, read-only)."""
        self.check_policy(
            action="view",
            resource="platform.audit_logs",
            context={"resource_type": "audit_logs"}
        )
        
        service = self.get_audit_service()
        logs = service.get_audit_logs(request.query_params)
        
        return Response({"logs": logs})
