"""
AI Agent Management Django App Configuration
"""

from django.apps import AppConfig


class AiAgentManagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.ai_agent_management"
    label = "ai_agent_management"
    verbose_name = "AI Agent Management"

    def ready(self) -> None:
        """Register reference extensions and durable handlers once."""

        from src.core.async_jobs.services import HandlerAlreadyRegistered, register_handler

        from .jobs import evaluation_job, execute_agent_job
        from .registries import runner_registry
        from .runners import published_provider_runner
        from .services import EVALUATE_COMMAND, EXECUTE_COMMAND, RED_TEAM_COMMAND

        runner_registry.register(published_provider_runner.key, published_provider_runner)
        for command, handler in (
            (EXECUTE_COMMAND, execute_agent_job),
            (EVALUATE_COMMAND, evaluation_job),
            (RED_TEAM_COMMAND, evaluation_job),
        ):
            try:
                register_handler(command, handler)
            except HandlerAlreadyRegistered:
                # Django may invoke ready more than once in autoreload.  The
                # registry itself rejects actual replacement.
                continue
