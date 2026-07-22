"""Django application registration for performance monitoring."""

from django.apps import AppConfig


class PerformanceMonitoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.performance_monitoring"
    label = "performance_monitoring"
    verbose_name = "Performance Monitoring"

    def ready(self) -> None:
        from src.core.async_jobs.services import HandlerNotRegistered, get_handler, register_handler

        from . import tasks
        from .events import register_event_consumers
        from .health import register_health_probes
        from .services import deliver_alert_notification_job

        del tasks
        command = "performance_monitoring.deliver_alert_notification"
        try:
            registered = get_handler(command)
        except HandlerNotRegistered:
            register_handler(command, deliver_alert_notification_job)
        else:
            if registered is not deliver_alert_notification_job:
                raise RuntimeError(f"Conflicting async handler registered for {command!r}.")
        register_event_consumers()
        register_health_probes()


__all__ = ["PerformanceMonitoringConfig"]
