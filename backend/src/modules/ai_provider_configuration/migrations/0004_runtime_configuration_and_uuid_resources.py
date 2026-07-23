"""Tenant runtime configuration and UUID resource ownership.

This migration is intentionally reversible. Existing resource rows are
validated before type conversion; non-UUID legacy values stop the migration
instead of silently manufacturing ownership.
"""

from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


def validate_legacy_resource_identifiers(apps, schema_editor):
    Resource = apps.get_model("ai_provider_configuration", "AIProviderConfigurationResource")
    for resource in Resource.objects.order_by("pk").iterator():
        for field in ("id", "tenant_id", "created_by"):
            value = getattr(resource, field)
            try:
                uuid.UUID(str(value))
            except (TypeError, ValueError, AttributeError) as exc:
                raise RuntimeError(
                    f"AIProviderConfigurationResource {resource.pk} has non-UUID {field}: {value!r}"
                ) from exc


def refresh_resource_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    table = schema_editor.quote_name("ai_provider_configuration_resources")
    policy = schema_editor.quote_name("aiprov_resources_tenant_policy")
    schema_editor.execute(f"DROP POLICY IF EXISTS {policy} ON {table};")
    schema_editor.execute(
        f"""CREATE POLICY {policy} ON {table}
        USING (tenant_id = saraise_current_tenant_id())
        WITH CHECK (tenant_id = saraise_current_tenant_id());"""
    )


def restore_resource_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    table = schema_editor.quote_name("ai_provider_configuration_resources")
    policy = schema_editor.quote_name("aiprov_resources_tenant_policy")
    schema_editor.execute(f"DROP POLICY IF EXISTS {policy} ON {table};")
    schema_editor.execute(
        f"""CREATE POLICY {policy} ON {table}
        USING (tenant_id = saraise_current_tenant_id()::text)
        WITH CHECK (tenant_id = saraise_current_tenant_id()::text);"""
    )


def enable_new_table_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    tables = (
        ("ai_provider_configuration_runtime_configs", "aiprov_runtime_cfg_tenant_policy"),
        ("ai_provider_configuration_runtime_config_versions", "aiprov_runtime_cfg_ver_tenant_policy"),
        ("ai_provider_configuration_runtime_config_audit", "aiprov_runtime_cfg_audit_tenant_policy"),
        ("ai_provider_configuration_idempotency_keys", "aiprov_idem_tenant_policy"),
    )
    for table_name, policy_name in tables:
        table = schema_editor.quote_name(table_name)
        policy = schema_editor.quote_name(policy_name)
        schema_editor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy} ON {table};")
        schema_editor.execute(
            f"""CREATE POLICY {policy} ON {table}
            USING (tenant_id = saraise_current_tenant_id())
            WITH CHECK (tenant_id = saraise_current_tenant_id());"""
        )


def disable_new_table_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    tables = (
        ("ai_provider_configuration_idempotency_keys", "aiprov_idem_tenant_policy"),
        ("ai_provider_configuration_runtime_config_audit", "aiprov_runtime_cfg_audit_tenant_policy"),
        ("ai_provider_configuration_runtime_config_versions", "aiprov_runtime_cfg_ver_tenant_policy"),
        ("ai_provider_configuration_runtime_configs", "aiprov_runtime_cfg_tenant_policy"),
    )
    for table_name, policy_name in tables:
        table = schema_editor.quote_name(table_name)
        policy = schema_editor.quote_name(policy_name)
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy} ON {table};")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("ai_provider_configuration", "0003_tenant_rls"),
    ]

    operations = [
        migrations.RunPython(validate_legacy_resource_identifiers, migrations.RunPython.noop),
        migrations.RemoveIndex(
            model_name="aiproviderconfigurationresource",
            name="aiprov_res_tenant_active_idx",
        ),
        migrations.RemoveIndex(
            model_name="aiproviderconfigurationresource",
            name="aiprov_res_tenant_name_idx",
        ),
        migrations.AlterField(
            model_name="aiproviderconfigurationresource",
            name="id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name="aiproviderconfigurationresource",
            name="tenant_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="aiproviderconfigurationresource",
            name="created_by",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AddField(
            model_name="aiproviderconfigurationresource",
            name="is_deleted",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="aiproviderconfigurationresource",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="aiproviderconfigurationresource",
            index=models.Index(fields=["tenant_id", "is_active"], name="aiprov_res_tenant_active_idx"),
        ),
        migrations.AddIndex(
            model_name="aiproviderconfigurationresource",
            index=models.Index(fields=["tenant_id", "name"], name="aiprov_res_tenant_name_idx"),
        ),
        migrations.AddIndex(
            model_name="aiproviderconfigurationresource",
            index=models.Index(fields=["tenant_id", "is_deleted"], name="aiprov_res_tenant_deleted_idx"),
        ),
        migrations.CreateModel(
            name="AIProviderRuntimeConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("environment", models.CharField(default="default", max_length=64)),
                ("values", models.JSONField(default=dict)),
                ("version", models.PositiveIntegerField(default=1)),
                ("updated_by", models.UUIDField()),
            ],
            options={
                "db_table": "ai_provider_configuration_runtime_configs",
                "indexes": [models.Index(fields=["tenant_id", "environment"], name="aiprov_runtime_config_env_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "environment"), name="aiprov_runtime_config_tenant_env_uq"),
                    models.CheckConstraint(condition=models.Q(("version__gte", 1)), name="aiprov_runtime_config_version_gte1"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AIProviderIdempotencyKey",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("key_digest", models.CharField(max_length=64)),
                ("request_fingerprint", models.CharField(max_length=64)),
                ("resource_type", models.CharField(max_length=64)),
                ("resource_id", models.UUIDField(blank=True, null=True)),
                ("response", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "db_table": "ai_provider_configuration_idempotency_keys",
                "indexes": [models.Index(fields=["tenant_id", "key_digest"], name="aiprov_idem_lookup_idx")],
                "constraints": [models.UniqueConstraint(fields=("tenant_id", "key_digest"), name="aiprov_idem_tenant_key_uq")],
            },
        ),
        migrations.CreateModel(
            name="AIProviderRuntimeConfigurationVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("version", models.PositiveIntegerField()),
                ("environment", models.CharField(max_length=64)),
                ("values", models.JSONField()),
                ("created_by", models.UUIDField()),
                ("correlation_id", models.UUIDField()),
                ("rollback_of", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "configuration",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="versions", to="ai_provider_configuration.aiproviderruntimeconfiguration"),
                ),
            ],
            options={
                "db_table": "ai_provider_configuration_runtime_config_versions",
                "indexes": [models.Index(fields=["tenant_id", "configuration", "-version"], name="aiprov_runtime_cfg_ver_idx")],
                "constraints": [models.UniqueConstraint(fields=("tenant_id", "configuration", "version"), name="aiprov_runtime_config_version_uq")],
            },
        ),
        migrations.CreateModel(
            name="AIProviderRuntimeConfigurationAudit",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("action", models.CharField(max_length=32)),
                ("actor_id", models.UUIDField()),
                ("correlation_id", models.UUIDField()),
                ("from_version", models.PositiveIntegerField(blank=True, null=True)),
                ("to_version", models.PositiveIntegerField()),
                ("before", models.JSONField()),
                ("after", models.JSONField()),
                ("rollback_of", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "configuration",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="audit_records", to="ai_provider_configuration.aiproviderruntimeconfiguration"),
                ),
            ],
            options={
                "db_table": "ai_provider_configuration_runtime_config_audit",
                "indexes": [models.Index(fields=["tenant_id", "configuration", "-created_at"], name="aiprov_runtime_cfg_audit_idx")],
            },
        ),
        migrations.RunPython(refresh_resource_rls, restore_resource_rls),
        migrations.RunPython(enable_new_table_rls, disable_new_table_rls),
    ]
