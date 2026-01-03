# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: TenantModule Model
# Reference: docs/architecture/module-framework.md § 3 (Module Models)
# Also: docs/architecture/application-architecture.md § 2 (Modular System)
# 
# CRITICAL NOTES:
# - Tracks module installations per tenant (tenant_id, module_name unique constraint)
# - Subscription plan determines available modules (TenantModuleLoader enforces)
# - Version tracks installed module version (used for upgrade/rollback)
# - All module access controlled by ModuleAccessMiddleware per-request

from django.db import models
from django.utils import timezone
from typing import Optional
from datetime import datetime
import uuid

class TenantModule(models.Model):
    """Platform-level module installation tracking.
    
    NOTE: This is a PLATFORM registry table, not a business data table.
    It tracks which modules are installed for which tenants.
    Business data tables in tenant schemas do NOT have tenant_id columns.
    """
    id = models.CharField(max_length=36, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = models.CharField(max_length=36, db_index=True)
    module_name = models.CharField(max_length=255, db_index=True)
    version = models.CharField(max_length=50)
    installed_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=50,
        choices=[('active', 'Active'), ('inactive', 'Inactive')],
        default='active',
        db_index=True
    )
    subscription_id = models.CharField(max_length=36, null=True, blank=True)

    class Meta:
        db_table = "tenant_modules"
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['module_name']),
            models.Index(fields=['tenant_id', 'module_name']),
            models.Index(fields=['tenant_id', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant_id', 'module_name'],
                name='uq_tenant_module'
            )
        ]

    def __str__(self):
        return f"{self.module_name} v{self.version} ({self.tenant_id})"

