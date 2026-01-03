# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: User Quota API Routes with Policy Engine
# backend/src/modules/*/views.py
# Reference: docs/architecture/policy-engine-spec.md
# Reference: docs/architecture/security-model.md

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from src.core.audit_service import AuditService
from .services import UserQuotaService
from .models import QuotaViolation
from .serializers import QuotaStatsResponseSerializer, QuotaCheckResponseSerializer, QuotaViolationSerializer
from typing import Optional, List
from datetime import datetime


class UserQuotaViewSet(viewsets.ViewSet):
    """
    ViewSet for managing user quotas with Policy Engine authorization.
    
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
        self.service = None
    
    def get_service(self) -> UserQuotaService:
        """Initialize service with request context."""
        if not self.service:
            self.service = UserQuotaService()
        return self.service
    
    def check_policy(self, action: str, context: dict = None) -> None:
        """Authorize via Policy Engine."""
        user = get_current_user_from_session(self.request)
        decision = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=user.tenant_id,
            resource="tenant.quotas",
            action=action,
            context=context or {}
        )
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
    
    @action(detail=False, methods=['get'], url_path='usage')
    def get_quota_stats(self, request):
        """Get quota usage statistics (tenant_admin only)."""
        quota_type = request.query_params.get('quota_type', None)
        
        self.check_policy(
            action="view",
            context={"quota_type": quota_type, "resource_type": "quota_stats"}
        )
        
        user = get_current_user_from_session(request)
        service = self.get_service()
        stats = service.get_quota_stats(
            tenant_id=user.tenant_id,
            quota_type=quota_type
        )
        
        return Response(stats)
    
    @action(detail=False, methods=['get'], url_path='check/(?P<quota_type>[^/.]+)')
    def check_quota(self, request, quota_type=None):
        """Check quota before action (tenant_admin only)."""
        self.check_policy(action="view", context={"quota_type": quota_type})
        
        user = get_current_user_from_session(request)
        service = self.get_service()
        is_allowed, info = service.check_quota(
            tenant_id=user.tenant_id,
            quota_type=quota_type
        )
        
        return Response({"allowed": is_allowed, "quota_info": info})
    
    @action(detail=False, methods=['get'], url_path='violations')
    def get_violations(self, request):
        """Get quota violations (tenant admin)."""
        self.check_policy(action="view")
        
        quota_type = request.query_params.get('quota_type', None)
        limit = int(request.query_params.get('limit', 100))
        
        user = get_current_user_from_session(request)
        
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        queryset = QuotaViolation.objects.filter(
            tenant_id=user.tenant_id
        )
        
        if quota_type:
            queryset = queryset.filter(quota_type=quota_type)
        
        queryset = queryset.order_by('-created_at')[:limit]
        
        serializer = QuotaViolationSerializer(queryset, many=True)
        return Response(serializer.data)
