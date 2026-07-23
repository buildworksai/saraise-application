"""Django app configuration for notifications module."""

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """Notifications module application configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.notifications"
    label = "notifications"
    verbose_name = "Notifications"

    def ready(self) -> None:
        """Register durable command and OSS adapter ownership on app startup."""

        from .adapters import register_builtin_adapters
        from src.core.tenancy import TENANT_SCOPED, register_model_scope
        from .tasks import register_async_handlers

        for model_name in (
            "NotificationTemplate", "NotificationTemplateVersion", "Notification",
            "NotificationDelivery", "NotificationDeliveryAttempt", "NotificationPreference",
            "NotificationEndpoint", "NotificationConfiguration",
            "NotificationConfigurationVersion", "NotificationConfigurationAudit",
        ):
            register_model_scope(f"notifications.{model_name}", TENANT_SCOPED)
        register_builtin_adapters()
        register_async_handlers()
