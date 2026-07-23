"""Add versioned tenant security configuration and mutation replay evidence."""

from __future__ import annotations

import uuid

from django.db import migrations, models


TENANT_TABLES = (
    "security_configurations",
    "security_configuration_versions",
    "security_mutation_replays",
)


def install_postgresql_guards(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TENANT_TABLES:
        schema_editor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        schema_editor.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        schema_editor.execute(
            f'''CREATE POLICY "{table}_tenant_isolation" ON "{table}"
                USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)'''
        )
    for table in ("security_configuration_versions", "security_mutation_replays"):
        function = f"{table}_reject_mutation"
        trigger = f"{table}_immutable"
        schema_editor.execute(
            f'''CREATE FUNCTION "{function}"() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'immutable security configuration evidence' USING ERRCODE = '55000'; END;
                $$'''
        )
        schema_editor.execute(
            f'''CREATE TRIGGER "{trigger}" BEFORE UPDATE OR DELETE ON "{table}"
                FOR EACH ROW EXECUTE FUNCTION "{function}"()'''
        )


def remove_postgresql_guards(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in ("security_configuration_versions", "security_mutation_replays"):
        schema_editor.execute(f'DROP TRIGGER IF EXISTS "{table}_immutable" ON "{table}"')
        schema_editor.execute(f'DROP FUNCTION IF EXISTS "{table}_reject_mutation"()')
    for table in TENANT_TABLES:
        schema_editor.execute(f'DROP POLICY IF EXISTS "{table}_tenant_isolation" ON "{table}"')


class Migration(migrations.Migration):
    dependencies = [("security_access_control", "0006_enforce_audit_immutability")]

    operations = [
        migrations.CreateModel(
            name="SecurityConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("environment", models.CharField(max_length=32)),
                ("version", models.PositiveIntegerField(default=1)),
                ("document", models.JSONField()),
                ("rollout", models.JSONField()),
                ("updated_by", models.UUIDField()),
                ("correlation_id", models.CharField(max_length=128)),
            ],
            options={
                "db_table": "security_configurations",
                "indexes": [
                    models.Index(fields=["tenant_id", "version"], name="sec_config_tenant_version_idx"),
                    models.Index(fields=["tenant_id", "environment"], name="sec_config_tenant_env_idx"),
                ],
                "constraints": [models.UniqueConstraint(fields=("tenant_id",), name="sec_config_tenant_uniq")],
            },
        ),
        migrations.CreateModel(
            name="SecurityConfigurationVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version", models.PositiveIntegerField()),
                ("environment", models.CharField(max_length=32)),
                ("previous_document", models.JSONField(null=True)),
                ("current_document", models.JSONField()),
                ("previous_rollout", models.JSONField(null=True)),
                ("current_rollout", models.JSONField()),
                ("actor_id", models.UUIDField()),
                ("correlation_id", models.CharField(max_length=128)),
                ("reason", models.TextField()),
                ("change_kind", models.CharField(max_length=24)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "security_configuration_versions",
                "ordering": ("-version",),
                "indexes": [
                    models.Index(fields=["tenant_id", "-version"], name="sec_config_version_history_idx"),
                    models.Index(fields=["tenant_id", "correlation_id"], name="sec_config_version_corr_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "version"), name="sec_config_version_tenant_uniq")
                ],
            },
        ),
        migrations.CreateModel(
            name="MutationReplay",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("idempotency_key", models.CharField(max_length=128)),
                ("request_hash", models.CharField(max_length=64)),
                ("operation", models.CharField(max_length=128)),
                ("resource_id", models.UUIDField(null=True)),
                ("response_status", models.PositiveSmallIntegerField()),
                ("response_document", models.JSONField()),
                ("correlation_id", models.CharField(max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "security_mutation_replays",
                "indexes": [
                    models.Index(fields=["tenant_id", "operation"], name="sec_replay_tenant_op_idx")
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="sec_replay_tenant_key_uniq")
                ],
            },
        ),
        migrations.RunPython(install_postgresql_guards, remove_postgresql_guards),
    ]
