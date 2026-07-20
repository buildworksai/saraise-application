"""Django application configuration for durable asynchronous jobs."""

from django.apps import AppConfig


class AsyncJobsConfig(AppConfig):
    """Register the async job models and their independent migration history."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "src.core.async_jobs"
    label = "async_jobs"
    verbose_name = "SARAISE Async Jobs"
