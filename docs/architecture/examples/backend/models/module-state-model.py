# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Module state management
# backend/src/models/module_state.py
# Reference: docs/architecture/module-framework.md § 4 (Module State)
# CRITICAL NOTES:
# - Enum states: INSTALLED, ACTIVE, INACTIVE, UPGRADING, UNINSTALLING, ERROR
# - Transitions: INSTALLED→ACTIVE→INACTIVE, UPGRADING (temporary), UNINSTALLING (final)
# - State timestamps: created_at, updated_at, activated_at, deactivated_at
# - Error state triggered on health check failure or upgrade failure
# - Tenant module state tracked separately (per tenant per module)
# - Module transitions trigger state change event notifications
# - Rollback returns to previous state (not direct state change)
# - State persistence in database (immutable audit trail)
# - Health checks verify state consistency (database ↔ actual state)
# Source: docs/architecture/module-framework.md § 4

from django.db.models import String, DateTime, Enum
from django.db import models
from enum import Enum as PyEnum
from src.models.base import Base
from datetime import datetime
from django.db.models import F

class ModuleState(PyEnum):
    INSTALLED = "installed"
    ACTIVE = "active"
    INACTIVE = "inactive"
    UPGRADING = "upgrading"
    UNINSTALLING = "uninstalling"
    ERROR = "error"

class InstalledModule(Base):
    class Meta:
        db_table = "installed_modules"

    name: str] = models.String, primary_key=True)
    version: str] = models.String, nullable=False)
    state: ModuleState] = models.Enum(ModuleState), default=ModuleState.INSTALLED)
    installed_at: datetime] = models.DateTimeField(timezone=True), server_default=func.now())
    updated_at: datetime] = models.DateTimeField(timezone=True), onupdate=func.now())

