# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Custom Field Customization with Row-Level Multitenancy
# backend/src/customization/services/custom_field_customizer.py
# Reference: docs/architecture/security-model.md (Row-Level Multitenancy § 2)
# Reference: docs/architecture/module-framework.md (Custom Fields § 5.2)
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from src.models.tenant import TenantCustomFieldDefinition
from typing import Optional, Dict, Any

class CustomFieldCustomizer:
    def __init__(self, tenant_id: str):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        self.tenant_id = tenant_id

    def add_custom_field_to_entity(
        self,
        entity_name: str,
        fieldname: str,
        label: str,
        fieldtype: str,
        options: Optional[Dict[str, Any]] = None
    ):
        """Add custom field to entity type with explicit tenant_id filtering.
        
        CRITICAL: Explicit tenant_id filtering enforces Row-Level Multitenancy.
        Do NOT rely on schema context or PostgreSQL search_path.
        """
        # Validate field doesn't conflict with standard fields
        self._validate_field_name(entity_name, fieldname)

        # Add custom field with explicit tenant_id
        # ✅ CORRECT: Django ORM - use Model.objects.create() instead of db.add()/commit()
        custom_field = TenantCustomFieldDefinition.objects.create(
            tenant_id=self.tenant_id,
            entity_name=entity_name,
            fieldname=fieldname,
            label=label,
            fieldtype=fieldtype,
            options=options or {}
        )

        return custom_field

    def _validate_field_name(self, entity_name: str, fieldname: str):
        """Validate custom field name doesn't conflict.
        
        CRITICAL: Use explicit tenant_id + entity_name filtering.
        """
        # Check against existing custom fields for this tenant
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        existing = TenantCustomFieldDefinition.objects.filter(
            tenant_id=self.tenant_id,
            entity_name=entity_name,
            fieldname=fieldname
        ).first()

        if existing:
            raise ValueError(f"Field {fieldname} already exists in {entity_name}")

