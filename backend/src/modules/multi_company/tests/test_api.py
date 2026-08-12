"""
API tests for Multi-Company module.
"""

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.test import APIClient

from src.core.access.permissions import RequiresAccess
from src.core.async_jobs.models import AsyncJob
from src.modules.multi_company import api as multi_company_api
from src.modules.multi_company.integrations import IntegrationError
from src.modules.multi_company.models import Company, ConsolidationRun, IntercompanyTransaction, TransferPricingRule
from src.modules.multi_company.services import (
    DEFAULT_SETTINGS,
    CompanyRegistryService,
    ConfigurationUnavailable,
    ConflictError,
    ConsolidationService,
    DomainError,
    IntercompanyTransactionService,
    MultiCompanyConfigurationService,
)

User = get_user_model()


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def authenticated_user(db):
    """Create authenticated user with tenant."""
    from unittest.mock import patch

    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = "tenant_admin"
            profile.save()
    return User.objects.get(pk=user.pk)


@pytest.fixture
def v2_auth(api_client, authenticated_user, monkeypatch):
    monkeypatch.setattr(RequiresAccess, "has_permission", lambda self, request, view: True)
    authenticated_user.has_perm = lambda perm: True
    api_client.force_authenticate(user=authenticated_user)
    return api_client, authenticated_user, uuid.UUID(authenticated_user.profile.tenant_id)


def _company(tenant_id, code, **overrides):
    data = {
        "tenant_id": tenant_id,
        "company_code": code,
        "company_name": f"{code} Company",
        "legal_name": f"{code} Legal",
        "currency": "USD",
        "consolidation_group": "GROUP",
    }
    data.update(overrides)
    return Company.objects.create(**data)


def _transaction(tenant_id, source, target, **overrides):
    data = {
        "tenant_id": tenant_id,
        "source_company": source,
        "target_company": target,
        "reference": overrides.pop("reference", "IC-API"),
        "transaction_type": "sale",
        "product_category": "standard",
        "original_amount": Decimal("25.0000"),
        "amount": Decimal("25.0000"),
        "currency": "USD",
        "transaction_date": date(2024, 1, 1),
    }
    data.update(overrides)
    return IntercompanyTransaction.objects.create(**data)


@pytest.mark.django_db
class TestCompanyAPI:
    """Test Company API endpoints."""

    def test_list_companies(self, api_client, authenticated_user):
        """Test listing companies."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)

        Company.objects.create(
            tenant_id=tenant_id,
            company_code="COMP-001",
            company_name="Test Company",
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v1/multi-company/companies/")

        assert response.status_code == status.HTTP_200_OK
        assert response["Deprecation"] == "true"
        assert response["Link"] == '</api/v2/multi-company/>; rel="successor-version"'
        assert len(response.data) > 0

    def test_create_company(self, api_client, authenticated_user):
        """Test creating a company."""
        api_client.force_authenticate(user=authenticated_user)

        data = {
            "company_code": "COMP-002",
            "company_name": "Another Company",
        }

        response = api_client.post("/api/v1/multi-company/companies/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response["Sunset"] == multi_company_api.DeprecatedV1HeadersMixin.sunset
        assert response.data["company_code"] == "COMP-002"


@pytest.mark.django_db
def test_v1_company_viewset_tenant_and_destroy_delegate_fail_closed(authenticated_user, monkeypatch):
    tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
    company = _company(tenant_id, "V1D")
    view = multi_company_api.CompanyViewSet()
    view.request = SimpleNamespace(user=authenticated_user, correlation_id="corr-v1-destroy")
    calls = []
    monkeypatch.setattr(
        CompanyRegistryService,
        "delete_company",
        lambda self, tenant, company_id, actor, correlation, expected: calls.append(
            (tenant, company_id, actor, correlation, expected)
        ),
    )

    view.perform_destroy(company)

    assert calls == [(tenant_id, company.pk, str(authenticated_user.id), "corr-v1-destroy", company.version)]

    view.request = SimpleNamespace(user=SimpleNamespace(profile=SimpleNamespace(tenant_id="bad-tenant")))
    with pytest.raises(PermissionDenied):
        view._tenant_id()


@pytest.mark.django_db
def test_v2_transaction_cancel_validates_payload_and_dispatches_service(api_client, authenticated_user, monkeypatch):
    tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
    source = Company.objects.create(
        tenant_id=tenant_id,
        company_code="SRC",
        company_name="Source",
        legal_name="Source",
        currency="USD",
    )
    target = Company.objects.create(
        tenant_id=tenant_id,
        company_code="TGT",
        company_name="Target",
        legal_name="Target",
        currency="USD",
    )
    transaction = IntercompanyTransaction.objects.create(
        tenant_id=tenant_id,
        source_company=source,
        target_company=target,
        reference="IC-001",
        transaction_type="sale",
        original_amount=Decimal("25.0000"),
        amount=Decimal("25.0000"),
        currency="USD",
        transaction_date=date(2024, 1, 1),
    )
    calls = {}

    def fake_cancel(tenant, transaction_id, actor, correlation_id, *, transition_key, reason):
        calls.update(
            {
                "tenant": tenant,
                "transaction_id": transaction_id,
                "actor": actor,
                "correlation_id": correlation_id,
                "transition_key": transition_key,
                "reason": reason,
            }
        )
        transaction.cancellation_reason = reason
        return transaction

    monkeypatch.setattr(RequiresAccess, "has_permission", lambda self, request, view: True)
    monkeypatch.setattr(IntercompanyTransactionService, "cancel", staticmethod(fake_cancel))
    api_client.force_authenticate(user=authenticated_user)

    response = api_client.post(
        f"/api/v2/multi-company/transactions/{transaction.id}/cancel/",
        {"transition_key": "cancel-once", "reason": "Entered in error"},
        format="json",
        HTTP_X_CORRELATION_ID="corr-cancel",
    )

    assert response.status_code == status.HTTP_200_OK
    assert calls["tenant"] == tenant_id
    assert calls["transaction_id"] == str(transaction.id)
    assert calls["actor"] == str(authenticated_user.id)
    assert uuid.UUID(calls["correlation_id"])
    assert calls["transition_key"] == "cancel-once"
    assert calls["reason"] == "Entered in error"
    assert response.data["cancellation_reason"] == "Entered in error"


@pytest.mark.django_db
def test_v2_transport_helpers_validate_pagination_filters_and_exception_translation():
    paginator = multi_company_api.MultiCompanyPagination()
    assert paginator.get_page_size(SimpleNamespace(query_params={})) == 25
    assert paginator.get_page_size(SimpleNamespace(query_params={"page_size": "2"})) == 2
    with pytest.raises(ValidationError):
        paginator.get_page_size(SimpleNamespace(query_params={"page_size": "bad"}))
    with pytest.raises(ValidationError):
        paginator.get_page_size(SimpleNamespace(query_params={"page_size": "101"}))

    assert multi_company_api._boolean("true", "is_active") is True
    with pytest.raises(ValidationError):
        multi_company_api._boolean("yes", "is_active")
    assert multi_company_api._date("2024-01-31", "period_start") == date(2024, 1, 31)
    assert multi_company_api._datetime("2024-01-31T10:00:00Z", "created_after").tzinfo is not None
    assert multi_company_api._ordering("-company_code", {"company_code"}, "company_code") == ("-company_code",)
    with pytest.raises(ValidationError):
        multi_company_api._uuid("not-a-uuid", "company_id")
    with pytest.raises(ValidationError):
        multi_company_api._date("31-01-2024", "period_start")
    with pytest.raises(ValidationError):
        multi_company_api._datetime("not-a-time", "created_after")
    with pytest.raises(ValidationError):
        multi_company_api._ordering("unsupported", {"company_code"}, "company_code")
    with pytest.raises(ValidationError):
        multi_company_api._choice("CAD", "currency", {"USD"})

    assert isinstance(
        multi_company_api._translate_service_exception(ConfigurationUnavailable("missing")),
        multi_company_api.OperationFailed,
    )
    assert isinstance(
        multi_company_api._translate_service_exception(ConflictError("conflict")), multi_company_api.OperationFailed
    )
    assert isinstance(
        multi_company_api._translate_service_exception(IntegrationError("down", dependency="ledger")),
        multi_company_api.OperationFailed,
    )
    assert isinstance(
        multi_company_api._translate_service_exception(DjangoValidationError({"field": ["bad"]})), ValidationError
    )
    assert isinstance(
        multi_company_api._translate_service_exception(DjangoPermissionDenied("denied")), PermissionDenied
    )
    assert isinstance(
        multi_company_api._translate_service_exception(DomainError("domain")), multi_company_api.OperationFailed
    )
    assert isinstance(
        multi_company_api._translate_service_exception(multi_company_api.NotFoundError("missing")), NotFound
    )


def test_v2_tenant_governed_helpers_fail_closed_and_delegate_errors(monkeypatch):
    tenant_id = uuid.uuid4()
    view = multi_company_api.TenantGovernedViewSet()
    view.request = SimpleNamespace(
        tenant_id=tenant_id,
        user=SimpleNamespace(id="actor-1"),
        headers={"Idempotency-Key": "mc-key"},
        query_params={},
    )
    assert view.tenant_id() == tenant_id
    assert view.actor_id() == "actor-1"
    assert view.idempotency_key() == "mc-key"

    view.request = SimpleNamespace(tenant_id="not-a-uuid", user=SimpleNamespace(id="actor-1"), headers={})
    with pytest.raises(PermissionDenied):
        view.tenant_id()

    view.request = SimpleNamespace(tenant_id=tenant_id, user=SimpleNamespace(id=None), headers={})
    with pytest.raises(PermissionDenied):
        view.actor_id()

    view.request = SimpleNamespace(tenant_id=tenant_id, user=SimpleNamespace(id="actor-1"), headers={})
    with pytest.raises(ValidationError):
        view.idempotency_key()

    view.request = SimpleNamespace(
        tenant_id=tenant_id,
        user=SimpleNamespace(id="actor-1"),
        headers={"Idempotency-Key": "x" * 256},
    )
    with pytest.raises(ValidationError):
        view.idempotency_key()

    view.paginate_queryset = lambda rows: None
    with pytest.raises(RuntimeError):
        view.paginated([SimpleNamespace(id=uuid.uuid4())], multi_company_api.CompanyListSerializer)

    captured = []
    monkeypatch.setattr(
        multi_company_api.APIView,
        "handle_exception",
        lambda self, exc: captured.append(exc) or multi_company_api.Response({"mapped": type(exc).__name__}),
    )
    response = view.handle_exception(ConflictError("conflict"))
    assert response.data == {"mapped": "OperationFailed"}
    assert captured[0].status_code == status.HTTP_409_CONFLICT


def test_v2_projection_sort_and_query_key_validation_are_deterministic():
    rows = [
        {"reference": "B", "source_amount": Decimal("10.00"), "variance": Decimal("1.00")},
        {"reference": "A", "source_amount": Decimal("20.00"), "variance": Decimal("0.00")},
        {"reference": "C", "variance": None},
    ]

    assert [row["reference"] for row in multi_company_api._sort_projection(rows, ("amount", "-reference"))] == [
        "B",
        "A",
        "C",
    ]

    with pytest.raises(ValidationError):
        multi_company_api._validate_query_keys({"unsupported": "1"}, {"known"})


@pytest.mark.django_db
def test_v2_company_filters_hierarchy_and_lifecycle_dispatch(v2_auth, monkeypatch):
    api_client, authenticated_user, tenant_id = v2_auth
    parent = _company(tenant_id, "HQ", company_name="Holding")
    _company(tenant_id, "SUB", parent_company=parent)
    calls = {}

    def fake_update(tenant, company_id, actor, correlation_id, expected_version, changes):
        calls["update"] = (tenant, company_id, actor, correlation_id, expected_version, changes)
        parent.company_name = changes["company_name"]
        return parent

    def fake_deactivate(tenant, company_id, actor, correlation_id, expected_version, transition_key=""):
        calls["deactivate"] = (tenant, company_id, actor, correlation_id, expected_version, transition_key)
        parent.is_active = False
        return parent

    def fake_create(tenant, actor, correlation_id, payload, idempotency_key):
        calls["create"] = (tenant, actor, correlation_id, payload, idempotency_key)
        return _company(tenant, payload["company_code"], company_name=payload["company_name"])

    def fake_delete(tenant, company_id, actor, correlation_id, expected_version):
        calls["delete"] = (tenant, company_id, actor, correlation_id, expected_version)

    def fake_reactivate(tenant, company_id, actor, correlation_id, expected_version, transition_key=""):
        calls["reactivate"] = (tenant, company_id, actor, correlation_id, expected_version, transition_key)
        parent.is_active = True
        return parent

    monkeypatch.setattr(CompanyRegistryService, "create_company", staticmethod(fake_create))
    monkeypatch.setattr(CompanyRegistryService, "update_company", staticmethod(fake_update))
    monkeypatch.setattr(CompanyRegistryService, "delete_company", staticmethod(fake_delete))
    monkeypatch.setattr(CompanyRegistryService, "deactivate_company", staticmethod(fake_deactivate))
    monkeypatch.setattr(CompanyRegistryService, "reactivate_company", staticmethod(fake_reactivate))

    list_response = api_client.get(
        "/api/v2/multi-company/companies/",
        {"search": "hold", "is_active": "true", "currency": "usd", "ordering": "company_code"},
    )
    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.data[0]["company_code"] == "HQ"

    created = api_client.post(
        "/api/v2/multi-company/companies/",
        {
            "company_code": "NEW",
            "company_name": "New Company",
            "legal_name": "New Company LLC",
            "currency": "USD",
            "idempotency_key": "company-create-api",
        },
        format="json",
        HTTP_X_CORRELATION_ID="corr-company-create",
    )
    assert created.status_code == status.HTTP_201_CREATED
    assert calls["create"][0] == tenant_id
    assert calls["create"][1] == str(authenticated_user.id)
    assert calls["create"][4] == "company-create-api"

    hierarchy = api_client.get("/api/v2/multi-company/companies/hierarchy/", {"root_company_id": str(parent.id)})
    assert hierarchy.status_code == status.HTTP_200_OK
    assert hierarchy.data[0]["children"][0]["company_code"] == "SUB"

    subsidiaries = api_client.get(f"/api/v2/multi-company/companies/{parent.id}/subsidiaries/", {"recursive": "true"})
    assert subsidiaries.status_code == status.HTTP_200_OK
    assert subsidiaries.data[0]["company_code"] == "SUB"

    updated = api_client.patch(
        f"/api/v2/multi-company/companies/{parent.id}/",
        {"expected_version": parent.version, "company_name": "Renamed"},
        format="json",
        HTTP_X_CORRELATION_ID="corr-company-update",
    )
    assert updated.status_code == status.HTTP_200_OK
    assert calls["update"][0] == tenant_id
    assert calls["update"][2] == str(authenticated_user.id)
    assert calls["update"][4] == parent.version

    deactivated = api_client.post(
        f"/api/v2/multi-company/companies/{parent.id}/deactivate/",
        {"expected_version": parent.version, "transition_key": "deactivate-api"},
        format="json",
    )
    assert deactivated.status_code == status.HTTP_200_OK
    assert calls["deactivate"][5] == "deactivate-api"

    reactivated = api_client.post(
        f"/api/v2/multi-company/companies/{parent.id}/reactivate/",
        {"expected_version": parent.version, "transition_key": "reactivate-api"},
        format="json",
    )
    assert reactivated.status_code == status.HTTP_200_OK
    assert calls["reactivate"][5] == "reactivate-api"

    deleted = api_client.delete(
        f"/api/v2/multi-company/companies/{parent.id}/",
        {"expected_version": parent.version, "transition_key": "delete-api"},
        format="json",
    )
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    assert calls["delete"][4] == parent.version

    invalid = api_client.get("/api/v2/multi-company/companies/", {"unknown": "field"})
    assert invalid.status_code == status.HTTP_400_BAD_REQUEST

    invalid_currency = api_client.get("/api/v2/multi-company/companies/", {"currency": "XXX"})
    assert invalid_currency.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_v2_access_grants_revoke_and_active_filters(v2_auth):
    api_client, _, tenant_id = v2_auth
    company = _company(tenant_id, "ACC")

    created = api_client.post(
        "/api/v2/multi-company/company-access/",
        {"company_id": str(company.id), "subject_id": "operator", "role": "operator"},
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED

    listed = api_client.get(
        "/api/v2/multi-company/company-access/",
        {"company_id": str(company.id), "subject_id": "operator", "role": "operator"},
    )
    assert listed.status_code == status.HTTP_200_OK
    assert listed.data[0]["subject_id"] == "operator"

    revoked = api_client.post(
        f"/api/v2/multi-company/company-access/{created.data['id']}/revoke/",
        {"reason": "Access review"},
        format="json",
    )
    assert revoked.status_code == status.HTTP_200_OK
    assert revoked.data["is_deleted"] is True


@pytest.mark.django_db
def test_v2_transaction_list_actions_enqueue_reverse_and_reconciliation(v2_auth, monkeypatch):
    api_client, _, tenant_id = v2_auth
    source = _company(tenant_id, "SRC")
    target = _company(tenant_id, "TGT")
    tx = _transaction(tenant_id, source, target, status="approved")
    posted = _transaction(tenant_id, source, target, reference="IC-POSTED", status="posted")
    calls = {}

    def fake_post(tenant, transaction_id, actor, correlation_id, idempotency_key, transition_key):
        calls["post"] = (tenant, transaction_id, actor, correlation_id, idempotency_key, transition_key)
        return AsyncJob.objects.create(
            tenant_id=tenant,
            actor_id=actor,
            command="multi_company.transaction.post",
            idempotency_key=idempotency_key,
            payload={"transaction_id": transaction_id},
            correlation_id=correlation_id,
        )

    def fake_reverse(tenant, transaction_id, actor, correlation_id, reason, idempotency_key):
        calls["reverse"] = (tenant, transaction_id, actor, correlation_id, reason, idempotency_key)
        return _transaction(tenant, target, source, reference=f"REV-{idempotency_key}", status="approved")

    monkeypatch.setattr(IntercompanyTransactionService, "post", staticmethod(fake_post))
    monkeypatch.setattr(IntercompanyTransactionService, "reverse", staticmethod(fake_reverse))

    list_response = api_client.get(
        "/api/v2/multi-company/transactions/",
        {"status": "approved", "source_company_id": str(source.id), "ordering": "reference"},
    )
    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.data[0]["reference"] == "IC-API"

    enqueued = api_client.post(
        f"/api/v2/multi-company/transactions/{tx.id}/post/",
        {"transition_key": "post-api"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="post-api-key",
    )
    assert enqueued.status_code == status.HTTP_202_ACCEPTED
    assert calls["post"][4] == "post-api-key"

    reversed_response = api_client.post(
        f"/api/v2/multi-company/transactions/{posted.id}/reverse/",
        {"reason": "Correction"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="reverse-api-key",
    )
    assert reversed_response.status_code == status.HTTP_201_CREATED
    assert calls["reverse"][4] == "Correction"

    reconciliation = api_client.get("/api/v2/multi-company/reconciliation/", {"variance_status": "matched"})
    assert reconciliation.status_code == status.HTTP_200_OK
    invalid = api_client.get("/api/v2/multi-company/reconciliation/", {"variance_status": "bad"})
    assert invalid.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_v2_consolidation_actions_eliminations_and_report(v2_auth, monkeypatch):
    api_client, _, tenant_id = v2_auth
    source = _company(tenant_id, "SRC")
    target = _company(tenant_id, "TGT")
    run = ConsolidationRun.objects.create(
        tenant_id=tenant_id,
        name="Close",
        consolidation_group="GROUP",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 31),
        reporting_currency="USD",
        translation_method="current_rate",
        total_companies=2,
        created_by="controller",
        updated_by="controller",
        correlation_id="corr-api-run",
    )
    calls = {}

    monkeypatch.setattr(
        ConsolidationService,
        "create_run",
        staticmethod(
            lambda tenant, actor, corr, payload: SimpleNamespace(
                id=uuid.uuid4(),
                status="draft",
                total_companies=2,
                total_eliminations=0,
                elimination_total=Decimal("0.0000"),
                minority_interest_total=Decimal("0.0000"),
                job_id=None,
                version=1,
                created_at=None,
                updated_at=None,
                allowed_commands=[],
                denial_reasons={},
                **payload,
            )
        ),
    )

    def fake_execute(tenant, run_id, actor, correlation_id, idempotency_key, transition_key):
        calls["execute"] = (tenant, run_id, actor, correlation_id, idempotency_key, transition_key)
        return AsyncJob.objects.create(
            tenant_id=tenant,
            actor_id=actor,
            command="multi_company.consolidation.execute",
            idempotency_key=idempotency_key,
            payload={"run_id": run_id},
            correlation_id=correlation_id,
        )

    monkeypatch.setattr(ConsolidationService, "execute", staticmethod(fake_execute))
    monkeypatch.setattr(
        ConsolidationService,
        "get_report",
        staticmethod(lambda tenant, run_id: {"currency": "USD", "total": "0.0000"}),
    )

    created = api_client.post(
        "/api/v2/multi-company/consolidation-runs/",
        {
            "name": "Close",
            "consolidation_group": "GROUP",
            "period_start": "2024-01-01",
            "period_end": "2024-01-31",
            "reporting_currency": "USD",
            "translation_method": "current_rate",
        },
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED

    job = api_client.post(
        f"/api/v2/multi-company/consolidation-runs/{run.id}/execute/",
        {"transition_key": "execute-api"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="execute-key",
    )
    assert job.status_code == status.HTTP_202_ACCEPTED
    assert calls["execute"][4] == "execute-key"

    elimination = api_client.post(
        f"/api/v2/multi-company/consolidation-runs/{run.id}/eliminations/",
        {
            "elimination_type": "intercompany_balance",
            "source_company_id": str(source.id),
            "target_company_id": str(target.id),
            "debit_account": "4000",
            "credit_account": "2000",
            "amount": "25.0000",
            "currency": "USD",
            "description": "Manual",
        },
        format="json",
    )
    assert elimination.status_code == status.HTTP_201_CREATED

    report = api_client.get(f"/api/v2/multi-company/consolidation-runs/{run.id}/report/")
    assert report.status_code == status.HTTP_200_OK
    assert report.data["currency"] == "USD"


@pytest.mark.django_db
def test_v2_transfer_pricing_configuration_export_import_and_job_lookup(v2_auth, monkeypatch):
    api_client, authenticated_user, tenant_id = v2_auth
    monkeypatch.setenv("MULTI_COMPANY_EXPORT_SIGNING_KEY", "api-signing-key")
    source = _company(tenant_id, "SRC")
    target = _company(tenant_id, "TGT")
    config = MultiCompanyConfigurationService.create_draft(
        tenant_id,
        "author",
        "corr-config",
        "development",
        DEFAULT_SETTINGS,
        "Defaults",
    )
    MultiCompanyConfigurationService.activate(tenant_id, config.id, "approver", "corr-activate")

    rule = api_client.post(
        "/api/v2/multi-company/transfer-pricing-rules/",
        {
            "name": "Cost plus",
            "source_company_id": str(source.id),
            "target_company_id": str(target.id),
            "product_category": "standard",
            "transaction_type": "sale",
            "pricing_method": "cost_plus",
            "markup_percentage": "10.0000",
            "effective_from": "2024-01-01",
        },
        format="json",
    )
    assert rule.status_code == status.HTTP_201_CREATED

    calculated = api_client.post(
        "/api/v2/multi-company/transfer-pricing/calculate/",
        {
            "rule_id": rule.data["id"],
            "source_company_id": str(source.id),
            "target_company_id": str(target.id),
            "product_category": "standard",
            "transaction_type": "sale",
            "effective_date": "2024-01-01",
            "amount": "50.0000",
            "currency": "USD",
        },
        format="json",
    )
    assert calculated.status_code == status.HTTP_200_OK
    assert calculated.data["amount"] == "55.0000"

    exported = api_client.get("/api/v2/multi-company/configuration/export/", {"environment": "development"})
    assert exported.status_code == status.HTTP_200_OK
    imported = api_client.post(
        "/api/v2/multi-company/configuration/import/",
        {"document": exported.data},
        format="json",
    )
    assert imported.status_code == status.HTTP_201_CREATED
    assert imported.data["status"] == "draft"

    job = AsyncJob.objects.create(
        tenant_id=tenant_id,
        actor_id=str(authenticated_user.id),
        command="multi_company.transaction.reverse",
        idempotency_key="lookup-job",
        payload={},
        correlation_id="corr-job",
    )
    looked_up = api_client.get(f"/api/v2/multi-company/jobs/{job.id}/")
    assert looked_up.status_code == status.HTTP_200_OK
    assert looked_up.data["command"] == "multi_company.transaction.reverse"

    invalid = api_client.get("/api/v2/multi-company/configuration/export/", {"environment": "qa"})
    assert invalid.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_v2_transfer_pricing_rule_lifecycle_calculate_preview_and_delete(v2_auth):
    api_client, _, tenant_id = v2_auth
    source = _company(tenant_id, "TPS")
    target = _company(tenant_id, "TPT")
    draft = MultiCompanyConfigurationService.create_draft(
        tenant_id,
        "author",
        "corr-config",
        "development",
        DEFAULT_SETTINGS,
        "Defaults",
    )
    MultiCompanyConfigurationService.activate(tenant_id, draft.id, "approver", "corr-activate")

    created = api_client.post(
        "/api/v2/multi-company/transfer-pricing-rules/",
        {
            "name": "Resale minus",
            "source_company_id": str(source.id),
            "target_company_id": str(target.id),
            "product_category": "standard",
            "transaction_type": "sale",
            "pricing_method": "resale_minus",
            "parameters": {"margin_percentage": "20.0000"},
            "effective_from": "2024-01-01",
        },
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED, created.content
    rule_id = created.data["id"]

    listed = api_client.get(
        "/api/v2/multi-company/transfer-pricing-rules/",
        {
            "source_company_id": str(source.id),
            "target_company_id": str(target.id),
            "pricing_method": "resale_minus",
            "active_date": "2024-01-31",
            "ordering": "name",
        },
    )
    assert listed.status_code == status.HTTP_200_OK
    assert listed.data[0]["id"] == rule_id

    calculated = api_client.post(
        "/api/v2/multi-company/transfer-pricing/calculate/",
        {
            "source_company_id": str(source.id),
            "target_company_id": str(target.id),
            "product_category": "standard",
            "transaction_type": "sale",
            "effective_date": "2024-01-31",
            "amount": "100.0000",
            "currency": "USD",
        },
        format="json",
    )
    assert calculated.status_code == status.HTTP_200_OK, calculated.content
    assert calculated.data["amount"] == "80.0000"

    preview = api_client.post(
        "/api/v2/multi-company/transfer-pricing/preview/",
        {
            "rule_id": rule_id,
            "source_company_id": str(source.id),
            "target_company_id": str(target.id),
            "product_category": "standard",
            "transaction_type": "sale",
            "effective_date": "2024-01-31",
            "amount": "100.0000",
            "currency": "USD",
            "scenarios": [{"amount": "50.0000"}, {"amount": "125.0000"}],
        },
        format="json",
    )
    assert preview.status_code == status.HTTP_200_OK, preview.content
    assert [row["amount"] for row in preview.data] == ["40.0000", "100.0000"]

    replacement = api_client.patch(
        f"/api/v2/multi-company/transfer-pricing-rules/{rule_id}/",
        {"expected_version": created.data["version"], "parameters": {"margin_percentage": "25.0000"}},
        format="json",
    )
    assert replacement.status_code == status.HTTP_200_OK, replacement.content
    assert replacement.data["rule_version"] == 2

    prior = TransferPricingRule.objects.get(pk=rule_id)
    deleted = api_client.delete(
        f"/api/v2/multi-company/transfer-pricing-rules/{rule_id}/"
        f"?expected_version={prior.version}&transition_key=delete-prior-rule",
    )
    assert deleted.status_code == status.HTTP_204_NO_CONTENT, deleted.content


@pytest.mark.django_db
def test_v2_configuration_versions_enforce_expected_version_and_actions(v2_auth):
    api_client, _, tenant_id = v2_auth
    active = MultiCompanyConfigurationService.create_draft(
        tenant_id,
        "author",
        "corr-config-active",
        "development",
        DEFAULT_SETTINGS,
        "Defaults",
    )
    MultiCompanyConfigurationService.activate(tenant_id, active.id, "approver", "corr-activate")
    changed = {**DEFAULT_SETTINGS, "job_timeout_seconds": 450}

    created = api_client.post(
        "/api/v2/multi-company/configuration/versions/",
        {
            "environment": "development",
            "schema_version": "1.0",
            "settings": changed,
            "change_summary": "Tune job timeout",
        },
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED, created.content
    version_id = created.data["id"]

    missing_expected = api_client.patch(
        f"/api/v2/multi-company/configuration/versions/{version_id}/",
        {
            "environment": "development",
            "schema_version": "1.0",
            "settings": changed,
            "change_summary": "Still missing expected version",
        },
        format="json",
    )
    assert missing_expected.status_code == status.HTTP_400_BAD_REQUEST

    stale = api_client.patch(
        f"/api/v2/multi-company/configuration/versions/{version_id}/",
        {
            "environment": "development",
            "schema_version": "1.0",
            "settings": changed,
            "change_summary": "Stale update",
            "expected_version": created.data["version"] + 1,
        },
        format="json",
    )
    assert stale.status_code == status.HTTP_409_CONFLICT

    updated = api_client.patch(
        f"/api/v2/multi-company/configuration/versions/{version_id}/",
        {
            "environment": "development",
            "schema_version": "1.0",
            "settings": {**DEFAULT_SETTINGS, "job_timeout_seconds": 600},
            "change_summary": "Valid update",
            "expected_version": created.data["version"],
        },
        format="json",
    )
    assert updated.status_code == status.HTTP_200_OK, updated.content
    assert updated.data["settings"]["job_timeout_seconds"] == 600

    listed = api_client.get("/api/v2/multi-company/configuration/versions/", {"environment": "development"})
    assert listed.status_code == status.HTTP_200_OK
    assert {row["id"] for row in listed.data} >= {str(active.id), version_id}

    validated = api_client.post(f"/api/v2/multi-company/configuration/versions/{version_id}/validate/")
    assert validated.status_code == status.HTTP_200_OK
    assert validated.data["valid"] is True

    preview = api_client.post(f"/api/v2/multi-company/configuration/versions/{version_id}/preview/")
    assert preview.status_code == status.HTTP_200_OK
    assert "job_timeout_seconds" in preview.data["changed_keys"]

    activated = api_client.post(f"/api/v2/multi-company/configuration/versions/{version_id}/activate/")
    assert activated.status_code == status.HTTP_200_OK, activated.content
    rollback = api_client.post(f"/api/v2/multi-company/configuration/versions/{active.id}/rollback/")
    assert rollback.status_code == status.HTTP_201_CREATED, rollback.content


@pytest.mark.django_db
def test_v2_consolidation_update_retry_publish_cancel_and_elimination_lookup(v2_auth, monkeypatch):
    api_client, _, tenant_id = v2_auth
    source = _company(tenant_id, "CNS")
    target = _company(tenant_id, "CNT")
    run = ConsolidationRun.objects.create(
        tenant_id=tenant_id,
        name="Close API",
        consolidation_group="GROUP",
        period_start=date(2024, 4, 1),
        period_end=date(2024, 4, 30),
        reporting_currency="USD",
        translation_method="current_rate",
        total_companies=2,
        created_by="controller",
        updated_by="controller",
        correlation_id="corr-run-api",
    )
    retry_run = ConsolidationRun.objects.create(
        tenant_id=tenant_id,
        name="Retry API",
        consolidation_group="GROUP",
        period_start=date(2024, 5, 1),
        period_end=date(2024, 5, 31),
        reporting_currency="USD",
        translation_method="current_rate",
        status="failed",
        total_companies=2,
        created_by="controller",
        updated_by="controller",
        correlation_id="corr-retry-api",
    )
    calls = {}

    def fake_retry(tenant, run_id, actor, correlation_id, idempotency_key, transition_key):
        calls["retry"] = (tenant, run_id, actor, correlation_id, idempotency_key, transition_key)
        return AsyncJob.objects.create(
            tenant_id=tenant,
            actor_id=actor,
            command="multi_company.consolidation.execute",
            idempotency_key=idempotency_key,
            payload={"run_id": run_id},
            correlation_id=correlation_id,
        )

    monkeypatch.setattr(ConsolidationService, "retry", staticmethod(fake_retry))

    retried = api_client.post(
        f"/api/v2/multi-company/consolidation-runs/{retry_run.id}/retry/",
        {"transition_key": "retry-api"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="consolidation-retry-api",
    )
    assert retried.status_code == status.HTTP_202_ACCEPTED, retried.content
    assert calls["retry"][4] == "consolidation-retry-api"

    cancelled = api_client.post(
        f"/api/v2/multi-company/consolidation-runs/{run.id}/cancel/",
        {"transition_key": "cancel-api", "reason": "Operator cancelled"},
        format="json",
    )
    assert cancelled.status_code == status.HTTP_200_OK, cancelled.content

    completed = ConsolidationRun.objects.create(
        tenant_id=tenant_id,
        name="Completed API",
        consolidation_group="GROUP",
        period_start=date(2024, 6, 1),
        period_end=date(2024, 6, 30),
        reporting_currency="USD",
        translation_method="current_rate",
        status="completed",
        report_snapshot={"currency": "USD", "total": "10.0000"},
        total_companies=2,
        created_by="controller",
        updated_by="controller",
        correlation_id="corr-completed-api",
    )
    elimination = api_client.post(
        f"/api/v2/multi-company/consolidation-runs/{completed.id}/eliminations/",
        {
            "elimination_type": "intercompany_balance",
            "source_company_id": str(source.id),
            "target_company_id": str(target.id),
            "debit_account": "4000",
            "credit_account": "2000",
            "amount": "10.0000",
            "currency": "USD",
        },
        format="json",
    )
    assert elimination.status_code == status.HTTP_201_CREATED, elimination.content
    listed = api_client.get(
        f"/api/v2/multi-company/consolidation-runs/{completed.id}/eliminations/",
        {"is_auto_generated": "false", "source_company_id": str(source.id)},
    )
    assert listed.status_code == status.HTTP_200_OK
    assert listed.data[0]["id"] == elimination.data["id"]
    retrieved = api_client.get(f"/api/v2/multi-company/eliminations/{elimination.data['id']}/")
    assert retrieved.status_code == status.HTTP_200_OK
