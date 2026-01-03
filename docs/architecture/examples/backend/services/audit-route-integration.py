# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Audit Route Integration with Policy Engine
# Reference: docs/architecture/policy-engine-spec.md
# Reference: docs/architecture/security-model.md (Audit Logging § 3)

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import PermissionDenied
from django.db import transaction
from typing import List
from rest_framework import serializers
from src.core.policy_engine import PolicyEngine
from src.core.audit_service import AuditService
from src.services.user_service import UserService

class RoleUpdateRequest(serializers.Serializer):
    """Request serializer for role updates."""
    roles = serializers.ListField(child=serializers.CharField(), required=True)

class UserRoleViewSet(viewsets.ViewSet):
    """User role management with Policy Engine and audit logging."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.audit_service = AuditService()
        self.user_service = UserService()
    
    @action(detail=True, methods=['patch'], url_path='roles')
    def update_roles(self, request: Request, pk: str = None):
        """Update user roles with Policy Engine authorization and audit logging."""
        role_update = RoleUpdateRequest(data=request.data)
        role_update.is_valid(raise_exception=True)
        
        # CRITICAL: Authorize via Policy Engine (not decorators)
        decision = self.policy_engine.evaluate(
            user_id=request.user.id,
            tenant_id=request.user.tenant_id,
            resource="users.roles",
            action="update",
            context={
                "target_user_id": pk,
                "new_roles": role_update.validated_data['roles'],
                "resource_type": "user_role"
            }
        )
        
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
        
        try:
            # CRITICAL: Tenant isolation - verify target user belongs to same tenant
            target_user = self.user_service.get_user(
                user_id=pk,
                tenant_id=request.user.tenant_id
            )
            if not target_user:
                return Response(
                    {"error": "User not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Perform role update
            with transaction.atomic():
                self.user_service.update_roles(
                    user_id=pk,
                    tenant_id=request.user.tenant_id,
                    new_roles=role_update.validated_data['roles']
                )
            
            # ✅ REQUIRED: Audit log for role changes (sensitive operation)
            self.audit_service.log_event(
                actor_sub=request.user.id,
                actor_email=request.user.email,
                tenant_id=request.user.tenant_id,
                resource="user_roles",
                action="update",
                result="success",
                metadata={
                    "target_user_id": pk,
                    "new_roles": role_update.validated_data['roles']
                },
                request=request
            )
            
            return Response(
                {"status": "updated", "user_id": pk},
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            # ✅ REQUIRED: Audit failure for sensitive operations
            self.audit_service.log_event(
                actor_sub=request.user.id,
                actor_email=request.user.email,
                tenant_id=request.user.tenant_id,
                resource="user_roles",
                action="update",
                result="error",
                error_message=str(e),
                metadata={"target_user_id": pk},
                request=request
            )
            return Response(
                {"error": "Failed to update user roles"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

