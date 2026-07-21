"""Django application startup for disaster-recovery extension contracts."""

from django.apps import AppConfig


class BackupDisasterRecoveryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.backup_disaster_recovery"
    label = "backup_disaster_recovery"
    verbose_name = "Backup and Disaster Recovery"

    def ready(self) -> None:
        # Imports stay inside ready so Django has completed model discovery.
        from .adapter_registry import (
            BackupRecoveryCatalogAdapter,
            LocalFilesystemStorageRecoveryAdapter,
            register_backup_catalog,
            register_storage_adapter,
        )
        from .health import register_health_probes
        from .tasks import register_async_handlers

        register_backup_catalog("default", BackupRecoveryCatalogAdapter(), replace=False)
        register_storage_adapter(
            LocalFilesystemStorageRecoveryAdapter.key,
            LocalFilesystemStorageRecoveryAdapter(),
            replace=False,
        )
        register_async_handlers()
        register_health_probes()


__all__ = ["BackupDisasterRecoveryConfig"]
