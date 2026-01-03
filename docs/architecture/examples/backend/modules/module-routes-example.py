# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Module Route Structure with Policy Engine and Row-Level Multitenancy
# backend/src/modules/module_name/views.py
# Reference: docs/architecture/policy-engine-spec.md
# Reference: docs/architecture/security-model.md

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import PermissionDenied
from typing import Any
from .serializers import ModuleItemSerializer, ModuleItemCreateSerializer
from .services import ModuleService
from src.core.policy_engine import PolicyEngine
from src.core.permissions import SessionAuthentication

class ModuleItemViewSet(viewsets.ModelViewSet):
    """Module Item ViewSet with Policy Engine authorization and Row-Level Multitenancy.
    
    CRITICAL: 
    - Use Policy Engine for authorization (not DRF permissions)
    - Filter by tenant_id explicitly (not queryset filtering)

class ModuleItemViewSet(viewsets.ModelViewSet):
    """Module Item ViewSet with Policy Engine authorization and Row-Level Multitenancy.
    
    CRITICAL: 
    - Use Policy Engine for authorization (not DRF permissions)
    - Filter by tenant_id explicitly (not queryset filtering)
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = ModuleItemSerializer
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.service = None
    
    def get_service(self) -> ModuleService:
        """Initialize service with request context."""
        if not self.service:
            self.service = ModuleService()
        return self.service
    
    def check_policy(self, action: str, context: dict = None) -> None:
        """Check authorization via Policy Engine.
        
        Raises:
            PermissionDenied: If policy evaluation denies access
        """
        decision = self.policy_engine.evaluate(
            user_id=self.request.user.id,
            tenant_id=self.request.user.tenant_id,
            resource="module_name.items",
            action=action,
            context=context or {"resource_type": "item"}
        )
        
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
    
    def create(self, request, *args, **kwargs):
        """Create module item with Policy Engine authorization and Row-Level Multitenancy."""
        # Authorize via Policy Engine
        self.check_policy(action="create")
        
        serializer = ModuleItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = self.get_service()
        # CRITICAL: Pass tenant_id for explicit Row-Level Multitenancy filtering
        item = service.create_item(
            data=serializer.validated_data,
            tenant_id=request.user.tenant_id
        )
        
        response_serializer = ModuleItemSerializer(item)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    def list(self, request, *args, **kwargs):
        """List module items with Policy Engine authorization and Row-Level Multitenancy."""
        # Authorize via Policy Engine
        self.check_policy(action="view")
        
        service = self.get_service()
        # CRITICAL: Pass tenant_id for explicit Row-Level Multitenancy filtering
        items = service.list_items(tenant_id=request.user.tenant_id)
        
        serializer = ModuleItemSerializer(items, many=True)
        return Response(serializer.data)

