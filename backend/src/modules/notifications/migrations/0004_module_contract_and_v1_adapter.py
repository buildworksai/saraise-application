"""Register the canonical module contract and v1 compatibility projection."""

import hashlib

from django.db import migrations

MANIFEST = """name: notifications
version: 2.0.0
module_type: foundation
lifecycle: managed
api:
  canonical: /api/v2/notifications/
  compatibility: /api/v1/notifications/
"""


def register_contract(apps, schema_editor):
    del schema_editor
    Entry = apps.get_model("core", "ModuleRegistryEntry")
    Entry.objects.update_or_create(
        name="notifications", version="2.0.0",
        defaults={
            "description": "Tenant-safe durable notification foundation",
            "module_type": "foundation", "lifecycle": "managed",
            "manifest_content": MANIFEST,
            "manifest_hash": hashlib.sha256(MANIFEST.encode()).hexdigest(),
            "dependencies": ["core.async_jobs", "core.tenancy", "core.access"],
            "permissions": [
                "notifications.inbox:read", "notifications.inbox:update",
                "notifications.template:read", "notifications.template:create", "notifications.template:update", "notifications.template:activate", "notifications.template:archive",
                "notifications.delivery:read", "notifications.delivery:dispatch", "notifications.delivery:dispatch_bulk", "notifications.delivery:dispatch_urgent", "notifications.delivery:retry", "notifications.delivery:cancel",
                "notifications.preference:read", "notifications.preference:update",
                "notifications.endpoint:read", "notifications.endpoint:create", "notifications.endpoint:verify", "notifications.endpoint:update", "notifications.endpoint:delete",
                "notifications.configuration:read", "notifications.configuration:update", "notifications.configuration:import", "notifications.configuration:export", "notifications.configuration:rollback",
                "notifications.health:read",
            ],
            "metadata": {"canonical_api": "/api/v2/notifications/", "v1_delegates": True},
            "is_active": True,
        },
    )
    from src.core.tenancy import TENANT_SCOPED, register_model_scope
    for name in (
        "NotificationTemplate", "NotificationTemplateVersion", "Notification", "NotificationDelivery",
        "NotificationDeliveryAttempt", "NotificationPreference", "NotificationEndpoint",
        "NotificationConfiguration", "NotificationConfigurationVersion", "NotificationConfigurationAudit",
    ):
        register_model_scope(f"notifications.{name}", TENANT_SCOPED)


def unregister_contract(apps, schema_editor):
    del schema_editor
    apps.get_model("core", "ModuleRegistryEntry").objects.filter(name="notifications", version="2.0.0").delete()


class Migration(migrations.Migration):
    dependencies = [("notifications", "0003_import_legacy_notifications"), ("core", "0011_apply_typed_rls_to_notifications")]
    operations = [migrations.RunPython(register_contract, unregister_contract)]
