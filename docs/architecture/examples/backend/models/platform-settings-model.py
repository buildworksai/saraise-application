# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Platform Settings Structure
# backend/src/modules/platform/models.py
# Reference: docs/architecture/application-architecture.md § 2 (Platform Architecture)
# Also: docs/architecture/module-framework.md § 3 (Module Models)
# 
# CRITICAL NOTES:
# - Platform settings NEVER tenant-scoped (applies to all tenants)
# - Settings managed by platform_owner role only (security-model.md § 2.1)
# - Changes immediately broadcast to all tenants (no stale cache exposure)
# - Version history maintained for rollback capability (operational-runbooks.md § 6)

from django.db import models
from django.utils import timezone
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

class PlatformSettings(models.Model):
    """Platform-wide settings (global, not tenant-scoped)."""
    id = models.CharField(max_length=36, primary_key=True, default=lambda: str(uuid.uuid4()))
    key = models.CharField(max_length=255, unique=True, db_index=True)
    value = models.JSONField(default=dict)
    description = models.CharField(max_length=1000, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=36, null=True, blank=True)

    class Meta:
        db_table = "platform_settings"
        indexes = [
            models.Index(fields=['key']),
        ]

    def __str__(self):
        return f"Setting: {self.key}"

