# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Rate Limit Routes with Policy Engine
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
from .services import RateLimitService
from .models import RateLimitViolation
from .serializers import RateLimitViolationSerializer
from datetime import datetime
from typing import Optional, List


class RateLimitViewSet(viewsets.ViewSet):
    """
    ViewSet for managing rate limit operations with Policy Engine authorization.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    Multitenancy: Row-level filtering by tenant_id
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.service = None
    
    def get_service(self) -> RateLimitService:
        """Initialize service with request context."""
        if not self.service:
            self.service = RateLimitService()
        return self.service
    
    def check_policy(self, action: str, context: dict = None) -> None:
        """Authorize via Policy Engine."""
        user = get_current_user_from_session(self.request)
        decision = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=user.tenant_id,
            resource="tenant.rate_limits",
            action=action,
            context=context or {}
        )
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
    
    @action(detail=False, methods=['get'], url_path='usage')
    def get_usage_stats(self, request):
        """Get rate limit usage statistics (tenant_admin only)."""
        scope = request.query_params.get('scope', None)
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        self.check_policy(
            action="view",
            context={"scope": scope, "resource_type": "rate_limit_stats"}
        )
        
        user = get_current_user_from_session(request)
        service = self.get_service()
        
        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None
        
        stats = service.get_usage_stats(
            tenant_id=user.tenant_id,
            scope=scope,
            start_date=start_dt,
            end_date=end_dt
        )
        
        return Response(stats)
    
    @action(detail=False, methods=['get'], url_path='violations')
    def get_violations(self, request):
        """Get rate limit violations (tenant_admin only, tenant-scoped)."""
        scope = request.query_params.get('scope', None)
        limit = int(request.query_params.get('limit', 100))
        
        self.check_policy(
            action="view",
            context={"scope": scope, "resource_type": "rate_limit_violations"}
        )
        
        user = get_current_user_from_session(request)
        
        # CRITICAL: Filter by tenant_id (Row-Level Multitenancy)
        queryset = RateLimitViolation.objects.filter(
            tenant_id=user.tenant_id
        )
        
        if scope:
            queryset = queryset.filter(scope=scope)
        
        violations = queryset.order_by('-created_at')[:limit]
        
        serializer = RateLimitViolationSerializer(violations, many=True)
        return Response(serializer.data)
