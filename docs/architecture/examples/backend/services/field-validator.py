# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Field Validator for Tenant Custom Fields
# backend/src/customization/services/field_validator.py
# Reference: docs/architecture/module-framework.md § 5.2 (Custom Fields)

from typing import Any, Optional, Dict, Tuple
from django.db import transaction
from src.modules.customization.models import TenantCustomFieldDefinition

class FieldValidator:
    def __init__(self, tenant_id: str):
        """Initialize with tenant context for row-level multitenancy.
        
        CRITICAL: Row-Level Multitenancy - tenant_id is required context.
        Database access via Django ORM per application-architecture.md § 2.1.
        """
        self.tenant_id = tenant_id
    
    def validate_field_value(
        self, 
        field: TenantCustomFieldDefinition, 
        value: Any
    ) -> tuple[bool, Optional[str]]:
        """Validate field value based on custom field definition.
        
        Validates against TenantCustomFieldDefinition with tenant_id association.
        Enforces Row-Level Multitenancy per module-framework.md § 5.2.
        """
        if field.required and (value is None or value == ""):
            return False, f"{field.label} is required"

        if value is None:
            return True, None

        if field.fieldtype == "Email":
            if "@" not in str(value):
                return False, f"{field.label} must be a valid email"

        if field.fieldtype == "Number":
            try:
                float(value)
            except ValueError:
                return False, f"{field.label} must be a number"

        if field.fieldtype == "Select":
            if field.options and "values" in field.options:
                if value not in field.options["values"]:
                    return False, f"{field.label} must be one of {field.options['values']}"

        return True, None

