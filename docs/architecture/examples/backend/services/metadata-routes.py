# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Metadata API Routes with Policy Engine
# backend/src/modules/*/views.py
# Reference: docs/architecture/module-framework.md § 5
# Reference: docs/architecture/policy-engine-spec.md

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from rest_framework.request import Request
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from .services import CustomFieldService
from .models import CustomField
from .serializers import CustomFieldSerializer, CustomFieldCreateSerializer
from typing import Optional, Dict, Any


class MetadataViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing metadata (custom fields) with Policy Engine authorization.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    Multitenancy: Row-level filtering by tenant_id
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = CustomFieldSerializer
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.service = None
    
    def get_service(self) -> CustomFieldService:
        """Initialize service with request context."""
        if not self.service:
            self.service = CustomFieldService()
        return self.service
    
    def get_queryset(self):
        """Filter by authenticated user's tenant_id (Row-Level Multitenancy)."""
        user = get_current_user_from_session(self.request)
        if not user or not user.tenant_id:
            return CustomField.objects.none()
        # CRITICAL: Explicit tenant_id filtering
        return CustomField.objects.filter(tenant_id=user.tenant_id)
    
    def check_policy(self, action: str, context: dict = None) -> None:
        """Authorize via Policy Engine."""
        user = get_current_user_from_session(self.request)
        decision = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=user.tenant_id,
            resource="tenant.metadata",
            action=action,
            context=context or {}
        )
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
    
    @action(detail=False, methods=['get'], url_path='entity-schema/(?P<entity_type>[^/.]+)')
    def get_entity_schema(self, request, entity_type=None):
        """Get entity schema (standard + custom fields for tenant)."""
        self.check_policy(action="view", context={"entity_type": entity_type, "resource_type": "entity_schema"})
        
        # Get standard fields + tenant custom fields
        service = self.get_service()
        user = get_current_user_from_session(request)
        custom_fields = service.get_custom_fields(
            tenant_id=user.tenant_id,
            entity_type=entity_type
        )
        
        return Response({
            "entity_type": entity_type,
            "custom_fields": CustomFieldSerializer(custom_fields, many=True).data
        })
    
    def create(self, request, *args, **kwargs):
        """Add custom field to entity type (tenant_admin only)."""
        self.check_policy(action="create", context={"entity_type": request.data.get("entity_type")})
        
        serializer = CustomFieldCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = get_current_user_from_session(request)
        service = self.get_service()
        custom_field = service.add_custom_field(
            tenant_id=user.tenant_id,
            entity_type=serializer.validated_data["entity_type"],
            field_name=serializer.validated_data["field_name"],
            field_label=serializer.validated_data["field_label"],
            field_type=serializer.validated_data["field_type"],
            options=serializer.validated_data.get("options")
        )
        
        return Response(
            CustomFieldSerializer(custom_field).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['get'], url_path='custom-fields/(?P<entity_type>[^/.]+)')
    def get_custom_fields(self, request, entity_type=None):
        """Get custom fields for entity type (tenant-scoped)."""
        self.check_policy(action="view", context={"entity_type": entity_type})
        
        user = get_current_user_from_session(request)
        service = self.get_service()
        custom_fields = service.get_custom_fields(
            tenant_id=user.tenant_id,
            entity_type=entity_type
        )
        
        return Response(CustomFieldSerializer(custom_fields, many=True).data)
    
    def list(self, request, *args, **kwargs):
        """List all custom fields for tenant."""
        self.check_policy(action="view")
        
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    def retrieve(self, request, pk=None, *args, **kwargs):
        """Retrieve single custom field."""
        self.check_policy(action="view", context={"field_id": pk})
        
        try:
            custom_field = self.get_queryset().get(pk=pk)
        except CustomField.DoesNotExist:
            raise NotFound(detail="Custom field not found")
        
        serializer = self.get_serializer(custom_field)
        return Response(serializer.data)
    
    def update(self, request, pk=None, *args, **kwargs):
        """Update custom field."""
        self.check_policy(action="update", context={"field_id": pk})
        
        try:
            custom_field = self.get_queryset().get(pk=pk)
        except CustomField.DoesNotExist:
            raise NotFound(detail="Custom field not found")
        
        serializer = CustomFieldCreateSerializer(custom_field, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(CustomFieldSerializer(custom_field).data)
    
    def destroy(self, request, pk=None, *args, **kwargs):
        """Delete custom field."""
        self.check_policy(action="delete", context={"field_id": pk})
        
        try:
            custom_field = self.get_queryset().get(pk=pk)
        except CustomField.DoesNotExist:
            raise NotFound(detail="Custom field not found")
        
        custom_field.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
