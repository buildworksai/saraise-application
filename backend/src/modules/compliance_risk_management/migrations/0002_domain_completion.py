"""Complete the compliance-risk domain without replacing legacy risk rows.

Legacy records receive the documented migration principal
``00000000-0000-0000-0000-00000000c0de``.  Their review date is one year after
their original creation date, and conservative square-matrix inputs preserve
the original risk level.  Reversal is lossless for legacy risk rows and is
refused when any new-domain table contains data.
"""

from __future__ import annotations

import datetime as dt
import uuid

import django.db.models.deletion
import src.modules.compliance_risk_management.models
from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations, models
from django.db.models import F, Q

MIGRATION_ACTOR_ID = uuid.UUID("00000000-0000-0000-0000-00000000c0de")
NEW_DOMAIN_MODELS = (
    "Control",
    "ControlTest",
    "ComplianceRequirement",
    "ComplianceCalendarEntry",
    "RemediationAction",
    "RiskConfiguration",
    "RiskConfigurationVersion",
)


def _mutable_fields() -> list[tuple[str, models.Field]]:
    return [
        ("tenant_id", models.UUIDField(db_index=True)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        ("created_by_id", models.UUIDField(db_index=True, editable=False)),
        ("updated_by_id", models.UUIDField(blank=True, db_index=True, editable=False, null=True)),
        ("is_deleted", models.BooleanField(db_index=True, default=False)),
        ("deleted_at", models.DateTimeField(blank=True, editable=False, null=True)),
        ("deleted_by_id", models.UUIDField(blank=True, editable=False, null=True)),
        ("transition_history", models.JSONField(blank=True, default=list, editable=False)),
    ]


def normalize_legacy_risks(apps, schema_editor) -> None:
    del schema_editor
    Risk = apps.get_model("compliance_risk_management", "RiskAssessment")
    seen: set[tuple[uuid.UUID, str]] = set()
    score_map = {
        "low": (1, 1, "1.00"),
        "medium": (2, 2, "4.00"),
        "high": (4, 4, "16.00"),
        "critical": (5, 5, "25.00"),
    }
    status_map = {"open": "identified", "mitigated": "mitigating", "closed": "closed"}
    for risk in Risk.objects.all().iterator():
        normalized_code = risk.risk_code.strip().upper()
        identity = (risk.tenant_id, normalized_code)
        if identity in seen:
            raise RuntimeError("Legacy risk codes collide after required uppercase normalization.")
        seen.add(identity)
        likelihood, impact, score = score_map.get(risk.risk_level, score_map["medium"])
        risk.risk_code = normalized_code
        risk.category = "compliance"
        risk.likelihood = likelihood
        risk.impact = impact
        risk.inherent_score = score
        risk.owner_id = MIGRATION_ACTOR_ID
        risk.created_by_id = MIGRATION_ACTOR_ID
        risk.review_date = risk.created_at.date() + dt.timedelta(days=365)
        risk.status = status_map.get(risk.status, "identified")
        risk.closed_at = risk.updated_at if risk.status == "closed" else None
        risk.save(
            update_fields=[
                "risk_code",
                "category",
                "likelihood",
                "impact",
                "inherent_score",
                "owner_id",
                "created_by_id",
                "review_date",
                "status",
                "closed_at",
            ]
        )


def restore_legacy_risks(apps, schema_editor) -> None:
    del schema_editor
    Risk = apps.get_model("compliance_risk_management", "RiskAssessment")
    reverse_status = {
        "identified": "open",
        "assessed": "open",
        "mitigating": "mitigated",
        "accepted": "open",
        "closed": "closed",
    }
    for risk in Risk.objects.all().iterator():
        risk.status = reverse_status[risk.status]
        risk.save(update_fields=["status"])


def guard_domain_reversal(apps, schema_editor) -> None:
    """Refuse the destructive reverse before any new table is removed."""

    del schema_editor
    populated = [
        name for name in NEW_DOMAIN_MODELS if apps.get_model("compliance_risk_management", name).objects.exists()
    ]
    if populated:
        raise RuntimeError(
            "Cannot reverse compliance-risk domain migration with dependent data: " + ", ".join(populated)
        )


class Migration(migrations.Migration):
    dependencies = [("compliance_risk_management", "0001_initial")]

    operations = [
        migrations.RemoveConstraint(model_name="compliancerisk", name="unique_risk_code_per_tenant"),
        migrations.RemoveIndex(model_name="compliancerisk", name="compliance__tenant__699219_idx"),
        migrations.RemoveIndex(model_name="compliancerisk", name="compliance__tenant__f784df_idx"),
        migrations.RemoveIndex(model_name="compliancerisk", name="compliance__tenant__91b888_idx"),
        migrations.RenameModel(old_name="ComplianceRisk", new_name="RiskAssessment"),
        migrations.RenameField(model_name="riskassessment", old_name="risk_name", new_name="name"),
        migrations.RenameField(model_name="riskassessment", old_name="mitigation_plan", new_name="mitigation_strategy"),
        migrations.AddField(
            model_name="riskassessment",
            name="created_by_id",
            field=models.UUIDField(db_index=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="updated_by_id",
            field=models.UUIDField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="riskassessment", name="is_deleted", field=models.BooleanField(db_index=True, default=False)
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="deleted_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="deleted_by_id",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="transition_history",
            field=models.JSONField(blank=True, default=list, editable=False),
        ),
        migrations.AddField(
            model_name="riskassessment", name="category", field=models.CharField(blank=True, max_length=32, null=True)
        ),
        migrations.AddField(
            model_name="riskassessment", name="likelihood", field=models.PositiveSmallIntegerField(null=True)
        ),
        migrations.AddField(
            model_name="riskassessment", name="impact", field=models.PositiveSmallIntegerField(null=True)
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="inherent_score",
            field=models.DecimalField(decimal_places=2, editable=False, max_digits=7, null=True),
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="residual_likelihood",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="residual_impact",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="residual_score",
            field=models.DecimalField(blank=True, decimal_places=2, editable=False, max_digits=7, null=True),
        ),
        migrations.AddField(
            model_name="riskassessment", name="qualitative_rationale", field=models.TextField(blank=True)
        ),
        migrations.AddField(
            model_name="riskassessment", name="owner_id", field=models.UUIDField(db_index=True, null=True)
        ),
        migrations.AddField(model_name="riskassessment", name="review_date", field=models.DateField(null=True)),
        migrations.AddField(
            model_name="riskassessment",
            name="accepted_until",
            field=models.DateField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="riskassessment",
            name="closed_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(normalize_legacy_risks, restore_legacy_risks),
        migrations.AlterField(
            model_name="riskassessment", name="created_by_id", field=models.UUIDField(db_index=True, editable=False)
        ),
        migrations.AlterField(
            model_name="riskassessment", name="created_at", field=models.DateTimeField(auto_now_add=True)
        ),
        migrations.AlterField(
            model_name="riskassessment",
            name="category",
            field=models.CharField(
                choices=[
                    ("operational", "Operational"),
                    ("financial", "Financial"),
                    ("compliance", "Compliance"),
                    ("strategic", "Strategic"),
                    ("technology", "Technology"),
                    ("reputational", "Reputational"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(model_name="riskassessment", name="description", field=models.TextField()),
        migrations.AlterField(model_name="riskassessment", name="likelihood", field=models.PositiveSmallIntegerField()),
        migrations.AlterField(model_name="riskassessment", name="impact", field=models.PositiveSmallIntegerField()),
        migrations.AlterField(
            model_name="riskassessment",
            name="inherent_score",
            field=models.DecimalField(decimal_places=2, editable=False, max_digits=7),
        ),
        migrations.AlterField(model_name="riskassessment", name="owner_id", field=models.UUIDField(db_index=True)),
        migrations.AlterField(model_name="riskassessment", name="review_date", field=models.DateField()),
        migrations.AlterField(model_name="riskassessment", name="risk_code", field=models.CharField(max_length=50)),
        migrations.AlterField(
            model_name="riskassessment",
            name="risk_level",
            field=models.CharField(
                choices=[
                    ("negligible", "Negligible"),
                    ("low", "Low"),
                    ("medium", "Medium"),
                    ("high", "High"),
                    ("critical", "Critical"),
                ],
                editable=False,
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="riskassessment",
            name="status",
            field=models.CharField(
                choices=[
                    ("identified", "Identified"),
                    ("assessed", "Assessed"),
                    ("mitigating", "Mitigating"),
                    ("accepted", "Accepted"),
                    ("closed", "Closed"),
                ],
                default="identified",
                editable=False,
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="riskassessment",
            index=models.Index(fields=("tenant_id", "status", "review_date"), name="crm_risk_status_review_idx"),
        ),
        migrations.AddIndex(
            model_name="riskassessment",
            index=models.Index(fields=("tenant_id", "risk_level", "status"), name="crm_risk_level_status_idx"),
        ),
        migrations.AddIndex(
            model_name="riskassessment",
            index=models.Index(fields=("tenant_id", "category", "status"), name="crm_risk_category_status_idx"),
        ),
        migrations.AddIndex(
            model_name="riskassessment",
            index=models.Index(fields=("tenant_id", "owner_id", "status"), name="crm_risk_owner_status_idx"),
        ),
        migrations.AddIndex(
            model_name="riskassessment",
            index=models.Index(fields=("tenant_id", "created_at"), name="crm_risk_created_idx"),
        ),
        migrations.AddConstraint(
            model_name="riskassessment",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "risk_code"), condition=Q(is_deleted=False), name="crm_risk_live_code_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="riskassessment",
            constraint=models.CheckConstraint(
                condition=Q(
                    category__in=["operational", "financial", "compliance", "strategic", "technology", "reputational"]
                ),
                name="crm_risk_category_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="riskassessment",
            constraint=models.CheckConstraint(
                condition=Q(risk_level__in=["negligible", "low", "medium", "high", "critical"]),
                name="crm_risk_level_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="riskassessment",
            constraint=models.CheckConstraint(
                condition=Q(status__in=["identified", "assessed", "mitigating", "accepted", "closed"]),
                name="crm_risk_status_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="riskassessment",
            constraint=models.CheckConstraint(
                condition=Q(likelihood__gte=1, impact__gte=1), name="crm_risk_scores_positive_ck"
            ),
        ),
        migrations.AddConstraint(
            model_name="riskassessment",
            constraint=models.CheckConstraint(
                condition=(
                    Q(residual_likelihood__isnull=True, residual_impact__isnull=True, residual_score__isnull=True)
                    | Q(residual_likelihood__isnull=False, residual_impact__isnull=False, residual_score__isnull=False)
                ),
                name="crm_risk_residual_pair_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="riskassessment",
            constraint=models.CheckConstraint(
                condition=Q(residual_score__isnull=True)
                | Q(residual_score__lte=F("inherent_score"))
                | ~Q(qualitative_rationale=""),
                name="crm_risk_residual_override_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="riskassessment",
            constraint=models.CheckConstraint(
                condition=(
                    Q(status="accepted", accepted_until__isnull=False, closed_at__isnull=True)
                    | Q(status="closed", accepted_until__isnull=True, closed_at__isnull=False)
                    | Q(
                        status__in=["identified", "assessed", "mitigating"],
                        accepted_until__isnull=True,
                        closed_at__isnull=True,
                    )
                ),
                name="crm_risk_lifecycle_fields_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="riskassessment",
            constraint=models.CheckConstraint(
                condition=(
                    Q(is_deleted=False, deleted_at__isnull=True, deleted_by_id__isnull=True)
                    | Q(is_deleted=True, deleted_at__isnull=False, deleted_by_id__isnull=False)
                ),
                name="crm_risk_soft_delete_ck",
            ),
        ),
        migrations.CreateModel(
            name="ComplianceRequirement",
            fields=_mutable_fields()
            + [
                ("regulation_code", models.CharField(max_length=50)),
                ("requirement_code", models.CharField(max_length=80)),
                ("regulation_name", models.CharField(max_length=255)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField()),
                (
                    "applicability",
                    models.CharField(
                        choices=[
                            ("mandatory", "Mandatory"),
                            ("conditional", "Conditional"),
                            ("recommended", "Recommended"),
                        ],
                        max_length=20,
                    ),
                ),
                ("applicability_rationale", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("not_assessed", "Not assessed"),
                            ("compliant", "Compliant"),
                            ("partially_compliant", "Partially compliant"),
                            ("non_compliant", "Non-compliant"),
                        ],
                        default="not_assessed",
                        editable=False,
                        max_length=24,
                    ),
                ),
                ("owner_id", models.UUIDField(db_index=True)),
                ("effective_date", models.DateField(blank=True, null=True)),
                ("due_date", models.DateField(blank=True, null=True)),
                ("last_assessed_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("source_url", models.URLField(blank=True, max_length=2048)),
                ("cross_references", models.JSONField(blank=True, default=list, encoder=DjangoJSONEncoder)),
            ],
            options={
                "db_table": "compliance_risk_requirements",
                "indexes": [
                    models.Index(fields=("tenant_id", "status", "due_date"), name="crm_req_status_due_idx"),
                    models.Index(fields=("tenant_id", "regulation_code", "applicability"), name="crm_req_reg_app_idx"),
                    models.Index(fields=("tenant_id", "owner_id", "status"), name="crm_req_owner_status_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "regulation_code", "requirement_code"),
                        condition=Q(is_deleted=False),
                        name="crm_req_live_code_uniq",
                    ),
                    models.CheckConstraint(
                        condition=Q(applicability__in=["mandatory", "conditional", "recommended"]),
                        name="crm_req_applicability_ck",
                    ),
                    models.CheckConstraint(
                        condition=Q(status__in=["not_assessed", "compliant", "partially_compliant", "non_compliant"]),
                        name="crm_req_status_ck",
                    ),
                    models.CheckConstraint(
                        condition=~Q(applicability="conditional") | ~Q(applicability_rationale=""),
                        name="crm_req_conditional_reason_ck",
                    ),
                    models.CheckConstraint(
                        condition=Q(effective_date__isnull=True)
                        | Q(due_date__isnull=True)
                        | Q(due_date__gte=F("effective_date")),
                        name="crm_req_date_order_ck",
                    ),
                    models.CheckConstraint(
                        condition=(
                            Q(is_deleted=False, deleted_at__isnull=True, deleted_by_id__isnull=True)
                            | Q(is_deleted=True, deleted_at__isnull=False, deleted_by_id__isnull=False)
                        ),
                        name="crm_req_soft_delete_ck",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Control",
            fields=_mutable_fields()
            + [
                ("control_code", models.CharField(max_length=50)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField()),
                ("test_procedure", models.TextField()),
                (
                    "frequency",
                    models.CharField(
                        choices=[
                            ("daily", "Daily"),
                            ("weekly", "Weekly"),
                            ("monthly", "Monthly"),
                            ("quarterly", "Quarterly"),
                            ("annually", "Annually"),
                            ("custom", "Custom"),
                        ],
                        max_length=20,
                    ),
                ),
                ("frequency_days", models.PositiveIntegerField(blank=True, null=True)),
                ("owner_id", models.UUIDField(db_index=True)),
                ("default_tester_id", models.UUIDField(blank=True, db_index=True, null=True)),
                ("next_test_due", models.DateField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("active", "Active"), ("retired", "Retired")],
                        default="draft",
                        editable=False,
                        max_length=20,
                    ),
                ),
                (
                    "risk",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="controls",
                        to="compliance_risk_management.riskassessment",
                    ),
                ),
            ],
            options={
                "db_table": "compliance_risk_controls",
                "indexes": [
                    models.Index(fields=("tenant_id", "risk", "status"), name="crm_control_risk_status_idx"),
                    models.Index(fields=("tenant_id", "status", "next_test_due"), name="crm_control_status_due_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "control_code"),
                        condition=Q(is_deleted=False),
                        name="crm_control_live_code_uniq",
                    ),
                    models.CheckConstraint(
                        condition=Q(frequency__in=["daily", "weekly", "monthly", "quarterly", "annually", "custom"]),
                        name="crm_control_frequency_ck",
                    ),
                    models.CheckConstraint(
                        condition=Q(status__in=["draft", "active", "retired"]), name="crm_control_status_ck"
                    ),
                    models.CheckConstraint(
                        condition=(
                            Q(frequency="custom", frequency_days__gte=1, frequency_days__lte=3660)
                            | (~Q(frequency="custom") & Q(frequency_days__isnull=True))
                        ),
                        name="crm_control_frequency_days_ck",
                    ),
                    models.CheckConstraint(
                        condition=~Q(status="active") | Q(next_test_due__isnull=False), name="crm_control_active_due_ck"
                    ),
                    models.CheckConstraint(
                        condition=(
                            Q(is_deleted=False, deleted_at__isnull=True, deleted_by_id__isnull=True)
                            | Q(is_deleted=True, deleted_at__isnull=False, deleted_by_id__isnull=False)
                        ),
                        name="crm_control_soft_delete_ck",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ControlTest",
            fields=_mutable_fields()
            + [
                ("scheduled_for", models.DateField()),
                ("started_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("completed_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("tester_id", models.UUIDField(db_index=True)),
                (
                    "result",
                    models.CharField(
                        choices=[
                            ("not_tested", "Not tested"),
                            ("passed", "Passed"),
                            ("failed", "Failed"),
                            ("partially_passed", "Partially passed"),
                        ],
                        default="not_tested",
                        editable=False,
                        max_length=24,
                    ),
                ),
                ("findings", models.TextField(blank=True)),
                ("evidence", models.JSONField(blank=True, default=list, encoder=DjangoJSONEncoder)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("scheduled", "Scheduled"),
                            ("in_progress", "In progress"),
                            ("completed", "Completed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="scheduled",
                        editable=False,
                        max_length=20,
                    ),
                ),
                ("cancellation_reason", models.TextField(blank=True)),
                (
                    "control",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="tests",
                        to="compliance_risk_management.control",
                    ),
                ),
            ],
            options={
                "db_table": "compliance_risk_control_tests",
                "indexes": [
                    models.Index(fields=("tenant_id", "status", "scheduled_for"), name="crm_test_status_schedule_idx"),
                    models.Index(fields=("tenant_id", "control", "completed_at"), name="crm_test_control_done_idx"),
                    models.Index(fields=("tenant_id", "tester_id", "status"), name="crm_test_tester_status_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "control", "scheduled_for"), name="crm_test_control_schedule_uniq"
                    ),
                    models.CheckConstraint(
                        condition=Q(result__in=["not_tested", "passed", "failed", "partially_passed"]),
                        name="crm_test_result_ck",
                    ),
                    models.CheckConstraint(
                        condition=Q(status__in=["scheduled", "in_progress", "completed", "cancelled"]),
                        name="crm_test_status_ck",
                    ),
                    models.CheckConstraint(
                        condition=(
                            Q(
                                status="scheduled",
                                started_at__isnull=True,
                                completed_at__isnull=True,
                                result="not_tested",
                                cancellation_reason="",
                            )
                            | Q(
                                status="in_progress",
                                started_at__isnull=False,
                                completed_at__isnull=True,
                                result="not_tested",
                                cancellation_reason="",
                            )
                            | (
                                Q(
                                    status="completed",
                                    started_at__isnull=False,
                                    completed_at__isnull=False,
                                    cancellation_reason="",
                                )
                                & ~Q(result="not_tested")
                            )
                            | (
                                Q(status="cancelled", completed_at__isnull=False, result="not_tested")
                                & ~Q(cancellation_reason="")
                            )
                        ),
                        name="crm_test_lifecycle_ck",
                    ),
                    models.CheckConstraint(
                        condition=~Q(result__in=["failed", "partially_passed"]) | ~Q(findings=""),
                        name="crm_test_findings_ck",
                    ),
                    models.CheckConstraint(
                        condition=(
                            Q(is_deleted=False, deleted_at__isnull=True, deleted_by_id__isnull=True)
                            | Q(is_deleted=True, deleted_at__isnull=False, deleted_by_id__isnull=False)
                        ),
                        name="crm_test_soft_delete_ck",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ComplianceCalendarEntry",
            fields=_mutable_fields()
            + [
                ("title", models.CharField(max_length=255)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("deadline", "Deadline"),
                            ("review", "Review"),
                            ("submission", "Submission"),
                            ("audit", "Audit"),
                            ("renewal", "Renewal"),
                        ],
                        max_length=20,
                    ),
                ),
                ("scheduled_date", models.DateField()),
                ("reminder_days", models.JSONField(blank=True, default=list)),
                ("assigned_to_id", models.UUIDField(db_index=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("upcoming", "Upcoming"),
                            ("overdue", "Overdue"),
                            ("completed", "Completed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="upcoming",
                        editable=False,
                        max_length=20,
                    ),
                ),
                ("completed_date", models.DateField(blank=True, editable=False, null=True)),
                ("completion_notes", models.TextField(blank=True)),
                (
                    "requirement",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="calendar_entries",
                        to="compliance_risk_management.compliancerequirement",
                    ),
                ),
            ],
            options={
                "db_table": "compliance_risk_calendar_entries",
                "indexes": [
                    models.Index(fields=("tenant_id", "status", "scheduled_date"), name="crm_calendar_status_date_idx"),
                    models.Index(fields=("tenant_id", "assigned_to_id", "status"), name="crm_calendar_assignee_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "requirement", "event_type", "scheduled_date", "title"),
                        name="crm_calendar_event_uniq",
                    ),
                    models.CheckConstraint(
                        condition=Q(event_type__in=["deadline", "review", "submission", "audit", "renewal"]),
                        name="crm_calendar_type_ck",
                    ),
                    models.CheckConstraint(
                        condition=Q(status__in=["upcoming", "overdue", "completed", "cancelled"]),
                        name="crm_calendar_status_ck",
                    ),
                    models.CheckConstraint(
                        condition=(
                            Q(status="completed", completed_date__isnull=False)
                            | Q(status__in=["upcoming", "overdue", "cancelled"], completed_date__isnull=True)
                        ),
                        name="crm_calendar_completion_ck",
                    ),
                    models.CheckConstraint(
                        condition=(
                            Q(is_deleted=False, deleted_at__isnull=True, deleted_by_id__isnull=True)
                            | Q(is_deleted=True, deleted_at__isnull=False, deleted_by_id__isnull=False)
                        ),
                        name="crm_calendar_soft_delete_ck",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="RemediationAction",
            fields=_mutable_fields()
            + [
                ("action_code", models.CharField(max_length=50)),
                ("description", models.TextField()),
                ("assigned_to_id", models.UUIDField(db_index=True)),
                ("due_date", models.DateField()),
                (
                    "priority",
                    models.CharField(
                        choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")],
                        max_length=12,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("planned", "Planned"),
                            ("in_progress", "In progress"),
                            ("overdue", "Overdue"),
                            ("completed", "Completed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="planned",
                        editable=False,
                        max_length=20,
                    ),
                ),
                ("completion_date", models.DateField(blank=True, editable=False, null=True)),
                ("completion_evidence", models.JSONField(blank=True, default=list, encoder=DjangoJSONEncoder)),
                ("cancellation_reason", models.TextField(blank=True)),
                (
                    "risk",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="remediation_actions",
                        to="compliance_risk_management.riskassessment",
                    ),
                ),
                (
                    "control_test",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="remediation_actions",
                        to="compliance_risk_management.controltest",
                    ),
                ),
            ],
            options={
                "db_table": "compliance_risk_remediation_actions",
                "indexes": [
                    models.Index(fields=("tenant_id", "risk", "status"), name="crm_action_risk_status_idx"),
                    models.Index(
                        fields=("tenant_id", "assigned_to_id", "status", "due_date"), name="crm_action_assignee_due_idx"
                    ),
                    models.Index(fields=("tenant_id", "priority", "status"), name="crm_action_priority_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "action_code"),
                        condition=Q(is_deleted=False),
                        name="crm_action_live_code_uniq",
                    ),
                    models.CheckConstraint(
                        condition=Q(priority__in=["low", "medium", "high", "critical"]), name="crm_action_priority_ck"
                    ),
                    models.CheckConstraint(
                        condition=Q(status__in=["planned", "in_progress", "overdue", "completed", "cancelled"]),
                        name="crm_action_status_ck",
                    ),
                    models.CheckConstraint(
                        condition=(
                            Q(status="completed", completion_date__isnull=False)
                            | Q(
                                status__in=["planned", "in_progress", "overdue", "cancelled"],
                                completion_date__isnull=True,
                            )
                        ),
                        name="crm_action_completion_ck",
                    ),
                    models.CheckConstraint(
                        condition=~Q(status="cancelled") | ~Q(cancellation_reason=""),
                        name="crm_action_cancel_reason_ck",
                    ),
                    models.CheckConstraint(
                        condition=(
                            Q(is_deleted=False, deleted_at__isnull=True, deleted_by_id__isnull=True)
                            | Q(is_deleted=True, deleted_at__isnull=False, deleted_by_id__isnull=False)
                        ),
                        name="crm_action_soft_delete_ck",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="RiskConfiguration",
            fields=_mutable_fields()
            + [
                (
                    "environment",
                    models.CharField(
                        choices=[("development", "Development"), ("staging", "Staging"), ("production", "Production")],
                        max_length=20,
                    ),
                ),
                ("version", models.PositiveIntegerField()),
                ("likelihood_scale_max", models.PositiveSmallIntegerField(default=5)),
                ("impact_scale_max", models.PositiveSmallIntegerField(default=5)),
                (
                    "level_thresholds",
                    models.JSONField(default=src.modules.compliance_risk_management.models.default_level_thresholds),
                ),
                ("default_review_days", models.PositiveIntegerField(default=365)),
                (
                    "default_reminder_days",
                    models.JSONField(default=src.modules.compliance_risk_management.models.default_reminder_days),
                ),
                ("acceptance_max_days", models.PositiveIntegerField(default=365)),
                ("overdue_job_enabled", models.BooleanField(default=True)),
                ("feature_flags", models.JSONField(blank=True, default=dict)),
                ("extension_config", models.JSONField(blank=True, default=dict)),
                ("published_at", models.DateTimeField()),
                ("published_by_id", models.UUIDField(db_index=True)),
            ],
            options={
                "db_table": "compliance_risk_configurations",
                "indexes": [
                    models.Index(fields=("tenant_id", "environment", "version"), name="crm_config_env_version_idx")
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "environment"), name="crm_config_tenant_env_uniq"),
                    models.CheckConstraint(
                        condition=Q(environment__in=["development", "staging", "production"]),
                        name="crm_config_environment_ck",
                    ),
                    models.CheckConstraint(
                        condition=Q(likelihood_scale_max__gte=3, likelihood_scale_max__lte=10),
                        name="crm_config_likelihood_scale_ck",
                    ),
                    models.CheckConstraint(
                        condition=Q(impact_scale_max__gte=3, impact_scale_max__lte=10),
                        name="crm_config_impact_scale_ck",
                    ),
                    models.CheckConstraint(
                        condition=Q(default_review_days__gte=1, default_review_days__lte=3650),
                        name="crm_config_review_days_ck",
                    ),
                    models.CheckConstraint(
                        condition=Q(acceptance_max_days__gte=1, acceptance_max_days__lte=1095),
                        name="crm_config_accept_days_ck",
                    ),
                    models.CheckConstraint(condition=Q(version__gte=1), name="crm_config_version_ck"),
                    models.CheckConstraint(
                        condition=(
                            Q(is_deleted=False, deleted_at__isnull=True, deleted_by_id__isnull=True)
                            | Q(is_deleted=True, deleted_at__isnull=False, deleted_by_id__isnull=False)
                        ),
                        name="crm_config_soft_delete_ck",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="RiskConfigurationVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "environment",
                    models.CharField(
                        choices=[("development", "Development"), ("staging", "Staging"), ("production", "Production")],
                        max_length=20,
                    ),
                ),
                ("version", models.PositiveIntegerField()),
                ("configuration", models.JSONField()),
                ("change_summary", models.TextField()),
                ("actor_id", models.UUIDField(db_index=True)),
                ("correlation_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("restored_from_version", models.PositiveIntegerField(blank=True, null=True)),
            ],
            options={
                "db_table": "compliance_risk_configuration_versions",
                "indexes": [
                    models.Index(fields=("tenant_id", "environment", "created_at"), name="crm_config_history_idx")
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "environment", "version"), name="crm_config_version_uniq"
                    ),
                    models.CheckConstraint(
                        condition=Q(environment__in=["development", "staging", "production"]),
                        name="crm_config_ver_environment_ck",
                    ),
                    models.CheckConstraint(condition=Q(version__gte=1), name="crm_config_ver_number_ck"),
                    models.CheckConstraint(
                        condition=Q(restored_from_version__isnull=True) | Q(restored_from_version__gte=1),
                        name="crm_config_ver_restore_ck",
                    ),
                ],
            },
        ),
        migrations.RunPython(migrations.RunPython.noop, guard_domain_reversal),
        migrations.CreateModel(
            name="ComplianceRisk",
            fields=[],
            options={"proxy": True, "indexes": [], "constraints": []},
            bases=("compliance_risk_management.riskassessment",),
        ),
    ]
