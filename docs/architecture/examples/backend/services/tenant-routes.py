# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Tenant Management Routes with Policy Engine
# backend/src/modules/*/views.py
# Reference: docs/architecture/policy-engine-spec.md
# Reference: docs/architecture/security-model.md
# Reference: docs/architecture/application-architecture.md § 4.1

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
from .services import TenantService, UserQuotaService
from typing import Any, Dict
from django.db import transaction


class TenantViewSet(viewsets.ViewSet):
    """
    ViewSet for tenant management with Policy Engine authorization.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.audit_service = AuditService()
        self.tenant_service = None
        self.quota_service = None
    
    def get_tenant_service(self) -> TenantService:
        if not self.tenant_service:
            self.tenant_service = TenantService()
        return self.tenant_service
    
    def get_quota_service(self) -> UserQuotaService:
        if not self.quota_service:
            self.quota_service = UserQuotaService()
        return self.quota_service
    
    def check_policy(self, action: str, resource: str, context: dict = None, tenant_id=None) -> None:
        """Authorize via Policy Engine."""
        user = get_current_user_from_session(self.request)
        decision = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=tenant_id,
            resource=resource,
            action=action,
            context=context or {}
        )
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
    
    def create(self, request, *args, **kwargs):
        """Create tenant (platform_owner only, platform operation)."""
        tenant_data: Dict[str, Any] = request.data
        
        # CRITICAL: Authorize via Policy Engine (not decorators)
        self.check_policy(
            action="create",
            resource="platform.tenants",
            context={"resource_type": "platform_tenants", "tenant_name": tenant_data.get("name")},
            tenant_id=None  # Platform operation
        )
        
        user = get_current_user_from_session(request)
        service = self.get_tenant_service()
        
        # Create tenant via service
        with transaction.atomic():
            tenant = service.create_tenant(
                name=tenant_data.get("name"),
                domain=tenant_data.get("domain"),
                subscription_plan_id=tenant_data.get("subscription_plan_id")
            )
        
        # Audit log
        self.audit_service.log_event(
            actor_sub=user.id,
            actor_email=user.email,
            tenant_id=None,  # Platform operation
            resource="tenants",
            action="create",
            result="success",
            metadata={"tenant_id": str(tenant.id), "tenant_name": tenant.name},
            request=request
        )
        
        return Response({"id": str(tenant.id), "name": tenant.name}, status=status.HTTP_201_CREATED)
    
    def retrieve(self, request, pk=None, *args, **kwargs):
        """Get tenant settings (tenant_admin only, tenant-scoped)."""
        user = get_current_user_from_session(request)
        
        # CRITICAL: Authorize via Policy Engine
        self.check_policy(
            action="view",
            resource="tenant.settings",
            context={"resource_type": "tenant_settings"},
            tenant_id=user.tenant_id
        )
        
        # Verify accessing own tenant
        if user.tenant_id != pk:
            raise PermissionDenied(detail="Cannot access other tenants")
        
        # Get tenant
        service = self.get_tenant_service()
        tenant = service.get_tenant(pk)
        
        if not tenant:
            raise NotFound(detail="Tenant not found")
        
        return Response({"id": str(tenant.id), "name": tenant.name})
    
    @action(detail=True, methods=['patch'], url_path='quota')
    def update_quota(self, request, pk=None):
        """Update tenant user quota (platform_owner only, platform operation)."""
        quota_data: Dict[str, Any] = request.data
        
        # CRITICAL: Authorize via Policy Engine
        self.check_policy(
            action="update",
            resource="platform.tenant_quotas",
            context={"target_tenant_id": pk, "max_users": quota_data.get("max_users")},
            tenant_id=None  # Platform operation
        )
        
        user = get_current_user_from_session(request)
        service = self.get_quota_service()
        
        # Update quota
        with transaction.atomic():
            quota = service.update_user_quota(pk, quota_data.get("max_users"))
        
        # Audit log
        self.audit_service.log_event(
            actor_sub=user.id,
            actor_email=user.email,
            tenant_id=None,
            resource="tenant_quotas",
            action="update",
            result="success",
            metadata={"target_tenant_id": pk, "max_users": quota_data.get("max_users")},
            request=request
        )
        
        return Response({"status": "updated"})
