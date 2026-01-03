# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Platform Management Routes with Policy Engine
# backend/src/modules/platform/views.py
# Reference: docs/architecture/policy-engine-spec.md

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.fields import Field
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from src.core.audit_service import AuditService
from .services import PlatformConfigService
from .serializers import PlatformSettingsUpdateSerializer
from typing import Dict, Any


class PlatformViewSet(viewsets.ViewSet):
    """
    ViewSet for platform-level management with Policy Engine authorization.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    Scope: Platform-level operations (no tenant_id)
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.audit_service = AuditService()
        self.service = None
    
    def get_service(self) -> PlatformConfigService:
        """Initialize service with request context."""
        if not self.service:
            self.service = PlatformConfigService()
        return self.service
    
    def check_policy(self, action: str, context: dict = None) -> None:
        """Authorize via Policy Engine for platform-level operations."""
        user = get_current_user_from_session(self.request)
        decision = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=None,  # Platform-level operations have no tenant_id
            resource="platform.settings",
            action=action,
            context=context or {}
        )
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
    
    @action(detail=False, methods=['get'], url_path='settings')
    def get_platform_settings(self, request):
        """Get platform settings (platform_owner only)."""
        self.check_policy(action="view", context={"resource_type": "platform_settings"})
        
        service = self.get_service()
        settings = service.get_all_settings()
        return Response(settings)
    
    @action(detail=False, methods=['post'], url_path='settings')
    def update_platform_settings(self, request):
        """Update platform settings (platform_owner only)."""
        serializer = PlatformSettingsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        self.check_policy(action="update", context={"resource_type": "platform_settings"})
        
        user = get_current_user_from_session(request)
        service = self.get_service()
        
        for key, value in serializer.validated_data["settings"].items():
            service.set_setting(key, value, user.id)
        
        # Audit log
        self.audit_service.log_event(
            actor_sub=user.id,
            actor_email=user.email,
            tenant_id=None,
            resource="platform_settings",
            action="UPDATE",
            result="success",
            metadata={"settings": serializer.validated_data["settings"]},
            request=request
        )
        
        return Response({"status": "updated"})
