"""Django app configuration for notifications module."""

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """Notifications module application configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.notifications"
    label = "notifications"
    verbose_name = "Notifications"
