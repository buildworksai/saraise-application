"""Reconcile legacy string-owned integration records with the UUID domain."""

from __future__ import annotations

import hashlib
import re
import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


def _uuid(value: object, label: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise RuntimeError(f"{label} contains a non-UUID value; repair it before migrating") from exc


def validate_legacy_uuids(apps, schema_editor) -> None:
    checks = {
        "Integration": ("id", "tenant_id", "created_by"),
        "IntegrationCredential": ("id", "integration_id"),
        "Webhook": ("id", "tenant_id", "created_by"),
        "WebhookDelivery": ("id", "webhook_id"),
        "Connector": ("id",),
        "DataMapping": ("id", "tenant_id", "integration_id"),
    }
    for model_name, fields in checks.items():
        model = apps.get_model("integration_platform", model_name)
        for values in model.objects.values_list(*fields).iterator():
            for field, value in zip(fields, values):
                _uuid(value, f"{model_name}.{field}")


def _slug(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (normalized or fallback)[:80]


def backfill_domain(apps, schema_editor) -> None:
    Connector = apps.get_model("integration_platform", "Connector")
    Integration = apps.get_model("integration_platform", "Integration")
    Credential = apps.get_model("integration_platform", "IntegrationCredential")
    Webhook = apps.get_model("integration_platform", "Webhook")
    Delivery = apps.get_model("integration_platform", "WebhookDelivery")
    Mapping = apps.get_model("integration_platform", "DataMapping")

    from django.db.models import Count

    duplicate_integrations = Integration.objects.values("tenant_id", "name").annotate(total=Count("id")).filter(total__gt=1).count()
    duplicate_webhooks = Webhook.objects.values("tenant_id", "name").annotate(total=Count("id")).filter(total__gt=1).count()
    if duplicate_integrations or duplicate_webhooks:
        raise RuntimeError(
            "Integration-platform migration found duplicate live names "
            f"({duplicate_integrations} integration groups, {duplicate_webhooks} webhook groups). "
            "Rename duplicates before retrying the migration."
        )

    used_keys: set[str] = set()
    for connector in Connector.objects.all().order_by("id"):
        base = _slug(connector.name, "connector")
        key = base
        if key in used_keys:
            key = f"{base[:70]}-{str(connector.id).replace('-', '')[:8]}"
        used_keys.add(key)
        connector.key = key
        connector.adapter_key = f"legacy.integration_platform.{key}"[:200]
        connector.version = "1.0.0"
        connector.module_id = "integration-platform"
        connector.save(update_fields=("key", "adapter_key", "version", "module_id"))

    legacy_connectors: dict[str, object] = {}
    for integration_type in Integration.objects.order_by().values_list("integration_type", flat=True).distinct():
        key = f"legacy-{integration_type}"
        connector = Connector.objects.filter(key=key).first()
        if connector is None:
            connector = Connector.objects.create(
                id=uuid.uuid4(),
                key=key,
                name=f"Legacy {str(integration_type).replace('_', ' ').title()}",
                connector_type=integration_type,
                adapter_key=f"legacy.integration_platform.unavailable.{integration_type}",
                version="1.0.0",
                schema={"type": "object", "additionalProperties": True},
                credential_schema={"type": "object", "additionalProperties": False},
                capabilities=[],
                module_id="integration-platform",
                required_entitlement="",
                is_active=True,
            )
        legacy_connectors[str(integration_type)] = connector

    for integration in Integration.objects.select_related(None).all():
        integration.connector = legacy_connectors[str(integration.integration_type)]
        integration.save(update_fields=("connector",))

    for credential in Credential.objects.select_related("integration").all():
        credential.tenant_id = credential.integration.tenant_id
        credential.created_by = credential.integration.created_by
        credential.save(update_fields=("tenant_id", "created_by"))

    for webhook in Webhook.objects.all():
        webhook.public_id = uuid.uuid4()
        webhook.save(update_fields=("public_id",))

    for delivery in Delivery.objects.select_related("webhook").all():
        delivery_uuid = _uuid(delivery.id, "WebhookDelivery.id")
        canonical = json_bytes(delivery.payload)
        delivery.tenant_id = delivery.webhook.tenant_id
        delivery.payload_hash = hashlib.sha256(canonical).hexdigest()
        delivery.idempotency_key = f"legacy:{delivery_uuid}"
        delivery.job_id = uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:legacy-webhook-delivery:{delivery_uuid}")
        delivery.correlation_id = hashlib.sha256(f"legacy:{delivery_uuid}".encode()).hexdigest()[:64]
        delivery.payload = redact(delivery.payload)
        delivery.response_body_excerpt = safe_excerpt(delivery.response_body_excerpt)
        delivery.error_message = safe_excerpt(delivery.error_message)
        delivery.save(update_fields=("tenant_id", "payload_hash", "idempotency_key", "job_id", "correlation_id", "payload", "response_body_excerpt", "error_message"))

    for mapping in Mapping.objects.select_related("integration").all():
        mapping.name = f"{mapping.source_field} to {mapping.target_field}"[:255]
        mapping.created_by = mapping.integration.created_by
        mapping.save(update_fields=("name", "created_by"))


def json_bytes(value: object) -> bytes:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


SECRET_KEYS = {"password", "secret", "token", "authorization", "api_key", "apikey", "credential", "private_key"}


def redact(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if str(key).lower().replace("-", "_") in SECRET_KEYS else redact(child) for key, child in value.items()}
    if isinstance(value, list):
        return [redact(child) for child in value]
    return value


def safe_excerpt(value: object) -> str:
    text = str(value)[:2048]
    return "[REDACTED]" if any(marker in text.lower() for marker in SECRET_KEYS) else text


def reverse_backfill(apps, schema_editor) -> None:
    # Columns removed by reverse migration carry the derived data away.  The
    # retained legacy fields need no lossy rewrite here.
    del apps, schema_editor


class Migration(migrations.Migration):
    dependencies = [("integration_platform", "0002_add_integration_models")]

    operations = [
        migrations.RunPython(validate_legacy_uuids, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[migrations.DeleteModel(name="IntegrationPlatformResource")],
        ),
        migrations.AlterField("connector", "id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        migrations.AlterField("integration", "id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        migrations.AlterField("integration", "tenant_id", models.UUIDField(db_index=True)),
        migrations.AlterField("integration", "created_by", models.UUIDField()),
        migrations.AlterField("integrationcredential", "id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        migrations.AlterField("webhook", "id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        migrations.AlterField("webhook", "tenant_id", models.UUIDField(db_index=True)),
        migrations.AlterField("webhook", "created_by", models.UUIDField()),
        migrations.AlterField("webhookdelivery", "id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        migrations.AlterField("datamapping", "id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        migrations.AlterField("datamapping", "tenant_id", models.UUIDField(db_index=True)),

        migrations.AlterField("connector", "name", models.CharField(max_length=255)),
        migrations.AddField("connector", "key", models.SlugField(max_length=100, null=True)),
        migrations.AddField("connector", "adapter_key", models.CharField(max_length=200, null=True)),
        migrations.AddField("connector", "version", models.CharField(max_length=32, default="1.0.0")),
        migrations.AddField("connector", "credential_schema", models.JSONField(default=dict)),
        migrations.AddField("connector", "capabilities", models.JSONField(default=list)),
        migrations.AddField("connector", "module_id", models.CharField(default="integration-platform", max_length=100)),
        migrations.AddField("connector", "required_entitlement", models.CharField(blank=True, max_length=200)),
        migrations.RemoveField("connector", "config"),

        migrations.AddField("integration", "connector", models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="integrations", to="integration_platform.connector")),
        migrations.AddField("integration", "description", models.TextField(blank=True)),
        migrations.AddField("integration", "updated_by", models.UUIDField(blank=True, null=True)),
        migrations.AddField("integration", "is_deleted", models.BooleanField(db_index=True, default=False)),
        migrations.AddField("integration", "deleted_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("integration", "deleted_by", models.UUIDField(blank=True, null=True)),
        migrations.AddField("integration", "last_tested_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("integration", "last_test_job_id", models.UUIDField(blank=True, null=True)),
        migrations.AddField("integration", "last_sync_job_id", models.UUIDField(blank=True, null=True)),
        migrations.AddField("integration", "last_error_code", models.CharField(blank=True, max_length=100)),
        migrations.AddField("integration", "last_error_message", models.TextField(blank=True)),

        migrations.AddField("integrationcredential", "tenant_id", models.UUIDField(db_index=True, null=True)),
        migrations.AddField("integrationcredential", "display_hint", models.CharField(blank=True, max_length=100)),
        migrations.AddField("integrationcredential", "version", models.PositiveIntegerField(default=1)),
        migrations.AddField("integrationcredential", "expires_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("integrationcredential", "created_by", models.UUIDField(null=True)),

        migrations.AddField("webhook", "direction", models.CharField(default="outbound", max_length=20)),
        migrations.AlterField("webhook", "url", models.URLField(blank=True, max_length=2000)),
        migrations.AddField("webhook", "public_id", models.UUIDField(editable=False, null=True)),
        migrations.AddField("webhook", "config", models.JSONField(default=dict)),
        migrations.AddField("webhook", "timeout_seconds", models.PositiveSmallIntegerField(default=10)),
        migrations.AddField("webhook", "max_attempts", models.PositiveSmallIntegerField(default=5)),
        migrations.AddField("webhook", "updated_by", models.UUIDField(blank=True, null=True)),
        migrations.AddField("webhook", "is_deleted", models.BooleanField(db_index=True, default=False)),
        migrations.AddField("webhook", "deleted_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("webhook", "deleted_by", models.UUIDField(blank=True, null=True)),
        migrations.AddField("webhook", "last_received_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("webhook", "last_delivered_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("webhook", "last_error_code", models.CharField(blank=True, max_length=100)),

        migrations.AddField("webhookdelivery", "tenant_id", models.UUIDField(db_index=True, null=True)),
        migrations.AddField("webhookdelivery", "updated_at", models.DateTimeField(default=timezone.now)),
        migrations.AddField("webhookdelivery", "payload_hash", models.CharField(default="", max_length=64)),
        migrations.AddField("webhookdelivery", "idempotency_key", models.CharField(default="", max_length=255)),
        migrations.AddField("webhookdelivery", "attempt_count", models.PositiveSmallIntegerField(default=0)),
        migrations.AddField("webhookdelivery", "max_attempts", models.PositiveSmallIntegerField(default=5)),
        migrations.AddField("webhookdelivery", "next_attempt_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("webhookdelivery", "error_code", models.CharField(blank=True, max_length=100)),
        migrations.AddField("webhookdelivery", "duration_ms", models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField("webhookdelivery", "job_id", models.UUIDField(db_index=True, null=True)),
        migrations.AddField("webhookdelivery", "correlation_id", models.CharField(db_index=True, default="", max_length=64)),
        migrations.RenameField("webhookdelivery", "response_body", "response_body_excerpt"),
        migrations.AlterField("webhookdelivery", "response_code", models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AlterField("webhookdelivery", "webhook", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="deliveries", to="integration_platform.webhook")),

        migrations.AddField("datamapping", "name", models.CharField(default="", max_length=255)),
        migrations.AddField("datamapping", "position", models.PositiveIntegerField(default=0)),
        migrations.AddField("datamapping", "is_required", models.BooleanField(default=False)),
        migrations.AddField("datamapping", "default_value", models.JSONField(blank=True, null=True)),
        migrations.AddField("datamapping", "created_by", models.UUIDField(null=True)),
        migrations.AddField("datamapping", "updated_by", models.UUIDField(blank=True, null=True)),
        migrations.AddField("datamapping", "is_deleted", models.BooleanField(db_index=True, default=False)),
        migrations.AddField("datamapping", "deleted_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("datamapping", "deleted_by", models.UUIDField(blank=True, null=True)),
        migrations.AlterUniqueTogether("datamapping", set()),

        migrations.RunPython(backfill_domain, reverse_backfill),

        migrations.AlterField("connector", "key", models.SlugField(max_length=100, unique=True)),
        migrations.AlterField("connector", "adapter_key", models.CharField(max_length=200, unique=True)),
        migrations.AlterField("integration", "connector", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="integrations", to="integration_platform.connector")),
        migrations.AlterField("integrationcredential", "tenant_id", models.UUIDField(db_index=True)),
        migrations.AlterField("integrationcredential", "created_by", models.UUIDField()),
        migrations.AlterField("webhook", "public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
        migrations.AlterField("webhookdelivery", "tenant_id", models.UUIDField(db_index=True)),
        migrations.AlterField("webhookdelivery", "job_id", models.UUIDField(db_index=True)),
        migrations.AlterField("webhookdelivery", "correlation_id", models.CharField(db_index=True, max_length=64)),
        migrations.AlterField("datamapping", "name", models.CharField(max_length=255)),
        migrations.AlterField("datamapping", "created_by", models.UUIDField()),

        migrations.AddConstraint("connector", models.UniqueConstraint(fields=("key", "version"), name="intplat_conn_key_ver_uniq")),
        migrations.AddConstraint("integration", models.UniqueConstraint(condition=models.Q(("is_deleted", False)), fields=("tenant_id", "name"), name="intplat_integ_tenant_name_live_uniq")),
        migrations.AddConstraint("webhook", models.UniqueConstraint(condition=models.Q(("is_deleted", False)), fields=("tenant_id", "name"), name="intplat_hook_tenant_name_live_uniq")),
        migrations.AddConstraint("webhook", models.CheckConstraint(condition=models.Q(("timeout_seconds__gte", 1), ("timeout_seconds__lte", 30)), name="intplat_hook_timeout_range")),
        migrations.AddConstraint("webhook", models.CheckConstraint(condition=models.Q(("max_attempts__gte", 1), ("max_attempts__lte", 10)), name="intplat_hook_attempt_range")),
        migrations.AddConstraint("webhookdelivery", models.UniqueConstraint(fields=("tenant_id", "webhook", "idempotency_key"), name="intplat_delivery_idem_uniq")),
        migrations.AddConstraint("datamapping", models.UniqueConstraint(condition=models.Q(("is_deleted", False)), fields=("tenant_id", "integration", "source_field", "target_field"), name="intplat_map_fields_live_uniq")),
        migrations.AddConstraint("datamapping", models.UniqueConstraint(condition=models.Q(("is_deleted", False)), fields=("tenant_id", "integration", "name"), name="intplat_map_name_live_uniq")),

        migrations.AddIndex("connector", models.Index(fields=("connector_type", "is_active"), name="intplat_conn_type_active_idx")),
        migrations.AddIndex("integration", models.Index(fields=("tenant_id", "status", "created_at"), name="intplat_integ_tenant_status_idx")),
        migrations.AddIndex("integration", models.Index(fields=("tenant_id", "connector", "status"), name="intplat_integ_tenant_conn_idx")),
        migrations.AddIndex("integration", models.Index(fields=("tenant_id", "integration_type", "is_deleted"), name="intplat_integ_tenant_type_idx")),
        migrations.AddIndex("integrationcredential", models.Index(fields=("tenant_id", "integration"), name="intplat_cred_tenant_int_pre_idx")),
        migrations.AddIndex("webhook", models.Index(fields=("tenant_id", "direction"), name="intplat_hook_tenant_dir_pre_idx")),
        migrations.AddIndex("webhook", models.Index(fields=("tenant_id", "public_id"), name="intplat_hook_tenant_pub_idx")),
        migrations.AddIndex("webhookdelivery", models.Index(fields=("tenant_id", "webhook", "created_at"), name="intplat_deliv_tenant_hook_pre_idx")),
        migrations.AddIndex("datamapping", models.Index(fields=("tenant_id", "integration", "position"), name="intplat_map_tenant_pos_idx")),
    ]
