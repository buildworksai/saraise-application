"""Add the v2 workflow contract without assuming legacy rows are clean."""

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workflow_automation", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="workflow",
            name="key",
            field=models.CharField(max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="workflow",
            name="version",
            field=models.PositiveIntegerField(null=True),
        ),
        migrations.AddField(
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
                default="sequential",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="workflow",
            name="trigger_config",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="workflow",
            name="required_context_schema",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="workflow",
            name="transition_history",
            field=models.JSONField(blank=True, default=list, editable=False),
        ),
        migrations.AddField(
            model_name="workflow",
            name="published_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="published_workflows",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="workflow",
            name="published_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workflow",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workflow",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workflowstep",
            name="tenant_id",
            field=models.UUIDField(db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="workflowstep",
            name="key",
            field=models.CharField(max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="workflowstep",
            name="next_step_keys",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="workflowstep",
            name="join_key",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="workflowstep",
            name="handler_contract_version",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="workflowstep",
            name="handler_contract_fingerprint",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="workflowstep",
            name="timeout_seconds",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workflowstep",
            name="timeout_action",
            field=models.CharField(
                blank=True,
                choices=[("fail", "Fail"), ("notify", "Notify"), ("escalate", "Escalate"), ("cancel", "Cancel")],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="workflowstep",
            name="is_terminal",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="workflowstep",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name="workflowstep",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AddField(
            model_name="workflowinstance",
            name="workflow_version",
            field=models.PositiveIntegerField(null=True),
        ),
        migrations.AddField(
            model_name="workflowinstance",
            name="active_step_keys",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="workflowinstance",
            name="result_data",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="workflowinstance",
            name="entity_type",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="workflowinstance",
            name="entity_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workflowinstance",
            name="priority",
            field=models.PositiveSmallIntegerField(default=5),
        ),
        migrations.AddField(
            model_name="workflowinstance",
            name="idempotency_key",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="workflowinstance",
            name="transition_history",
            field=models.JSONField(blank=True, default=list, editable=False),
        ),
        migrations.AddField(
            model_name="workflowinstance",
            name="correlation_id",
            field=models.CharField(db_index=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="workflowinstance",
            name="async_job_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workflowinstance",
            name="failure_code",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="workflowinstance",
            name="failure_message",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="workflowinstance",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name="workflowinstance",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AddField(
            model_name="workflowtask",
            name="assignment_kind",
            field=models.CharField(
                choices=[("user", "User"), ("role", "Role")],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="workflowtask",
            name="assignment_key",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="workflowtask",
            name="completed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="completed_workflow_tasks",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="workflowtask",
            name="transition_history",
            field=models.JSONField(blank=True, default=list, editable=False),
        ),
        migrations.AddField(
            model_name="workflowtask",
            name="correlation_id",
            field=models.CharField(db_index=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="workflowtask",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.CreateModel(
            name="WorkflowStepExecution",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("attempt", models.PositiveSmallIntegerField(default=1)),
                ("operation_key", models.CharField(max_length=255)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("handler_key", models.CharField(max_length=150)),
                ("handler_contract_version", models.CharField(max_length=128)),
                ("handler_contract_fingerprint", models.CharField(max_length=64)),
                ("input_fingerprint", models.CharField(max_length=64)),
                ("output_evidence", models.JSONField(blank=True, default=dict)),
                ("provider_evidence", models.JSONField(blank=True, default=dict)),
                ("correlation_id", models.CharField(db_index=True, max_length=64)),
                ("async_job_id", models.UUIDField(blank=True, null=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("duration_ms", models.PositiveBigIntegerField(blank=True, null=True)),
                ("failure_code", models.CharField(blank=True, default="", max_length=64)),
                ("failure_message", models.TextField(blank=True, default="")),
                (
                    "instance",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="step_executions",
                        to="workflow_automation.workflowinstance",
                    ),
                ),
                (
                    "step",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="executions",
                        to="workflow_automation.workflowstep",
                    ),
                ),
            ],
            options={
                "db_table": "workflow_step_executions",
                "ordering": ("created_at", "attempt"),
            },
        ),
    ]
