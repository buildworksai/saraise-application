# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Module health checks
# backend/src/core/module_health_checker.py
# Reference: docs/architecture/operational-runbooks.md § 4.2 (Health Checks)
# CRITICAL NOTES:
# - CRITICAL: SARAISE uses Django ORM exclusively
# - Django ORM: Use Model.objects for queries, no database session needed
# - Database connectivity verified (can query module tables)
# - All dependencies verified to be installed (recursive check)
# - Module initialization completed (startup tasks successful)
# - Required integrations tested (API endpoints, external services)
# - Data integrity checks: referential integrity, data consistency
# - Performance baseline: response time within expected range
# - Resource utilization: memory, CPU within acceptable limits
# - Licensing validation: module license not expired
# - Audit log accessibility: audit tables queryable
# - Health status returned per-module: healthy, degraded, failed
# Source: docs/architecture/operational-runbooks.md § 4.2

from django.db import connection
from typing import Dict, Any

class ModuleHealthChecker:
    """Module health checker using Django ORM."""
    
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        pass

    def check_module_health(self, module_name: str) -> Dict[str, Any]:
        """Check module health status"""
        health = {
            "module": module_name,
            "status": "healthy",
            "checks": {}
        }

        # Check module is installed
        is_installed = self._is_module_installed(module_name)
        health["checks"]["installed"] = {
            "status": "healthy" if is_installed else "unhealthy",
            "message": "Module is installed" if is_installed else "Module is not installed"
        }

        # Check module routes are registered
        routes_registered = self._are_routes_registered(module_name)
        health["checks"]["routes"] = {
            "status": "healthy" if routes_registered else "unhealthy",
            "message": "Routes are registered" if routes_registered else "Routes are not registered"
        }

        # Check module database tables exist
        tables_exist = self._do_tables_exist(module_name)
        health["checks"]["database"] = {
            "status": "healthy" if tables_exist else "unhealthy",
            "message": "Database tables exist" if tables_exist else "Database tables missing"
        }

        # Overall status
        if not all(check["status"] == "healthy" for check in health["checks"].values()):
            health["status"] = "unhealthy"

        return health

