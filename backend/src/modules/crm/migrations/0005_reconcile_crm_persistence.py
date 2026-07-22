"""Expand and reconcile the applied CRM schema without dropping rows."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db import migrations, models

import src.modules.crm.models


MARKER = "__crm_0005_original__"
MODEL_NAMES = ("Lead", "Account", "Contact", "Opportunity", "Activity")


def _remember(instance, **values):
    metadata = instance.metadata if isinstance(instance.metadata, dict) else {}
    marker = dict(metadata.get(MARKER, {}))
    if not isinstance(instance.metadata, dict):
        marker.setdefault("metadata", instance.metadata)
    for field, value in values.items():
        if field not in marker:
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            elif isinstance(value, (UUID, Decimal)):
                value = str(value)
            marker[field] = value
    metadata[MARKER] = marker
    instance.metadata = metadata


def _soft_delete(instance):
    if not instance.is_deleted:
        _remember(instance, is_deleted=False, deleted_at=instance.deleted_at)
        instance.is_deleted = True
    if instance.deleted_at is None:
        instance.deleted_at = instance.updated_at


def _common(instance):
    changed = {"metadata"}
    if not isinstance(instance.metadata, dict):
        _remember(instance, metadata=instance.metadata)
    if instance.is_deleted and instance.deleted_at is None:
        _remember(instance, deleted_at=None)
        instance.deleted_at = instance.updated_at
        changed.add("deleted_at")
    elif not instance.is_deleted and instance.deleted_at is not None:
        _remember(instance, is_deleted=False)
        instance.is_deleted = True
        changed.add("is_deleted")
    return changed


def _normalize_leads(Lead):
    seen = set()
    for lead in Lead.objects.order_by("created_at", "id").iterator():
        changed = _common(lead)
        normalized_email = lead.email.strip().lower() if lead.email else None
        if lead.email != normalized_email:
            _remember(lead, email=lead.email)
            lead.email = normalized_email
            changed.add("email")
        normalized_score = min(100, max(0, int(lead.score or 0)))
        grade = "A" if normalized_score >= 80 else "B" if normalized_score >= 60 else "C" if normalized_score >= 40 else "D"
        if lead.score != normalized_score or lead.grade != grade:
            _remember(lead, score=lead.score, grade=lead.grade)
            lead.score, lead.grade = normalized_score, grade
            changed.update({"score", "grade"})
        if lead.status not in {"new", "contacted", "qualified", "converted", "lost"}:
            _remember(lead, status=lead.status)
            lead.status = "new"
            changed.add("status")
        complete_conversion = lead.converted_at is not None and lead.converted_to_opportunity_id is not None
        if lead.status == "converted" and not complete_conversion:
            _remember(
                lead,
                status=lead.status,
                converted_at=lead.converted_at,
                converted_to_opportunity_id=lead.converted_to_opportunity_id,
            )
            lead.status = "qualified"
            lead.converted_at = None
            lead.converted_to_opportunity_id = None
            changed.update({"status", "converted_at", "converted_to_opportunity_id"})
        elif lead.status != "converted" and (lead.converted_at or lead.converted_to_opportunity_id):
            _remember(
                lead,
                converted_at=lead.converted_at,
                converted_to_opportunity_id=lead.converted_to_opportunity_id,
            )
            lead.converted_at = None
            lead.converted_to_opportunity_id = None
            changed.update({"converted_at", "converted_to_opportunity_id"})
        key = (lead.tenant_id, normalized_email)
        if normalized_email and not lead.is_deleted:
            if key in seen:
                _soft_delete(lead)
                changed.update({"is_deleted", "deleted_at", "metadata"})
            else:
                seen.add(key)
        lead.save(update_fields=changed)


def _valid_parent(Account, account):
    parent_id = account.parent_account_id
    visited = {account.id}
    ancestors = 0
    while parent_id:
        if parent_id in visited:
            return False
        visited.add(parent_id)
        parent = Account.objects.filter(
            id=parent_id, tenant_id=account.tenant_id, is_deleted=False
        ).only("id", "parent_account_id").first()
        if parent is None:
            return False
        ancestors += 1
        if ancestors >= 3:
            return False
        parent_id = parent.parent_account_id
    return True


def _normalize_accounts(Account):
    countries = src.modules.crm.models.ISO_3166_ALPHA_2
    seen = set()
    for account in Account.objects.order_by("created_at", "id").iterator():
        changed = _common(account)
        name = account.name.strip()
        if name != account.name:
            _remember(account, name=account.name)
            account.name = name
            changed.add("name")
        country = account.billing_country.strip().upper()
        if country not in countries:
            country = ""
        if country != account.billing_country:
            _remember(account, billing_country=account.billing_country)
            account.billing_country = country
            changed.add("billing_country")
        if account.employees is not None and account.employees < 0:
            _remember(account, employees=account.employees)
            account.employees = None
            changed.add("employees")
        if account.annual_revenue is not None and account.annual_revenue < 0:
            _remember(account, annual_revenue=account.annual_revenue)
            account.annual_revenue = None
            changed.add("annual_revenue")
        if account.account_type not in {"prospect", "customer", "partner"}:
            _remember(account, account_type=account.account_type)
            account.account_type = "prospect"
            changed.add("account_type")
        if account.parent_account_id and not _valid_parent(Account, account):
            _remember(account, parent_account_id=account.parent_account_id)
            account.parent_account_id = None
            changed.add("parent_account_id")
        key = (account.tenant_id, name.lower())
        if not name or (not account.is_deleted and key in seen):
            _soft_delete(account)
            changed.update({"is_deleted", "deleted_at", "metadata"})
        elif not account.is_deleted:
            seen.add(key)
        account.save(update_fields=changed)


def _normalize_contacts(Contact, Account):
    seen = set()
    for contact in Contact.objects.order_by("created_at", "id").iterator():
        changed = _common(contact)
        email = contact.email.strip().lower() if contact.email else None
        if email != contact.email:
            _remember(contact, email=contact.email)
            contact.email = email
            changed.add("email")
        score = min(100, max(0, int(contact.engagement_score or 0)))
        if score != contact.engagement_score:
            _remember(contact, engagement_score=contact.engagement_score)
            contact.engagement_score = score
            changed.add("engagement_score")
        active_account = Account.objects.filter(
            id=contact.account_id, tenant_id=contact.tenant_id, is_deleted=False
        ).exists()
        key = (contact.tenant_id, contact.account_id, email)
        if not active_account or (email and not contact.is_deleted and key in seen):
            _soft_delete(contact)
            changed.update({"is_deleted", "deleted_at", "metadata"})
        elif email and not contact.is_deleted:
            seen.add(key)
        contact.save(update_fields=changed)


def _normalize_opportunities(Opportunity, Account, Contact):
    currencies = src.modules.crm.models.ISO_4217_CODES
    open_stages = {"prospecting", "qualification", "needs_analysis", "proposal", "negotiation"}
    for opportunity in Opportunity.objects.iterator():
        changed = _common(opportunity)
        if opportunity.amount is None or opportunity.amount <= 0:
            _remember(opportunity, amount=opportunity.amount)
            opportunity.amount = abs(opportunity.amount or Decimal("0")) or Decimal("0.01")
            _soft_delete(opportunity)
            changed.update({"amount", "is_deleted", "deleted_at", "metadata"})
        probability = min(100, max(0, int(opportunity.probability or 0)))
        if probability != opportunity.probability:
            _remember(opportunity, probability=opportunity.probability)
            opportunity.probability = probability
            changed.add("probability")
        currency = opportunity.currency.strip().upper()
        if currency not in currencies:
            _remember(opportunity, currency=opportunity.currency)
            opportunity.currency = "USD"
            _soft_delete(opportunity)
            changed.update({"currency", "is_deleted", "deleted_at", "metadata"})
        active_account = Account.objects.filter(
            id=opportunity.account_id, tenant_id=opportunity.tenant_id, is_deleted=False
        ).exists()
        if not active_account:
            _soft_delete(opportunity)
            changed.update({"is_deleted", "deleted_at", "metadata"})
        if opportunity.primary_contact_id and not Contact.objects.filter(
            id=opportunity.primary_contact_id,
            account_id=opportunity.account_id,
            tenant_id=opportunity.tenant_id,
            is_deleted=False,
        ).exists():
            _remember(opportunity, primary_contact_id=opportunity.primary_contact_id)
            opportunity.primary_contact_id = None
            changed.add("primary_contact_id")
        if opportunity.status == "won":
            opportunity.stage = "closed_won"
            opportunity.probability = 100
            opportunity.closed_at = opportunity.closed_at or opportunity.updated_at
            opportunity.loss_reason = ""
            changed.update({"stage", "probability", "closed_at", "loss_reason"})
        elif opportunity.status == "lost" and opportunity.loss_reason.strip():
            opportunity.stage = "closed_lost"
            opportunity.probability = 0
            opportunity.closed_at = opportunity.closed_at or opportunity.updated_at
            opportunity.loss_reason = opportunity.loss_reason.strip()
            changed.update({"stage", "probability", "closed_at", "loss_reason"})
        else:
            if opportunity.status != "open" or opportunity.stage not in open_stages or opportunity.closed_at:
                _remember(
                    opportunity,
                    status=opportunity.status,
                    stage=opportunity.stage,
                    closed_at=opportunity.closed_at,
                    loss_reason=opportunity.loss_reason,
                )
            opportunity.status = "open"
            opportunity.stage = opportunity.stage if opportunity.stage in open_stages else "prospecting"
            opportunity.closed_at = None
            opportunity.loss_reason = ""
            changed.update({"status", "stage", "closed_at", "loss_reason"})
        opportunity.save(update_fields=changed)


def _normalize_activities(Activity, related_models):
    seen = set()
    valid_types = {"call", "email", "meeting", "task", "note"}
    for activity in Activity.objects.order_by("created_at", "id").iterator():
        changed = _common(activity)
        if activity.activity_type not in valid_types:
            _remember(activity, activity_type=activity.activity_type)
            activity.activity_type = "note"
            changed.add("activity_type")
        model = related_models.get(activity.related_to_type)
        related_exists = bool(
            model
            and model.objects.filter(
                id=activity.related_to_id, tenant_id=activity.tenant_id, is_deleted=False
            ).exists()
        )
        if not related_exists:
            _soft_delete(activity)
            changed.update({"is_deleted", "deleted_at", "metadata"})
        if activity.completed and activity.completed_at is None:
            _remember(activity, completed=True, completed_at=None)
            activity.completed = False
            changed.add("completed")
        elif not activity.completed and activity.completed_at is not None:
            _remember(activity, completed=False, completed_at=activity.completed_at)
            activity.completed_at = None
            changed.add("completed_at")
        activity.external_id = activity.external_id.strip()
        key = (activity.tenant_id, activity.activity_type, activity.external_id)
        if activity.external_id and not activity.is_deleted:
            if key in seen:
                _soft_delete(activity)
                changed.update({"is_deleted", "deleted_at", "metadata"})
            else:
                seen.add(key)
        changed.add("external_id")
        activity.save(update_fields=changed)


def reconcile_rows(apps, schema_editor):
    del schema_editor
    models_by_name = {name: apps.get_model("crm", name) for name in MODEL_NAMES}
    _normalize_accounts(models_by_name["Account"])
    _normalize_leads(models_by_name["Lead"])
    _normalize_contacts(models_by_name["Contact"], models_by_name["Account"])
    _normalize_opportunities(
        models_by_name["Opportunity"], models_by_name["Account"], models_by_name["Contact"]
    )
    _normalize_activities(
        models_by_name["Activity"],
        {
            "Lead": models_by_name["Lead"],
            "Contact": models_by_name["Contact"],
            "Account": models_by_name["Account"],
            "Opportunity": models_by_name["Opportunity"],
        },
    )


def restore_rows(apps, schema_editor):
    del schema_editor
    for name in reversed(MODEL_NAMES):
        model = apps.get_model("crm", name)
        for instance in model.objects.filter(metadata__has_key=MARKER).iterator():  # noqa: E711
            metadata = dict(instance.metadata)
            original = metadata.pop(MARKER)
            update_fields = {"metadata"}
            for field_name, value in original.items():
                if field_name == "metadata":
                    metadata = value
                    continue
                field = model._meta.get_field(field_name)
                setattr(instance, field_name, field.to_python(value))
                update_fields.add(field_name)
            instance.metadata = metadata
            instance.save(update_fields=update_fields)


def widen_actor_columns(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in ("crm_leads", "crm_accounts", "crm_contacts", "crm_opportunities", "crm_activities"):
        schema_editor.execute(f'ALTER TABLE "{table}" ALTER COLUMN "created_by" TYPE varchar(255)')


def preserve_wide_actor_columns(apps, schema_editor):
    """Intentionally retain varchar(255) during rollback to avoid truncation."""

    del apps, schema_editor


ACTOR_STATE = [
    migrations.AlterField(
        model_name=name.lower(),
        name="created_by",
        field=models.CharField(blank=True, db_index=True, editable=False, max_length=255, null=True),
    )
    for name in MODEL_NAMES
]


class Migration(migrations.Migration):
    dependencies = [("crm", "0004_alter_activity_owner_id_alter_opportunity_owner_id")]

    operations = [
        migrations.RemoveConstraint(model_name="lead", name="unique_lead_email_per_tenant"),
        migrations.RemoveConstraint(model_name="account", name="unique_account_name_per_tenant"),
        *[
            migrations.RemoveIndex(model_name=model_name, name=index_name)
            for model_name, index_name in (
                ("account", "idx_account_tenant_name"),
                ("account", "idx_account_owner"),
                ("account", "idx_account_parent"),
                ("activity", "idx_activity_relation"),
                ("activity", "idx_activity_owner_due"),
                ("activity", "idx_activity_type"),
                ("activity", "idx_activity_external"),
                ("contact", "idx_contact_tenant_account"),
                ("contact", "idx_contact_email"),
                ("contact", "idx_contact_owner"),
                ("lead", "idx_lead_tenant_status"),
                ("lead", "idx_lead_tenant_email"),
                ("lead", "idx_lead_score"),
                ("lead", "idx_lead_owner_status"),
                ("opportunity", "idx_opp_tenant_status"),
                ("opportunity", "idx_opp_owner_stage"),
                ("opportunity", "idx_opp_close_date"),
                ("opportunity", "idx_opp_account"),
            )
        ],
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(widen_actor_columns, preserve_wide_actor_columns)],
            state_operations=ACTOR_STATE,
        ),
        *[
            operation
            for name in MODEL_NAMES
            for operation in (
                migrations.AddField(
                    model_name=name.lower(),
                    name="updated_by",
                    field=models.CharField(
                        blank=True, db_index=True, editable=False, max_length=255, null=True
                    ),
                ),
                migrations.AddField(
                    model_name=name.lower(),
                    name="version",
                    field=models.PositiveBigIntegerField(default=1, editable=False),
                ),
            )
        ],
        migrations.AddField(
            model_name="lead",
            name="score_source",
            field=models.CharField(
                choices=[("rules", "Rules"), ("provider", "Provider")], default="rules", max_length=20
            ),
        ),
        migrations.AddField(
            model_name="lead",
            name="score_explanation",
            field=models.JSONField(
                blank=True, default=dict, validators=[src.modules.crm.models.validate_metadata]
            ),
        ),
        migrations.AddField(
            model_name="lead",
            name="transition_history",
            field=models.JSONField(blank=True, default=list, editable=False),
        ),
        migrations.AddField(
            model_name="opportunity",
            name="transition_history",
            field=models.JSONField(blank=True, default=list, editable=False),
        ),
        migrations.RunPython(reconcile_rows, restore_rows),
        migrations.AlterField(
            model_name="account", name="name", field=models.CharField(max_length=255)
        ),
        migrations.AlterField(
            model_name="account", name="billing_country", field=models.CharField(blank=True, max_length=2)
        ),
        migrations.AlterField(
            model_name="account",
            name="account_type",
            field=models.CharField(
                choices=[("prospect", "Prospect"), ("customer", "Customer"), ("partner", "Partner")],
                default="prospect",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="lead", name="email", field=models.EmailField(blank=True, max_length=255, null=True)
        ),
        migrations.AlterField(
            model_name="lead", name="score", field=models.SmallIntegerField(default=0)
        ),
        migrations.AlterField(
            model_name="lead",
            name="grade",
            field=models.CharField(
                choices=[("A", "A"), ("B", "B"), ("C", "C"), ("D", "D")], default="D", max_length=1
            ),
        ),
        migrations.AlterField(
            model_name="lead",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "New"),
                    ("contacted", "Contacted"),
                    ("qualified", "Qualified"),
                    ("converted", "Converted"),
                    ("lost", "Lost"),
                ],
                default="new",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="contact", name="email", field=models.EmailField(blank=True, max_length=255, null=True)
        ),
        migrations.AlterField(
            model_name="contact", name="engagement_score", field=models.SmallIntegerField(default=0)
        ),
        migrations.AlterField(
            model_name="opportunity",
            name="primary_contact_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="opportunity", name="probability", field=models.SmallIntegerField(default=10)
        ),
        migrations.AlterField(
            model_name="opportunity",
            name="stage",
            field=models.CharField(
                choices=[
                    ("prospecting", "Prospecting"),
                    ("qualification", "Qualification"),
                    ("needs_analysis", "Needs Analysis"),
                    ("proposal", "Proposal"),
                    ("negotiation", "Negotiation"),
                    ("closed_won", "Closed Won"),
                    ("closed_lost", "Closed Lost"),
                ],
                default="prospecting",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="opportunity",
            name="status",
            field=models.CharField(
                choices=[("open", "Open"), ("won", "Won"), ("lost", "Lost")],
                default="open",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="opportunity",
            name="product_ids",
            field=models.JSONField(
                blank=True, default=list, validators=[src.modules.crm.models.validate_uuid_string_array]
            ),
        ),
        migrations.AlterField(
            model_name="opportunity",
            name="competitors",
            field=models.JSONField(
                blank=True, default=list, validators=[src.modules.crm.models.validate_non_empty_string_array]
            ),
        ),
        migrations.AlterField(
            model_name="activity",
            name="activity_type",
            field=models.CharField(
                choices=[
                    ("call", "Call"),
                    ("email", "Email"),
                    ("meeting", "Meeting"),
                    ("task", "Task"),
                    ("note", "Note"),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="activity",
            name="related_to_type",
            field=models.CharField(
                choices=[
                    ("Lead", "Lead"),
                    ("Contact", "Contact"),
                    ("Account", "Account"),
                    ("Opportunity", "Opportunity"),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(model_name="activity", name="related_to_id", field=models.UUIDField()),
        migrations.AlterField(
            model_name="activity", name="due_date", field=models.DateTimeField(blank=True, null=True)
        ),
        migrations.AlterField(
            model_name="activity", name="completed", field=models.BooleanField(default=False)
        ),
        migrations.AlterField(
            model_name="activity", name="external_id", field=models.CharField(blank=True, max_length=255)
        ),
        *[
            migrations.AlterField(
                model_name=name.lower(),
                name="created_at",
                field=models.DateTimeField(auto_now_add=True),
            )
            for name in MODEL_NAMES
        ],
        *[
            migrations.AlterField(
                model_name=name.lower(),
                name="metadata",
                field=models.JSONField(
                    blank=True, default=dict, validators=[src.modules.crm.models.validate_metadata]
                ),
            )
            for name in MODEL_NAMES
        ],
    ]
