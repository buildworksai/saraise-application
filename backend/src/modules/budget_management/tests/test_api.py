"""
API tests for Budget Management module.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from src.core.access.permissions import RequiresAccess
from src.modules.budget_management.api import (
    _choice_filter,
    _date_filter,
    _decimal_filter,
    _integer_filter,
    _ordering,
    _uuid_filter,
)
from src.modules.budget_management.integrations import ApprovalRequest, ApprovalStep, configure_integrations
from src.modules.budget_management.models import Budget, BudgetLine
from src.modules.budget_management.services import BudgetControlService, BudgetService, VarianceAlertService

User = get_user_model()


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture(autouse=True)
def allow_declared_access(monkeypatch):
    """Isolate module transport tests from the separately-tested policy engine."""
    monkeypatch.setattr(RequiresAccess, "has_permission", lambda self, request, view: True)
    monkeypatch.setattr(RequiresAccess, "has_object_permission", lambda self, request, view, obj: True)


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


@pytest.fixture(autouse=True)
def reset_budget_integrations():
    previous = configure_integrations()
    yield
    configure_integrations(
        accounting=previous.accounting,
        workflow=previous.workflow,
        notification=previous.notification,
    )


class WorkflowAdapter:
    def __init__(self, approver_id):
        self.approver_id = approver_id
        self.workflow_request_id = uuid.uuid4()

    def create_approval_request(self, tenant_id, *, budget, submitter_id, idempotency_key):
        del tenant_id, budget, submitter_id, idempotency_key
        return ApprovalRequest(
            workflow_request_id=self.workflow_request_id,
            steps=(ApprovalStep(approver_id=self.approver_id, approval_level=1),),
        )

    def get_approval_status(self, tenant_id, workflow_request_id):
        del tenant_id, workflow_request_id
        return "pending"

    def health_state(self):
        return "closed"


def _actor_id(user):
    try:
        return uuid.UUID(str(user.id))
    except (TypeError, ValueError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{user.id}")


def _budget_payload(code="BUD-API"):
    return {
        "budget_code": code,
        "budget_name": f"{code} budget",
        "fiscal_year": 2025,
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "budget_type": "operating",
        "currency": "USD",
        "budget_ceiling": "500.00",
    }


def test_api_filter_helpers_validate_protocol_values() -> None:
    tenant_id = uuid.uuid4()

    assert _ordering("-created_at,budget_code", {"created_at", "budget_code"}, "budget_code") == (
        "-created_at",
        "budget_code",
    )
    assert _uuid_filter(str(tenant_id), "tenant_id") == tenant_id
    assert _date_filter("2025-12-31", "as_of_date") == date(2025, 12, 31)
    assert _integer_filter("25", "page_size", maximum=100) == 25
    assert _decimal_filter("10.10", "amount") == Decimal("10.10")
    assert _choice_filter("draft", "status", {"draft", "approved"}) == "draft"

    invalid_inputs = (
        lambda: _ordering("updated_at", {"created_at"}, "created_at"),
        lambda: _uuid_filter("not-a-uuid", "tenant_id"),
        lambda: _date_filter("2025-02-30", "as_of_date"),
        lambda: _integer_filter("0", "page_size", maximum=100),
        lambda: _decimal_filter("1.234", "amount"),
        lambda: _choice_filter("deleted", "status", {"draft", "approved"}),
    )
    for invalid in invalid_inputs:
        with pytest.raises(ValidationError):
            invalid()


@pytest.mark.django_db
class TestBudgetAPI:
    """Test Budget API endpoints."""

    def test_list_budgets(self, api_client, authenticated_user):
        """Test listing budgets."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)

        Budget.objects.create(
            tenant_id=tenant_id,
            created_by=uuid.uuid4(),
            updated_by=uuid.uuid4(),
            budget_code="BUD-001",
            budget_name="Test Budget",
            fiscal_year=2024,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        api_client.force_login(user=authenticated_user)
        response = api_client.get("/api/v2/budget-management/budgets/")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"][0]["budget_code"] == "BUD-001"

    def test_create_budget(self, api_client, authenticated_user):
        """Test creating a budget."""
        api_client.force_login(user=authenticated_user)

        data = {
            "budget_code": "BUD-002",
            "budget_name": "Another Budget",
            "fiscal_year": 2024,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "budget_type": "operating",
            "currency": "USD",
        }

        response = api_client.post("/api/v2/budget-management/budgets/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["data"]["budget_code"] == "BUD-002"

    def test_session_mutation_enforces_csrf(self, authenticated_user):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user=authenticated_user)
        response = client.post(
            "/api/v2/budget-management/budgets/",
            {
                "budget_code": "CSRF-1",
                "budget_name": "CSRF proof",
                "fiscal_year": 2024,
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "budget_type": "operating",
                "currency": "USD",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_budget_update_allocations_variance_and_invalid_filters(self, api_client, authenticated_user):
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        api_client.force_login(user=authenticated_user)
        created = api_client.post("/api/v2/budget-management/budgets/", _budget_payload("BUD-UPD"), format="json")
        assert created.status_code == status.HTTP_201_CREATED
        budget = Budget.objects.get(tenant_id=tenant_id, budget_code="BUD-UPD")

        updated = api_client.patch(
            f"/api/v2/budget-management/budgets/{budget.id}/",
            {
                "expected_updated_at": budget.updated_at.isoformat().replace("+00:00", "Z"),
                "budget_name": "Updated budget name",
                "budget_ceiling": "200.00",
            },
            format="json",
        )
        assert updated.status_code == status.HTTP_200_OK
        assert updated.json()["data"]["budget_name"] == "Updated budget name"

        budget.refresh_from_db()
        allocations = api_client.put(
            f"/api/v2/budget-management/budgets/{budget.id}/allocations/",
            {
                "expected_updated_at": budget.updated_at.isoformat().replace("+00:00", "Z"),
                "allocations": [
                    {
                        "account_code": "6100",
                        "period_type": "annual",
                        "period_number": 1,
                        "budget_amount": "200.00",
                    }
                ],
            },
            format="json",
        )
        assert allocations.status_code == status.HTTP_200_OK
        assert BudgetLine.objects.get(tenant_id=tenant_id, budget=budget).budget_amount == Decimal("200.00")

        variance = api_client.get(
            f"/api/v2/budget-management/budgets/{budget.id}/variance/?account_code=6100&threshold_percentage=5.00"
        )
        assert variance.status_code == status.HTTP_200_OK
        assert variance.json()["data"]["budgeted"] == "200.00"

        invalid = api_client.get("/api/v2/budget-management/budgets/?ordering=not_allowed")
        assert invalid.status_code == status.HTTP_400_BAD_REQUEST
        assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_budget_line_crud_and_availability_routes(self, api_client, authenticated_user):
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        actor_id = _actor_id(authenticated_user)
        budget = BudgetService.create_budget(
            tenant_id,
            actor_id,
            **_budget_payload("BUD-LINE"),
        )
        api_client.force_login(user=authenticated_user)

        created = api_client.post(
            "/api/v2/budget-management/budget-lines/",
            {
                "budget_id": str(budget.id),
                "account_code": "6200",
                "period_type": "monthly",
                "period_number": 3,
                "budget_amount": "120.00",
            },
            format="json",
        )
        assert created.status_code == status.HTTP_201_CREATED
        line_id = created.json()["data"]["id"]
        line = BudgetLine.objects.get(pk=line_id)

        listed = api_client.get(
            f"/api/v2/budget-management/budget-lines/?budget_id={budget.id}&period_type=monthly&period_number=3"
        )
        assert listed.status_code == status.HTTP_200_OK
        assert [item["id"] for item in listed.json()["data"]] == [line_id]

        patched = api_client.patch(
            f"/api/v2/budget-management/budget-lines/{line_id}/",
            {
                "expected_updated_at": line.updated_at.isoformat().replace("+00:00", "Z"),
                "budget_amount": "150.00",
            },
            format="json",
        )
        assert patched.status_code == status.HTTP_200_OK
        assert patched.json()["data"]["budget_amount"] == "150.00"

        line.refresh_from_db()
        deleted = api_client.delete(
            f"/api/v2/budget-management/budget-lines/{line_id}/",
            {"expected_updated_at": line.updated_at.isoformat().replace("+00:00", "Z")},
            format="json",
        )
        assert deleted.status_code == status.HTTP_204_NO_CONTENT

        BudgetService.create_line(
            tenant_id,
            budget.id,
            actor_id,
            {"account_code": "6200", "period_type": "monthly", "period_number": 3, "budget_amount": "150.00"},
        )
        Budget.objects.filter(pk=budget.pk).update(
            status="approved",
            approved_at=timezone.now(),
            approved_by=actor_id,
        )
        availability = api_client.post(
            "/api/v2/budget-management/availability/",
            {
                "account_code": "6200",
                "amount": "40.00",
                "period": "2025-03-15",
                "budget_id": str(budget.id),
            },
            format="json",
        )
        assert availability.status_code == status.HTTP_200_OK
        assert availability.json()["data"]["sufficient"] is True

    def test_transition_and_variance_alert_routes_translate_domain_results(self, api_client, authenticated_user):
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        actor_id = _actor_id(authenticated_user)
        approver_id = uuid.uuid4()
        configure_integrations(workflow=WorkflowAdapter(approver_id))
        budget = BudgetService.create_budget(
            tenant_id,
            actor_id,
            **_budget_payload("BUD-FLOW"),
        )
        BudgetService.update_budget(
            tenant_id,
            budget.id,
            actor_id,
            expected_updated_at=budget.updated_at,
            changes={"budget_ceiling": Decimal("100.00")},
        )
        BudgetService.create_line(
            tenant_id,
            budget.id,
            actor_id,
            {"account_code": "6300", "period_type": "annual", "period_number": 1, "budget_amount": "100.00"},
        )
        api_client.force_login(user=authenticated_user)

        missing_key = api_client.post(f"/api/v2/budget-management/budgets/{budget.id}/submit/", {}, format="json")
        assert missing_key.status_code == status.HTTP_400_BAD_REQUEST
        assert missing_key.json()["error"]["code"] == "VALIDATION_ERROR"

        submitted = api_client.post(
            f"/api/v2/budget-management/budgets/{budget.id}/submit/",
            {"notes": "Submit for governed approval."},
            format="json",
            HTTP_IDEMPOTENCY_KEY="api-submit-budget",
        )
        assert submitted.status_code == status.HTTP_200_OK
        assert submitted.json()["data"]["status"] == "pending_approval"

        self_approval = api_client.post(
            f"/api/v2/budget-management/budgets/{budget.id}/approve/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="api-self-approve",
        )
        assert self_approval.status_code == status.HTTP_403_FORBIDDEN
        assert self_approval.json()["error"]["code"] in {
            "APPROVAL_NOT_ASSIGNED",
            "APPROVAL_LEVEL_PENDING",
            "SELF_APPROVAL_FORBIDDEN",
        }

        generated = VarianceAlertService.generate_alerts(
            tenant_id,
            threshold_percentage="10.00",
            alert_type="approaching_limit",
            alert_date=date(2025, 12, 31),
        )
        if not generated:
            line = BudgetLine.objects.get(tenant_id=tenant_id, budget=budget)
            BudgetControlService.record_commitment(
                tenant_id,
                line.id,
                "85.00",
                source_id=uuid.uuid4(),
                idempotency_key="api-alert-commitment",
            )
            Budget.objects.filter(pk=budget.pk).update(
                status="approved",
                approved_at=timezone.now(),
                approved_by=actor_id,
            )
            generated = VarianceAlertService.generate_alerts(
                tenant_id,
                threshold_percentage="10.00",
                alert_type="approaching_limit",
                alert_date=date(2025, 12, 31),
            )
        alert = generated[0]

        alerts = api_client.get("/api/v2/budget-management/variance-alerts/?acknowledged=false")
        assert alerts.status_code == status.HTTP_200_OK
        assert str(alert.id) in {item["id"] for item in alerts.json()["data"]}

        acknowledged = api_client.post(
            f"/api/v2/budget-management/variance-alerts/{alert.id}/acknowledge/",
            {},
            format="json",
        )
        assert acknowledged.status_code == status.HTTP_200_OK
        assert acknowledged.json()["data"]["acknowledged_at"] is not None

        job_response = api_client.post(
            "/api/v2/budget-management/variance-alerts/generate/",
            {"threshold_percentage": "10.00", "alert_type": "over_budget"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="api-alert-generation-job",
        )
        assert job_response.status_code == status.HTTP_202_ACCEPTED
        assert job_response.json()["data"]["command"] == "budget_management.generate_variance_alerts"
