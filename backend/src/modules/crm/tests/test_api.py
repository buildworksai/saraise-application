"""
API Endpoint Tests for CRM module.

Tests DRF ViewSets and API endpoints.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied, ValidationError
from rest_framework.test import APIClient

from src.core.async_jobs.models import AsyncJob
from src.modules.crm import api as crm_api
from src.modules.crm.models import Account, Activity, Contact, Lead, LeadStatus, Opportunity, OpportunityStatus
from src.modules.crm.services import CRMServiceError

User = get_user_model()


def test_api_parse_helpers_and_actor_fail_closed():
    assert crm_api._parse_uuid(uuid.UUID(int=1), "owner_id") == uuid.UUID(int=1)
    assert crm_api._parse_int(None, "period", minimum=1, maximum=10) is None
    assert crm_api._parse_int("7", "period", minimum=1, maximum=10) == 7
    assert crm_api._parse_bool(None, "completed") is None
    assert crm_api._parse_bool("TRUE", "completed") is True
    assert crm_api._parse_bool("0", "completed") is False
    assert crm_api._parse_date(None, "close_date") is None
    assert crm_api._parse_date("2026-08-03", "close_date") == date(2026, 8, 3)

    with pytest.raises(ValidationError):
        crm_api._parse_uuid(None, "owner_id")
    with pytest.raises(ValidationError):
        crm_api._parse_uuid("not-a-uuid", "owner_id")
    with pytest.raises(ValidationError):
        crm_api._parse_int("abc", "period", minimum=1, maximum=10)
    with pytest.raises(ValidationError):
        crm_api._parse_int("11", "period", minimum=1, maximum=10)
    with pytest.raises(ValidationError):
        crm_api._parse_bool("maybe", "completed")
    with pytest.raises(ValidationError):
        crm_api._parse_date("03/08/2026", "close_date")
    with pytest.raises(PermissionDenied):
        crm_api._actor(SimpleNamespace(user=SimpleNamespace(id=None, pk=None)))


def test_governed_viewset_query_version_and_replay_branches():
    view = crm_api.GovernedCRMViewSet()
    view.request = SimpleNamespace(query_params={"unknown": "1"})
    with pytest.raises(ValidationError):
        view._validate_query({"allowed"})

    view.request = SimpleNamespace(headers={"If-Match": 'W/"4"'}, path="/api/v2/crm/leads/")
    values = {"version": 4}
    assert view._expected_version(values, SimpleNamespace(version=2)) == 4
    assert values == {}

    view.request = SimpleNamespace(headers={"If-Match": '"5"'}, path="/api/v2/crm/leads/")
    with pytest.raises(ValidationError):
        view._expected_version({"version": 4}, SimpleNamespace(version=4))

    view.request = SimpleNamespace(headers={"If-Match": "not-int"}, path="/api/v2/crm/leads/")
    with pytest.raises(ValidationError):
        view._expected_version({}, SimpleNamespace(version=4))

    view.request = SimpleNamespace(headers={}, path="/api/v1/crm/leads/")
    assert view._expected_version({}, SimpleNamespace(version=9)) == 9

    view.request = SimpleNamespace(headers={}, path="/api/v2/crm/leads/")
    with pytest.raises(ValidationError):
        view._expected_version({}, SimpleNamespace(version=9))

    response = view.handle_exception(crm_api.CRMIdempotentReplay({"id": "lead-1"}, status.HTTP_202_ACCEPTED))
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response["Idempotent-Replayed"] == "true"


def test_governed_viewset_exception_mapping_branches(monkeypatch):
    captured = []

    def fake_super(self, exc):
        captured.append(exc)
        return exc

    monkeypatch.setattr(crm_api.TenantScopedModelViewSet, "handle_exception", fake_super)
    view = crm_api.GovernedCRMViewSet()

    mapped = view.handle_exception(CRMServiceError("denied", code="CRM_DENIED", http_status=status.HTTP_409_CONFLICT))
    assert mapped.error_code == "CRM_DENIED"
    assert mapped.status_code == status.HTTP_409_CONFLICT

    mapped = view.handle_exception(ValidationError({"name": "invalid"}))
    assert isinstance(mapped, ValidationError)

    mapped = view.handle_exception(IntegrityError("duplicate"))
    assert mapped.error_code == "CONFLICT"
    assert mapped.status_code == status.HTTP_409_CONFLICT

    mapped = view.handle_exception(ObjectDoesNotExist())
    assert isinstance(mapped, crm_api.NotFound)


def test_csrf_session_authentication_advertises_real_challenge():
    assert crm_api.CsrfSessionAuthentication().authenticate_header(SimpleNamespace()) == "Session"


def test_governed_viewset_idempotency_lifecycle_and_fail_closed_mutations(monkeypatch):
    tenant_id = uuid.uuid4()
    record = SimpleNamespace(id=uuid.uuid4(), completed=False)
    calls = []

    monkeypatch.setattr(crm_api.TenantScopedModelViewSet, "initial", lambda self, request, *args, **kwargs: None)
    monkeypatch.setattr(
        crm_api.TenantScopedModelViewSet,
        "finalize_response",
        lambda self, request, response, *args, **kwargs: response,
    )

    def fake_begin(tenant, *, key, method, path, payload):
        calls.append(("begin", tenant, key, method, path, payload))
        return record

    def fake_complete(tenant, *, record_id, response_status, response_body):
        calls.append(("complete", tenant, record_id, response_status, response_body))

    monkeypatch.setattr(crm_api.CRMIdempotencyService, "begin", staticmethod(fake_begin))
    monkeypatch.setattr(crm_api.CRMIdempotencyService, "complete", staticmethod(fake_complete))

    view = crm_api.GovernedCRMViewSet()
    view.action = "create"
    view.tenant_id = lambda: tenant_id
    request = SimpleNamespace(
        method="POST",
        headers={"Idempotency-Key": "crm-mutation-key"},
        data={"name": "Acme"},
        get_full_path=lambda: "/api/v2/crm/accounts/",
    )

    view.initial(request)
    assert request.crm_idempotency_record is record
    assert calls[0] == ("begin", tenant_id, "crm-mutation-key", "POST", "/api/v2/crm/accounts/", {"name": "Acme"})

    request.tenant_id = tenant_id
    response = crm_api.Response({"id": "crm-object"}, status=status.HTTP_201_CREATED)
    finalized = view.finalize_response(request, response)
    assert finalized is response
    assert calls[-1] == ("complete", tenant_id, record.id, status.HTTP_201_CREATED, {"id": "crm-object"})

    missing = SimpleNamespace(method="PATCH", headers={}, data={}, get_full_path=lambda: "/api/v2/crm/accounts/1/")
    with pytest.raises(ValidationError):
        view.initial(missing)

    preview_view = crm_api.GovernedCRMViewSet()
    preview_view.action = "preview"
    preview_request = SimpleNamespace(method="POST", headers={}, data={}, get_full_path=lambda: "/api/v2/crm/config/")
    preview_view.initial(preview_request)
    assert not hasattr(preview_request, "crm_idempotency_record")


def test_governed_viewset_check_permissions_sets_quota_and_rejects_unknown_method(monkeypatch):
    tenant_id = uuid.uuid4()
    view = crm_api.GovernedCRMViewSet()
    view.action = "create"
    view.permission_map = {"create": "crm.account:create"}
    view.request = SimpleNamespace(method="POST")
    view._get_tenant_id = lambda: tenant_id
    calls = []
    monkeypatch.setattr(crm_api, "effective_configuration", lambda tenant: {"api": {"quota_cost": 3}})
    monkeypatch.setattr(crm_api.TenantScopedModelViewSet, "check_permissions", lambda self, request: calls.append(self))

    request = SimpleNamespace(method="POST")
    view.check_permissions(request)

    assert request.tenant_id == tenant_id
    assert view.required_permission == "crm.account:create"
    assert view.quota_resource == "crm.api.create"
    assert view.quota_cost > 0
    assert calls == [view]

    view.request = SimpleNamespace(method="TRACE")
    with pytest.raises(MethodNotAllowed):
        view.check_permissions(SimpleNamespace(method="TRACE"))


def test_crm_additional_permission_fails_closed(monkeypatch):
    monkeypatch.setattr(crm_api.RequiresAccess, "has_permission", lambda self, request, view: False)
    view = crm_api.GovernedCRMViewSet()
    view.request = SimpleNamespace()

    with pytest.raises(PermissionDenied):
        view._require_additional_permission("crm.contact:override_domain")


@pytest.fixture(autouse=True)
def authorized_access_pipeline(monkeypatch):
    """Exercise endpoint behavior behind an explicit successful access decision."""

    from src.core.access.decision import AccessDecision, AccessDecisionPipeline, AccessReasonCode

    def decide(_self, tenant_id, _identity, _permission, **_kwargs):
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="Test policy, entitlement, and quota granted access.",
            tenant_id=uuid.UUID(str(tenant_id)),
        )

    monkeypatch.setattr(AccessDecisionPipeline, "decide", decide)


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
    """Create authenticated user for testing."""
    from unittest.mock import patch

    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",  # pragma: allowlist secret
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


@pytest.mark.django_db
class TestLeadAPI:
    """Test Lead API endpoints."""

    def test_create_lead_requires_idempotency_key(self, api_client, authenticated_user):
        api_client.force_authenticate(user=authenticated_user)

        response = api_client.post(
            "/api/v1/crm/leads/",
            {"first_name": "No", "last_name": "Duplicate"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Lead.objects.filter(
            tenant_id=uuid.UUID(authenticated_user.profile.tenant_id),
            first_name="No",
            last_name="Duplicate",
        ).exists()

    def test_create_lead(self, api_client, authenticated_user):
        """Test creating a lead via API."""
        api_client.force_authenticate(user=authenticated_user)

        data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "company": "Acme Corp",
        }

        response = api_client.post(
            "/api/v1/crm/leads/",
            data,
            format="json",
            HTTP_IDEMPOTENCY_KEY="create-lead",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["first_name"] == "John"
        assert response.data["last_name"] == "Doe"

    def test_list_leads(self, api_client, authenticated_user):
        """Test listing leads."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        user_id = authenticated_user.id

        # Create test leads
        Lead.objects.create(
            tenant_id=tenant_id,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            company="Acme Corp",
            created_by=str(user_id),
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v1/crm/leads/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    def test_v2_list_leads_filters_orders_and_stays_tenant_scoped(self, api_client, authenticated_user):
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        other_tenant_id = uuid.uuid4()
        Lead.objects.create(
            tenant_id=tenant_id,
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.test",
            company="Acme Corp",
            status=LeadStatus.NEW,
            score=80,
            grade="A",
            created_by=str(authenticated_user.id),
        )
        Lead.objects.create(
            tenant_id=tenant_id,
            first_name="Grace",
            last_name="Hopper",
            email="grace@example.test",
            company="Acme Corp",
            status=LeadStatus.QUALIFIED,
            score=90,
            grade="A",
            created_by=str(authenticated_user.id),
        )
        Lead.objects.create(
            tenant_id=other_tenant_id,
            first_name="Ada",
            last_name="Tenant",
            email="other@example.test",
            company="Acme Corp",
            status=LeadStatus.NEW,
            score=99,
            grade="A",
            created_by=str(authenticated_user.id),
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v2/crm/leads/?status=new&search=Acme&ordering=-score")

        assert response.status_code == status.HTTP_200_OK
        rows = response.data["data"] if isinstance(response.data, dict) and "data" in response.data else response.data
        assert [row["email"] for row in rows] == ["ada@example.test"]

    @pytest.mark.parametrize(
        "query",
        (
            "?unexpected=true",
            "?status=invalid",
            "?score_min=100&score_max=1",
            "?owner_id=not-a-uuid",
            "?ordering=tenant_id",
        ),
    )
    def test_v2_lead_query_contract_rejects_unsupported_filters(self, api_client, authenticated_user, query):
        api_client.force_authenticate(user=authenticated_user)

        response = api_client.get(f"/api/v2/crm/leads/{query}")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_v2_lead_id_is_controlled_resource_error_not_permission_denial(
        self, api_client, authenticated_user
    ):
        """Authorized malformed detail routes must reach validation/resource handling."""

        api_client.force_authenticate(user=authenticated_user)

        response = api_client.get("/api/v2/crm/leads/__uat_invalid_id__/")

        assert response.status_code in {
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        }
        assert response.status_code != status.HTTP_403_FORBIDDEN

    def test_convert_lead_to_opportunity(self, api_client, authenticated_user):
        """Test converting lead to opportunity."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        user_id = authenticated_user.id

        lead = Lead.objects.create(
            tenant_id=tenant_id,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            company="Acme Corp",
            created_by=str(user_id),
        )

        api_client.force_authenticate(user=authenticated_user)

        data = {
            "amount": "10000.00",
            "close_date": str(date.today() + timedelta(days=30)),
        }

        response = api_client.post(
            f"/api/v1/crm/leads/{lead.id}/convert/",
            data,
            format="json",
            HTTP_IDEMPOTENCY_KEY="convert-lead",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert "id" in response.data  # Opportunity created

        # Verify lead status updated
        lead.refresh_from_db()
        assert lead.status == LeadStatus.CONVERTED


@pytest.mark.django_db
class TestOpportunityAPI:
    """Test Opportunity API endpoints."""

    def test_create_opportunity(self, api_client, authenticated_user):
        """Test creating an opportunity via API."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        user_id = authenticated_user.id

        # Create account first
        account = Account.objects.create(
            tenant_id=tenant_id,
            name="Acme Corp",
            created_by=str(user_id),
        )

        api_client.force_authenticate(user=authenticated_user)

        # Use a UUID for owner_id since it's a UUIDField
        owner_uuid = uuid.uuid4()
        data = {
            "account_id": str(account.id),
            "name": "Deal 1",
            "amount": "10000.00",
            "close_date": str(date.today() + timedelta(days=30)),
            "owner_id": str(owner_uuid),
        }

        response = api_client.post(
            "/api/v1/crm/opportunities/",
            data,
            format="json",
            HTTP_IDEMPOTENCY_KEY="create-opportunity",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "Deal 1"

    def test_close_opportunity_won(self, api_client, authenticated_user):
        """Test closing opportunity as won."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        user_id = authenticated_user.id

        account = Account.objects.create(
            tenant_id=tenant_id,
            name="Acme Corp",
            created_by=str(user_id),
        )

        # Use a UUID for owner_id since it's a UUIDField
        owner_uuid = uuid.uuid4()
        opportunity = Opportunity.objects.create(
            tenant_id=tenant_id,
            account_id=account.id,
            name="Deal 1",
            amount=Decimal("10000.00"),
            close_date=date.today() + timedelta(days=30),
            owner_id=owner_uuid,
            created_by=str(user_id),
        )

        api_client.force_authenticate(user=authenticated_user)

        response = api_client.post(
            f"/api/v1/crm/opportunities/{opportunity.id}/close-won/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="close-opportunity-won",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == OpportunityStatus.WON

    def test_close_opportunity_lost_requires_reason(self, api_client, authenticated_user):
        """Test closing opportunity as lost requires loss_reason."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        user_id = authenticated_user.id

        account = Account.objects.create(
            tenant_id=tenant_id,
            name="Acme Corp",
            created_by=str(user_id),
        )

        # Use a UUID for owner_id since it's a UUIDField
        owner_uuid = uuid.uuid4()
        opportunity = Opportunity.objects.create(
            tenant_id=tenant_id,
            account_id=account.id,
            name="Deal 1",
            amount=Decimal("10000.00"),
            close_date=date.today() + timedelta(days=30),
            owner_id=owner_uuid,
            created_by=str(user_id),
        )

        api_client.force_authenticate(user=authenticated_user)

        # Try without loss_reason
        response = api_client.post(
            f"/api/v1/crm/opportunities/{opportunity.id}/close-lost/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="close-opportunity-lost-invalid",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Try with loss_reason
        response = api_client.post(
            f"/api/v1/crm/opportunities/{opportunity.id}/close-lost/",
            {"loss_reason": "Customer chose competitor"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="close-opportunity-lost",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == OpportunityStatus.LOST

    def test_v2_update_requires_matching_if_match_version(self, api_client, authenticated_user):
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        account = Account.objects.create(
            tenant_id=tenant_id,
            name="Versioned Account",
            created_by=str(authenticated_user.id),
        )
        opportunity = Opportunity.objects.create(
            tenant_id=tenant_id,
            account_id=account.id,
            name="Versioned Deal",
            amount=Decimal("10000.00"),
            close_date=date.today() + timedelta(days=30),
            owner_id=uuid.uuid4(),
            created_by=str(authenticated_user.id),
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.patch(
            f"/api/v2/crm/opportunities/{opportunity.id}/",
            {"name": "Matched If-Match", "version": opportunity.version + 1},
            format="json",
            HTTP_IDEMPOTENCY_KEY="opportunity-version-match",
            HTTP_IF_MATCH=str(opportunity.version),
        )

        assert response.status_code == status.HTTP_200_OK
        opportunity.refresh_from_db()
        assert opportunity.name == "Matched If-Match"


@pytest.mark.django_db
class TestCRMAPIContracts:
    def test_v2_lead_update_destroy_transition_and_scoring_delegate_with_guards(
        self, monkeypatch, api_client, authenticated_user
    ):
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        lead = Lead.objects.create(
            tenant_id=tenant_id,
            first_name="Governed",
            last_name="Lead",
            email="governed@example.test",
            company="Acme",
            score=10,
            created_by=str(authenticated_user.id),
        )
        calls: list[tuple[str, dict[str, object]]] = []

        def update_lead(tenant_id_arg, *, lead_id, data, expected_version, actor_id):
            calls.append(
                (
                    "update",
                    {
                        "tenant_id": tenant_id_arg,
                        "lead_id": lead_id,
                        "data": dict(data),
                        "expected_version": expected_version,
                        "actor_id": actor_id,
                    },
                )
            )
            lead.first_name = data["first_name"]
            lead.version = expected_version + 1
            return lead

        def delete_lead(tenant_id_arg, *, lead_id, expected_version, actor_id):
            calls.append(
                (
                    "delete",
                    {
                        "tenant_id": tenant_id_arg,
                        "lead_id": lead_id,
                        "expected_version": expected_version,
                        "actor_id": actor_id,
                    },
                )
            )

        def transition_lead(tenant_id_arg, *, lead_id, command, transition_key, context, actor_id, expected_version):
            calls.append(
                (
                    "transition",
                    {
                        "tenant_id": tenant_id_arg,
                        "lead_id": lead_id,
                        "command": command,
                        "transition_key": transition_key,
                        "context": dict(context),
                        "actor_id": actor_id,
                        "expected_version": expected_version,
                    },
                )
            )
            lead.status = LeadStatus.QUALIFIED
            lead.version = expected_version + 1
            return lead

        monkeypatch.setattr("src.modules.crm.api.LeadService.update_lead", update_lead)
        monkeypatch.setattr("src.modules.crm.api.LeadService.delete_lead", delete_lead)
        monkeypatch.setattr("src.modules.crm.api.LeadService.transition_lead", transition_lead)
        monkeypatch.setattr(
            "src.modules.crm.api.LeadService.score_lead", lambda *args, **kwargs: SimpleNamespace(unwrap=lambda: lead)
        )
        view = crm_api.LeadViewSet()
        view.request = SimpleNamespace(
            data={"first_name": "Updated"},
            headers={"If-Match": str(lead.version)},
            path="/api/v2/crm/leads/",
            user=authenticated_user,
        )
        view.get_object = lambda: lead
        view.tenant_id = lambda: tenant_id
        view.correlation_id = lambda: "lead-api-correlation"

        response = view.partial_update(view.request, pk=str(lead.id))
        assert response.status_code == status.HTTP_200_OK
        assert calls[-1][0] == "update"
        assert calls[-1][1]["expected_version"] == 1

        view.request = SimpleNamespace(
            data={
                "command": "qualify",
                "transition_key": "lead-transition-api",
                "expected_version": lead.version,
                "context": {"qualified_amount": "1000.00"},
            },
            headers={},
            path="/api/v2/crm/leads/",
            user=authenticated_user,
        )
        response = view.transition(view.request, pk=str(lead.id))
        assert response.status_code == status.HTTP_200_OK
        assert calls[-1][0] == "transition"
        assert calls[-1][1]["context"] == {"qualified_amount": "1000.00"}

        view.request = SimpleNamespace(
            data={"async_execution": False, "idempotency_key": "lead-score-sync"},
            headers={},
            path="/api/v2/crm/leads/",
            user=authenticated_user,
        )
        response = view.score(view.request, pk=str(lead.id))
        assert response.status_code == status.HTTP_200_OK

        view.request = SimpleNamespace(
            data={},
            headers={"If-Match": str(lead.version)},
            path="/api/v2/crm/leads/",
            user=authenticated_user,
        )
        response = view.destroy(view.request, pk=str(lead.id))
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert calls[-1][0] == "delete"

    def test_v2_lead_async_score_returns_job_operation(self, monkeypatch, api_client, authenticated_user):
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        lead = Lead.objects.create(
            tenant_id=tenant_id,
            first_name="Async",
            last_name="Score",
            company="Acme",
            created_by=str(authenticated_user.id),
        )

        def enqueue(tenant_id_arg, *, lead_id, idempotency_key, actor_id, correlation_id):
            assert tenant_id_arg == tenant_id
            assert lead_id == lead.id
            assert idempotency_key == "lead-score-async"
            return AsyncJob.objects.create(
                tenant_id=tenant_id,
                actor_id=actor_id,
                command="crm.lead.score",
                idempotency_key=idempotency_key,
                payload={"lead_id": str(lead_id)},
                correlation_id=correlation_id or "score-correlation",
            )

        monkeypatch.setattr("src.modules.crm.api.enqueue_lead_scoring_job", enqueue)
        api_client.force_authenticate(user=authenticated_user)

        response = api_client.post(
            f"/api/v2/crm/leads/{lead.id}/score/",
            {"async_execution": True, "idempotency_key": "lead-score-async"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="lead-score-async",
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.data["command"] == "crm.lead.score"

    def test_v2_lead_idempotency_replay_maps_to_original_response(self, api_client, authenticated_user):
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        Lead.objects.create(
            tenant_id=tenant_id,
            first_name="Replay",
            last_name="Lead",
            company="Acme",
            created_by=str(authenticated_user.id),
        )
        api_client.force_authenticate(user=authenticated_user)

        first = api_client.post(
            "/api/v2/crm/leads/",
            {
                "first_name": "Replay",
                "last_name": "Once",
                "email": "replay.once@example.test",
                "company": "Acme",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="lead-create-replay",
        )
        second = api_client.post(
            "/api/v2/crm/leads/",
            {
                "first_name": "Replay",
                "last_name": "Once",
                "email": "replay.once@example.test",
                "company": "Acme",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="lead-create-replay",
        )

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_201_CREATED
        assert second["Idempotent-Replayed"] == "true"
        assert second.data == first.data

    def test_contact_domain_override_permission_is_checked_before_service_call(
        self, monkeypatch, api_client, authenticated_user
    ):
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        account = Account.objects.create(
            tenant_id=tenant_id,
            name="Override Account",
            website="https://example.com",
            created_by=str(authenticated_user.id),
        )
        calls: list[dict[str, object]] = []

        def create_contact(*_args, **kwargs):
            calls.append(kwargs)
            return Contact.objects.create(
                tenant_id=tenant_id,
                account_id=account.id,
                first_name="External",
                last_name="Contact",
                email="external@different.test",
                created_by=str(authenticated_user.id),
            )

        monkeypatch.setattr("src.modules.crm.api.ContactService.create_contact", create_contact)
        api_client.force_authenticate(user=authenticated_user)

        response = api_client.post(
            "/api/v2/crm/contacts/",
            {
                "account_id": str(account.id),
                "first_name": "External",
                "last_name": "Contact",
                "email": "external@different.test",
                "domain_override_reason": "Documented acquisition exception.",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="contact-domain-override",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert calls[0]["allow_domain_override"] is True

    def test_activity_delete_is_append_only_even_with_idempotency_key(self, api_client, authenticated_user):
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        lead = Lead.objects.create(
            tenant_id=tenant_id,
            first_name="Append",
            last_name="Only",
            company="Acme",
            created_by=str(authenticated_user.id),
        )
        activity = Activity.objects.create(
            tenant_id=tenant_id,
            related_to_type="Lead",
            related_to_id=lead.id,
            activity_type="call",
            subject="Cannot delete evidence",
            created_by=str(authenticated_user.id),
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.delete(
            f"/api/v2/crm/activities/{activity.id}/",
            HTTP_IDEMPOTENCY_KEY="activity-delete-attempt",
            HTTP_IF_MATCH=str(activity.version),
        )

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert Activity.objects.filter(id=activity.id).exists()

    def test_account_duplicates_validates_query_and_delegates(self, monkeypatch, api_client, authenticated_user):
        calls: list[dict[str, object]] = []

        def find_duplicates(tenant_id, **kwargs):
            calls.append({"tenant_id": tenant_id, **kwargs})
            return SimpleNamespace(local_matches=[], external_matches=[{"name": "Acme"}], enrichment_status="ok")

        monkeypatch.setattr("src.modules.crm.api.AccountService.find_duplicates", find_duplicates)
        api_client.force_authenticate(user=authenticated_user)

        response = api_client.get("/api/v2/crm/accounts/duplicates/?name=Acme&website=https://acme.example")

        assert response.status_code == status.HTTP_200_OK
        assert calls == [
            {
                "tenant_id": uuid.UUID(authenticated_user.profile.tenant_id),
                "name": "Acme",
                "website": "https://acme.example",
            }
        ]
        assert response.data["external_matches"] == [{"name": "Acme"}]

    def test_async_job_permission_comes_from_job_command(self, api_client, authenticated_user):
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        job = AsyncJob.objects.create(
            tenant_id=tenant_id,
            actor_id=str(authenticated_user.id),
            command="crm.lead.score",
            idempotency_key="crm-job-score",
            payload={"lead_id": str(uuid.uuid4())},
            correlation_id="crm-job-correlation",
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get(f"/api/v2/crm/jobs/{job.id}/")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["error"]["code"] == "POLICY_DENIED"


def test_crm_helper_parsers_fail_closed() -> None:
    assert crm_api._parse_bool("true", "completed") is True
    assert crm_api._parse_bool("0", "completed") is False
    assert crm_api._parse_date("2026-08-03", "due_from") == date(2026, 8, 3)
    with pytest.raises(ValidationError):
        crm_api._parse_bool("yes", "completed")
    with pytest.raises(ValidationError):
        crm_api._parse_int("1000", "score", minimum=0, maximum=100)
    with pytest.raises(ValidationError):
        crm_api._parse_date("03-08-2026", "due_from")


@pytest.mark.django_db
class TestForecastingAPI:
    """Test Forecasting API endpoints."""

    def test_get_pipeline(self, api_client, authenticated_user):
        """Test getting weighted pipeline."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        user_id = authenticated_user.id

        account = Account.objects.create(
            tenant_id=tenant_id,
            name="Acme Corp",
            created_by=str(user_id),
        )

        # Use a UUID for owner_id since it's a UUIDField
        owner_uuid = uuid.uuid4()
        Opportunity.objects.create(
            tenant_id=tenant_id,
            account_id=account.id,
            name="Deal 1",
            amount=Decimal("10000.00"),
            probability=50,
            close_date=date.today() + timedelta(days=30),
            owner_id=owner_uuid,
            created_by=str(user_id),
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v1/crm/forecasting/pipeline/")
        assert response.status_code == status.HTTP_200_OK
        assert "weighted_pipeline_value" in response.data
        assert response.data["opportunity_count"] >= 1
