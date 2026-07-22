"""Enforce final budget-domain choices, constraints, and query indexes."""

from django.db import migrations, models
from django.db.models import F, Q
from django.db.models.functions import Lower


BUDGET_TYPES = [
    ("operating", "Operating"),
    ("capital", "Capital"),
    ("project", "Project"),
    ("departmental", "Departmental"),
]
BUDGET_STATUSES = [
    ("draft", "Draft"),
    ("pending_approval", "Pending approval"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
    ("revision", "Revision"),
    ("closed", "Closed"),
]
PERIOD_TYPES = [("annual", "Annual"), ("monthly", "Monthly"), ("quarterly", "Quarterly")]
LINE_SOURCES = [("manual", "Manual"), ("accounting_sync", "Accounting sync")]
APPROVAL_STATUSES = [
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
    ("cancelled", "Cancelled"),
]
ALERT_TYPES = [
    ("over_budget", "Over budget"),
    ("approaching_limit", "Approaching limit"),
    ("underspend", "Underspend"),
]
NOTIFICATION_STATUSES = [
    ("pending", "Pending"),
    ("sent", "Sent"),
    ("failed", "Failed"),
    ("unavailable", "Unavailable"),
]


class Migration(migrations.Migration):
    dependencies = [("budget_management", "0003_backfill_budget_domain")]

    operations = [
        migrations.RemoveConstraint(
            model_name="budget",
            name="unique_budget_code_per_tenant",
        ),
        migrations.RemoveIndex(model_name="budget", name="budget_budg_tenant__81cbbe_idx"),
        migrations.RemoveIndex(model_name="budget", name="budget_budg_tenant__ac1f01_idx"),
        migrations.RemoveIndex(model_name="budget", name="budget_budg_tenant__4c8967_idx"),
        migrations.RemoveIndex(model_name="budgetline", name="budget_line_tenant__a760da_idx"),
        migrations.RemoveIndex(model_name="budgetline", name="budget_line_tenant__6f3be3_idx"),
        migrations.AlterField(
            model_name="budget",
            name="budget_type",
            field=models.CharField(choices=BUDGET_TYPES, default="operating", max_length=20),
        ),
        migrations.AlterField(model_name="budget", name="created_by", field=models.UUIDField()),
        migrations.AlterField(model_name="budget", name="updated_by", field=models.UUIDField()),
        migrations.AlterField(
            model_name="budget",
            name="status",
            field=models.CharField(choices=BUDGET_STATUSES, default="draft", max_length=24),
        ),
        migrations.AlterField(
            model_name="budgetline",
            name="created_by",
            field=models.UUIDField(),
        ),
        migrations.AlterField(
            model_name="budgetline",
            name="updated_by",
            field=models.UUIDField(),
        ),
        migrations.AlterField(
            model_name="budgetline",
            name="period_type",
            field=models.CharField(choices=PERIOD_TYPES, default="annual", max_length=12),
        ),
        migrations.AlterField(
            model_name="budgetline",
            name="period_number",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AlterField(
            model_name="budgetline",
            name="source",
            field=models.CharField(choices=LINE_SOURCES, default="manual", max_length=16),
        ),
        migrations.AlterField(
            model_name="budgetapproval",
            name="status",
            field=models.CharField(choices=APPROVAL_STATUSES, default="pending", max_length=16),
        ),
        migrations.AlterField(
            model_name="variancealert",
            name="alert_type",
            field=models.CharField(choices=ALERT_TYPES, max_length=24),
        ),
        migrations.AlterField(
            model_name="variancealert",
            name="notification_status",
            field=models.CharField(choices=NOTIFICATION_STATUSES, default="pending", max_length=16),
        ),
        migrations.AlterField(
            model_name="budgetcommitment",
            name="operation",
            field=models.CharField(choices=[("record", "Record"), ("release", "Release")], max_length=12),
        ),
        migrations.AlterField(
            model_name="budgetapprovaldecision",
            name="status",
            field=models.CharField(
                choices=[("approved", "Approved"), ("rejected", "Rejected"), ("cancelled", "Cancelled")],
                max_length=16,
            ),
        ),
        migrations.AddConstraint(
            model_name="budget",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "budget_code"),
                condition=Q(is_deleted=False),
                name="budget_tenant_code_live_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="budget",
            constraint=models.UniqueConstraint(
                F("tenant_id"),
                F("fiscal_year"),
                Lower("budget_name"),
                condition=Q(is_deleted=False),
                name="budget_tenant_year_name_live_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="budget",
            constraint=models.CheckConstraint(condition=Q(start_date__lte=F("end_date")), name="budget_date_order_ck"),
        ),
        migrations.AddConstraint(
            model_name="budget",
            constraint=models.CheckConstraint(
                condition=Q(budget_type__in=["operating", "capital", "project", "departmental"]),
                name="budget_type_valid_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="budget",
            constraint=models.CheckConstraint(
                condition=Q(status__in=["draft", "pending_approval", "approved", "rejected", "revision", "closed"]),
                name="budget_status_valid_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="budget",
            constraint=models.CheckConstraint(condition=Q(total_budget__gte=0), name="budget_total_nonnegative_ck"),
        ),
        migrations.AddConstraint(
            model_name="budget",
            constraint=models.CheckConstraint(
                condition=Q(budget_ceiling__isnull=True) | Q(budget_ceiling__gte=0),
                name="budget_ceiling_nonnegative_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="budget",
            constraint=models.CheckConstraint(
                condition=~Q(budget_type="departmental") | Q(department_id__isnull=False),
                name="budget_department_required_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="budget",
            constraint=models.CheckConstraint(
                condition=~Q(budget_type="project") | Q(project_id__isnull=False),
                name="budget_project_required_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="budget",
            constraint=models.CheckConstraint(
                condition=(
                    Q(status__in=["approved", "closed"], approved_at__isnull=False, approved_by__isnull=False)
                    | Q(
                        ~Q(status__in=["approved", "closed"]),
                        approved_at__isnull=True,
                        approved_by__isnull=True,
                    )
                ),
                name="budget_approval_metadata_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="budget",
            constraint=models.CheckConstraint(
                condition=(
                    ~Q(status="rejected")
                    | (Q(rejected_at__isnull=False, rejected_by__isnull=False) & ~Q(rejection_reason=""))
                ),
                name="budget_rejection_metadata_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="budget",
            constraint=models.CheckConstraint(
                condition=(
                    Q(is_deleted=False, deleted_at__isnull=True, deleted_by__isnull=True)
                    | Q(is_deleted=True, deleted_at__isnull=False, deleted_by__isnull=False)
                ),
                name="budget_soft_delete_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="budget",
            index=models.Index(fields=["tenant_id", "fiscal_year", "status"], name="budget_tenant_year_status_idx"),
        ),
        migrations.AddIndex(
            model_name="budget",
            index=models.Index(fields=["tenant_id", "budget_type", "fiscal_year"], name="budget_tenant_type_year_idx"),
        ),
        migrations.AddIndex(
            model_name="budget",
            index=models.Index(fields=["tenant_id", "start_date", "end_date"], name="budget_tenant_dates_idx"),
        ),
        migrations.AddIndex(
            model_name="budget",
            index=models.Index(fields=["tenant_id", "department_id", "fiscal_year"], name="budget_tenant_dept_year_idx"),
        ),
        migrations.AddIndex(
            model_name="budget",
            index=models.Index(fields=["tenant_id", "project_id", "fiscal_year"], name="budget_tenant_proj_year_idx"),
        ),
        migrations.AddIndex(
            model_name="budget",
            index=models.Index(fields=["tenant_id", "is_deleted", "updated_at"], name="budget_tenant_deleted_upd_idx"),
        ),
        migrations.AddConstraint(
            model_name="budgetline",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "budget", "account_code", "period_type", "period_number"),
                condition=Q(is_deleted=False),
                name="budget_line_allocation_live_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetline",
            constraint=models.CheckConstraint(
                condition=Q(budget_amount__gte=0) & Q(committed_amount__gte=0) & Q(actual_amount__gte=0),
                name="budget_line_amounts_nonnegative_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetline",
            constraint=models.CheckConstraint(
                condition=(
                    Q(period_type="annual", period_number=1)
                    | Q(period_type="monthly", period_number__gte=1, period_number__lte=12)
                    | Q(period_type="quarterly", period_number__gte=1, period_number__lte=4)
                ),
                name="budget_line_period_number_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetline",
            constraint=models.CheckConstraint(
                condition=Q(period_type__in=["annual", "monthly", "quarterly"]),
                name="budget_line_period_type_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetline",
            constraint=models.CheckConstraint(
                condition=Q(source__in=["manual", "accounting_sync"]),
                name="budget_line_source_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetline",
            constraint=models.CheckConstraint(
                condition=(
                    Q(is_deleted=False, deleted_at__isnull=True, deleted_by__isnull=True)
                    | Q(is_deleted=True, deleted_at__isnull=False, deleted_by__isnull=False)
                ),
                name="budget_line_soft_delete_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="budgetline",
            index=models.Index(fields=["tenant_id", "budget", "is_deleted"], name="bud_line_tenant_budget_idx"),
        ),
        migrations.AddIndex(
            model_name="budgetline",
            index=models.Index(
                fields=["tenant_id", "account_code", "period_type", "period_number"],
                name="bud_line_tenant_acct_per_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="budgetline",
            index=models.Index(fields=["tenant_id", "account_id"], name="budget_line_tenant_acct_id_idx"),
        ),
        migrations.AddIndex(
            model_name="budgetline",
            index=models.Index(fields=["tenant_id", "actuals_as_of"], name="budget_line_tenant_actuals_idx"),
        ),
        migrations.AddConstraint(
            model_name="budgetapproval",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "budget", "approval_level", "approver_id"),
                name="budget_approval_assignment_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetapproval",
            constraint=models.CheckConstraint(condition=Q(approval_level__gte=1), name="budget_approval_level_ck"),
        ),
        migrations.AddConstraint(
            model_name="budgetapproval",
            constraint=models.CheckConstraint(
                condition=Q(status__in=["pending", "approved", "rejected", "cancelled"]),
                name="budget_approval_status_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetapproval",
            constraint=models.CheckConstraint(
                condition=(
                    ~Q(status__in=["approved", "rejected"])
                    | Q(decision_at__isnull=False)
                ),
                name="budget_approval_decision_at_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetapproval",
            constraint=models.CheckConstraint(
                condition=~Q(status="rejected") | ~Q(rejection_reason=""),
                name="budget_approval_rejection_reason_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="budgetapproval",
            index=models.Index(
                fields=["tenant_id", "status", "approval_level", "created_at"],
                name="bud_appr_tenant_status_lvl_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="budgetapproval",
            index=models.Index(fields=["tenant_id", "approver_id", "status"], name="budget_appr_tenant_actor_idx"),
        ),
        migrations.AddIndex(
            model_name="budgetapproval",
            index=models.Index(fields=["tenant_id", "budget", "approval_level"], name="budget_appr_tenant_budget_idx"),
        ),
        migrations.AddConstraint(
            model_name="budgetapprovaldecision",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "approval"),
                name="budget_approval_one_decision_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetapprovaldecision",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "budget", "idempotency_key"),
                name="budget_approval_decision_key_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetapprovaldecision",
            constraint=models.CheckConstraint(
                condition=Q(status__in=["approved", "rejected", "cancelled"]),
                name="budget_approval_decision_status_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetapprovaldecision",
            constraint=models.CheckConstraint(
                condition=~Q(status="rejected") | ~Q(rejection_reason=""),
                name="budget_approval_decision_reason_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="budgetapprovaldecision",
            index=models.Index(
                fields=["tenant_id", "budget", "decided_at"],
                name="bud_appr_dec_tenant_budget_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="budgetapprovaldecision",
            index=models.Index(
                fields=["tenant_id", "actor_id", "decided_at"],
                name="bud_appr_dec_tenant_actor_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgettransition",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "budget", "transition_key"),
                name="budget_transition_key_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="budgettransition",
            index=models.Index(fields=["tenant_id", "budget", "occurred_at"], name="budget_trans_tenant_budget_idx"),
        ),
        migrations.AddConstraint(
            model_name="budgetcommitment",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "budget_line", "source_id", "idempotency_key"),
                name="budget_commitment_idempotency_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetcommitment",
            constraint=models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="budget_commitment_amount_positive_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="budgetcommitment",
            constraint=models.CheckConstraint(
                condition=Q(operation__in=["record", "release"]),
                name="budget_commitment_operation_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="budgetcommitment",
            index=models.Index(
                fields=["tenant_id", "budget_line", "created_at"],
                name="budget_commit_tenant_line_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="budgetcommitment",
            index=models.Index(fields=["tenant_id", "source_id"], name="bud_commit_tenant_source_idx"),
        ),
        migrations.AddConstraint(
            model_name="variancealert",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "budget_line", "alert_type", "threshold_percentage", "alert_date"),
                name="budget_alert_dedup_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="variancealert",
            constraint=models.CheckConstraint(
                condition=(
                    Q(threshold_percentage__gte=0)
                    & Q(budget_amount__gte=0)
                    & Q(actual_amount__gte=0)
                    & Q(committed_amount__gte=0)
                ),
                name="budget_alert_amounts_nonnegative_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="variancealert",
            constraint=models.CheckConstraint(
                condition=(
                    Q(acknowledged_at__isnull=True, acknowledged_by__isnull=True)
                    | Q(acknowledged_at__isnull=False, acknowledged_by__isnull=False)
                ),
                name="budget_alert_ack_pair_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="variancealert",
            constraint=models.CheckConstraint(
                condition=Q(alert_type__in=["over_budget", "approaching_limit", "underspend"]),
                name="budget_alert_type_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="variancealert",
            constraint=models.CheckConstraint(
                condition=Q(notification_status__in=["pending", "sent", "failed", "unavailable"]),
                name="budget_alert_notify_status_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="variancealert",
            index=models.Index(fields=["tenant_id", "alert_type", "alert_date"], name="bud_alert_tenant_type_date_idx"),
        ),
        migrations.AddIndex(
            model_name="variancealert",
            index=models.Index(fields=["tenant_id", "budget", "alert_date"], name="budget_alert_tenant_budget_idx"),
        ),
        migrations.AddIndex(
            model_name="variancealert",
            index=models.Index(
                fields=["tenant_id", "notification_status", "created_at"],
                name="budget_alert_tenant_notify_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="variancealert",
            index=models.Index(fields=["tenant_id", "acknowledged_at"], name="budget_alert_tenant_ack_idx"),
        ),
    ]
