"""
Tenant Management Module.

CRITICAL: These are PLATFORM-LEVEL models (NO tenant_id).
Tenant Management operates at the platform level to manage all tenants.
All queries are platform-scoped, not tenant-scoped.
"""

default_app_config = "src.modules.tenant_management.apps.TenantManagementConfig"
