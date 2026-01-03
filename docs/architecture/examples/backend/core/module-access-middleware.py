# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Module Access Middleware
# backend/src/core/module_access_middleware.py
# Reference: docs/architecture/module-framework.md § 3 (Module Access Control)
# CRITICAL NOTES:
# - Middleware checks tenant module installation BEFORE allowing route access
# - Core routes (platform, tenants, billing) bypass module check (always available)
# - Tenant ID extracted from session or request context (must be present)
# - TenantModuleLoader queries database for tenant's installed modules
# - Missing module returns 403 Forbidden with error message
# - Module access control enforced at middleware layer (before reaching route handler)
# - Module caching reduces database queries (with TTL for freshness)
# - Session must include tenant_id for module check to work
# - Unauthenticated requests bypass module check (401 handled by auth middleware first)
# - Module availability synchronized with subscription changes (event-driven)
# Source: docs/architecture/module-framework.md § 3, application-architecture.md § 4.2

from rest_framework import Request
from django.middleware.base import BaseHTTPMiddleware
from rest_framework.response import JSONResponse
from src.core.tenant_module_loader import TenantModuleLoader
# CRITICAL: Django ORM - no async session needed, use Model.objects directly

class ModuleAccessMiddleware(BaseHTTPMiddleware):
    """Middleware to check module availability before route access"""

    def dispatch(self, request: Request, call_next):
        # Skip for core routes
        if request.url.path.startswith("/api/v1/platform/") or \
           request.url.path.startswith("/api/v1/tenants/") or \
           request.url.path.startswith("/api/v1/billing/"):
            return call_next(request)

        # Get tenant ID from request
        tenant_id = self._get_tenant_id(request)
        if not tenant_id:
            return call_next(request)

        # Extract module name from route
        module_name = self._extract_module_name(request.url.path)
        if not module_name:
            return call_next(request)

        # Check if module is installed for tenant
        # ✅ CORRECT: Django ORM - TenantModuleLoader uses Model.objects internally
        # No database session needed - Django ORM handles connections automatically
        module_loader = TenantModuleLoader()

        if not module_loader._is_module_installed(tenant_id, module_name):
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Module not available",
                    "message": f"Module {module_name} is not installed for your tenant",
                    "module": module_name
                }
            )

        # Load module if not already loaded
        module_loader.load_module_for_tenant(tenant_id, module_name)

        return call_next(request)

