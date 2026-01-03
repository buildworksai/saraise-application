# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Module rollback process
# backend/src/core/module_rollback.py
# Reference: docs/architecture/module-framework.md § 4 (Disaster Recovery)
# CRITICAL NOTES:
# - CRITICAL: SARAISE uses Django ORM exclusively
# - Django ORM: Use Model.objects for queries, no database session needed
# - Rollback triggered by administrator after failed upgrade
# - Previous version snapshot used for recovery (blue-green deployment)
# - Data restoration from backup (pre-upgrade state)
# - Django migrations reverse migration restores schema
# - Permission updates reverted to previous state
# - SoD policy rollback restores original duty segregations
# - Service restart with previous version code
# - Health checks validate rollback success
# - User notification on rollback completion
# - Audit logging: rollback event recorded with reason
# Source: docs/architecture/module-framework.md § 4, operational-runbooks.md § 6 (Disaster Recovery)

from django.db import transaction

class ModuleRollback:
    """Module rollback manager using Django ORM."""
    
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        pass

    def rollback_module(self, module_name: str, to_version: str):
        """Rollback module to previous version"""
        # 1. Get current version
        current_version = self._get_current_version(module_name)

        # 2. Backup current state
        self._backup_current_state(module_name)

        # 3. Run rollback migrations
        self._run_rollback_migrations(module_name, current_version, to_version)

        # 4. Restore data from backup
        self._restore_data_from_backup(module_name, to_version)

        # 5. Update module version
        self._update_module_version(module_name, to_version)

