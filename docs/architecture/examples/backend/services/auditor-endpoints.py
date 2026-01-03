# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Auditor Endpoints with Policy Engine
# backend/src/modules/audit/views.py
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
from .models import AuditLog
from .serializers import AuditLogSerializer
from datetime import datetime
from typing import Optional


class AuditorViewSet(viewsets.ViewSet):
    """
    ViewSet for audit log access with Policy Engine authorization.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
    
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
    
    @action(detail=False, methods=['get'], url_path='admin/audit-logs')
    def get_platform_audit_logs(self, request):
        """
        Query platform audit logs (platform_auditor, platform_owner via inheritance).
        
        Policy Engine evaluates:
        - permission "audit.logs:view" at platform level
        - Role hierarchy (platform_owner inherits platform_auditor)
        """
        tenant_id = request.query_params.get('tenant_id', None)
        resource = request.query_params.get('resource', None)
        start_date = request.query_params.get('start_date', None)
        limit = int(request.query_params.get('limit', 100))
        
        self.check_policy(
            action="view",
            resource="platform.audit_logs",
            context={
                "resource_type": "platform_audit_logs",
                "filters": {"tenant_id": tenant_id, "resource": resource}
            },
            tenant_id=None  # Platform operation
        )
        
        # Query audit logs with filters
        queryset = AuditLog.objects.all()
        
        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)
        if resource:
            queryset = queryset.filter(resource=resource)
        if start_date:
            start_dt = datetime.fromisoformat(start_date)
            queryset = queryset.filter(timestamp__gte=start_dt)
        
        logs = queryset.order_by('-timestamp')[:limit]
        
        serializer = AuditLogSerializer(logs, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='audit-logs')
    def get_tenant_audit_logs(self, request):
        """
        Query tenant audit logs (tenant_auditor, tenant_admin via inheritance).
        
        CRITICAL: Filter by tenant_id explicitly (Row-Level Multitenancy).
        """
        resource = request.query_params.get('resource', None)
        limit = int(request.query_params.get('limit', 100))
        
        user = get_current_user_from_session(request)
        
        self.check_policy(
            action="view",
            resource="tenant.audit_logs",
            context={
                "resource_type": "tenant_audit_logs",
                "filters": {"resource": resource}
            },
            tenant_id=user.tenant_id
        )
        
        # Query tenant audit logs - CRITICAL: Filter by tenant_id
        queryset = AuditLog.objects.filter(
            tenant_id=user.tenant_id  # CRITICAL: Tenant filter
        )
        
        if resource:
            queryset = queryset.filter(resource=resource)
        
        logs = queryset.order_by('-timestamp')[:limit]
        
        serializer = AuditLogSerializer(logs, many=True)
        return Response(serializer.data)
