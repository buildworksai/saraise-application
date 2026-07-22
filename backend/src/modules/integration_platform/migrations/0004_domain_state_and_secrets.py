"""Encrypt webhook secrets and introduce guarded domain lifecycle evidence."""

from __future__ import annotations

from django.conf import settings
from django.db import migrations, models

from src.core.encryption.service import EncryptionService


def migrate_state_and_secrets(apps, schema_editor) -> None:
    Webhook = apps.get_model("integration_platform", "Webhook")
    Delivery = apps.get_model("integration_platform", "WebhookDelivery")
    Credential = apps.get_model("integration_platform", "IntegrationCredential")
    for webhook in Webhook.objects.all():
        webhook.status = "active" if webhook.is_active else "inactive"
        webhook.encrypted_signing_secret = EncryptionService.encrypt(webhook.secret)
        webhook.transition_history = []
        webhook.save(update_fields=("status", "encrypted_signing_secret", "transition_history"))
    state_map = {"pending": "queued", "failed": "dead_letter", "retrying": "retrying", "delivered": "delivered"}
    for delivery in Delivery.objects.all():
        delivery.status = state_map.get(delivery.status, "dead_letter")
        delivery.transition_history = []
        delivery.save(update_fields=("status", "transition_history"))
    groups = Credential.objects.order_by().values_list("tenant_id", "integration_id", "credential_type").distinct()
    for tenant_id, integration_id, credential_type in groups:
        credentials = list(
            Credential.objects.filter(
                tenant_id=tenant_id,
                integration_id=integration_id,
                credential_type=credential_type,
            ).order_by("created_at", "id")
        )
        for version, credential in enumerate(credentials, start=1):
            newest = version == len(credentials)
            credential.version = version
            credential.status = "active" if newest else "revoked"
            if not newest:
                credential.revoked_at = credential.updated_at
                credential.revoked_by = credential.created_by
                credential.transition_history = [
                    {
                        "transition_key": f"migration:deduplicate:{credential.id}",
                        "command": "rotate",
                        "from_state": "active",
                        "to_state": "revoked",
                        "occurred_at": credential.updated_at.isoformat(),
                        "metadata": {"actor_id": str(credential.created_by), "reason": "Legacy credential superseded during UUID reconciliation", "correlation_id": "migration"},
                    }
                ]
            credential.save(update_fields=("version", "status", "revoked_at", "revoked_by", "transition_history"))


def restore_state_and_secrets(apps, schema_editor) -> None:
    if not getattr(settings, "SARAISE_ALLOW_SECRET_ROLLBACK", False):
        raise RuntimeError("Secret rollback is disabled; set SARAISE_ALLOW_SECRET_ROLLBACK only in a secured rollback environment")
    Webhook = apps.get_model("integration_platform", "Webhook")
    Delivery = apps.get_model("integration_platform", "WebhookDelivery")
    for webhook in Webhook.objects.all():
        webhook.is_active = webhook.status == "active"
        webhook.secret = EncryptionService.decrypt(webhook.encrypted_signing_secret)
        webhook.save(update_fields=("is_active", "secret"))
    state_map = {"queued": "pending", "delivering": "pending", "retrying": "retrying", "delivered": "delivered", "dead_letter": "failed", "cancelled": "failed"}
    for delivery in Delivery.objects.all():
        delivery.status = state_map[delivery.status]
        delivery.save(update_fields=("status",))


class Migration(migrations.Migration):
    dependencies = [("integration_platform", "0003_reconcile_domain_schema")]

    operations = [
        migrations.RemoveIndex("connector", "integration_connector_type__active_idx"),
        migrations.RemoveIndex("integration", "integration_tenant__status_idx"),
        migrations.RemoveIndex("integration", "integration_tenant__type_idx"),
        migrations.RemoveIndex("integrationcredential", "integration_cred_integration_idx"),
        migrations.RemoveIndex("webhook", "integration_webhook_tenant__active_idx"),
        migrations.RemoveIndex("webhookdelivery", "integration_webhook_webhook__status_idx"),
        migrations.RemoveIndex("webhookdelivery", "integration_webhook_webhook__created_idx"),
        migrations.RemoveIndex("datamapping", "integration_mapping_tenant__integration_idx"),

        migrations.AddField("integration", "transition_history", models.JSONField(default=list)),
        migrations.AddField("integrationcredential", "status", models.CharField(default="active", max_length=20)),
        migrations.AddField("integrationcredential", "transition_history", models.JSONField(default=list)),
        migrations.AddField("integrationcredential", "rotated_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("integrationcredential", "revoked_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("integrationcredential", "revoked_by", models.UUIDField(blank=True, null=True)),
        migrations.AddField("webhook", "status", models.CharField(default="inactive", max_length=20)),
        migrations.AddField("webhook", "transition_history", models.JSONField(default=list)),
        migrations.AddField("webhook", "encrypted_signing_secret", models.TextField(default="")),
        migrations.AddField("webhookdelivery", "transition_history", models.JSONField(default=list)),

        migrations.RunPython(migrate_state_and_secrets, restore_state_and_secrets),

        migrations.RemoveField("webhook", "secret"),
        migrations.RemoveField("webhook", "is_active"),
        migrations.AlterField("integration", "integration_type", models.CharField(choices=[("api", "API"), ("webhook", "Webhook"), ("database", "Database"), ("file", "File"), ("message_queue", "Message queue")], max_length=32)),
        migrations.AlterField("integration", "status", models.CharField(choices=[("inactive", "Inactive"), ("testing", "Testing"), ("active", "Active"), ("error", "Error")], default="inactive", max_length=20)),
        migrations.AlterField("integrationcredential", "credential_type", models.CharField(choices=[("api_key", "API key"), ("oauth_token", "OAuth token"), ("username_password", "Username/password"), ("certificate", "Certificate")], max_length=32)),
        migrations.AlterField("integrationcredential", "status", models.CharField(choices=[("active", "Active"), ("revoked", "Revoked"), ("expired", "Expired")], default="active", max_length=20)),
        migrations.AlterField("connector", "connector_type", models.CharField(choices=[("api", "API"), ("webhook", "Webhook"), ("database", "Database"), ("file", "File"), ("message_queue", "Message queue")], max_length=32)),
        migrations.AlterField("webhook", "direction", models.CharField(choices=[("inbound", "Inbound"), ("outbound", "Outbound")], max_length=20)),
        migrations.AlterField("webhook", "status", models.CharField(choices=[("inactive", "Inactive"), ("active", "Active"), ("error", "Error")], default="inactive", max_length=20)),
        migrations.AlterField("webhookdelivery", "status", models.CharField(choices=[("queued", "Queued"), ("delivering", "Delivering"), ("retrying", "Retrying"), ("delivered", "Delivered"), ("dead_letter", "Dead letter"), ("cancelled", "Cancelled")], default="queued", max_length=20)),
        migrations.AlterField("webhookdelivery", "updated_at", models.DateTimeField(auto_now=True)),

        migrations.AddConstraint("integrationcredential", models.UniqueConstraint(fields=("tenant_id", "integration", "credential_type", "version"), name="intplat_cred_version_uniq")),
        migrations.AddConstraint("integrationcredential", models.UniqueConstraint(condition=models.Q(("status", "active")), fields=("tenant_id", "integration", "credential_type"), name="intplat_cred_one_active_uniq")),

        migrations.RemoveIndex("integrationcredential", "intplat_cred_tenant_int_pre_idx"),
        migrations.RemoveIndex("webhook", "intplat_hook_tenant_dir_pre_idx"),
        migrations.RemoveIndex("webhookdelivery", "intplat_deliv_tenant_hook_pre_idx"),
        migrations.AddIndex("integrationcredential", models.Index(fields=("tenant_id", "integration", "status"), name="intplat_cred_tenant_int_idx")),
        migrations.AddIndex("webhook", models.Index(fields=("tenant_id", "direction", "status"), name="intplat_hook_tenant_dir_idx")),
        migrations.AddIndex("webhookdelivery", models.Index(fields=("tenant_id", "webhook", "status", "created_at"), name="intplat_deliv_tenant_hook_idx")),
        migrations.AddIndex("webhookdelivery", models.Index(fields=("tenant_id", "status", "next_attempt_at"), name="intplat_deliv_tenant_retry_idx")),
    ]
