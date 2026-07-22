"""Expand the legacy BI schema without discarding existing definitions."""

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("async_jobs", "0001_initial"),
        ("business_intelligence", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(model_name="report", old_name="query", new_name="legacy_query"),
        migrations.RenameField(model_name="report", old_name="parameters", new_name="default_parameters"),
        migrations.RenameField(model_name="dashboard", old_name="layout", new_name="legacy_layout"),
        migrations.RemoveConstraint(model_name="report", name="unique_report_code_per_tenant"),
        migrations.RemoveConstraint(model_name="dashboard", name="unique_dashboard_code_per_tenant"),
        migrations.RemoveIndex(model_name="report", name="bi_reports_tenant__7c4ef1_idx"),
        migrations.RemoveIndex(model_name="report", name="bi_reports_tenant__2183dc_idx"),
        migrations.RemoveIndex(model_name="dashboard", name="bi_dashboar_tenant__9b0f84_idx"),
        migrations.AlterField(model_name="report", name="report_code", field=models.CharField(max_length=64)),
        migrations.AlterField(
            model_name="report",
            name="report_type",
            field=models.CharField(
                choices=[("table", "Table"), ("pivot", "Pivot"), ("chart", "Chart"), ("kpi", "KPI")],
                max_length=16,
            ),
        ),
        migrations.AlterField(model_name="report", name="legacy_query", field=models.TextField(blank=True)),
        migrations.AlterField(model_name="report", name="default_parameters", field=models.JSONField(default=dict)),
        migrations.AlterField(model_name="dashboard", name="dashboard_code", field=models.CharField(max_length=64)),
        migrations.AlterField(
            model_name="dashboard", name="legacy_layout", field=models.JSONField(blank=True, null=True)
        ),
        migrations.CreateModel(
            name="QueryDefinition",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("query_code", models.CharField(max_length=64)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("dataset_key", models.CharField(db_index=True, max_length=160)),
                ("dataset_version", models.CharField(blank=True, max_length=64)),
                ("dataset_schema_fingerprint", models.CharField(blank=True, max_length=64)),
                ("dimensions", models.JSONField(default=list)),
                ("measures", models.JSONField(default=list)),
                ("filters", models.JSONField(default=list)),
                ("grouping", models.JSONField(default=list)),
                ("ordering", models.JSONField(default=list)),
                ("parameters_schema", models.JSONField(default=dict)),
                ("row_limit", models.PositiveIntegerField(default=500)),
                ("cache_ttl_seconds", models.PositiveIntegerField(default=300)),
                (
                    "state",
                    models.CharField(
                        choices=[("draft", "Draft"), ("published", "Published"), ("archived", "Archived")],
                        default="draft",
                        max_length=16,
                    ),
                ),
                ("transition_history", models.JSONField(default=list)),
                ("version", models.PositiveIntegerField(default=1)),
                ("created_by_id", models.CharField(max_length=255)),
                ("updated_by_id", models.CharField(max_length=255)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"db_table": "bi_query_definitions", "ordering": ("name", "id")},
        ),
        migrations.AddField(model_name="report", name="description", field=models.TextField(blank=True)),
        migrations.AddField(model_name="report", name="visualization", field=models.JSONField(default=dict)),
        migrations.AddField(model_name="report", name="state", field=models.CharField(default="draft", max_length=16)),
        migrations.AddField(model_name="report", name="transition_history", field=models.JSONField(default=list)),
        migrations.AddField(model_name="report", name="version", field=models.PositiveIntegerField(default=1)),
        migrations.AddField(
            model_name="report",
            name="created_by_id",
            field=models.CharField(default="migration", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="report",
            name="updated_by_id",
            field=models.CharField(default="migration", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(model_name="report", name="deleted_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(
            model_name="report",
            name="query_definition",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reports",
                to="business_intelligence.querydefinition",
            ),
        ),
        migrations.AddField(model_name="dashboard", name="description", field=models.TextField(blank=True)),
        migrations.AddField(model_name="dashboard", name="global_filters", field=models.JSONField(default=list)),
        migrations.AddField(
            model_name="dashboard",
            name="refresh_interval_seconds",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="dashboard", name="state", field=models.CharField(default="draft", max_length=16)
        ),
        migrations.AddField(model_name="dashboard", name="transition_history", field=models.JSONField(default=list)),
        migrations.AddField(model_name="dashboard", name="version", field=models.PositiveIntegerField(default=1)),
        migrations.AddField(
            model_name="dashboard",
            name="created_by_id",
            field=models.CharField(default="migration", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="dashboard",
            name="updated_by_id",
            field=models.CharField(default="migration", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="dashboard", name="deleted_at", field=models.DateTimeField(blank=True, null=True)
        ),
        migrations.CreateModel(
            name="DashboardWidget",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("widget_type", models.CharField(max_length=16)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("x", models.PositiveIntegerField(default=0)),
                ("y", models.PositiveIntegerField(default=0)),
                ("width", models.PositiveIntegerField(default=4)),
                ("height", models.PositiveIntegerField(default=4)),
                ("visualization", models.JSONField(default=dict)),
                ("filters", models.JSONField(default=list)),
                ("refresh_interval_seconds", models.PositiveIntegerField(blank=True, null=True)),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("version", models.PositiveIntegerField(default=1)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "dashboard",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="widgets",
                        to="business_intelligence.dashboard",
                    ),
                ),
                (
                    "query_definition",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="widgets",
                        to="business_intelligence.querydefinition",
                    ),
                ),
                (
                    "report",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="widgets",
                        to="business_intelligence.report",
                    ),
                ),
            ],
            options={"db_table": "bi_dashboard_widgets", "ordering": ("display_order", "id")},
        ),
        migrations.CreateModel(
            name="DashboardShare",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("subject_type", models.CharField(max_length=16)),
                ("subject_id", models.CharField(max_length=255)),
                ("access_level", models.CharField(max_length=8)),
                ("shared_by_id", models.CharField(max_length=255)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "dashboard",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shares",
                        to="business_intelligence.dashboard",
                    ),
                ),
            ],
            options={"db_table": "bi_dashboard_shares", "ordering": ("-created_at", "id")},
        ),
        migrations.CreateModel(
            name="QueryExecution",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("actor_id", models.CharField(max_length=255)),
                ("idempotency_key", models.CharField(max_length=255)),
                ("definition_version", models.PositiveIntegerField()),
                ("dataset_key", models.CharField(max_length=160)),
                ("dataset_version", models.CharField(blank=True, max_length=64)),
                ("dataset_schema_fingerprint", models.CharField(blank=True, max_length=64)),
                ("effective_query_fingerprint", models.CharField(blank=True, max_length=64)),
                ("freshness_token", models.CharField(blank=True, max_length=255)),
                ("data_as_of", models.DateTimeField(blank=True, null=True)),
                ("result_purged_at", models.DateTimeField(blank=True, null=True)),
                ("parameters", models.JSONField(default=dict)),
                ("status", models.CharField(default="queued", max_length=16)),
                ("transition_history", models.JSONField(default=list)),
                ("result_columns", models.JSONField(default=list)),
                ("result_rows", models.JSONField(default=list)),
                ("row_count", models.PositiveIntegerField(blank=True, null=True)),
                ("truncated", models.BooleanField(default=False)),
                ("cache_hit", models.BooleanField(default=False)),
                ("duration_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("error_code", models.CharField(blank=True, max_length=64)),
                ("error_message", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "async_job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="bi_executions",
                        to="async_jobs.asyncjob",
                        unique=True,
                    ),
                ),
                (
                    "dashboard",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="executions",
                        to="business_intelligence.dashboard",
                    ),
                ),
                (
                    "query_definition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="executions",
                        to="business_intelligence.querydefinition",
                    ),
                ),
                (
                    "report",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="executions",
                        to="business_intelligence.report",
                    ),
                ),
            ],
            options={"db_table": "bi_query_executions", "ordering": ("-created_at", "id")},
        ),
    ]
