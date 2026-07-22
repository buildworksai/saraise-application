"""Contract the HR schema with v2 fields, constraints, and access indexes."""

from decimal import Decimal

from django.db import migrations, models
from django.db.models import F, Q
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [("human_resources", "0002_expand_and_backfill")]

    operations = [
        migrations.RemoveConstraint(
            model_name="department",
            name="unique_department_code_per_tenant",
        ),
        migrations.RemoveConstraint(
            model_name="employee",
            name="unique_employee_number_per_tenant",
        ),
        migrations.RemoveConstraint(
            model_name="attendance",
            name="unique_attendance_per_employee_date",
        ),
        migrations.RemoveIndex(
            model_name="department",
            name="hr_departme_tenant__2a661d_idx",
        ),
        migrations.RemoveIndex(
            model_name="employee",
            name="hr_employee_tenant__849266_idx",
        ),
        migrations.RemoveIndex(
            model_name="employee",
            name="hr_employee_tenant__cd4845_idx",
        ),
        migrations.RemoveIndex(
            model_name="employee",
            name="hr_employee_tenant__b2d6bf_idx",
        ),
        migrations.RemoveIndex(
            model_name="attendance",
            name="hr_attendan_tenant__a7937d_idx",
        ),
        migrations.RemoveIndex(
            model_name="attendance",
            name="hr_attendan_tenant__861621_idx",
        ),
        migrations.RemoveIndex(
            model_name="leaverequest",
            name="hr_leave_re_tenant__c39fb6_idx",
        ),
        migrations.RemoveIndex(
            model_name="leaverequest",
            name="hr_leave_re_tenant__a9a147_idx",
        ),
        migrations.AlterField(
            model_name="department",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="department",
            name="department_code",
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name="department",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="employee",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="employee",
            name="employee_number",
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name="employee",
            name="email",
            field=models.EmailField(max_length=255),
        ),
        migrations.AlterField(
            model_name="employee",
            name="hire_date",
            field=models.DateField(),
        ),
        migrations.AlterField(
            model_name="employee",
            name="phone",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AlterField(
            model_name="employee",
            name="position",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AlterField(
            model_name="employee",
            name="employment_type",
            field=models.CharField(
                choices=[
                    ("full_time", "Full time"),
                    ("part_time", "Part time"),
                    ("contractor", "Contractor"),
                    ("temporary", "Temporary"),
                ],
                default="full_time",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="employee",
            name="is_active",
            field=models.BooleanField(default=True, editable=False),
        ),
        migrations.AlterField(
            model_name="attendance",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="attendance",
            name="attendance_date",
            field=models.DateField(),
        ),
        migrations.AlterField(
            model_name="attendance",
            name="status",
            field=models.CharField(
                choices=[
                    ("present", "Present"),
                    ("absent", "Absent"),
                    ("late", "Late"),
                    ("half_day", "Half day"),
                    ("on_leave", "On leave"),
                ],
                default="present",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="leaverequest",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="leaverequest",
            name="approved_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AlterField(
            model_name="leaverequest",
            name="leave_type",
            field=models.CharField(
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
        migrations.AlterField(
            model_name="leaverequest",
            name="start_date",
            field=models.DateField(),
        ),
        migrations.AlterField(
            model_name="leaverequest",
            name="end_date",
            field=models.DateField(),
        ),
        migrations.AlterField(
            model_name="leaverequest",
            name="days_requested",
            field=models.DecimalField(decimal_places=2, max_digits=7),
        ),
        migrations.AlterField(
            model_name="leaverequest",
            name="reason",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="leaverequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                editable=False,
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="department",
            constraint=models.UniqueConstraint(
                condition=Q(deleted_at__isnull=True),
                fields=("tenant_id", "department_code"),
                name="hr_dept_live_code_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="department",
            constraint=models.CheckConstraint(
                condition=Q(parent_department__isnull=True) | ~Q(parent_department=F("id")),
                name="hr_dept_not_self_parent_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="employee",
            constraint=models.UniqueConstraint(
                condition=Q(deleted_at__isnull=True),
                fields=("tenant_id", "employee_number"),
                name="hr_emp_live_number_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="employee",
            constraint=models.UniqueConstraint(
                Lower("email"),
                F("tenant_id"),
                condition=Q(deleted_at__isnull=True),
                name="hr_emp_live_email_ci_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="employee",
            constraint=models.CheckConstraint(
                condition=Q(manager__isnull=True) | ~Q(manager=F("id")),
                name="hr_emp_not_self_manager_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="employee",
            constraint=models.CheckConstraint(
                condition=(Q(employment_status="terminated", termination_date__isnull=False))
                | (~Q(employment_status="terminated") & Q(termination_date__isnull=True)),
                name="hr_emp_termination_state_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="employee",
            constraint=models.CheckConstraint(
                condition=Q(termination_date__isnull=True) | Q(termination_date__gte=F("hire_date")),
                name="hr_emp_termination_date_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="employee",
            constraint=models.CheckConstraint(
                condition=(Q(employment_status__in=("active", "on_leave"), is_active=True))
                | Q(employment_status__in=("inactive", "terminated"), is_active=False),
                name="hr_emp_active_sync_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="attendance",
            constraint=models.UniqueConstraint(
                condition=Q(deleted_at__isnull=True),
                fields=("tenant_id", "employee", "attendance_date"),
                name="hr_att_live_employee_date_uq",
            ),
        ),
        migrations.AddConstraint(
            model_name="attendance",
            constraint=models.CheckConstraint(
                condition=Q(hours_worked__gte=0) & Q(hours_worked__lte=24),
                name="hr_att_hours_range_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="attendance",
            constraint=models.CheckConstraint(
                condition=Q(check_in_time__isnull=True)
                | Q(check_out_time__isnull=True)
                | Q(check_out_time__gt=F("check_in_time")),
                name="hr_att_clock_order_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="attendance",
            constraint=models.CheckConstraint(
                condition=~Q(status__in=("absent", "on_leave"))
                | (Q(hours_worked=Decimal("0")) & Q(check_in_time__isnull=True) & Q(check_out_time__isnull=True)),
                name="hr_att_nonwork_zero_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="attendance",
            constraint=models.CheckConstraint(
                condition=~Q(source="clock") | Q(check_in_time__isnull=False),
                name="hr_att_clock_has_in_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="leavebalance",
            constraint=models.UniqueConstraint(
                condition=Q(deleted_at__isnull=True),
                fields=("tenant_id", "employee", "leave_type", "period_start", "period_end"),
                name="hr_bal_live_period_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="leavebalance",
            constraint=models.CheckConstraint(
                condition=Q(period_end__gte=F("period_start")),
                name="hr_bal_period_order_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="leavebalance",
            constraint=models.CheckConstraint(
                condition=Q(entitled_days__gte=0)
                & Q(carried_days__gte=0)
                & Q(used_days__gte=0)
                & Q(pending_days__gte=0),
                name="hr_bal_amounts_nonneg_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="leavebalance",
            constraint=models.CheckConstraint(
                condition=Q(used_days__lte=F("entitled_days") + F("carried_days") - F("pending_days")),
                name="hr_bal_capacity_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="leaverequest",
            constraint=models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")),
                name="hr_req_date_order_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="leaverequest",
            constraint=models.CheckConstraint(
                condition=Q(days_requested__gt=0),
                name="hr_req_days_positive_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="leaverequest",
            constraint=models.CheckConstraint(
                condition=~Q(status="approved") | (Q(approved_by__gt="") & Q(approved_at__isnull=False)),
                name="hr_req_approved_meta_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="leaverequest",
            constraint=models.CheckConstraint(
                condition=~Q(status="rejected") | Q(rejection_reason__gt=""),
                name="hr_req_rejected_meta_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="leaverequest",
            constraint=models.CheckConstraint(
                condition=~Q(status="cancelled") | (Q(cancelled_by__gt="") & Q(cancelled_at__isnull=False)),
                name="hr_req_cancelled_meta_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="department",
            index=models.Index(fields=("tenant_id", "department_code"), name="hr_dept_t_code_idx"),
        ),
        migrations.AddIndex(
            model_name="department",
            index=models.Index(fields=("tenant_id", "department_name"), name="hr_dept_t_name_idx"),
        ),
        migrations.AddIndex(
            model_name="department",
            index=models.Index(fields=("tenant_id", "parent_department"), name="hr_dept_t_parent_idx"),
        ),
        migrations.AddIndex(
            model_name="department",
            index=models.Index(fields=("tenant_id", "manager"), name="hr_dept_t_manager_idx"),
        ),
        migrations.AddIndex(
            model_name="department",
            index=models.Index(
                fields=("tenant_id", "is_active", "deleted_at"),
                name="hr_dept_t_active_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="employee",
            index=models.Index(fields=("tenant_id", "employee_number"), name="hr_emp_t_number_idx"),
        ),
        migrations.AddIndex(
            model_name="employee",
            index=models.Index(fields=("tenant_id", "email"), name="hr_emp_t_email_idx"),
        ),
        migrations.AddIndex(
            model_name="employee",
            index=models.Index(
                fields=("tenant_id", "department", "employment_status"),
                name="hr_emp_t_dept_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="employee",
            index=models.Index(
                fields=("tenant_id", "manager", "employment_status"),
                name="hr_emp_t_mgr_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="employee",
            index=models.Index(fields=("tenant_id", "hire_date"), name="hr_emp_t_hire_idx"),
        ),
        migrations.AddIndex(
            model_name="employee",
            index=models.Index(
                fields=("tenant_id", "employment_status", "deleted_at"),
                name="hr_emp_t_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="attendance",
            index=models.Index(
                fields=("tenant_id", "employee", "attendance_date"),
                name="hr_att_t_emp_date_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="attendance",
            index=models.Index(
                fields=("tenant_id", "attendance_date", "status"),
                name="hr_att_t_date_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="attendance",
            index=models.Index(
                fields=("tenant_id", "status", "deleted_at"),
                name="hr_att_t_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="leavebalance",
            index=models.Index(
                fields=("tenant_id", "employee", "leave_type", "period_start"),
                name="hr_bal_t_emp_type_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="leavebalance",
            index=models.Index(fields=("tenant_id", "period_end"), name="hr_bal_t_end_idx"),
        ),
        migrations.AddIndex(
            model_name="leavebalance",
            index=models.Index(
                fields=("tenant_id", "leave_type", "deleted_at"),
                name="hr_bal_t_type_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="leaverequest",
            index=models.Index(
                fields=("tenant_id", "employee", "start_date"),
                name="hr_req_t_emp_start_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="leaverequest",
            index=models.Index(
                fields=("tenant_id", "employee", "status"),
                name="hr_req_t_emp_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="leaverequest",
            index=models.Index(
                fields=("tenant_id", "status", "start_date"),
                name="hr_req_t_status_start_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="leaverequest",
            index=models.Index(
                fields=("tenant_id", "leave_type", "start_date", "end_date"),
                name="hr_req_t_type_dates_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="leaverequest",
            index=models.Index(fields=("tenant_id", "created_at"), name="hr_req_t_created_idx"),
        ),
    ]
