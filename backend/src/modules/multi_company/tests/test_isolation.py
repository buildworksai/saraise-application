"""
Tenant Isolation Tests for Multi-Company module.
"""

import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.modules.multi_company.models import Company

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
class TestCompanyTenantIsolation:
    """CRITICAL: Tenant isolation tests for Company model."""

    def test_user_cannot_list_other_tenant_companies(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's companies in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create company for tenant A
        company_a = Company.objects.create(
            tenant_id=tenant_a_id,
            company_code="COMP-A",
            company_name="Company A",
        )

        # Create company for tenant B
        company_b = Company.objects.create(
            tenant_id=tenant_b_id,
            company_code="COMP-B",
            company_name="Company B",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/multi-company/companies/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        company_ids = [c["id"] for c in data]

        # User A should see tenant A's company, but NOT tenant B's company
        assert str(company_a.id) in company_ids
        assert str(company_b.id) not in company_ids

    def test_user_cannot_get_other_tenant_company_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's company by ID (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create company for tenant B
        company_b = Company.objects.create(
            tenant_id=tenant_b_id,
            company_code="COMP-B",
            company_name="Company B",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's company
        response = api_client.get(f"/api/v1/multi-company/companies/{company_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_binds_authenticated_tenant_and_ignores_spoofed_owner(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """A server-owned tenant identifier can never redirect a create."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.post(
            "/api/v1/multi-company/companies/",
            {
                "tenant_id": str(tenant_b_id),
                "company_code": "BOUND-A",
                "company_name": "Bound to A",
                "legal_name": "Bound to A Limited",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        company = Company.objects.get(pk=response.data["id"])
        assert company.tenant_id == tenant_a_id
        assert company.tenant_id != tenant_b_id

    def test_cross_tenant_update_and_delete_are_404_and_leave_row_unchanged(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Mutation lookup is tenant-scoped before either update or deletion."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        company_b = Company.objects.create(
            tenant_id=tenant_b_id,
            company_code="PROTECTED-B",
            company_name="Protected B",
            legal_name="Protected B Limited",
            currency="USD",
        )
        before = Company.objects.filter(pk=company_b.pk).values().get()
        api_client.force_authenticate(user=tenant_a_user)

        patch_response = api_client.patch(
            f"/api/v1/multi-company/companies/{company_b.id}/",
            {"company_name": "Compromised"},
            format="json",
        )
        delete_response = api_client.delete(
            f"/api/v1/multi-company/companies/{company_b.id}/"
        )

        assert patch_response.status_code == status.HTTP_404_NOT_FOUND
        assert delete_response.status_code == status.HTTP_404_NOT_FOUND
        assert Company.objects.filter(pk=company_b.pk).values().get() == before
