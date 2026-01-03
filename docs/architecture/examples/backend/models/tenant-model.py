# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Tenant Model Structure
# Reference: docs/architecture/application-architecture.md § 4.1 (Row-Level Multitenancy)
# Also: docs/architecture/module-framework.md § 3 (Module Models)
# 
# CRITICAL NOTES:
# - Tenant model NEVER has tenant_id (represents the tenant itself)
# - Status field controls tenant lifecycle (active, suspended, deleted)
# - Subscription plan references Plan model (determines available modules)
# - All platform operations filtered by tenant_id context

from django.db import models
from django.utils import timezone
from typing import Optional
from datetime import datetime
import uuid

class Tenant(models.Model):
    """Tenant registry model (lives in platform/public schema).
    
    This model tracks tenant organizations. It is the ONLY model with 
    tenant_id references at the platform level. Business data models
    in tenant-specific schemas do NOT have tenant_id columns.
    """
    id = models.CharField(max_length=36, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = models.CharField(max_length=255, db_index=True)
    schema_name = models.CharField(max_length=255, unique=True, db_index=True)  # PostgreSQL schema name
    domain = models.CharField(max_length=255, unique=True, db_index=True, null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    subscription_id = models.CharField(max_length=36, db_index=True, null=True, blank=True)
    max_users = models.IntegerField(default=10)
    current_users = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants"
        indexes = [
            models.Index(fields=['domain']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.id})"

