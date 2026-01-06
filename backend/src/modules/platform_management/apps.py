"""
Platform Management Django App Configuration
"""
from django.apps import AppConfig


class PlatformManagementConfig(AppConfig):
    """Platform Management app configuration."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.modules.platform_management'
    label = 'platform_management'
    verbose_name = 'Platform Management'

