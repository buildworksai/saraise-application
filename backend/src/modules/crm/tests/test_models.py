"""Complete persistence contract coverage for the five CRM entities."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from src.core.tenancy import TenantScopedModel, TimestampedModel

from ..models import (
    Account,
    AccountType,
    Activity,
    ActivityType,
    Contact,
    CRMModel,
    Lead,
    LeadGrade,
    LeadScoreSource,
    LeadStatus,
    Opportunity,
    OpportunityStage,
    OpportunityStatus,
    RelatedToType,
    validate_metadata,
    validate_non_empty_string_array,
    validate_uuid_string_array,
)
from .factories import AccountFactory, ActivityFactory, ContactFactory, LeadFactory, OpportunityFactory

pytestmark = pytest.mark.django_db
MODELS = (Lead, Account, Contact, Opportunity, Activity)


@pytest.mark.parametrize("model", MODELS)
def test_every_entity_uses_the_canonical_common_contract(model):
    assert issubclass(model, TenantScopedModel)
    assert issubclass(model, TimestampedModel)
    assert issubclass(model, CRMModel)
    fields = {field.name: field for field in model._meta.fields}
    assert fields["id"].get_internal_type() == "UUIDField"
    assert fields["id"].primary_key and not fields["id"].editable
    assert fields["tenant_id"].get_internal_type() == "UUIDField" and fields["tenant_id"].db_index
    assert fields["created_by"].max_length == fields["updated_by"].max_length == 255
    assert fields["created_by"].db_index and fields["updated_by"].db_index
    assert fields["version"].get_internal_type() == "PositiveBigIntegerField"
    assert fields["is_deleted"].db_index
    assert any(index.fields == ["tenant_id", "is_deleted", "-created_at"] for index in model._meta.indexes)


def test_choice_contracts_are_exact():
    assert set(LeadStatus.values) == {"new", "contacted", "qualified", "converted", "lost"}
    assert set(LeadGrade.values) == {"A", "B", "C", "D"}
    assert set(LeadScoreSource.values) == {"rules", "provider"}
    assert set(AccountType.values) == {"prospect", "customer", "partner"}
    assert set(OpportunityStage.values) == {
        "prospecting",
        "qualification",
        "needs_analysis",
        "proposal",
        "negotiation",
        "closed_won",
        "closed_lost",
    }
    assert set(OpportunityStatus.values) == {"open", "won", "lost"}
    assert set(ActivityType.values) == {"call", "email", "meeting", "task", "note"}
    assert set(RelatedToType.values) == {"Lead", "Contact", "Account", "Opportunity"}


def test_defaults_and_string_representations():
    lead = LeadFactory(first_name="Ada", last_name="Lovelace", company="Analytical Engines")
    account = AccountFactory(name="BuildWorks")
    contact = ContactFactory(account=account, tenant_id=account.tenant_id, first_name="Grace", last_name="Hopper")
    opportunity = OpportunityFactory(account=account, tenant_id=account.tenant_id, name="Platform")
    activity = ActivityFactory(related=lead, tenant_id=lead.tenant_id, activity_type="call", subject="Discovery")
    assert (lead.score, lead.grade, lead.score_source, lead.status) == (0, "D", "rules", "new")
    assert account.account_type == "prospect"
    assert contact.engagement_score == 0
    assert (opportunity.currency, opportunity.probability, opportunity.status) == ("USD", 10, "open")
    assert not activity.completed and activity.completed_at is None
    assert str(lead) == "Ada Lovelace (Analytical Engines)"
    assert str(account) == "BuildWorks"
    assert str(contact) == "Grace Hopper"
    assert str(opportunity) == "Platform"
    assert str(activity) == "call: Discovery"


@pytest.mark.parametrize(
    "score,grade", [(0, "D"), (39, "D"), (40, "C"), (59, "C"), (60, "B"), (79, "B"), (80, "A"), (100, "A")]
)
def test_lead_score_grade_boundaries(score, grade):
    lead = LeadFactory.build(score=score, grade=grade)
    lead.full_clean()


@pytest.mark.parametrize("score,grade", [(-1, "D"), (101, "A"), (80, "D"), (20, "A")])
def test_lead_rejects_invalid_score_grade_pairs(score, grade):
    with pytest.raises(ValidationError):
        LeadFactory.build(score=score, grade=grade).full_clean()


def test_lead_conversion_and_case_insensitive_active_email_constraints():
    tenant = uuid.uuid4()
    LeadFactory(tenant_id=tenant, email="Case@Example.test")
    with pytest.raises(ValidationError):
        LeadFactory(tenant_id=tenant, email="case@example.test")
    deleted = LeadFactory(tenant_id=tenant, email="deleted@example.test")
    deleted.is_deleted, deleted.deleted_at = True, timezone.now()
    deleted.save()
    LeadFactory(tenant_id=tenant, email="deleted@example.test")
    with pytest.raises(ValidationError, match="Conversion"):
        LeadFactory.build(status="converted", converted_at=None, converted_to_opportunity_id=None).full_clean()


def test_soft_delete_invariant_hard_delete_and_optimistic_version():
    lead = LeadFactory()
    assert lead.version == 1
    lead.first_name = "Updated"
    lead.updated_by = "actor-2"
    lead.save()
    assert lead.version == 2
    with pytest.raises(ValidationError, match="deleted_at"):
        LeadFactory.build(is_deleted=True, deleted_at=None).full_clean()
    with pytest.raises(ValidationError, match="hard-deleted"):
        lead.delete()


def test_metadata_and_array_validators_are_strict():
    validate_metadata({"industry.example.flag": True, "evidence": [1, "two", None]})
    validate_uuid_string_array([str(uuid.uuid4())])
    validate_non_empty_string_array(["Competitor"])
    for validator, value in (
        (validate_metadata, []),
        (validate_metadata, {"bad": object()}),
        (validate_uuid_string_array, [uuid.uuid4()]),
        (validate_non_empty_string_array, [""]),
    ):
        with pytest.raises(ValidationError):
            validator(value)
    with pytest.raises(ValidationError, match="custom_fields"):
        LeadFactory.build(metadata={"custom_fields": []}).full_clean()


def test_account_case_insensitive_name_financial_country_and_parent_rules():
    tenant = uuid.uuid4()
    root = AccountFactory(tenant_id=tenant, name="Root", billing_country="in")
    assert root.billing_country == "IN"
    with pytest.raises(ValidationError):
        AccountFactory(tenant_id=tenant, name=" root ")
    for values in ({"employees": -1}, {"annual_revenue": Decimal("-0.01")}, {"billing_country": "ZZ"}):
        with pytest.raises(ValidationError):
            AccountFactory.build(tenant_id=tenant, **values).full_clean()
    foreign = AccountFactory()
    with pytest.raises(ValidationError, match="not found"):
        AccountFactory.build(tenant_id=tenant, parent_account_id=foreign.id).full_clean()
    child = AccountFactory(tenant_id=tenant, parent_account_id=root.id)
    grandchild = AccountFactory(tenant_id=tenant, parent_account_id=child.id)
    with pytest.raises(ValidationError, match="three nodes"):
        AccountFactory.build(tenant_id=tenant, parent_account_id=grandchild.id).full_clean()
    root.parent_account_id = child.id
    with pytest.raises(ValidationError, match="acyclic"):
        root.full_clean()


def test_contact_reference_engagement_uniqueness_and_domain_override():
    tenant = uuid.uuid4()
    account = AccountFactory(tenant_id=tenant, metadata={"email_domain": "example.test"})
    ContactFactory(tenant_id=tenant, account=account, email="Person@Example.test")
    with pytest.raises(ValidationError):
        ContactFactory(tenant_id=tenant, account=account, email="person@example.test")
    with pytest.raises(ValidationError, match="account domain"):
        ContactFactory.build(tenant_id=tenant, account=account, email="person@other.test").full_clean()
    override = ContactFactory.build(tenant_id=tenant, account=account, email="person@other.test")
    override._allow_domain_override = True
    override.full_clean()
    with pytest.raises(ValidationError, match="between 0 and 100"):
        ContactFactory.build(tenant_id=tenant, account=account, engagement_score=101).full_clean()


def test_opportunity_reference_currency_date_array_and_state_rules():
    tenant = uuid.uuid4()
    account = AccountFactory(tenant_id=tenant)
    contact = ContactFactory(tenant_id=tenant, account=account)
    opportunity = OpportunityFactory(
        tenant_id=tenant,
        account=account,
        primary_contact_id=contact.id,
        currency="eur",
        product_ids=[str(uuid.uuid4())],
        competitors=["Incumbent"],
    )
    assert opportunity.currency == "EUR"
    bad_contact = ContactFactory(tenant_id=tenant)
    invalid_values = (
        {"amount": 0},
        {"probability": 101},
        {"currency": "ZZZ"},
        {"close_date": timezone.localdate() - timedelta(days=1)},
        {"product_ids": ["not-a-uuid"]},
        {"competitors": [""]},
        {"primary_contact_id": bad_contact.id},
        {"status": "won", "stage": "closed_won", "probability": 90, "closed_at": timezone.now()},
        {"status": "lost", "stage": "closed_lost", "probability": 0, "closed_at": timezone.now(), "loss_reason": ""},
    )
    for values in invalid_values:
        with pytest.raises(ValidationError):
            OpportunityFactory.build(tenant_id=tenant, account=account, **values).full_clean()
    OpportunityFactory(
        tenant_id=tenant,
        account=account,
        status="won",
        stage="closed_won",
        probability=100,
        closed_at=timezone.now(),
    )
    OpportunityFactory(
        tenant_id=tenant,
        account=account,
        status="lost",
        stage="closed_lost",
        probability=0,
        closed_at=timezone.now(),
        loss_reason="Budget",
    )


def test_activity_reference_due_completion_external_uniqueness_and_immutability():
    tenant = uuid.uuid4()
    lead = LeadFactory(tenant_id=tenant)
    with pytest.raises(ValidationError, match="future"):
        ActivityFactory.build(
            tenant_id=tenant,
            related=lead,
            activity_type="task",
            due_date=timezone.now() - timedelta(seconds=1),
        ).full_clean()
    with pytest.raises(ValidationError, match="if and only if"):
        ActivityFactory.build(tenant_id=tenant, related=lead, completed=True).full_clean()
    foreign = LeadFactory()
    with pytest.raises(ValidationError, match="not found"):
        ActivityFactory.build(tenant_id=tenant, related_to_id=foreign.id).full_clean()
    ActivityFactory(tenant_id=tenant, related=lead, activity_type="email", external_id="message-1")
    with pytest.raises(ValidationError):
        ActivityFactory(tenant_id=tenant, related=lead, activity_type="email", external_id="message-1")
    completed = ActivityFactory(tenant_id=tenant, related=lead, completed=True, completed_at=timezone.now())
    completed.subject = "Tampered"
    with pytest.raises(ValidationError, match="immutable"):
        completed.save()
    completed.refresh_from_db()
    completed.is_deleted, completed.deleted_at = True, timezone.now()
    completed._allow_admin_delete = True
    with pytest.raises(ValidationError, match="immutable"):
        completed.save()


def test_declared_constraint_and_index_names_are_complete():
    expected = {
        Lead: {
            "crm_lead_soft_del_ck",
            "crm_lead_score_range_ck",
            "crm_lead_grade_score_ck",
            "crm_lead_conversion_ck",
            "crm_lead_active_email_uniq",
        },
        Account: {
            "crm_account_soft_del_ck",
            "crm_account_active_name_uniq",
            "crm_account_employees_ck",
            "crm_account_revenue_ck",
            "crm_account_not_parent_ck",
        },
        Contact: {"crm_contact_soft_del_ck", "crm_contact_engagement_ck", "crm_contact_account_email_uniq"},
        Opportunity: {
            "crm_opportunity_soft_del_ck",
            "crm_opp_amount_positive_ck",
            "crm_opp_probability_ck",
            "crm_opp_state_consistency_ck",
        },
        Activity: {"crm_activity_soft_del_ck", "crm_activity_completion_ck", "crm_activity_external_uniq"},
    }
    for model, names in expected.items():
        assert {constraint.name for constraint in model._meta.constraints} == names
        assert all(index.name for index in model._meta.indexes)


def test_database_check_constraint_rejects_bypass_write():
    lead = LeadFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        Lead.objects.filter(pk=lead.pk).update(score=101)
