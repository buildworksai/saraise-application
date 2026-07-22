"""Expand the v1 HR schema and deterministically backfill legacy rows."""

from __future__ import annotations

import uuid
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


AUDITED_MODELS = ("department", "employee", "attendance", "leaverequest")


def preflight_and_backfill(apps, schema_editor) -> None:
    """Reject ambiguous legacy data rather than inventing HR facts."""

    del schema_editor
    Department = apps.get_model("human_resources", "Department")
    Employee = apps.get_model("human_resources", "Employee")
    Attendance = apps.get_model("human_resources", "Attendance")
    LeaveRequest = apps.get_model("human_resources", "LeaveRequest")

    departments = {row.id: row.tenant_id for row in Department.objects.all()}
    employees = {row.id: row.tenant_id for row in Employee.objects.all()}
    for row in Department.objects.all().iterator():
        if row.parent_department_id and departments.get(row.parent_department_id) != row.tenant_id:
            raise RuntimeError("HR migration preflight: dangling or cross-tenant department parent")
        if row.manager_id and employees.get(row.manager_id) != row.tenant_id:
            raise RuntimeError("HR migration preflight: dangling or cross-tenant department manager")
    for row in Employee.objects.all().iterator():
        if row.department_id and departments.get(row.department_id) != row.tenant_id:
            raise RuntimeError("HR migration preflight: dangling or cross-tenant employee department")
    for model, relation in ((Attendance, "employee_id"), (LeaveRequest, "employee_id")):
        for row in model.objects.all().iterator():
            if employees.get(getattr(row, relation)) != row.tenant_id:
                raise RuntimeError("HR migration preflight: dangling or cross-tenant employee reference")

    # A balance cannot be inferred from a request. Deployments with legacy
    # requests must import explicit allocations before applying this migration.
    if LeaveRequest.objects.exists():
        raise RuntimeError("HR migration requires explicit leave-allocation input for every legacy leave request")

    aliases = {
        "full_time": "full_time",
        "full-time": "full_time",
        "full time": "full_time",
        "permanent": "full_time",
        "part_time": "part_time",
        "part-time": "part_time",
        "part time": "part_time",
        "contract": "contractor",
        "contractor": "contractor",
        "temporary": "temporary",
        "temp": "temporary",
    }
    for employee in Employee.objects.all().iterator():
        legacy_type = str(employee.employment_type or "").strip().lower()
        normalized = aliases.get(legacy_type)
        if normalized is None:
            raise RuntimeError(f"HR migration cannot normalize employment type {legacy_type!r}")
        employee.employment_type = normalized
        employee.employment_status = "active" if employee.is_active else "inactive"
        employee.save(update_fields=("employment_type", "employment_status"))


def reverse_backfill(apps, schema_editor) -> None:
    """Canonical v2 employment values are valid deterministic v1 values."""

    del schema_editor
    Employee = apps.get_model("human_resources", "Employee")
    Employee.objects.filter(employment_status__in=("active", "on_leave")).update(is_active=True)
    Employee.objects.filter(employment_status__in=("inactive", "terminated")).update(is_active=False)


def noop(apps, schema_editor) -> None:
    del apps, schema_editor


def prepare_legacy_approval_actors(apps, schema_editor) -> None:
    """Make mode-neutral v2 actor identifiers compatible with the v1 UUID column."""

    LeaveRequest = apps.get_model("human_resources", "LeaveRequest")
    namespace = uuid.UUID("acfae8b4-7a20-5e2d-9cec-4a3989ee80d2")
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("ALTER TABLE hr_leave_requests ALTER COLUMN approved_by DROP NOT NULL;")
    for request in LeaveRequest.objects.all().iterator():
        value = str(request.approved_by or "").strip()
        if not value:
            request.approved_by = (
                None
                if schema_editor.connection.vendor == "postgresql"
                else str(uuid.uuid5(namespace, "legacy-empty-approval-actor"))
            )
            request.save(update_fields=("approved_by",))
            continue
        try:
            uuid.UUID(value)
        except (ValueError, AttributeError):
            request.approved_by = str(uuid.uuid5(namespace, value))
            request.save(update_fields=("approved_by",))


def audit_fields(model_name: str) -> list[migrations.operations.base.Operation]:
    return [
        migrations.AddField(
            model_name=model_name,
            name="created_by",
            field=models.CharField(default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name=model_name,
            name="updated_by",
            field=models.CharField(default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name=model_name,
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name=model_name,
            name="deleted_by",
            field=models.CharField(blank=True, default="", editable=False, max_length=255),
        ),
    ]


class Migration(migrations.Migration):
    dependencies = [("human_resources", "0001_initial")]

    operations = [
        *[operation for model_name in AUDITED_MODELS for operation in audit_fields(model_name)],
        migrations.AddField(
            model_name="department",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="employee",
            name="employment_status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("on_leave", "On leave"),
                    ("inactive", "Inactive"),
                    ("terminated", "Terminated"),
                ],
                default="active",
                editable=False,
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="manager",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="direct_reports",
                to="human_resources.employee",
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="termination_date",
            field=models.DateField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="employee",
            name="termination_reason",
            field=models.TextField(blank=True, default="", editable=False),
        ),
        migrations.AddField(
            model_name="employee",
            name="transition_history",
            field=models.JSONField(blank=True, default=list, editable=False),
        ),
        migrations.AddField(
            model_name="attendance",
            name="notes",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="attendance",
            name="source",
            field=models.CharField(
                choices=[("manual", "Manual"), ("clock", "Clock"), ("import", "Import")],
                default="manual",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="LeaveBalance",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.CharField(max_length=255)),
                ("updated_by", models.CharField(max_length=255)),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, editable=False, null=True)),
                ("deleted_by", models.CharField(blank=True, default="", editable=False, max_length=255)),
                (
                    "leave_type",
                    models.CharField(
                        choices=[
                            ("annual", "Annual leave"),
                            ("sick", "Sick leave"),
                            ("personal", "Personal leave"),
                            ("maternity", "Maternity leave"),
                            ("paternity", "Paternity leave"),
                            ("unpaid", "Unpaid leave"),
                        ],
                        max_length=20,
                    ),
                ),
                ("period_start", models.DateField()),
                ("period_end", models.DateField()),
                (
                    "entitled_days",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=7),
                ),
                (
                    "carried_days",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=7),
                ),
                (
                    "used_days",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        editable=False,
                        max_digits=7,
                    ),
                ),
                (
                    "pending_days",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        editable=False,
                        max_digits=7,
                    ),
                ),
                ("adjustment_version", models.PositiveIntegerField(default=1, editable=False)),
                (
                    "last_adjusted_by",
                    models.CharField(blank=True, default="", editable=False, max_length=255),
                ),
                ("adjustment_note", models.TextField(blank=True, default="", editable=False)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="leave_balances",
                        to="human_resources.employee",
                    ),
                ),
            ],
            options={"db_table": "hr_leave_balances"},
        ),
        migrations.AddField(
            model_name="leaverequest",
            name="leave_balance",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="requests",
                to="human_resources.leavebalance",
            ),
        ),
        migrations.AddField(
            model_name="leaverequest",
            name="rejection_reason",
            field=models.TextField(blank=True, default="", editable=False),
        ),
        migrations.AddField(
            model_name="leaverequest",
            name="cancelled_by",
            field=models.CharField(blank=True, default="", editable=False, max_length=255),
        ),
        migrations.AddField(
            model_name="leaverequest",
            name="cancelled_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="leaverequest",
            name="transition_history",
            field=models.JSONField(blank=True, default=list, editable=False),
        ),
        migrations.RunPython(preflight_and_backfill, reverse_backfill),
        migrations.RenameField(
            model_name="department",
            old_name="parent_department_id",
            new_name="parent_department",
        ),
        migrations.RenameField(
            model_name="department",
            old_name="manager_id",
            new_name="manager",
        ),
        migrations.AlterField(
            model_name="department",
            name="parent_department",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="children",
                to="human_resources.department",
            ),
        ),
        migrations.AlterField(
            model_name="department",
            name="manager",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="managed_departments",
                to="human_resources.employee",
            ),
        ),
        migrations.AlterField(
            model_name="attendance",
            name="employee",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="attendances",
                to="human_resources.employee",
            ),
        ),
        migrations.AlterField(
            model_name="leaverequest",
            name="employee",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="leave_requests",
                to="human_resources.employee",
            ),
        ),
        migrations.AlterField(
            model_name="leaverequest",
            name="leave_balance",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="requests",
                to="human_resources.leavebalance",
            ),
        ),
        migrations.AlterField(
            model_name="leaverequest",
            name="approved_by",
            field=models.CharField(blank=True, default="", editable=False, max_length=255),
        ),
        # On reverse this executes before varchar is cast back to the legacy
        # UUID column, making arbitrary runtime-mode actor strings reversible.
        migrations.RunPython(noop, prepare_legacy_approval_actors),
    ]
