# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Module Model Structure
# backend/src/modules/module_name/models.py
# Reference: docs/architecture/module-framework.md § 3 (Module Models)
# Also: docs/architecture/application-architecture.md § 4.1 (Row-Level Multitenancy)
# 
# CRITICAL NOTES:
# - All models include tenant_id field for Row-Level Multitenancy
# - Django ORM with typed fields required
# - Models defined only in module directory (no cross-module dependencies)
# - Foreign key relationships must cross module boundaries cautiously

from django.db import models
from django.utils import timezone
from typing import Optional, List
from datetime import datetime

class ModuleBaseModel(models.Model):
    """Base model for module-specific models"""
    # CRITICAL: tenant_id column IS REQUIRED for Row-Level Multitenancy
    # All queries MUST filter explicitly by tenant_id (approved security model)
    # Do NOT rely on implicit isolation or schema context
    tenant_id = models.CharField(max_length=36, db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'created_at']),
        ]

class ModuleSpecificModel(ModuleBaseModel):
    """Example module-specific model with Row-Level Multitenancy."""
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=1000, null=True, blank=True)
    module_id = models.CharField(max_length=36, db_index=True)

    class Meta:
        db_table = 'module_specific_table'
        indexes = [
            models.Index(fields=['tenant_id', 'module_id']),
        ]

    def __str__(self):
        return f"{self.name} ({self.tenant_id})"



