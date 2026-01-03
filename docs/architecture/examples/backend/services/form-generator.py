# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Form Generator with Custom Fields Pattern
# backend/src/customization/services/form_generator.py
# Reference: docs/architecture/module-framework.md § 5.2 (Custom Fields)
# Reference: docs/architecture/security-model.md (Row-Level Multitenancy)

from django.db import transaction
from django.db.models import Q
from typing import Dict, Any, List, Optional
from src.modules.customization.models import TenantCustomFieldDefinition
from src.modules.metadata.models import EntityDefinition

class FormGenerator:
    def __init__(self, tenant_id: str):
        """Initialize form generator with tenant context.
        
        Uses Django ORM for all database operations.
        All queries automatically scoped to tenant via tenant_id.
        """
        self.tenant_id = tenant_id

    def generate_form_schema(self, entity_name: str) -> Dict[str, Any]:
        """Generate form schema from entity definition and custom fields.
        
        CRITICAL: Uses TenantCustomFieldDefinition with explicit tenant_id filtering.
        Implements Row-Level Multitenancy per application-architecture.md § 2.1.
        """
        # Get entity definition (standard fields)
        try:
            entity_obj = EntityDefinition.objects.get(name=entity_name)
        except EntityDefinition.DoesNotExist:
            raise ValueError(f"Entity {entity_name} not found")

        # Get custom fields for this tenant (explicit tenant_id filtering)
        custom_fields = TenantCustomFieldDefinition.objects.filter(
            tenant_id=self.tenant_id,
            entity_name=entity_name
        )

        # Build form schema
        schema = {
            "entity_name": entity_name,
            "label": entity_obj.label,
            "fields": []
        }

        # Add standard fields
        for field in entity_obj.fields:
            schema["fields"].append(field)


        # Add custom fields
        for custom_field in custom_fields:
            schema["fields"].append({
                "fieldname": custom_field.fieldname,
                "label": custom_field.label,
                "fieldtype": custom_field.fieldtype,
                "options": custom_field.options,
                "default_value": custom_field.default_value,
                "required": custom_field.required,
                "is_custom": True
            })

        return schema

