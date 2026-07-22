"""
Tenant Isolation Tests for Budget Management module.
"""

import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_tenant_id
from src.core.testing.tenant_contract import TenantIsolationContract
from src.modules.budget_management.models import Budget, BudgetLine

pytest_plugins = ["src.core.testing.factories"]

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
    monkeypatch.setattr(RequiresAccess, "has_permission", lambda self, request, view: True)
    monkeypatch.setattr(RequiresAccess, "has_object_permission", lambda self, request, view, obj: True)


@pytest.fixture
def tenant_a_user(db):
    """Create user for tenant A."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_a",
        email="usera@example.com",
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
def tenant_b_user(db):
    """Create user for tenant B."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_b",
        email="userb@example.com",
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


@pytest.mark.django_db
class TestBudgetTenantIsolation:
    """CRITICAL: Tenant isolation tests for Budget model."""

    def test_user_cannot_list_other_tenant_budgets(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's budgets in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        from datetime import date

        # Create budget for tenant A
        budget_a = Budget.objects.create(
            tenant_id=tenant_a_id,
            created_by=uuid.uuid4(),
            updated_by=uuid.uuid4(),
            budget_code="BUD-A",
            budget_name="Budget A",
            fiscal_year=2024,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        # Create budget for tenant B
        budget_b = Budget.objects.create(
            tenant_id=tenant_b_id,
            created_by=uuid.uuid4(),
            updated_by=uuid.uuid4(),
            budget_code="BUD-B",
            budget_name="Budget B",
            fiscal_year=2024,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        # Login as tenant A
        api_client.force_login(user=tenant_a_user)

        response = api_client.get("/api/v2/budget-management/budgets/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        budget_ids = [b["id"] for b in data]

        # User A should see tenant A's budget, but NOT tenant B's budget
        assert str(budget_a.id) in budget_ids
        assert str(budget_b.id) not in budget_ids

    def test_user_cannot_get_other_tenant_budget_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's budget by ID (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        from datetime import date

        # Create budget for tenant B
        budget_b = Budget.objects.create(
            tenant_id=tenant_b_id,
            created_by=uuid.uuid4(),
            updated_by=uuid.uuid4(),
            budget_code="BUD-B",
            budget_name="Budget B",
            fiscal_year=2024,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        # Login as tenant A
        api_client.force_login(user=tenant_a_user)

        # Try to access tenant B's budget
        response = api_client.get(f"/api/v2/budget-management/budgets/{budget_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestBudgetIsolationContract(TenantIsolationContract):
    """Reusable full CRUD boundary with exact v2 envelope extraction."""

    model = Budget
    list_url = "/api/v2/budget-management/budgets/"
    detail_url_template = "/api/v2/budget-management/budgets/{pk}/"
    create_payload = {
        "budget_code": "SPOOF", "budget_name": "Spoof attempt", "fiscal_year": 2025,
        "start_date": "2025-01-01", "end_date": "2025-12-31",
        "budget_type": "operating", "currency": "USD",
    }
    update_payload = {"expected_updated_at": "2025-01-01T00:00:00Z", "budget_name": "Blocked"}
    read_denial_statuses = frozenset({status.HTTP_404_NOT_FOUND})

    @pytest.fixture(autouse=True)
    def isolation_context(self, api_client, tenant_a_user, tenant_b_user):
        actor = uuid.uuid4()
        self.tenant_a_row = Budget.objects.create(
            tenant_id=uuid.UUID(get_user_tenant_id(tenant_a_user)), created_by=actor, updated_by=actor,
            budget_code="CONTRACT-A", budget_name="Contract A", fiscal_year=2025,
            start_date="2025-01-01", end_date="2025-12-31", budget_type="operating", currency="USD",
        )
        self.tenant_b_row = Budget.objects.create(
            tenant_id=uuid.UUID(get_user_tenant_id(tenant_b_user)), created_by=actor, updated_by=actor,
            budget_code="CONTRACT-B", budget_name="Contract B", fiscal_year=2025,
            start_date="2025-01-01", end_date="2025-12-31", budget_type="operating", currency="USD",
        )
        api_client.force_login(user=tenant_a_user)
        self.client = api_client

    def get_list_items(self, response):
        return response.json()["data"]


@pytest.mark.django_db
class TestBudgetLineIsolationContract(TenantIsolationContract):
    model = BudgetLine
    list_url = "/api/v2/budget-management/budget-lines/"
    detail_url_template = "/api/v2/budget-management/budget-lines/{pk}/"
    update_payload = {"expected_updated_at": "2025-01-01T00:00:00Z", "budget_amount": "9.00"}
    read_denial_statuses = frozenset({status.HTTP_404_NOT_FOUND})

    @pytest.fixture(autouse=True)
    def isolation_context(self, api_client, tenant_a_user, tenant_b_user):
        actor = uuid.uuid4()
        tenant_a, tenant_b = uuid.UUID(get_user_tenant_id(tenant_a_user)), uuid.UUID(get_user_tenant_id(tenant_b_user))
        budget_a = Budget.objects.create(
            tenant_id=tenant_a, created_by=actor, updated_by=actor, budget_code="LINE-A",
            budget_name="Line A", fiscal_year=2025, start_date="2025-01-01", end_date="2025-12-31",
            budget_type="operating", currency="USD",
        )
        budget_b = Budget.objects.create(
            tenant_id=tenant_b, created_by=actor, updated_by=actor, budget_code="LINE-B",
            budget_name="Line B", fiscal_year=2025, start_date="2025-01-01", end_date="2025-12-31",
            budget_type="operating", currency="USD",
        )
        self.tenant_a_row = BudgetLine.objects.create(
            tenant_id=tenant_a, budget=budget_a, created_by=actor, updated_by=actor,
            account_code="6000", period_type="annual", period_number=1, budget_amount="1.00",
        )
        self.tenant_b_row = BudgetLine.objects.create(
            tenant_id=tenant_b, budget=budget_b, created_by=actor, updated_by=actor,
            account_code="6000", period_type="annual", period_number=1, budget_amount="1.00",
        )
        api_client.force_login(user=tenant_a_user)
        self.client = api_client

    def get_create_payload(self):
        return {
            "budget_id": str(self.tenant_a_row.budget_id), "account_code": "7000",
            "period_type": "annual", "period_number": 1, "budget_amount": "2.00",
        }

    def get_list_items(self, response):
        return response.json()["data"]
