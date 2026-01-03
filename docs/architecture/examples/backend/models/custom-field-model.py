# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Custom Field Model for Metadata Modeling
# Reference: docs/architecture/module-framework.md § 3 (Module Models)
# Also: docs/architecture/metadata-modeling.md § 2 (Custom Fields)
# 
# CRITICAL NOTES:
# - Model: TenantCustomFieldDefinition per metadata-modeling.md § 2
# - Field configuration via manifest.yaml per module-framework.md § 3
# - Custom field values stored as JSON in field_config column
# - Validation rules enforced by service layer per module-framework.md § 5.2

from django.db import models
from src.models.base import TenantBase
from typing import Optional, Dict, Any
from datetime import datetime


class TenantCustomFieldDefinition(TenantBase):
    """Custom field definition for tenant-specific metadata modeling.
    
    Stores custom field definitions that extend base entities (Customer, Invoice, etc.).
    Validation and enforcement happen in service layer, not in model.
    """
    
    class Meta:
        db_table = "tenant_custom_field_definitions"
        indexes = [
            models.Index(fields=["tenant_id", "entity_name"]),
        ]
    
    entity_name = models.CharField(
        max_length=255, 
        db_index=True, 
        help_text="Entity type (e.g., 'customer', 'invoice')"
    )
    field_name = models.CharField(
        max_length=255,
        help_text="Field name (e.g., 'custom_department')"
    )
    field_config = models.JSONField(
        default=dict,
        help_text="Field configuration: {label, fieldtype, required, options, ...}"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # CRITICAL: tenant_id column IS REQUIRED for Row-Level Multitenancy
    # Inherited from TenantBase - do NOT rely on schema context or PostgreSQL search_path
    # Always filter by tenant_id explicitly in queries

