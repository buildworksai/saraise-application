"""Django lifecycle wiring for workflow automation contracts."""

from django.apps import AppConfig


class WorkflowAutomationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.workflow_automation"
    label = "workflow_automation"

    def ready(self) -> None:
        from .extensions import register_builtin_handlers
        from .state_machines import register_workflow_state_machines

        register_builtin_handlers()
        register_workflow_state_machines()

        # Durable commands and readiness are imported lazily to avoid model
        # import cycles.  Their registration functions are idempotent for
        # autoreload and worker boot.
        from .health import register_module_health
        from .jobs import register_async_handlers

        register_async_handlers()
        register_module_health()
