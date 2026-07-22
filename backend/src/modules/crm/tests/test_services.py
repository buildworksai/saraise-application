"""Executable contracts for the CRM v2 service layer.

These tests intentionally call services rather than models for mutations.  In
addition to happy paths they prove optimistic concurrency, transaction rollback,
idempotency and explicit dependency-unavailable outcomes.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent
from src.modules.crm import services
from src.modules.crm.integrations import (
    IntegrationUnavailable,
    LeadScoreResult,
    RevenuePredictionResult,
)
from src.modules.crm.models import (
    Account,
    AccountType,
    Activity,
    ActivityType,
    Contact,
    Lead,
    LeadScoreSource,
    LeadStatus,
    Opportunity,
    OpportunityStage,
    OpportunityStatus,
    RelatedToType,
)
from src.modules.crm.services import (
    AccountService,
    ActivityService,
    CRMServiceError,
    ContactService,
    ForecastingService,
    IntegrationService,
    LeadService,
    OpportunityService,
    StaleVersionError,
)

from .factories import AccountFactory, ContactFactory, LeadFactory, OpportunityFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant_id():
    return uuid.uuid4()


@pytest.fixture
def actor_id():
    return uuid.uuid4()


def _account_data(name="Acme"):
    return {"name": name, "website": f"https://{name.lower()}.example"}


def _opportunity_data(account, **overrides):
    data = {
        "account_id": account.id,
        "name": "Expansion",
        "amount": Decimal("10000.00"),
        "currency": "USD",
        "close_date": timezone.localdate() + timedelta(days=30),
    }
    data.update(overrides)
    return data


def test_lead_crud_assignment_rule_scoring_and_soft_delete(tenant_id, actor_id):
    lead = LeadService.create_lead(
        tenant_id,
        data={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ADA@EXAMPLE.COM",
            "company": "Analytical Engines",
            "source": "referral",
        },
        actor_id=actor_id,
        correlation_id="lead-create",
    )
    assert lead.email == "ada@example.com"
    assert (lead.score, lead.grade, lead.score_source) == (60, "B", LeadScoreSource.RULES)
    assert OutboxEvent.objects.filter(tenant_id=tenant_id, event_type="crm.lead.created").exists()

    original_version = lead.version
    lead = LeadService.update_lead(
        tenant_id,
        lead_id=lead.id,
        data={"phone": "+1 202 555 0100"},
        expected_version=original_version,
        actor_id=actor_id,
    )
    assert lead.version == original_version + 1
    with pytest.raises(StaleVersionError):
        LeadService.update_lead(
            tenant_id,
            lead_id=lead.id,
            data={"title": "CTO"},
            expected_version=original_version,
            actor_id=actor_id,
        )

    owner_id = uuid.uuid4()
    lead = LeadService.assign_lead(
        tenant_id,
        lead_id=lead.id,
        owner_id=owner_id,
        expected_version=lead.version,
        actor_id=actor_id,
    )
    assert lead.owner_id == owner_id
    LeadService.delete_lead(
        tenant_id,
        lead_id=lead.id,
        expected_version=lead.version,
        actor_id=actor_id,
    )
    lead.refresh_from_db()
    assert lead.is_deleted and lead.deleted_at is not None


def test_lead_transitions_are_guarded_and_idempotent(tenant_id, actor_id):
    lead = LeadFactory(tenant_id=tenant_id)
    contacted = LeadService.transition_lead(
        tenant_id,
        lead_id=lead.id,
        command="contact",
        transition_key="lead-contact-1",
        context={},
        expected_version=lead.version,
        actor_id=actor_id,
    )
    replay = LeadService.transition_lead(
        tenant_id,
        lead_id=lead.id,
        command="contact",
        transition_key="lead-contact-1",
        context={},
        expected_version=lead.version,
        actor_id=actor_id,
    )
    assert replay.id == contacted.id
    assert replay.version == contacted.version

    qualified = LeadService.transition_lead(
        tenant_id,
        lead_id=lead.id,
        command="qualify",
        transition_key="lead-qualify-1",
        context={},
        expected_version=contacted.version,
        actor_id=actor_id,
    )
    assert qualified.status == LeadStatus.QUALIFIED
    with pytest.raises(CRMServiceError) as exc:
        LeadService.transition_lead(
            tenant_id,
            lead_id=lead.id,
            command="contact",
            transition_key="illegal-after-qualified",
            context={},
            expected_version=qualified.version,
            actor_id=actor_id,
        )
    assert exc.value.error_code == "ILLEGAL_TRANSITION"


def test_lead_provider_scoring_success_and_explicit_unavailable(monkeypatch, tenant_id, actor_id):
    lead = LeadFactory(tenant_id=tenant_id)

    class Scorer:
        def score_lead(self, payload, *, correlation_id):
            assert payload["lead_id"] == str(lead.id)
            assert correlation_id == "score-request"
            return LeadScoreResult("verified-provider", "score-v2", 88, "A", {"fit": 9}, "req-1")

    monkeypatch.setattr(services, "get_scoring_client", lambda: Scorer())
    result = LeadService.score_lead(tenant_id, lead_id=lead.id, actor_id=actor_id, correlation_id="score-request")
    assert result.status == "succeeded"
    scored = result.unwrap()
    assert (scored.score, scored.grade, scored.score_source) == (88, "A", LeadScoreSource.PROVIDER)
    assert result.evidence["provider_request_id"] == "req-1"

    def unavailable():
        raise IntegrationUnavailable("not configured")

    monkeypatch.setattr(services, "get_scoring_client", unavailable)
    result = LeadService.score_lead(tenant_id, lead_id=lead.id, actor_id=actor_id)
    assert (result.status, result.error_code, result.http_status) == (
        "unavailable",
        "CAPABILITY_UNAVAILABLE",
        503,
    )


def test_conversion_is_complete_and_rolls_back_on_event_failure(monkeypatch, tenant_id, actor_id):
    lead = LeadFactory(tenant_id=tenant_id, company="Conversion Co", owner_id=uuid.uuid4())
    lead = LeadService.transition_lead(
        tenant_id,
        lead_id=lead.id,
        command="qualify",
        transition_key="qualify-conversion",
        context={},
        expected_version=lead.version,
        actor_id=actor_id,
    )
    result = LeadService.convert_lead(
        tenant_id,
        lead_id=lead.id,
        data={
            "amount": Decimal("25000"),
            "currency": "EUR",
            "close_date": timezone.localdate() + timedelta(days=60),
            "create_new_account": True,
        },
        expected_version=lead.version,
        transition_key="convert-1",
        actor_id=actor_id,
        correlation_id="convert-correlation",
    )
    assert result.lead.status == LeadStatus.CONVERTED
    assert result.opportunity.account_id == result.account.id
    assert result.opportunity.primary_contact_id == result.contact.id
    assert result.opportunity.owner_id == lead.owner_id
    assert result.opportunity.currency == "EUR"

    rollback_lead = LeadFactory(tenant_id=tenant_id, company="Rollback Co")
    rollback_lead = LeadService.transition_lead(
        tenant_id,
        lead_id=rollback_lead.id,
        command="qualify",
        transition_key="qualify-rollback",
        context={},
        expected_version=rollback_lead.version,
        actor_id=actor_id,
    )
    baseline = (Account.objects.count(), Contact.objects.count(), Opportunity.objects.count())

    def fail_event(*args, **kwargs):
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr(services, "publish_crm_event", fail_event)
    with pytest.raises(RuntimeError, match="outbox unavailable"):
        LeadService.convert_lead(
            tenant_id,
            lead_id=rollback_lead.id,
            data={
                "amount": Decimal("5000"),
                "close_date": timezone.localdate() + timedelta(days=30),
                "create_new_account": True,
            },
            expected_version=rollback_lead.version,
            transition_key="convert-rollback",
            actor_id=actor_id,
            correlation_id="convert-rollback",
        )
    rollback_lead.refresh_from_db()
    assert rollback_lead.status == LeadStatus.QUALIFIED
    assert (Account.objects.count(), Contact.objects.count(), Opportunity.objects.count()) == baseline


def test_account_crud_hierarchy_duplicates_and_delete_guards(tenant_id, actor_id):
    root = AccountService.create_account(tenant_id, data=_account_data("Root"), actor_id=actor_id)
    child = AccountService.create_account(
        tenant_id,
        data={**_account_data("Child"), "parent_account_id": root.id},
        actor_id=actor_id,
    )
    tree = AccountService.get_hierarchy(tenant_id, account_id=root.id)
    assert [node.id for node in tree.children] == [child.id]
    duplicate = AccountService.find_duplicates(tenant_id, name=" root ", website="")
    assert [item.id for item in duplicate.local_matches] == [root.id]
    assert duplicate.enrichment_status == "unavailable"

    root = AccountService.update_account(
        tenant_id,
        account_id=root.id,
        data={"industry": "Technology"},
        expected_version=root.version,
        actor_id=actor_id,
    )
    with pytest.raises(StaleVersionError):
        AccountService.update_account(
            tenant_id,
            account_id=root.id,
            data={"industry": "Finance"},
            expected_version=1,
            actor_id=actor_id,
        )
    with pytest.raises(CRMServiceError) as exc:
        AccountService.delete_account(
            tenant_id,
            account_id=root.id,
            expected_version=root.version,
            actor_id=actor_id,
        )
    assert exc.value.error_code == "ACCOUNT_HAS_CHILDREN"
    AccountService.delete_account(
        tenant_id,
        account_id=child.id,
        expected_version=child.version,
        actor_id=actor_id,
    )
    root.refresh_from_db()
    AccountService.delete_account(
        tenant_id,
        account_id=root.id,
        expected_version=root.version,
        actor_id=actor_id,
    )
    root.refresh_from_db()
    assert root.is_deleted


def test_contact_crud_domain_override_engagement_and_timeline(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id, metadata={"email_domain": "acme.test"})
    with pytest.raises(Exception):
        ContactService.create_contact(
            tenant_id,
            data={"account_id": account.id, "last_name": "Wrong", "email": "wrong@elsewhere.test"},
            actor_id=actor_id,
        )
    contact = ContactService.create_contact(
        tenant_id,
        data={"account_id": account.id, "first_name": "Grace", "last_name": "Hopper", "email": "grace@elsewhere.test"},
        actor_id=actor_id,
        allow_domain_override=True,
    )
    contact = ContactService.update_contact(
        tenant_id,
        contact_id=contact.id,
        data={"department": "Engineering"},
        expected_version=contact.version,
        actor_id=actor_id,
        allow_domain_override=True,
    )
    for index in range(3):
        ActivityService.create_activity(
            tenant_id,
            data={
                "activity_type": ActivityType.CALL,
                "related_to_type": RelatedToType.CONTACT,
                "related_to_id": contact.id,
                "subject": f"Conversation {index}",
            },
            actor_id=actor_id,
        )
    contact = ContactService.recalculate_engagement(
        tenant_id, contact_id=contact.id, as_of=timezone.now(), actor_id=actor_id
    )
    assert contact.engagement_score == 30
    assert ContactService.get_timeline(tenant_id, contact_id=contact.id).count() == 3
    with pytest.raises(CRMServiceError) as exc:
        ContactService.get_timeline(tenant_id, contact_id=contact.id, page=0)
    assert exc.value.error_code == "INVALID_PAGE"
    ContactService.delete_contact(
        tenant_id,
        contact_id=contact.id,
        expected_version=contact.version,
        actor_id=actor_id,
    )
    contact.refresh_from_db()
    assert contact.is_deleted


def test_opportunity_crud_transition_and_close_won(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id, account_type=AccountType.PROSPECT)
    opportunity = OpportunityService.create_opportunity(tenant_id, data=_opportunity_data(account), actor_id=actor_id)
    opportunity = OpportunityService.update_opportunity(
        tenant_id,
        opportunity_id=opportunity.id,
        data={"description": "Qualified expansion"},
        expected_version=opportunity.version,
        actor_id=actor_id,
    )
    with pytest.raises(CRMServiceError) as exc:
        OpportunityService.update_opportunity(
            tenant_id,
            opportunity_id=opportunity.id,
            data={"stage": OpportunityStage.NEGOTIATION},
            expected_version=opportunity.version,
            actor_id=actor_id,
        )
    assert exc.value.error_code == "IMMUTABLE_FIELD"
    opportunity = OpportunityService.transition_stage(
        tenant_id,
        opportunity_id=opportunity.id,
        command="advance_to_qualification",
        transition_key="opp-qualify",
        expected_version=opportunity.version,
        actor_id=actor_id,
    )
    won = OpportunityService.close_won(
        tenant_id,
        opportunity_id=opportunity.id,
        transition_key="opp-won",
        expected_version=opportunity.version,
        actor_id=actor_id,
    )
    account.refresh_from_db()
    assert (won.stage, won.status, won.probability) == (
        OpportunityStage.CLOSED_WON,
        OpportunityStatus.WON,
        100,
    )
    assert account.account_type == AccountType.CUSTOMER
    assert (
        Activity.objects.filter(
            tenant_id=tenant_id,
            related_to_type=RelatedToType.OPPORTUNITY,
            related_to_id=won.id,
            subject="Opportunity closed as won",
        ).count()
        == 1
    )


def test_opportunity_closing_rolls_back_and_loss_requires_reason(monkeypatch, tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id, account_type=AccountType.PROSPECT)
    opportunity = OpportunityFactory(tenant_id=tenant_id, account_id=account.id)

    def fail_activity(*args, **kwargs):
        raise RuntimeError("activity unavailable")

    monkeypatch.setattr(ActivityService, "create_activity", fail_activity)
    with pytest.raises(RuntimeError, match="activity unavailable"):
        OpportunityService.close_won(
            tenant_id,
            opportunity_id=opportunity.id,
            transition_key="rollback-won",
            expected_version=opportunity.version,
            actor_id=actor_id,
        )
    opportunity.refresh_from_db()
    account.refresh_from_db()
    assert opportunity.status == OpportunityStatus.OPEN
    assert account.account_type == AccountType.PROSPECT

    with pytest.raises(CRMServiceError) as exc:
        OpportunityService.close_lost(
            tenant_id,
            opportunity_id=opportunity.id,
            loss_reason=" ",
            transition_key="lost-empty",
            expected_version=opportunity.version,
            actor_id=actor_id,
        )
    assert exc.value.error_code == "LOSS_REASON_REQUIRED"


def test_sales_order_acknowledgement_is_verified_stateful_and_idempotent(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id)
    open_opportunity = OpportunityFactory(tenant_id=tenant_id, account_id=account.id)
    with pytest.raises(CRMServiceError) as exc:
        OpportunityService.acknowledge_sales_order(
            tenant_id,
            opportunity_id=open_opportunity.id,
            order_id=uuid.uuid4(),
            acknowledgement_id=uuid.uuid4(),
            idempotency_key="ack-open",
            actor_id=actor_id,
            correlation_id="ack-open",
        )
    assert exc.value.error_code == "OPPORTUNITY_NOT_WON"

    won = OpportunityService.close_won(
        tenant_id,
        opportunity_id=open_opportunity.id,
        transition_key="close-for-order",
        expected_version=open_opportunity.version,
        actor_id=actor_id,
    )
    order_id, acknowledgement_id = uuid.uuid4(), uuid.uuid4()
    linked = OpportunityService.acknowledge_sales_order(
        tenant_id,
        opportunity_id=won.id,
        order_id=order_id,
        acknowledgement_id=acknowledgement_id,
        idempotency_key="ack-1",
        actor_id=actor_id,
        correlation_id="ack-correlation",
    )
    version = linked.version
    replay = OpportunityService.acknowledge_sales_order(
        tenant_id,
        opportunity_id=won.id,
        order_id=order_id,
        acknowledgement_id=acknowledgement_id,
        idempotency_key="ack-1",
        actor_id=actor_id,
        correlation_id="ack-correlation",
    )
    assert replay.version == version
    with pytest.raises(CRMServiceError) as exc:
        OpportunityService.acknowledge_sales_order(
            tenant_id,
            opportunity_id=won.id,
            order_id=uuid.uuid4(),
            acknowledgement_id=acknowledgement_id,
            idempotency_key="ack-2",
            actor_id=actor_id,
            correlation_id="ack-correlation",
        )
    assert exc.value.error_code == "ORDER_ACKNOWLEDGEMENT_CONFLICT"


def test_activity_crud_completion_immutability_delete_and_timeline(tenant_id, actor_id):
    lead = LeadFactory(tenant_id=tenant_id)
    activity = ActivityService.create_activity(
        tenant_id,
        data={
            "activity_type": ActivityType.TASK,
            "related_to_type": RelatedToType.LEAD,
            "related_to_id": lead.id,
            "subject": "Follow up",
            "due_date": timezone.now() + timedelta(days=1),
        },
        actor_id=actor_id,
    )
    activity = ActivityService.update_activity(
        tenant_id,
        activity_id=activity.id,
        data={"description": "Call after lunch"},
        expected_version=activity.version,
        actor_id=actor_id,
    )
    completed = ActivityService.complete_activity(
        tenant_id,
        activity_id=activity.id,
        transition_key="complete-1",
        expected_version=activity.version,
        actor_id=actor_id,
    )
    replay = ActivityService.complete_activity(
        tenant_id,
        activity_id=activity.id,
        transition_key="complete-1",
        expected_version=activity.version,
        actor_id=actor_id,
    )
    assert replay.version == completed.version
    with pytest.raises(CRMServiceError) as exc:
        ActivityService.complete_activity(
            tenant_id,
            activity_id=activity.id,
            transition_key="complete-2",
            expected_version=completed.version,
            actor_id=actor_id,
        )
    assert exc.value.error_code == "IDEMPOTENCY_CONFLICT"
    with pytest.raises(CRMServiceError) as exc:
        ActivityService.update_activity(
            tenant_id,
            activity_id=activity.id,
            data={"subject": "Mutated"},
            expected_version=completed.version,
            actor_id=actor_id,
        )
    assert exc.value.error_code == "ACTIVITY_IMMUTABLE"
    assert (
        ActivityService.get_timeline(tenant_id, related_to_type=RelatedToType.LEAD, related_to_id=lead.id).count() == 1
    )
    with pytest.raises(Exception):
        ActivityService.delete_activity(
            tenant_id,
            activity_id=activity.id,
            expected_version=completed.version,
            actor_id=actor_id,
        )
    ActivityService.delete_activity(
        tenant_id,
        activity_id=activity.id,
        expected_version=completed.version,
        actor_id=actor_id,
        is_administrator=True,
    )
    activity.refresh_from_db()
    assert activity.is_deleted


def test_external_activity_sync_is_idempotent_and_conflict_safe(tenant_id):
    lead = LeadFactory(tenant_id=tenant_id)
    event = {
        "activity_type": ActivityType.EMAIL,
        "related_to_type": RelatedToType.LEAD,
        "related_to_id": lead.id,
        "subject": "Published email",
        "external_id": "message-42",
    }
    first = ActivityService.sync_external_activity(
        tenant_id, event=event, idempotency_key="delivery-1", correlation_id="sync-1"
    )
    replay = ActivityService.sync_external_activity(
        tenant_id, event=event, idempotency_key="delivery-1", correlation_id="sync-1"
    )
    assert first.id == replay.id
    assert Activity.objects.filter(tenant_id=tenant_id, external_id="message-42").count() == 1
    with pytest.raises(CRMServiceError) as exc:
        ActivityService.sync_external_activity(
            tenant_id, event=event, idempotency_key="delivery-2", correlation_id="sync-2"
        )
    assert exc.value.error_code == "IDEMPOTENCY_CONFLICT"


def test_forecasts_are_tenant_owner_stage_and_currency_bounded(tenant_id):
    account = AccountFactory(tenant_id=tenant_id)
    owner = uuid.uuid4()
    OpportunityFactory(
        tenant_id=tenant_id,
        account_id=account.id,
        amount=Decimal("1000"),
        probability=20,
        currency="USD",
        owner_id=owner,
        stage=OpportunityStage.PROSPECTING,
    )
    OpportunityFactory(
        tenant_id=tenant_id,
        account_id=account.id,
        amount=Decimal("2000"),
        probability=50,
        currency="EUR",
        owner_id=owner,
        stage=OpportunityStage.PROPOSAL,
    )
    OpportunityFactory(tenant_id=uuid.uuid4(), amount=Decimal("999999"), currency="USD")

    pipeline = ForecastingService.get_weighted_pipeline(tenant_id, owner_id=owner, period_days=90)
    by_currency = {row.currency: row for row in pipeline.currencies}
    assert by_currency["USD"].total_pipeline_value == Decimal("1000")
    assert by_currency["USD"].weighted_pipeline_value == Decimal("200")
    assert by_currency["EUR"].weighted_pipeline_value == Decimal("1000")
    stages = ForecastingService.get_pipeline_by_stage(tenant_id, owner_id=owner, period_days=90)
    assert {(row.stage, row.currency) for row in stages} == {
        (OpportunityStage.PROSPECTING, "USD"),
        (OpportunityStage.PROPOSAL, "EUR"),
    }

    won = OpportunityFactory(tenant_id=tenant_id, account_id=account.id, owner_id=owner)
    lost = OpportunityFactory(tenant_id=tenant_id, account_id=account.id, owner_id=owner)
    now = timezone.now()
    Opportunity.objects.filter(pk=won.pk).update(
        stage=OpportunityStage.CLOSED_WON,
        status=OpportunityStatus.WON,
        probability=100,
        closed_at=now,
    )
    Opportunity.objects.filter(pk=lost.pk).update(
        stage=OpportunityStage.CLOSED_LOST,
        status=OpportunityStatus.LOST,
        probability=0,
        loss_reason="Budget",
        closed_at=now,
    )
    rate = ForecastingService.get_win_rate(tenant_id, owner_id=owner, period_days=90)
    assert (rate.win_rate, rate.won_count, rate.lost_count) == (Decimal("50.00"), 1, 1)
    with pytest.raises(CRMServiceError):
        ForecastingService.get_weighted_pipeline(tenant_id, period_days=0)


def test_revenue_prediction_success_and_explicit_unavailable(monkeypatch, tenant_id, actor_id):
    class Predictor:
        def predict_revenue(self, payload, *, correlation_id):
            assert payload["period_days"] == 30
            return RevenuePredictionResult(
                "forecast-provider",
                "forecast-v3",
                Decimal("5432.10"),
                "USD",
                Decimal("0.81"),
                {"pipeline_rows": 4},
                "2026-07-22T00:00:00Z",
                "prediction-1",
            )

    monkeypatch.setattr(services, "get_revenue_prediction_client", lambda: Predictor())
    result = ForecastingService.predict_revenue(
        tenant_id, period_days=30, actor_id=actor_id, correlation_id="prediction-correlation"
    )
    assert result.status == "succeeded"
    assert result.unwrap().amount == Decimal("5432.10")
    assert result.evidence["provider_request_id"] == "prediction-1"

    def unavailable():
        raise IntegrationUnavailable("not configured")

    monkeypatch.setattr(services, "get_revenue_prediction_client", unavailable)
    result = ForecastingService.predict_revenue(
        tenant_id, period_days=30, actor_id=actor_id, correlation_id="prediction-unavailable"
    )
    assert (result.status, result.error_code, result.http_status) == (
        "unavailable",
        "CAPABILITY_UNAVAILABLE",
        503,
    )


def test_legacy_conversion_facade_delegates_to_real_workflow(tenant_id, actor_id):
    lead = LeadFactory(tenant_id=tenant_id, company="Legacy Co")
    result = IntegrationService.convert_lead_to_opportunity(
        lead.id,
        tenant_id,
        {
            "amount": Decimal("5000"),
            "currency": "USD",
            "close_date": timezone.localdate() + timedelta(days=30),
        },
        actor_id,
    )
    assert result["lead"].status == LeadStatus.CONVERTED
    assert result["opportunity"].account_id == result["account"].id


def test_all_service_reads_fail_closed_for_unknown_tenant(tenant_id):
    lead = LeadFactory(tenant_id=tenant_id)
    account = AccountFactory(tenant_id=tenant_id)
    contact = ContactFactory(tenant_id=tenant_id, account_id=account.id)
    other_tenant = uuid.uuid4()
    with pytest.raises(ObjectDoesNotExist):
        LeadService.update_lead(
            other_tenant,
            lead_id=lead.id,
            data={"title": "cross-tenant"},
            expected_version=lead.version,
            actor_id=None,
        )
    with pytest.raises(ObjectDoesNotExist):
        AccountService.get_hierarchy(other_tenant, account_id=account.id)
    with pytest.raises(ObjectDoesNotExist):
        ContactService.get_timeline(other_tenant, contact_id=contact.id)
