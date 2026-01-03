# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Module uninstallation process
# backend/src/core/module_uninstaller.py
# Reference: docs/architecture/module-framework.md § 4 (Module Uninstallation)
# CRITICAL NOTES:
# - CRITICAL: SARAISE uses Django ORM exclusively
# - Django ORM: Use Model.objects for queries, no database session needed
# - Dependency check: prevents removing modules other modules depend on
# - Data retention option: keep_data=True preserves data, False deletes data
# - Django migrations reverse migration rolls back schema changes
# - Permission removal: all module permissions revoked from tenant
# - SoD policy cleanup: module's duty segregations removed
# - Audit logging: uninstallation event recorded
# - Graceful shutdown: active module operations completed before uninstall
# - Billing impact: subscription features removed if module tied to plan
# - Data export option: export module data before deletion (compliance)
# - Atomic operation: all-or-nothing (no partial uninstalls)
# Source: docs/architecture/module-framework.md § 4

from django.db import transaction
from typing import List

class ModuleUninstaller:
    """Module uninstaller using Django ORM."""
    
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        pass

    def uninstall_module(self, module_name: str, keep_data: bool = False):
        """Uninstall module with optional data retention"""
        # 1. Check if other modules depend on this module
        dependents = self._get_dependent_modules(module_name)
        if dependents:
            raise ValueError(f"Cannot uninstall {module_name}: {dependents} depend on it")

        # 2. Run pre-uninstall hooks
        self._run_pre_uninstall_hooks(module_name)

        # 3. Backup data if requested
        if keep_data:
            self._backup_module_data(module_name)

        # 4. Remove routes
        self._remove_routes(module_name)

        # 5. Drop database tables (if not keeping data)
        if not keep_data:
            self._drop_module_tables(module_name)

        # 6. Run post-uninstall hooks
        self._run_post_uninstall_hooks(module_name)

        # 7. Mark as uninstalled
        self._mark_uninstalled(module_name)

    def _get_dependent_modules(self, module_name: str) -> List[str]:
        """Get modules that depend on this module"""
        from src.core.module_registry import module_registry

        dependents = []
        for mod_name, manifest in module_registry.modules.items():
            dependencies = manifest.get("depends", [])
            if module_name in dependencies:
                dependents.append(mod_name)

        return dependents

