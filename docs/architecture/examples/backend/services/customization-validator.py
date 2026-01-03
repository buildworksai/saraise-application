# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Customization Validation for Custom Fields
# backend/src/customization/validation/customization_validate_.py
# Reference: docs/architecture/module-framework.md § 5.2

from typing import Dict, Any, Optional

class CustomizationValidator:
    """Validation for tenant custom fields.
    
    CRITICAL: Validates custom field definitions against TenantCustomFieldDefinition.
    Enforces schema constraints per module-framework.md § 5.2.
    """
    
    @staticmethod
    def validate_custom_field(field_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate custom field data.
        
        Required fields: entity_name, fieldname, label, fieldtype
        (entity_name refers to the model/table name for custom field definitions)
        """
        required_fields = ["entity_name", "fieldname", "label", "fieldtype"]

        for field in required_fields:
            if field not in field_data:
                return False, f"{field} is required"

        # Validate field type
        valid_field_types = ["Data", "Email", "Number", "Date", "Select", "Link"]
        if field_data["fieldtype"] not in valid_field_types:
            return False, f"Invalid field type: {field_data['fieldtype']}"

        # Validate field name
        if not field_data["fieldname"].startswith("custom_"):
            return False, "Custom field name must start with 'custom_'"

        return True, None

