"""Django application configuration and integration registration."""

from django.apps import AppConfig


class DocumentIntelligenceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.document_intelligence"
    label = "document_intelligence"
    verbose_name = "Document Intelligence"

    def ready(self) -> None:
        # Importing these modules registers the five state machines and five
        # durable command handlers.  Django invokes ready once per app registry.
        from . import state_machines, tasks
        from .health import register_health_probes

        del state_machines, tasks
        register_health_probes()


__all__ = ["DocumentIntelligenceConfig"]
