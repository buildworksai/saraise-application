"""Django lifecycle wiring for the orchestration extension surface."""

from django.apps import AppConfig


class AutomationOrchestrationConfig(AppConfig):
    """Register durable handlers and readiness only after Django is ready."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.automation_orchestration"
    label = "automation_orchestration"

    def ready(self) -> None:
        # Imports are intentionally deferred: paid modules register their node
        # descriptors from their own AppConfig.ready methods against this SPI.
        from .health import register_module_health
        from .tasks import register_async_handlers

        register_async_handlers()
        register_module_health()
