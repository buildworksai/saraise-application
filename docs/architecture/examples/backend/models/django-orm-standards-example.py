# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Django ORM Model Standards Example
# backend/src/models/example.py
# Reference: docs/architecture/module-framework.md § 3 (Module Models)
# Also: docs/architecture/application-architecture.md § 4.1 (Row-Level Multitenancy)
# 
# CRITICAL NOTES:
# - All models use Django ORM with proper field types
# - MANDATORY: All tenant-scoped models include tenant_id CharField
# - Relationships declared with models.ForeignKey or models.ManyToManyField
# - Indexes on frequent query columns (tenant_id, user_id, created_at)

# Good - Django ORM model with proper types and constraints
from django.db import models
from django.utils import timezone
from typing import Optional

class User(models.Model):
    """User model with Row-Level Multitenancy support."""
    
    id = models.CharField(max_length=36, primary_key=True, db_index=True)
    name = models.CharField(max_length=100)
    email = models.EmailField(max_length=255, unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    
    # CRITICAL: tenant_id for Row-Level Multitenancy
    tenant_id = models.CharField(max_length=36, db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'email']),
            models.Index(fields=['tenant_id', 'created_at']),
        ]

    def __str__(self):
        return f"{self.name} ({self.tenant_id})"



