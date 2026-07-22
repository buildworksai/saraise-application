"""Add governed configuration/evidence models and normalize the legacy tenant key."""

import uuid

import django.db.models.deletion
from django.db import migrations, models


def normalize_legacy_tenant_id(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "ALTER TABLE process_mining_resources ALTER COLUMN tenant_id TYPE uuid USING tenant_id::uuid"
    )


def restore_legacy_tenant_id(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "ALTER TABLE process_mining_resources ALTER COLUMN tenant_id TYPE varchar(255) USING tenant_id::text"
    )


def append_fields():
    return [
        ("tenant_id", models.UUIDField(db_index=True)),
        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        ("created_by", models.UUIDField(db_index=True, editable=False)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
    ]


class Migration(migrations.Migration):
    dependencies = [("process_mining", "0003_enable_process_mining_rls")]

    operations = [
        migrations.RunPython(normalize_legacy_tenant_id, restore_legacy_tenant_id),
        migrations.CreateModel(
            name="ProcessMiningConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("document", models.JSONField()),
                ("version", models.PositiveIntegerField(default=1)),
                ("updated_by", models.UUIDField(db_index=True)),
            ],
            options={
                "db_table": "process_mining_configurations",
                "constraints": [models.UniqueConstraint(fields=("tenant_id",), name="pm_config_one_per_tenant")],
            },
        ),
        migrations.CreateModel(
            name="ProcessEventRetentionTombstone",
            fields=[
                *append_fields(),
                ("cutoff", models.DateTimeField()),
                ("event_count", models.PositiveBigIntegerField()),
                ("reason", models.TextField()),
                ("correlation_id", models.CharField(db_index=True, max_length=128)),
            ],
            options={
                "db_table": "process_mining_event_retention_tombstones",
                "constraints": [models.UniqueConstraint(fields=("tenant_id", "cutoff"), name="pm_retention_cutoff_uniq")],
            },
        ),
        migrations.CreateModel(
            name="ProcessModelReferenceAssignment",
            fields=[
                *append_fields(),
                ("transition_key", models.CharField(max_length=255)),
                ("reason", models.TextField(blank=True)),
                ("correlation_id", models.CharField(db_index=True, max_length=128)),
                ("process_model", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reference_assignments", to="process_mining.processmodel")),
                ("process_model_version", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reference_assignments", to="process_mining.processmodelversion")),
            ],
            options={
                "db_table": "process_mining_model_reference_assignments",
                "constraints": [models.UniqueConstraint(fields=("tenant_id", "process_model", "transition_key"), name="pm_ref_assignment_key_uniq")],
                "indexes": [models.Index(fields=["tenant_id", "process_model", "created_at"], name="pm_ref_current")],
            },
        ),
        migrations.CreateModel(
            name="ProcessMiningConfigurationVersion",
            fields=[
                *append_fields(),
                ("version", models.PositiveIntegerField()),
                ("document", models.JSONField()),
                ("correlation_id", models.CharField(db_index=True, max_length=128)),
                ("source", models.CharField(max_length=32)),
                ("configuration", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="versions", to="process_mining.processminingconfiguration")),
            ],
            options={
                "db_table": "process_mining_configuration_versions",
                "constraints": [models.UniqueConstraint(fields=("tenant_id", "configuration", "version"), name="pm_config_version_uniq")],
                "indexes": [models.Index(fields=["tenant_id", "configuration", "version"], name="pm_config_history")],
            },
        ),
        migrations.CreateModel(
            name="ProcessMiningConfigurationAudit",
            fields=[
                *append_fields(),
                ("version", models.PositiveIntegerField()),
                ("action", models.CharField(max_length=32)),
                ("previous_document", models.JSONField(blank=True)),
                ("current_document", models.JSONField()),
                ("correlation_id", models.CharField(db_index=True, max_length=128)),
                ("configuration", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="audits", to="process_mining.processminingconfiguration")),
            ],
            options={
                "db_table": "process_mining_configuration_audits",
                "indexes": [models.Index(fields=["tenant_id", "configuration", "created_at"], name="pm_config_audit_time")],
            },
        ),
        migrations.CreateModel(
            name="ExportArtifactDeletion",
            fields=[
                *append_fields(),
                ("artifact_key", models.CharField(max_length=1024)),
                ("correlation_id", models.CharField(db_index=True, max_length=128)),
                ("export_job", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="artifact_deletions", to="process_mining.eventexportjob")),
            ],
            options={
                "db_table": "process_mining_export_artifact_deletions",
                "constraints": [models.UniqueConstraint(fields=("tenant_id", "export_job"), name="pm_export_delete_once")],
            },
        ),
    ]
