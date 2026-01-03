# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Custom Field Service for Tenant Customization
# backend/src/modules/*/services.py
# Reference: docs/architecture/module-framework.md § 5
# Reference: docs/architecture/application-architecture.md § 2.1

from django.db import transaction
from typing import List, Optional, Dict, Any
from src.models.tenant_custom_field_definition import TenantCustomFieldDefinition
from src.models.tenant_custom_field_value import TenantCustomFieldValue

class CustomFieldService:
    """
    Tenant-scoped custom field management.
    
    Architecture:
    - Custom fields stored in TenantCustomFieldDefinition table
    - Row-Level Multitenancy: all queries filter by tenant_id
    - Custom field values stored in entity's custom_fields JSON column
    CRITICAL: SARAISE uses Django ORM exclusively
    """
    
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        pass

    def add_custom_field(
        self,
        tenant_id: int,
        entity_type: str,
        field_name: str,
        field_label: str,
        field_type: str,
        options: Optional[Dict[str, Any]] = None
    ) -> TenantCustomFieldDefinition:
        """
        Add custom field for tenant entity type.
        
        CRITICAL: Set tenant_id explicitly for Row-Level Multitenancy.
        """
        custom_field = TenantCustomFieldDefinition(
            tenant_id=tenant_id,  # CRITICAL: Explicit tenant isolation
            entity_type=entity_type,
            field_name=field_name,
            field_label=field_label,
            field_type=field_type,
            config=options or {}
        )
        
        # ✅ CORRECT: Django ORM - use instance.save()
        custom_field.save()
        
        return custom_field

    def get_custom_fields(
        self,
        tenant_id: int,
        entity_type: str
    ) -> List[TenantCustomFieldDefinition]:
        """
        Get custom field definitions for tenant entity type.
        
        CRITICAL: Filter by tenant_id explicitly (Row-Level Multitenancy).
        """
        custom_fields = self.Model.objects.filter(TenantCustomFieldDefinition).filter(
            TenantCustomFieldDefinition.tenant_id == tenant_id,
            TenantCustomFieldDefinition.entity_type == entity_type,
            TenantCustomFieldDefinition.is_active == True
        ).all()
        
        return custom_fields

    def validate_custom_field_values(
        self,
        tenant_id: int,
        entity_type: str,
        custom_field_values: Dict[str, Any]
    ) -> bool:
        """
        Validate custom field values against field definitions.
        
        CRITICAL: Validate only against tenant's own custom field definitions.
        """
        # Get tenant's custom field definitions
        custom_field_defs = self.Model.objects.filter(
            TenantCustomFieldDefinition.field_name,
            TenantCustomFieldDefinition.field_type,
            TenantCustomFieldDefinition.config
        ).filter(
            TenantCustomFieldDefinition.tenant_id == tenant_id,
            TenantCustomFieldDefinition.entity_type == entity_type
        ).all()
        
        # Validate each custom field value
        for field_name in custom_field_values.keys():
            field_def = next(
                (f for f in custom_field_defs if f.field_name == field_name),
                None
            )
            
            if not field_def:
                # Field not defined for this tenant
                return False
            
            # Additional type validation can be added here
        
        return True

# ✅ CORRECT: Usage in route
# def create("/api/v1/custom-fields")
# def create_custom_field(
#     field_request: CustomFieldRequest,
#     request.user,
#     # Django ORM uses automatic transaction management,
#     self.policy_engine
# ):
#     # Authorization check
#     decision = policy_engine.evaluate(
#         user_id=current_user.id,
#         tenant_id=current_user.tenant_id,
#         resource="tenant.customization.fields",
#         action="create",
#         context={"entity_type": field_request.entity_type}
#     )
#     if not decision.allowed:
#         raise Response(status=status.HTTP_403)
#     
#     # Create custom field - always use current_user.tenant_id
#     field_service = CustomFieldService(db)
#     custom_field = field_service.add_custom_field(
#         tenant_id=current_user.tenant_id,  # CRITICAL: Use authenticated tenant
#         entity_type=field_request.entity_type,
#         field_name=field_request.field_name,
#         field_label=field_request.field_label,
#         field_type=field_request.field_type,
#         options=field_request.options
#     )
#     return custom_field
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        custom_field_def = TenantCustomFieldDefinition.objects.filter(
            entity_name=entity_name
        ).first()

        if custom_field_def:
            custom_fields = custom_field_def.field_config or {}
            custom_fields[field_name] = {
                "fieldname": field_name,
                "label": field_label,
                "fieldtype": field_type,
                "options": options,
                "default_value": default_value,
                "required": required
            }
            custom_field_def.field_config = custom_fields
            # ✅ CORRECT: Django ORM - use instance.save() to persist changes
            custom_field_def.save()
        
        return custom_field

