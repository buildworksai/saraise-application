"""Django application registration for performance monitoring."""

from django.apps import AppConfig


class PerformanceMonitoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.performance_monitoring"
    label = "performance_monitoring"
    verbose_name = "Performance Monitoring"

    def ready(self) -> None:
        from . import tasks
        from .health import register_health_probes

        del tasks
        register_health_probes()


__all__ = ["PerformanceMonitoringConfig"]
