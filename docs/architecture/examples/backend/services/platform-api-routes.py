# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Platform API Routes with Policy Engine
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
from .services import PlatformHealthService, PlatformAnalyticsService, PlatformBackupService


class PlatformAPIViewSet(viewsets.ViewSet):
    """
    ViewSet for platform-level API operations with Policy Engine authorization.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    Scope: Platform-level operations (no tenant_id)
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.health_service = None
        self.analytics_service = None
        self.backup_service = None
    
    def get_health_service(self) -> PlatformHealthService:
        if not self.health_service:
            self.health_service = PlatformHealthService()
        return self.health_service
    
    def get_analytics_service(self) -> PlatformAnalyticsService:
        if not self.analytics_service:
            self.analytics_service = PlatformAnalyticsService()
        return self.analytics_service
    
    def get_backup_service(self) -> PlatformBackupService:
        if not self.backup_service:
            self.backup_service = PlatformBackupService()
        return self.backup_service
    
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
    
    @action(detail=False, methods=['get'], url_path='health')
    def get_platform_health(self, request):
        """Get platform health (platform_operator only)."""
        self.check_policy(
            action="view",
            resource="platform.health",
            context={"resource_type": "platform_health"}
        )
        
        service = self.get_health_service()
        health = service.get_platform_health()
        return Response(health)
    
    @action(detail=False, methods=['get'], url_path='analytics')
    def get_platform_analytics(self, request):
        """Get platform analytics (platform_owner only)."""
        period = request.query_params.get('period', '30d')
        
        self.check_policy(
            action="view",
            resource="platform.analytics",
            context={"resource_type": "platform_analytics", "period": period}
        )
        
        service = self.get_analytics_service()
        analytics = service.get_platform_analytics(period)
        return Response(analytics)
    
    @action(detail=False, methods=['post'], url_path='backup')
    def create_platform_backup(self, request):
        """Create platform backup (platform_owner only)."""
        backup_type = request.data.get('backup_type', 'full')
        
        self.check_policy(
            action="create",
            resource="platform.backup",
            context={"resource_type": "platform_backup", "backup_type": backup_type}
        )
        
        service = self.get_backup_service()
        backup = service.create_backup(backup_type)
        return Response(backup, status=status.HTTP_201_CREATED)
