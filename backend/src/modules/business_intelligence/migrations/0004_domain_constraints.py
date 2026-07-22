"""Finalize BI lifecycle fields, indexes, and database invariants."""

from django.db import migrations, models
from django.db.models import Q


TENANT_FOREIGN_KEYS = (
    ("bi_reports", "query_definition_id", "bi_query_definitions", "bi_report_query_tenant_fk"),
    ("bi_dashboard_widgets", "dashboard_id", "bi_dashboards", "bi_widget_dashboard_tenant_fk"),
    ("bi_dashboard_widgets", "query_definition_id", "bi_query_definitions", "bi_widget_query_tenant_fk"),
    ("bi_dashboard_widgets", "report_id", "bi_reports", "bi_widget_report_tenant_fk"),
    ("bi_dashboard_shares", "dashboard_id", "bi_dashboards", "bi_share_dashboard_tenant_fk"),
    ("bi_query_executions", "query_definition_id", "bi_query_definitions", "bi_exec_query_tenant_fk"),
    ("bi_query_executions", "report_id", "bi_reports", "bi_exec_report_tenant_fk"),
    ("bi_query_executions", "dashboard_id", "bi_dashboards", "bi_exec_dashboard_tenant_fk"),
    ("bi_query_executions", "async_job_id", "async_jobs", "bi_exec_job_tenant_fk"),
)


def add_tenant_relationship_constraints(apps, schema_editor):
    """Make tenant equality part of every relationship at the PostgreSQL boundary."""

    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            'ALTER TABLE "async_jobs" ADD CONSTRAINT "asyncjob_tenant_id_uniq" UNIQUE ("tenant_id", "id")'
        )
        for child_table, child_column, parent_table, constraint_name in TENANT_FOREIGN_KEYS:
            cursor.execute(
                f'ALTER TABLE "{child_table}" ADD CONSTRAINT "{constraint_name}" '
                f'FOREIGN KEY ("tenant_id", "{child_column}") '
                f'REFERENCES "{parent_table}" ("tenant_id", "id")'
            )


def remove_tenant_relationship_constraints(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for child_table, _child_column, _parent_table, constraint_name in reversed(TENANT_FOREIGN_KEYS):
            cursor.execute(f'ALTER TABLE "{child_table}" DROP CONSTRAINT IF EXISTS "{constraint_name}"')
        cursor.execute('ALTER TABLE "async_jobs" DROP CONSTRAINT IF EXISTS "asyncjob_tenant_id_uniq"')


class Migration(migrations.Migration):
    dependencies = [("business_intelligence", "0003_migrate_legacy_definitions")]

    operations = [
        migrations.RemoveField(model_name="report", name="is_active"),
        migrations.RemoveField(model_name="dashboard", name="is_active"),
        migrations.AlterModelOptions(name="querydefinition", options={"ordering": ("name", "id")}),
        migrations.AlterModelOptions(name="report", options={"ordering": ("report_name", "id")}),
        migrations.AlterModelOptions(name="dashboard", options={"ordering": ("dashboard_name", "id")}),
        migrations.AlterModelOptions(name="dashboardwidget", options={"ordering": ("display_order", "id")}),
        migrations.AlterModelOptions(name="dashboardshare", options={"ordering": ("-created_at", "id")}),
        migrations.AlterModelOptions(name="queryexecution", options={"ordering": ("-created_at", "id")}),
        migrations.AlterField(model_name="report", name="created_at", field=models.DateTimeField(auto_now_add=True)),
        migrations.AlterField(model_name="dashboard", name="created_at", field=models.DateTimeField(auto_now_add=True)),
        migrations.AlterField(
            model_name="report",
            name="state",
            field=models.CharField(choices=[("draft", "Draft"), ("published", "Published"), ("archived", "Archived")], default="draft", max_length=16),
        ),
        migrations.AlterField(
            model_name="dashboard",
            name="state",
            field=models.CharField(choices=[("draft", "Draft"), ("published", "Published"), ("archived", "Archived")], default="draft", max_length=16),
        ),
        migrations.AlterField(
            model_name="dashboardwidget",
            name="widget_type",
            field=models.CharField(choices=[("kpi", "KPI"), ("table", "Table"), ("bar", "Bar"), ("line", "Line"), ("area", "Area"), ("pie", "Pie"), ("funnel", "Funnel")], max_length=16),
        ),
        migrations.AlterField(
            model_name="dashboardshare",
            name="subject_type",
            field=models.CharField(choices=[("user", "User"), ("role", "Role")], max_length=16),
        ),
        migrations.AlterField(
            model_name="dashboardshare",
            name="access_level",
            field=models.CharField(choices=[("view", "View"), ("edit", "Edit")], max_length=8),
        ),
        migrations.AlterField(
            model_name="queryexecution",
            name="status",
            field=models.CharField(choices=[("queued", "Queued"), ("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("cancelled", "Cancelled"), ("timed_out", "Timed out")], default="queued", max_length=16),
        ),
        migrations.AddConstraint(model_name="querydefinition", constraint=models.UniqueConstraint(fields=("tenant_id", "id"), name="bi_query_tenant_id_uniq")),
        migrations.AddConstraint(model_name="querydefinition", constraint=models.UniqueConstraint(fields=("tenant_id", "query_code"), condition=Q(deleted_at__isnull=True), name="bi_query_live_code_uniq")),
        migrations.AddConstraint(model_name="querydefinition", constraint=models.CheckConstraint(condition=Q(row_limit__gte=1) & Q(row_limit__lte=10000), name="bi_query_row_limit_ck")),
        migrations.AddConstraint(model_name="querydefinition", constraint=models.CheckConstraint(condition=Q(cache_ttl_seconds__gte=0) & Q(cache_ttl_seconds__lte=86400), name="bi_query_cache_ttl_ck")),
        migrations.AddIndex(model_name="querydefinition", index=models.Index(fields=("tenant_id", "state", "updated_at"), name="bi_query_tenant_state_idx")),
        migrations.AddIndex(model_name="querydefinition", index=models.Index(fields=("tenant_id", "dataset_key", "state"), name="bi_query_tenant_data_idx")),
        migrations.AddIndex(model_name="querydefinition", index=models.Index(fields=("tenant_id", "deleted_at", "query_code"), name="bi_query_tenant_del_idx")),
        migrations.AddConstraint(model_name="report", constraint=models.UniqueConstraint(fields=("tenant_id", "id"), name="bi_report_tenant_id_uniq")),
        migrations.AddConstraint(model_name="report", constraint=models.UniqueConstraint(fields=("tenant_id", "report_code"), condition=Q(deleted_at__isnull=True), name="bi_report_live_code_uniq")),
        migrations.AddConstraint(model_name="report", constraint=models.CheckConstraint(condition=~Q(state="published") | (Q(query_definition__isnull=False) & Q(legacy_query="")), name="bi_report_published_query_ck")),
        migrations.AddIndex(model_name="report", index=models.Index(fields=("tenant_id", "report_type", "state"), name="bi_report_tenant_type_idx")),
        migrations.AddIndex(model_name="report", index=models.Index(fields=("tenant_id", "query_definition"), name="bi_report_tenant_query_idx")),
        migrations.AddIndex(model_name="report", index=models.Index(fields=("tenant_id", "updated_at"), name="bi_report_tenant_upd_idx")),
        migrations.AddConstraint(model_name="dashboard", constraint=models.UniqueConstraint(fields=("tenant_id", "id"), name="bi_dash_tenant_id_uniq")),
        migrations.AddConstraint(model_name="dashboard", constraint=models.UniqueConstraint(fields=("tenant_id", "dashboard_code"), condition=Q(deleted_at__isnull=True), name="bi_dash_live_code_uniq")),
        migrations.AddConstraint(model_name="dashboard", constraint=models.CheckConstraint(condition=Q(refresh_interval_seconds__isnull=True) | (Q(refresh_interval_seconds__gte=30) & Q(refresh_interval_seconds__lte=86400)), name="bi_dash_refresh_ck")),
        migrations.AddIndex(model_name="dashboard", index=models.Index(fields=("tenant_id", "state", "updated_at"), name="bi_dash_tenant_state_idx")),
        migrations.AddIndex(model_name="dashboard", index=models.Index(fields=("tenant_id", "deleted_at", "dashboard_code"), name="bi_dash_tenant_del_idx")),
        migrations.AddConstraint(model_name="dashboardwidget", constraint=models.CheckConstraint(condition=(Q(query_definition__isnull=False) & Q(report__isnull=True)) | (Q(query_definition__isnull=True) & Q(report__isnull=False)), name="bi_widget_source_xor_ck")),
        migrations.AddConstraint(model_name="dashboardwidget", constraint=models.CheckConstraint(condition=Q(width__gte=1) & Q(width__lte=12), name="bi_widget_width_ck")),
        migrations.AddConstraint(model_name="dashboardwidget", constraint=models.CheckConstraint(condition=Q(height__gte=1) & Q(height__lte=24), name="bi_widget_height_ck")),
        migrations.AddConstraint(model_name="dashboardwidget", constraint=models.CheckConstraint(condition=Q(refresh_interval_seconds__isnull=True) | (Q(refresh_interval_seconds__gte=30) & Q(refresh_interval_seconds__lte=86400)), name="bi_widget_refresh_ck")),
        migrations.AddConstraint(model_name="dashboardwidget", constraint=models.CheckConstraint(condition=Q(x__gte=0), name="bi_widget_x_ck")),
        migrations.AddConstraint(model_name="dashboardwidget", constraint=models.CheckConstraint(condition=Q(y__gte=0), name="bi_widget_y_ck")),
        migrations.AddConstraint(model_name="dashboardwidget", constraint=models.UniqueConstraint(fields=("tenant_id", "dashboard", "display_order"), condition=Q(deleted_at__isnull=True), name="bi_widget_live_order_uniq")),
        migrations.AddIndex(model_name="dashboardwidget", index=models.Index(fields=("tenant_id", "dashboard", "display_order"), name="bi_widget_tenant_dash_idx")),
        migrations.AddIndex(model_name="dashboardwidget", index=models.Index(fields=("tenant_id", "query_definition"), name="bi_widget_tenant_query_idx")),
        migrations.AddIndex(model_name="dashboardwidget", index=models.Index(fields=("tenant_id", "report"), name="bi_widget_tenant_report_idx")),
        migrations.AddConstraint(model_name="dashboardshare", constraint=models.UniqueConstraint(fields=("tenant_id", "dashboard", "subject_type", "subject_id"), condition=Q(revoked_at__isnull=True), name="bi_share_active_subject_uniq")),
        migrations.AddConstraint(model_name="dashboardshare", constraint=models.CheckConstraint(condition=Q(expires_at__isnull=True) | Q(expires_at__gt=models.F("created_at")), name="bi_share_expiry_ck")),
        migrations.AddIndex(model_name="dashboardshare", index=models.Index(fields=("tenant_id", "subject_type", "subject_id", "revoked_at"), name="bi_share_tenant_subj_idx")),
        migrations.AddIndex(model_name="dashboardshare", index=models.Index(fields=("tenant_id", "dashboard", "revoked_at"), name="bi_share_tenant_dash_idx")),
        migrations.AddConstraint(model_name="queryexecution", constraint=models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="bi_execution_tenant_idem_uniq")),
        migrations.AddConstraint(model_name="queryexecution", constraint=models.CheckConstraint(condition=~Q(status="failed") | Q(result_rows=[]), name="bi_execution_failed_empty_ck")),
        migrations.AddConstraint(model_name="queryexecution", constraint=models.CheckConstraint(condition=~Q(status="succeeded") | Q(row_count__isnull=False), name="bi_execution_success_count_ck")),
        migrations.AddIndex(model_name="queryexecution", index=models.Index(fields=("tenant_id", "status", "created_at"), name="bi_exec_tenant_status_idx")),
        migrations.AddIndex(model_name="queryexecution", index=models.Index(fields=("tenant_id", "query_definition", "created_at"), name="bi_exec_tenant_query_idx")),
        migrations.AddIndex(model_name="queryexecution", index=models.Index(fields=("tenant_id", "report", "created_at"), name="bi_exec_tenant_report_idx")),
        migrations.AddIndex(model_name="queryexecution", index=models.Index(fields=("tenant_id", "dashboard", "created_at"), name="bi_exec_tenant_dash_idx")),
        migrations.RunPython(add_tenant_relationship_constraints, remove_tenant_relationship_constraints),
    ]
