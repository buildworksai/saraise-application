"""Add tenant runtime policy and safely retire the wrongly typed legacy table."""

import uuid

import django.db.models.deletion
from django.db import migrations, models


LEGACY_TABLE = "automation_orchestration_resources"
TENANT_TABLES = (
    "automation_orchestration_commands",
    "automation_orchestration_configurations",
    "automation_orchestration_configuration_versions",
    "automation_orchestration_configuration_audits",
    "automation_orchestration_reconciliations",
)


def retire_legacy_table(apps, schema_editor) -> None:
    """Validate UUID data, then convert the legacy tenant column on PostgreSQL."""
    del apps
    tables = set(schema_editor.connection.introspection.table_names(include_views=True))
    if LEGACY_TABLE not in tables:
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f'SELECT "tenant_id", "id", "created_by" FROM "{LEGACY_TABLE}"')
        for tenant_id, resource_id, created_by in cursor.fetchall():
            uuid.UUID(str(tenant_id))
            uuid.UUID(str(resource_id))
            uuid.UUID(str(created_by))
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            f'ALTER TABLE "{LEGACY_TABLE}" ALTER COLUMN "tenant_id" TYPE uuid USING "tenant_id"::uuid'
        )


def restore_legacy_table(apps, schema_editor) -> None:
    """Restore the historical varchar representation on reverse migration."""
    del apps
    tables = set(schema_editor.connection.introspection.table_names(include_views=True))
    if LEGACY_TABLE in tables and schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            f'ALTER TABLE "{LEGACY_TABLE}" ALTER COLUMN "tenant_id" TYPE varchar(36) USING "tenant_id"::text'
        )


def enable_rls(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table_name}'::REGCLASS);")


def disable_rls(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in reversed(TENANT_TABLES):
        policy_name = f"tenant_isolation_{table_name}"
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name};")
        schema_editor.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [("automation_orchestration", "0003_enable_orchestration_rls")]

    operations = [
        migrations.CreateModel(
            name="OrchestrationCommand",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("operation", models.CharField(max_length=64)),
                ("idempotency_key", models.CharField(max_length=255)),
                ("request_fingerprint", models.CharField(max_length=64)),
                ("result_type", models.CharField(blank=True, default="", max_length=64)),
                ("result_id", models.UUIDField(blank=True, null=True)),
                ("correlation_id", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "automation_orchestration_commands",
                "indexes": [models.Index(fields=["tenant_id", "created_at"], name="ao_command_tenant_created_idx")],
                "constraints": [models.UniqueConstraint(fields=("tenant_id", "operation", "idempotency_key"), name="ao_command_tenant_op_key_uniq")],
            },
        ),
        migrations.CreateModel(
            name="OrchestrationConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("environment", models.CharField(choices=[("development", "Development"), ("self-hosted", "Self-hosted"), ("saas", "SaaS")], max_length=24)),
                ("cohort", models.CharField(default="all", max_length=64)),
                ("version", models.PositiveIntegerField(default=1)),
                ("document", models.JSONField(default=dict)),
                ("enabled", models.BooleanField(default=True)),
                ("rollout_percentage", models.PositiveSmallIntegerField(default=100)),
                ("allowed_roles", models.JSONField(blank=True, default=list)),
                ("updated_by", models.UUIDField()),
                ("correlation_id", models.CharField(max_length=64)),
            ],
            options={
                "db_table": "automation_orchestration_configurations",
                "indexes": [models.Index(fields=["tenant_id", "environment", "cohort"], name="ao_config_tenant_scope_idx"), models.Index(fields=["tenant_id", "updated_at"], name="ao_config_tenant_updated_idx")],
                "constraints": [models.UniqueConstraint(fields=("tenant_id", "environment", "cohort"), name="ao_config_tenant_scope_uniq"), models.CheckConstraint(condition=models.Q(rollout_percentage__gte=0, rollout_percentage__lte=100), name="ao_config_rollout_0_100"), models.CheckConstraint(condition=models.Q(version__gte=1), name="ao_config_version_gte_1")],
            },
        ),
        migrations.CreateModel(
            name="OrchestrationConfigurationAudit",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version", models.PositiveIntegerField()),
                ("action", models.CharField(max_length=24)),
                ("actor_id", models.UUIDField()),
                ("correlation_id", models.CharField(max_length=64)),
                ("before", models.JSONField(blank=True, null=True)),
                ("after", models.JSONField()),
                ("changed_at", models.DateTimeField(auto_now_add=True)),
                ("configuration", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="audits", to="automation_orchestration.orchestrationconfiguration")),
            ],
            options={"db_table": "automation_orchestration_configuration_audits", "ordering": ("-changed_at", "-version"), "indexes": [models.Index(fields=["tenant_id", "configuration", "version"], name="ao_cfgaudit_tenant_cfg_idx"), models.Index(fields=["tenant_id", "correlation_id"], name="ao_cfgaudit_tenant_corr_idx")]},
        ),
        migrations.CreateModel(
            name="OrchestrationConfigurationVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version", models.PositiveIntegerField()),
                ("document", models.JSONField()),
                ("enabled", models.BooleanField()),
                ("rollout_percentage", models.PositiveSmallIntegerField()),
                ("allowed_roles", models.JSONField(blank=True, default=list)),
                ("actor_id", models.UUIDField()),
                ("correlation_id", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("configuration", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="versions", to="automation_orchestration.orchestrationconfiguration")),
                ("parent_version", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="children", to="automation_orchestration.orchestrationconfigurationversion")),
                ("rollback_of", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="rollbacks", to="automation_orchestration.orchestrationconfigurationversion")),
            ],
            options={"db_table": "automation_orchestration_configuration_versions", "ordering": ("-version",), "indexes": [models.Index(fields=["tenant_id", "configuration", "version"], name="ao_cfgver_tenant_config_idx"), models.Index(fields=["tenant_id", "created_at"], name="ao_cfgver_tenant_created_idx")], "constraints": [models.UniqueConstraint(fields=("configuration", "version"), name="ao_config_version_uniq"), models.CheckConstraint(condition=models.Q(version__gte=1), name="ao_config_ver_version_gte_1")]},
        ),
        migrations.CreateModel(
            name="OrchestrationReconciliation",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("provider_key", models.CharField(max_length=150)),
                ("status", models.CharField(choices=[("required", "Required"), ("reconciling", "Reconciling"), ("compensated", "Compensated"), ("confirmed", "Confirmed")], default="required", max_length=20)),
                ("evidence", models.JSONField(default=dict)),
                ("resolution", models.JSONField(blank=True, null=True)),
                ("requested_by", models.UUIDField(blank=True, null=True)),
                ("resolved_by", models.UUIDField(blank=True, null=True)),
                ("correlation_id", models.CharField(max_length=64)),
                ("attempt", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="reconciliation", to="automation_orchestration.retryattempt")),
            ],
            options={"db_table": "automation_orchestration_reconciliations", "indexes": [models.Index(fields=["tenant_id", "status", "created_at"], name="ao_recon_tenant_status_idx")]},
        ),
        migrations.RunPython(retire_legacy_table, restore_legacy_table),
        migrations.RunPython(enable_rls, disable_rls),
    ]
