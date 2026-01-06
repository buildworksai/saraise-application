"""
Tenant Management Django App Configuration.
"""

from django.apps import AppConfig


class TenantManagementConfig(AppConfig):
    """Tenant Management module configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.tenant_management"
    label = "tenant_management"
    verbose_name = "Tenant Management"

    def ready(self):
        """App ready hook."""
        pass
