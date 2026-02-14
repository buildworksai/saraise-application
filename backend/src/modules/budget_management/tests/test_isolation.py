"""
Tenant Isolation Tests for Budget Management module.
"""

import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.modules.budget_management.models import Budget

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
            budget_code="BUD-A",
            budget_name="Budget A",
            fiscal_year=2024,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        # Create budget for tenant B
        budget_b = Budget.objects.create(
            tenant_id=tenant_b_id,
            budget_code="BUD-B",
            budget_name="Budget B",
            fiscal_year=2024,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/budget-management/budgets/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
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
            budget_code="BUD-B",
            budget_name="Budget B",
            fiscal_year=2024,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's budget
        response = api_client.get(f"/api/v1/budget-management/budgets/{budget_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
