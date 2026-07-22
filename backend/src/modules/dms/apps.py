"""Django application configuration for the DMS foundation."""

from django.apps import AppConfig


class DmsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.dms"
    label = "dms"
    verbose_name = "Document Management"

    def ready(self) -> None:
        """Register DMS as a critical application-readiness dependency."""

        from .health import register_health_probes
        from .services import register_document_intelligence_gateway

        register_health_probes()
        register_document_intelligence_gateway()


__all__ = ["DmsConfig"]
