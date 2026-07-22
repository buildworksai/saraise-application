"""Repair the legacy tenant schema and add governed configuration/evidence."""

import uuid

import django.db.models.deletion
import src.modules.backup_disaster_recovery.models
from django.db import migrations, models


LEGACY_TABLE = "backup_disaster_recovery_resources"
LEGACY_ARCHIVE_TABLE = "bdr_legacy_resources_archive"
NEW_TENANT_TABLES = (
    "bdr_configurations",
    "bdr_configuration_versions",
    "bdr_recovery_point_evidence",
)


def validate_legacy_ids(apps, schema_editor):
    """Stop before schema mutation when historical tenant identity is invalid."""

    del apps
    tables = schema_editor.connection.introspection.table_names()
    if LEGACY_TABLE not in tables:
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f'SELECT tenant_id, id, created_by FROM "{LEGACY_TABLE}"'  # noqa: S608 - static identifier
        )
        for tenant_id, resource_id, created_by in cursor.fetchall():
            for field, value in (
                ("tenant_id", tenant_id),
                ("id", resource_id),
                ("created_by", created_by),
            ):
                try:
                    uuid.UUID(str(value))
                except (TypeError, ValueError, AttributeError) as exc:
                    raise RuntimeError(
                        f"Cannot migrate legacy disaster-recovery {field}: invalid UUID"
                    ) from exc


def archive_legacy_table(apps, schema_editor):
    """Retain legacy rows under a typed, explicitly quarantined table."""

    del apps
    tables = schema_editor.connection.introspection.table_names()
    if LEGACY_TABLE not in tables or LEGACY_ARCHIVE_TABLE in tables:
        return
    qn = schema_editor.quote_name
    schema_editor.execute(
        f"ALTER TABLE {qn(LEGACY_TABLE)} RENAME TO {qn(LEGACY_ARCHIVE_TABLE)}"
    )
    if schema_editor.connection.vendor == "postgresql":
        for column in ("tenant_id", "id", "created_by"):
            schema_editor.execute(
                f"ALTER TABLE {qn(LEGACY_ARCHIVE_TABLE)} "
                f"ALTER COLUMN {qn(column)} TYPE uuid USING {qn(column)}::uuid"
            )


def restore_legacy_table(apps, schema_editor):
    """Fully reverse the quarantine and UUID conversion."""

    del apps
    tables = schema_editor.connection.introspection.table_names()
    if LEGACY_ARCHIVE_TABLE not in tables or LEGACY_TABLE in tables:
        return
    qn = schema_editor.quote_name
    if schema_editor.connection.vendor == "postgresql":
        for column in ("tenant_id", "id", "created_by"):
            schema_editor.execute(
                f"ALTER TABLE {qn(LEGACY_ARCHIVE_TABLE)} "
                f"ALTER COLUMN {qn(column)} TYPE varchar(36) USING {qn(column)}::text"
            )
    schema_editor.execute(
        f"ALTER TABLE {qn(LEGACY_ARCHIVE_TABLE)} RENAME TO {qn(LEGACY_TABLE)}"
    )


def enable_new_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in NEW_TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table}'::REGCLASS);")


def disable_new_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(NEW_TENANT_TABLES):
        schema_editor.execute(
            f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )


class Migration(migrations.Migration):
    dependencies = [("backup_disaster_recovery", "0003_enable_rls")]

    operations = [
        migrations.RunPython(validate_legacy_ids, migrations.RunPython.noop),
        migrations.RunPython(archive_legacy_table, restore_legacy_table),
        migrations.RemoveConstraint(model_name="runbookstep", name="bdr_step_timeout_range"),
        migrations.RemoveConstraint(model_name="runbookstep", name="bdr_step_retry_range"),
        migrations.RemoveConstraint(model_name="restorerun", name="bdr_rr_prod_approved"),
        migrations.AlterField(
            model_name="runbookstep",
            name="timeout_seconds",
            field=models.PositiveIntegerField(
                default=src.modules.backup_disaster_recovery.models.configured_step_timeout_default
            ),
        ),
        migrations.AlterField(
            model_name="drexercise",
            name="environment",
            field=models.CharField(
                choices=[("isolated", "Isolated"), ("standby", "Standby"), ("production", "Production")],
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="drrunbook",
            name="idempotency_key",
            field=models.CharField(
                default=src.modules.backup_disaster_recovery.models.generate_uuid, max_length=255
            ),
        ),
        migrations.AddField(
            model_name="runbookstep",
            name="idempotency_key",
            field=models.CharField(
                default=src.modules.backup_disaster_recovery.models.generate_uuid, max_length=255
            ),
        ),
        migrations.AddConstraint(
            model_name="drrunbook",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"), name="bdr_rb_tenant_idem_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="runbookstep",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"), name="bdr_step_tenant_idem_uniq"
            ),
        ),
        migrations.AlterField(
            model_name="runbookstep",
            name="retry_limit",
            field=models.PositiveSmallIntegerField(
                default=src.modules.backup_disaster_recovery.models.configured_step_retry_default
            ),
        ),
        migrations.CreateModel(
            name="BDRConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("environment", models.CharField(default="default", max_length=64)),
                ("document", models.JSONField(default=dict)),
                ("rollout", models.JSONField(default=dict)),
                ("version", models.PositiveIntegerField(default=1)),
            ],
            options={
                "db_table": "bdr_configurations",
                "indexes": [models.Index(fields=["tenant_id", "environment"], name="bdr_cfg_tenant_env_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "environment"), name="bdr_cfg_tenant_env_uniq"),
                    models.CheckConstraint(condition=models.Q(("version__gt", 0)), name="bdr_cfg_version_positive"),
                ],
            },
        ),
        migrations.CreateModel(
            name="BDRConfigurationVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version", models.PositiveIntegerField()),
                ("actor_id", models.UUIDField()),
                ("correlation_id", models.UUIDField(db_index=True)),
                ("prior_value", models.JSONField(blank=True, default=dict)),
                ("new_value", models.JSONField(default=dict)),
                (
                    "configuration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="versions",
                        to="backup_disaster_recovery.bdrconfiguration",
                    ),
                ),
                (
                    "rollback_of",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="rollback_versions",
                        to="backup_disaster_recovery.bdrconfigurationversion",
                    ),
                ),
            ],
            options={
                "db_table": "bdr_configuration_versions",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "configuration", "-version"], name="bdr_cfgver_tenant_ver_idx"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "configuration", "version"), name="bdr_cfgver_tenant_version_uniq"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="RecoveryPointEvidence",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("sequence", models.PositiveIntegerField()),
                ("actor_id", models.UUIDField()),
                ("correlation_id", models.UUIDField(db_index=True)),
                ("evidence", models.JSONField(default=dict)),
                (
                    "recovery_point",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="verification_events",
                        to="backup_disaster_recovery.recoverypoint",
                    ),
                ),
            ],
            options={
                "db_table": "bdr_recovery_point_evidence",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "recovery_point", "-sequence"], name="bdr_rpe_tenant_seq_idx"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "recovery_point", "sequence"), name="bdr_rpe_tenant_seq_uniq"
                    )
                ],
            },
        ),
        migrations.AddField(
            model_name="recoverypoint",
            name="latest_verification_evidence",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="current_for_points",
                to="backup_disaster_recovery.recoverypointevidence",
            ),
        ),
        migrations.AddField(
            model_name="restorerun",
            name="compensation_state",
            field=models.CharField(blank=True, max_length=24),
        ),
        migrations.AddField(
            model_name="restorerun",
            name="compensation_evidence",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RunPython(enable_new_rls, disable_new_rls),
    ]
