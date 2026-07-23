from __future__ import annotations

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


TENANT_TABLES = (
    "workflow_automation_configurations",
    "workflow_automation_configuration_revisions",
    "workflow_transition_audits",
)


def install_configuration_rls(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in TENANT_TABLES:
        policy_name = f"tenant_isolation_{table_name}"
        schema_editor.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name};")
        schema_editor.execute(
            f"CREATE POLICY {policy_name} ON {table_name} "
            "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
            "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);"
        )


def remove_configuration_rls(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in reversed(TENANT_TABLES):
        policy_name = f"tenant_isolation_{table_name}"
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name};")
        schema_editor.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("workflow_automation", "0006_remove_unsafe_legacy_contract"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkflowAutomationConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("environment", models.CharField(default="production", max_length=32)),
                ("version", models.PositiveIntegerField(default=1)),
                ("document", models.JSONField(default=dict)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="updated_workflow_automation_configurations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"db_table": "workflow_automation_configurations"},
        ),
        migrations.CreateModel(
            name="WorkflowAutomationConfigurationRevision",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version", models.PositiveIntegerField()),
                ("previous_document", models.JSONField(blank=True, default=dict)),
                ("document", models.JSONField(default=dict)),
                ("correlation_id", models.CharField(db_index=True, max_length=64)),
                ("change_reason", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="workflow_automation_configuration_revisions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "configuration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="revisions",
                        to="workflow_automation.workflowautomationconfiguration",
                    ),
                ),
            ],
            options={"db_table": "workflow_automation_configuration_revisions", "ordering": ("-version",)},
        ),
        migrations.CreateModel(
            name="WorkflowTransitionAudit",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("transition_key", models.CharField(max_length=255)),
                ("command", models.CharField(max_length=64)),
                ("from_state", models.CharField(max_length=32)),
                ("to_state", models.CharField(max_length=32)),
                ("actor_id", models.CharField(blank=True, max_length=128, null=True)),
                ("correlation_id", models.CharField(db_index=True, max_length=64)),
                ("occurred_at", models.DateTimeField()),
                (
                    "workflow",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transition_audits",
                        to="workflow_automation.workflow",
                    ),
                ),
            ],
            options={"db_table": "workflow_transition_audits"},
        ),
        migrations.AddConstraint(
            model_name="workflowautomationconfiguration",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "environment"), name="wf_config_tenant_environment_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="workflowautomationconfiguration",
            constraint=models.CheckConstraint(condition=models.Q(("version__gte", 1)), name="wf_config_version_gte_1"),
        ),
        migrations.AddIndex(
            model_name="workflowautomationconfiguration",
            index=models.Index(fields=["tenant_id", "environment"], name="wf_config_tenant_env_idx"),
        ),
        migrations.AddIndex(
            model_name="workflowautomationconfiguration",
            index=models.Index(fields=["tenant_id", "-version"], name="wf_config_tenant_ver_idx"),
        ),
        migrations.AddConstraint(
            model_name="workflowautomationconfigurationrevision",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "configuration", "version"), name="wf_config_revision_version_uniq"
            ),
        ),
        migrations.AddIndex(
            model_name="workflowautomationconfigurationrevision",
            index=models.Index(
                fields=["tenant_id", "configuration", "-version"], name="wf_config_rev_tenant_ver_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="workflowautomationconfigurationrevision",
            index=models.Index(fields=["tenant_id", "correlation_id"], name="wf_config_rev_tenant_corr_idx"),
        ),
        migrations.AddConstraint(
            model_name="workflowtransitionaudit",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "workflow", "transition_key", "command"),
                name="wf_transition_audit_idempotency_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="workflowtransitionaudit",
            index=models.Index(fields=["tenant_id", "workflow", "-occurred_at"], name="wf_trans_audit_tenant_idx"),
        ),
        migrations.AlterField(
            model_name="workflow",
            name="version",
            field=models.PositiveIntegerField(),
        ),
        migrations.AlterField(
            model_name="workflow",
            name="workflow_type",
            field=models.CharField(
                choices=[
                    ("approval", "Approval"),
                    ("state_machine", "State machine"),
                    ("sequential", "Sequential"),
                    ("parallel", "Parallel"),
                    ("conditional", "Conditional"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="workflow",
            name="trigger_type",
            field=models.CharField(
                choices=[("manual", "Manual"), ("event", "Event"), ("scheduled", "Scheduled")],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="workflow",
            name="status",
            field=models.CharField(
                choices=[("draft", "Draft"), ("published", "Published"), ("archived", "Archived")],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="workflowinstance",
            name="priority",
            field=models.PositiveSmallIntegerField(),
        ),
        migrations.AlterField(
            model_name="workflowstepexecution",
            name="attempt",
            field=models.PositiveSmallIntegerField(),
        ),
        migrations.RunPython(install_configuration_rls, remove_configuration_rls),
    ]
