# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Customization API Routes with Policy Engine
# backend/src/modules/*/views.py
# Reference: docs/architecture/module-framework.md § 5
# Reference: docs/architecture/policy-engine-spec.md

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from rest_framework.fields import Field
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from .services import CustomFieldService, FormCustomizer
from .models import CustomField, CustomForm
from .serializers import (
    CustomFieldSerializer,
    CustomFieldCreateSerializer,
    CustomFormSerializer,
    CustomFormCreateSerializer
)
from typing import Optional, Dict, Any


class CustomizationViewSet(viewsets.ViewSet):
    """
    ViewSet for managing customization (custom fields and forms) with Policy Engine authorization.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    Multitenancy: Row-level filtering by tenant_id
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.field_service = None
        self.form_service = None
    
    def get_field_service(self) -> CustomFieldService:
        """Initialize custom field service."""
        if not self.field_service:
            self.field_service = CustomFieldService()
        return self.field_service
    
    def get_form_service(self) -> FormCustomizer:
        """Initialize form customizer service."""
        if not self.form_service:
            self.form_service = FormCustomizer()
        return self.form_service
    
    def check_policy(self, action: str, resource: str, context: dict = None) -> None:
        """Authorize via Policy Engine."""
        user = get_current_user_from_session(self.request)
        decision = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=user.tenant_id,
            resource=resource,
            action=action,
            context=context or {}
        )
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
    
    @action(detail=False, methods=['post'], url_path='fields')
    def add_custom_field(self, request):
        """Add custom field for tenant entity type (tenant_admin only)."""
        serializer = CustomFieldCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = get_current_user_from_session(request)
        self.check_policy(
            action="create",
            resource="tenant.customization.fields",
            context={"entity_type": serializer.validated_data["entity_type"], "resource_type": "custom_field"}
        )
        
        service = self.get_field_service()
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
    
    @action(detail=False, methods=['post'], url_path='forms')
    def customize_form(self, request):
        """Customize form layout for entity type (tenant_admin only)."""
        serializer = CustomFormCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = get_current_user_from_session(request)
        self.check_policy(
            action="update",
            resource="tenant.customization.forms",
            context={"entity_type": serializer.validated_data["entity_type"], "resource_type": "custom_form"}
        )
        
        service = self.get_form_service()
        custom_form = service.customize_form_layout(
            tenant_id=user.tenant_id,
            entity_type=serializer.validated_data["entity_type"],
            layout=serializer.validated_data["layout"]
        )
        
        return Response(
            CustomFormSerializer(custom_form).data,
            status=status.HTTP_201_CREATED
        )
