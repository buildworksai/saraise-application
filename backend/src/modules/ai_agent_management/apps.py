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
        from .providers.factory import configure_provider_factory
        from .providers.published import (
            ADAPTER_KEY,
            TenantConfiguredProvider,
            resolve_published_deployment,
        )
        from .providers.registry import get_registry
        from .registries import runner_registry
        from .runners import published_provider_runner
        from .services import DEFAULT_CONFIGURATION, EVALUATE_COMMAND, EXECUTE_COMMAND, RED_TEAM_COMMAND

        maximum_key_length = int(DEFAULT_CONFIGURATION["registry"]["key_maximum_length"])
        runner_registry.configure(maximum_key_length)
        from .registries import evaluation_registry
        evaluation_registry.configure(maximum_key_length)
        get_registry().register(ADAPTER_KEY, TenantConfiguredProvider)
        configure_provider_factory(resolve_published_deployment)
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
