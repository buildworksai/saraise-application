"""
AI Agent Management Django App Configuration
"""

from django.apps import AppConfig


class AiAgentManagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.ai_agent_management"
    label = "ai_agent_management"
    verbose_name = "AI Agent Management"
