"""Expand the legacy budget slice into the complete governed domain."""

import uuid
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("budget_management", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="budget",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="budget",
            name="budget_code",
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name="budget",
            name="fiscal_year",
            field=models.PositiveSmallIntegerField(),
        ),
        migrations.AlterField(model_name="budget", name="start_date", field=models.DateField()),
        migrations.AlterField(model_name="budget", name="end_date", field=models.DateField()),
        migrations.AlterField(
            model_name="budget",
            name="status",
            field=models.CharField(default="draft", max_length=24),
        ),
        migrations.AddField(
            model_name="budget",
            name="budget_type",
            field=models.CharField(max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="budget",
            name="department_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="budget",
            name="project_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="budget",
            name="budget_ceiling",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True),
        ),
        migrations.AddField(
            model_name="budget",
            name="submitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="budget",
            name="submitted_by",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="budget",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="budget",
            name="approved_by",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="budget",
            name="rejected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="budget",
            name="rejected_by",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="budget",
            name="rejection_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="budget",
            name="created_by",
            field=models.UUIDField(null=True),
        ),
        migrations.AddField(
            model_name="budget",
            name="updated_by",
            field=models.UUIDField(null=True),
        ),
        migrations.AddField(
            model_name="budget",
            name="is_deleted",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="budget",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="budget",
            name="deleted_by",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="budgetline",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="budgetline",
            name="account_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="budgetline",
            name="budget",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="lines",
                to="budget_management.budget",
            ),
        ),
        migrations.AlterField(
            model_name="budgetline",
            name="budget_amount",
            field=models.DecimalField(decimal_places=2, max_digits=15),
        ),
        migrations.AddField(
            model_name="budgetline",
            name="account_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="budgetline",
            name="period_type",
            field=models.CharField(max_length=12, null=True),
        ),
        migrations.AddField(
            model_name="budgetline",
            name="period_number",
            field=models.PositiveSmallIntegerField(null=True),
        ),
        migrations.AddField(
            model_name="budgetline",
            name="committed_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=15),
        ),
        migrations.AddField(
            model_name="budgetline",
            name="actuals_as_of",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="budgetline",
            name="source",
            field=models.CharField(default="manual", max_length=16),
        ),
        migrations.AddField(
            model_name="budgetline",
            name="created_by",
            field=models.UUIDField(null=True),
        ),
        migrations.AddField(
            model_name="budgetline",
            name="updated_by",
            field=models.UUIDField(null=True),
        ),
        migrations.AddField(
            model_name="budgetline",
            name="is_deleted",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="budgetline",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="budgetline",
            name="deleted_by",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="BudgetApproval",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("workflow_request_id", models.UUIDField(blank=True, null=True)),
                ("approver_id", models.UUIDField(db_index=True)),
                ("approval_level", models.PositiveSmallIntegerField()),
                ("status", models.CharField(default="pending", max_length=16)),
                ("decision_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("rejection_reason", models.TextField(blank=True)),
                ("created_by", models.UUIDField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "budget",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="approvals",
                        to="budget_management.budget",
                    ),
                ),
            ],
            options={"db_table": "budget_approvals"},
        ),
        migrations.CreateModel(
            name="BudgetTransition",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("transition_key", models.CharField(max_length=255)),
                ("command", models.CharField(max_length=32)),
                ("from_state", models.CharField(max_length=24)),
                ("to_state", models.CharField(max_length=24)),
                ("actor_id", models.UUIDField()),
                ("notes", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
                (
                    "budget",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transitions",
                        to="budget_management.budget",
                    ),
                ),
            ],
            options={"db_table": "budget_transitions"},
        ),
        migrations.CreateModel(
            name="BudgetApprovalDecision",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("actor_id", models.UUIDField(db_index=True)),
                ("status", models.CharField(max_length=16)),
                ("idempotency_key", models.CharField(max_length=255)),
                ("notes", models.TextField(blank=True)),
                ("rejection_reason", models.TextField(blank=True)),
                ("decided_at", models.DateTimeField(auto_now_add=True)),
                (
                    "approval",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="decisions",
                        to="budget_management.budgetapproval",
                    ),
                ),
                (
                    "budget",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="approval_decisions",
                        to="budget_management.budget",
                    ),
                ),
            ],
            options={"db_table": "budget_approval_decisions"},
        ),
        migrations.CreateModel(
            name="VarianceAlert",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("alert_type", models.CharField(max_length=24)),
                ("threshold_percentage", models.DecimalField(decimal_places=2, max_digits=7)),
                ("variance_percentage", models.DecimalField(blank=True, decimal_places=2, max_digits=9, null=True)),
                ("budget_amount", models.DecimalField(decimal_places=2, max_digits=15)),
                ("actual_amount", models.DecimalField(decimal_places=2, max_digits=15)),
                ("committed_amount", models.DecimalField(decimal_places=2, max_digits=15)),
                ("alert_date", models.DateField()),
                ("notification_status", models.CharField(default="pending", max_length=16)),
                ("notification_job_id", models.UUIDField(blank=True, null=True)),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                ("acknowledged_by", models.UUIDField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "budget",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="variance_alerts",
                        to="budget_management.budget",
                    ),
                ),
                (
                    "budget_line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="variance_alerts",
                        to="budget_management.budgetline",
                    ),
                ),
            ],
            options={"db_table": "budget_variance_alerts"},
        ),
        migrations.CreateModel(
            name="BudgetCommitment",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("source_id", models.UUIDField()),
                ("idempotency_key", models.CharField(max_length=255)),
                ("operation", models.CharField(max_length=12)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=15)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "budget_line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="commitment_events",
                        to="budget_management.budgetline",
                    ),
                ),
            ],
            options={"db_table": "budget_commitments"},
        ),
    ]
