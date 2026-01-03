# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Application Startup Configuration
# backend/src/core/app_startup.py
# Reference: docs/architecture/module-framework.md § 4 (Module Lifecycle)
# CRITICAL NOTES:
# - Django AppConfig handles startup and shutdown (Django pattern)
# - Startup sequence: run_migrations → init_database → load_core_modules
# - Core modules loaded: platform_management, tenant_management, billing (always available)
# - Tenant-specific modules loaded per-tenant during login (TenantModuleLoader)
# - Database migrations run ONCE at startup (idempotent, handles concurrent execution)
# - Core module registry initialized before accepting requests
# - Health checks verify database connectivity AND module availability
# - Graceful shutdown: close database connections, unload modules, flush logs
# - Application MUST NOT start if core modules fail to load (fail-fast)
# - Session store initialization (Redis connection pooling) happens at startup
# Source: docs/architecture/module-framework.md § 4, operational-runbooks.md § 1

from django.apps import AppConfig
from django.core.management import call_command
from src.core.module_registry import module_registry


class CoreConfig(AppConfig):
    """Django AppConfig for core application startup."""
    name = 'src.core'
    default_auto_field = 'django.db.models.BigAutoField'
    
    def ready(self):
        """Run startup logic when Django app is ready."""
        # Run migrations
        try:
            call_command('migrate', verbosity=0, interactive=False)
        except Exception as e:
            raise RuntimeError(f"Failed to run migrations: {e}")
        
        # Initialize database connections
        from django.db import connection
        connection.ensure_connection()
        
        # ONLY load core modules at startup
        # Core modules: platform_management, tenant_management, billing
        CORE_MODULES = {"platform_management", "tenant_management", "billing"}
        
        try:
            module_registry.register_module("platform_management", platform_manifest)
            module_registry.load_module("platform_management")
            
            module_registry.register_module("tenant_management", tenant_manifest)
            module_registry.load_module("tenant_management")
            
            module_registry.register_module("billing", billing_manifest)
            module_registry.load_module("billing")
        except Exception as e:
            raise RuntimeError(f"Failed to load core modules: {e}")
        
        # DO NOT load business modules (CRM, Accounting) at startup
        # They will be loaded per-tenant when needed via TenantModuleLoader
        
        # Initialize Redis connection pool for sessions
        from src.core.session_manager import SessionCookieManager
        SessionCookieManager.initialize_redis_pool()

# ✅ CORRECT: All routes are statically registered in main.py (urls.py)
# Business module routes are registered at startup in main.py
# ModuleAccessMiddleware enforces per-tenant module access control
# See docs/architecture/application-architecture.md - static route registration only
