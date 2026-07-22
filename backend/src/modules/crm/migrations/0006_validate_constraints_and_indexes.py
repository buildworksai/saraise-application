"""Validate reconciled CRM rows, then add invariants and query indexes."""

from django.db import migrations, models
from django.db.models.functions import Lower


INDEXES = {
    "Lead": (
        models.Index(fields=["tenant_id", "is_deleted", "-created_at"], name="crm_lead_tenant_del_ct"),
        models.Index(fields=["tenant_id", "status", "-created_at"], name="crm_lead_status_ct"),
        models.Index(fields=["tenant_id", "owner_id", "status"], name="crm_lead_owner_status"),
        models.Index(fields=["tenant_id", "-score"], name="crm_lead_score_desc"),
        models.Index(fields=["tenant_id", "source", "-created_at"], name="crm_lead_source_ct"),
        models.Index(
            fields=["tenant_id", "converted_to_opportunity_id"], name="crm_lead_converted_opp"
        ),
    ),
    "Account": (
        models.Index(fields=["tenant_id", "is_deleted", "-created_at"], name="crm_account_tenant_del_ct"),
        models.Index(fields=["tenant_id", "account_type", "name"], name="crm_account_type_name"),
        models.Index(fields=["tenant_id", "owner_id", "account_type"], name="crm_account_owner_type"),
        models.Index(fields=["tenant_id", "parent_account_id", "name"], name="crm_account_parent_name"),
    ),
    "Contact": (
        models.Index(fields=["tenant_id", "is_deleted", "-created_at"], name="crm_contact_tenant_del_ct"),
        models.Index(fields=["tenant_id", "account_id", "last_name"], name="crm_contact_account_name"),
        models.Index(fields=["tenant_id", "owner_id", "last_name"], name="crm_contact_owner_name"),
        models.Index(fields=["tenant_id", "-last_contacted_at"], name="crm_contact_last_contact"),
        models.Index(fields=["tenant_id", "-engagement_score"], name="crm_contact_engagement"),
    ),
    "Opportunity": (
        models.Index(
            fields=["tenant_id", "is_deleted", "-created_at"], name="crm_opportunity_tenant_del_ct"
        ),
        models.Index(fields=["tenant_id", "status", "close_date"], name="crm_opp_status_close"),
        models.Index(
            fields=["tenant_id", "owner_id", "stage", "close_date"], name="crm_opp_owner_stage_close"
        ),
        models.Index(fields=["tenant_id", "account_id", "status"], name="crm_opp_account_status"),
        models.Index(fields=["tenant_id", "stage", "amount"], name="crm_opp_stage_amount"),
        models.Index(fields=["tenant_id", "last_activity_at"], name="crm_opp_last_activity"),
    ),
    "Activity": (
        models.Index(fields=["tenant_id", "is_deleted", "-created_at"], name="crm_activity_tenant_del_ct"),
        models.Index(
            fields=["tenant_id", "related_to_type", "related_to_id", "-created_at"],
            name="crm_activity_relation_ct",
        ),
        models.Index(
            fields=["tenant_id", "owner_id", "completed", "due_date"], name="crm_activity_owner_due"
        ),
        models.Index(fields=["tenant_id", "activity_type", "-created_at"], name="crm_activity_type_ct"),
        models.Index(fields=["tenant_id", "external_id"], name="crm_activity_external"),
    ),
}


def validate_rows(apps, schema_editor):
    del schema_editor
    Lead = apps.get_model("crm", "Lead")
    Account = apps.get_model("crm", "Account")
    Contact = apps.get_model("crm", "Contact")
    Opportunity = apps.get_model("crm", "Opportunity")
    Activity = apps.get_model("crm", "Activity")
    soft_invalid = models.Q(is_deleted=False, deleted_at__isnull=False) | models.Q(
        is_deleted=True, deleted_at__isnull=True
    )
    for model in (Lead, Account, Contact, Opportunity, Activity):
        if model.objects.filter(soft_invalid).exists():
            raise RuntimeError(f"{model._meta.db_table} contains an invalid soft-delete pair")
    if Lead.objects.exclude(score__range=(0, 100)).exists():
        raise RuntimeError("crm_leads contains an out-of-range score")
    grade_valid = (
        models.Q(grade="A", score__range=(80, 100))
        | models.Q(grade="B", score__range=(60, 79))
        | models.Q(grade="C", score__range=(40, 59))
        | models.Q(grade="D", score__range=(0, 39))
    )
    if Lead.objects.exclude(grade_valid).exists():
        raise RuntimeError("crm_leads contains an inconsistent score grade")
    conversion_valid = models.Q(
        status="converted", converted_at__isnull=False, converted_to_opportunity_id__isnull=False
    ) | (
        ~models.Q(status="converted")
        & models.Q(converted_at__isnull=True, converted_to_opportunity_id__isnull=True)
    )
    if Lead.objects.exclude(conversion_valid).exists():
        raise RuntimeError("crm_leads contains inconsistent conversion evidence")
    if Account.objects.filter(employees__lt=0).exists() or Account.objects.filter(annual_revenue__lt=0).exists():
        raise RuntimeError("crm_accounts contains negative evidence")
    if Account.objects.filter(parent_account_id=models.F("id")).exists():
        raise RuntimeError("crm_accounts contains a self-parent")
    if Contact.objects.exclude(engagement_score__range=(0, 100)).exists():
        raise RuntimeError("crm_contacts contains an out-of-range engagement score")
    if Opportunity.objects.filter(amount__lte=0).exists() or Opportunity.objects.exclude(
        probability__range=(0, 100)
    ).exists():
        raise RuntimeError("crm_opportunities contains invalid financial evidence")
    open_stages = ["prospecting", "qualification", "needs_analysis", "proposal", "negotiation"]
    opportunity_valid = (
        models.Q(status="open", stage__in=open_stages, closed_at__isnull=True)
        | models.Q(status="won", stage="closed_won", probability=100, closed_at__isnull=False)
        | (
            models.Q(status="lost", stage="closed_lost", probability=0, closed_at__isnull=False)
            & ~models.Q(loss_reason="")
        )
    )
    if Opportunity.objects.exclude(opportunity_valid).exists():
        raise RuntimeError("crm_opportunities contains inconsistent state")
    completion_valid = models.Q(completed=False, completed_at__isnull=True) | models.Q(
        completed=True, completed_at__isnull=False
    )
    if Activity.objects.exclude(completion_valid).exists():
        raise RuntimeError("crm_activities contains inconsistent completion evidence")


def noop_reverse(apps, schema_editor):
    del apps, schema_editor


def add_indexes(apps, schema_editor):
    for model_name, indexes in INDEXES.items():
        model = apps.get_model("crm", model_name)
        for index in indexes:
            if schema_editor.connection.vendor == "postgresql":
                statement = str(index.create_sql(model, schema_editor))
                schema_editor.execute(statement.replace("CREATE INDEX", "CREATE INDEX CONCURRENTLY", 1))
            else:
                schema_editor.add_index(model, index)


def remove_indexes(apps, schema_editor):
    for model_name, indexes in reversed(tuple(INDEXES.items())):
        model = apps.get_model("crm", model_name)
        for index in reversed(indexes):
            if schema_editor.connection.vendor == "postgresql":
                schema_editor.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{index.name}"')
            else:
                schema_editor.remove_index(model, index)


CONSTRAINTS = {
    "lead": (
        models.CheckConstraint(
            condition=(models.Q(is_deleted=False, deleted_at__isnull=True))
            | models.Q(is_deleted=True, deleted_at__isnull=False),
            name="crm_lead_soft_del_ck",
        ),
        models.CheckConstraint(condition=models.Q(score__gte=0, score__lte=100), name="crm_lead_score_range_ck"),
        models.CheckConstraint(
            condition=(models.Q(grade="A", score__gte=80, score__lte=100))
            | (models.Q(grade="B", score__gte=60, score__lte=79))
            | (models.Q(grade="C", score__gte=40, score__lte=59))
            | (models.Q(grade="D", score__gte=0, score__lte=39)),
            name="crm_lead_grade_score_ck",
        ),
        models.CheckConstraint(
            condition=(
                models.Q(
                    status="converted",
                    converted_at__isnull=False,
                    converted_to_opportunity_id__isnull=False,
                )
                | (
                    ~models.Q(status="converted")
                    & models.Q(converted_at__isnull=True, converted_to_opportunity_id__isnull=True)
                )
            ),
            name="crm_lead_conversion_ck",
        ),
        models.UniqueConstraint(
            models.F("tenant_id"),
            Lower("email"),
            condition=models.Q(email__isnull=False, is_deleted=False),
            name="crm_lead_active_email_uniq",
        ),
    ),
    "account": (
        models.CheckConstraint(
            condition=(models.Q(is_deleted=False, deleted_at__isnull=True))
            | models.Q(is_deleted=True, deleted_at__isnull=False),
            name="crm_account_soft_del_ck",
        ),
        models.UniqueConstraint(
            models.F("tenant_id"),
            Lower("name"),
            condition=models.Q(is_deleted=False),
            name="crm_account_active_name_uniq",
        ),
        models.CheckConstraint(
            condition=models.Q(employees__isnull=True) | models.Q(employees__gte=0),
            name="crm_account_employees_ck",
        ),
        models.CheckConstraint(
            condition=models.Q(annual_revenue__isnull=True) | models.Q(annual_revenue__gte=0),
            name="crm_account_revenue_ck",
        ),
        models.CheckConstraint(
            condition=models.Q(parent_account_id__isnull=True) | ~models.Q(parent_account_id=models.F("id")),
            name="crm_account_not_parent_ck",
        ),
    ),
    "contact": (
        models.CheckConstraint(
            condition=(models.Q(is_deleted=False, deleted_at__isnull=True))
            | models.Q(is_deleted=True, deleted_at__isnull=False),
            name="crm_contact_soft_del_ck",
        ),
        models.CheckConstraint(
            condition=models.Q(engagement_score__gte=0, engagement_score__lte=100),
            name="crm_contact_engagement_ck",
        ),
        models.UniqueConstraint(
            models.F("tenant_id"),
            models.F("account_id"),
            Lower("email"),
            condition=models.Q(email__isnull=False, is_deleted=False),
            name="crm_contact_account_email_uniq",
        ),
    ),
    "opportunity": (
        models.CheckConstraint(
            condition=(models.Q(is_deleted=False, deleted_at__isnull=True))
            | models.Q(is_deleted=True, deleted_at__isnull=False),
            name="crm_opportunity_soft_del_ck",
        ),
        models.CheckConstraint(condition=models.Q(amount__gt=0), name="crm_opp_amount_positive_ck"),
        models.CheckConstraint(
            condition=models.Q(probability__gte=0, probability__lte=100), name="crm_opp_probability_ck"
        ),
        models.CheckConstraint(
            condition=(
                models.Q(
                    status="open",
                    stage__in=["prospecting", "qualification", "needs_analysis", "proposal", "negotiation"],
                    closed_at__isnull=True,
                )
                | models.Q(status="won", stage="closed_won", probability=100, closed_at__isnull=False)
                | (
                    models.Q(
                        status="lost",
                        stage="closed_lost",
                        probability=0,
                        closed_at__isnull=False,
                    )
                    & ~models.Q(loss_reason="")
                )
            ),
            name="crm_opp_state_consistency_ck",
        ),
    ),
    "activity": (
        models.CheckConstraint(
            condition=(models.Q(is_deleted=False, deleted_at__isnull=True))
            | models.Q(is_deleted=True, deleted_at__isnull=False),
            name="crm_activity_soft_del_ck",
        ),
        models.CheckConstraint(
            condition=(models.Q(completed=False, completed_at__isnull=True))
            | models.Q(completed=True, completed_at__isnull=False),
            name="crm_activity_completion_ck",
        ),
        models.UniqueConstraint(
            fields=["tenant_id", "activity_type", "external_id"],
            condition=~models.Q(external_id="") & models.Q(is_deleted=False),
            name="crm_activity_external_uniq",
        ),
    ),
}


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("crm", "0005_reconcile_crm_persistence")]

    operations = [
        migrations.RunPython(validate_rows, noop_reverse),
        *[
            migrations.AddConstraint(model_name=model_name, constraint=constraint)
            for model_name, constraints in CONSTRAINTS.items()
            for constraint in constraints
        ],
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(add_indexes, remove_indexes)],
            state_operations=[
                migrations.AddIndex(model_name=model_name.lower(), index=index)
                for model_name, indexes in INDEXES.items()
                for index in indexes
            ],
        ),
    ]
