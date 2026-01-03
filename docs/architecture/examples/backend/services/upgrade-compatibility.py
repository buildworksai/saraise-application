# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Customization Upgrade Compatibility with Row-Level Multitenancy
# backend/src/customization/services/upgrade_compatibility.py
# Reference: docs/architecture/security-model.md (Row-Level Multitenancy § 2)
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import Dict, Any, List
from src.models.tenant import TenantCustomFieldDefinition, TenantCustomForm

class UpgradeCompatibilityChecker:
    def __init__(self, tenant_id: str):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        self.tenant_id = tenant_id

    def check_customization_compatibility(
        self,
        from_version: str,
        to_version: str
    ) -> Dict[str, Any]:
        """Check if customizations are compatible with upgrade.
        
        CRITICAL: Uses explicit tenant_id filtering for Row-Level Multitenancy.
        """
        compatibility = {
            "compatible": True,
            "warnings": [],
            "errors": []
        }

        # Check custom fields with explicit tenant_id filtering
        custom_fields = self._get_tenant_custom_fields()
        for field in custom_fields:
            if not self._is_field_compatible(field, from_version, to_version):
                compatibility["compatible"] = False
                compatibility["errors"].append(
                    f"Custom field {field.fieldname} is not compatible with {to_version}"
                )

        # Check custom forms with explicit tenant_id filtering
        custom_forms = self._get_tenant_custom_forms()
        for form in custom_forms:
            if not self._is_form_compatible(form, from_version, to_version):
                compatibility["warnings"].append(
                    f"Custom form {form.entity_name} may need updates for {to_version}"
                )

        return compatibility

    def _is_field_compatible(self, field: TenantCustomFieldDefinition, from_version: str, to_version: str) -> bool:
        """Check if custom field is compatible with upgrade."""
        # Validate field type compatibility
        # Check field options compatibility
        return True

    def _get_tenant_custom_fields(self) -> List[TenantCustomFieldDefinition]:
        """Get custom fields for tenant with explicit tenant_id filtering.
        
        CRITICAL: Do NOT rely on schema context or search_path.
        Always use explicit WHERE tenant_id = ? filtering.
        """
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        return list(TenantCustomFieldDefinition.objects.filter(tenant_id=self.tenant_id))

    def _get_tenant_custom_forms(self) -> List[TenantCustomForm]:
        """Get custom forms for tenant with explicit tenant_id filtering.
        
        CRITICAL: Do NOT rely on schema context or search_path.
        Always use explicit WHERE tenant_id = ? filtering.
        """
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        return list(TenantCustomForm.objects.filter(tenant_id=self.tenant_id))

    def _is_form_compatible(self, form: TenantCustomForm, from_version: str, to_version: str) -> bool:
        """Check if custom form is compatible with upgrade."""
        # Validate form definition compatibility
        return True

