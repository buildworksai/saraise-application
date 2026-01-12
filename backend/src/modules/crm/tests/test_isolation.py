"""
Tenant Isolation Tests for CRM module.

CRITICAL: These tests verify that tenants cannot access each other's data.
This is the PRIMARY security mechanism for multi-tenant isolation.

Reference: saraise-documentation/rules/compliance-enforcement.md
Rule: ALL tenant-scoped queries MUST filter by tenant_id
"""
import uuid
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.modules.crm.models import Account, Activity, Contact, Lead, Opportunity

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


@pytest.fixture
def tenant_b_user(db):
    """Create user for tenant B."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_b",
        email="userb@example.com",
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
class TestLeadTenantIsolation:
    """CRITICAL: Tenant isolation tests for Lead model."""

    def test_user_cannot_list_other_tenant_leads(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's leads in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create lead for tenant A
        lead_a = Lead.objects.create(
            tenant_id=tenant_a_id,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            company="Acme Corp",
            created_by=tenant_a_user.id,
        )

        # Create lead for tenant B
        lead_b = Lead.objects.create(
            tenant_id=tenant_b_id,
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            company="Beta Corp",
            created_by=tenant_b_user.id,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/crm/leads/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        lead_ids = [str(lead["id"]) for lead in data]

        # User A should see tenant A's lead, but NOT tenant B's lead
        assert str(lead_a.id) in lead_ids
        assert str(lead_b.id) not in lead_ids

    def test_user_cannot_get_other_tenant_lead_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's lead by ID (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create lead for tenant B
        lead_b = Lead.objects.create(
            tenant_id=tenant_b_id,
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            company="Beta Corp",
            created_by=tenant_b_user.id,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's lead
        response = api_client.get(f"/api/v1/crm/leads/{lead_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_update_other_tenant_lead(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot UPDATE other tenant's lead (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create lead for tenant B
        lead_b = Lead.objects.create(
            tenant_id=tenant_b_id,
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            company="Beta Corp",
            created_by=tenant_b_user.id,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to update tenant B's lead
        data = {"first_name": "Hacked Name"}
        response = api_client.patch(
            f"/api/v1/crm/leads/{lead_b.id}/",
            data,
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify lead was not modified
        lead_b.refresh_from_db()
        assert lead_b.first_name == "Jane"

    def test_user_cannot_delete_other_tenant_lead(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot DELETE other tenant's lead (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create lead for tenant B
        lead_b = Lead.objects.create(
            tenant_id=tenant_b_id,
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            company="Beta Corp",
            created_by=tenant_b_user.id,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to delete tenant B's lead
        response = api_client.delete(f"/api/v1/crm/leads/{lead_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify lead still exists
        assert Lead.objects.filter(id=lead_b.id).exists()


@pytest.mark.django_db
class TestAccountTenantIsolation:
    """Tenant isolation tests for Account model."""

    def test_user_cannot_list_other_tenant_accounts(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's accounts in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create account for tenant A
        account_a = Account.objects.create(
            tenant_id=tenant_a_id,
            name="Acme Corp",
            created_by=tenant_a_user.id,
        )

        # Create account for tenant B
        account_b = Account.objects.create(
            tenant_id=tenant_b_id,
            name="Beta Corp",
            created_by=tenant_b_user.id,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/crm/accounts/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        account_ids = [str(account["id"]) for account in data]

        # User A should see tenant A's account, but NOT tenant B's account
        assert str(account_a.id) in account_ids
        assert str(account_b.id) not in account_ids

    def test_user_cannot_get_other_tenant_account_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's account by ID (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create account for tenant B
        account_b = Account.objects.create(
            tenant_id=tenant_b_id,
            name="Beta Corp",
            created_by=tenant_b_user.id,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's account
        response = api_client.get(f"/api/v1/crm/accounts/{account_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestContactTenantIsolation:
    """Tenant isolation tests for Contact model."""

    def test_user_cannot_list_other_tenant_contacts(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's contacts in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create accounts
        account_a = Account.objects.create(
            tenant_id=tenant_a_id,
            name="Acme Corp",
            created_by=tenant_a_user.id,
        )

        account_b = Account.objects.create(
            tenant_id=tenant_b_id,
            name="Beta Corp",
            created_by=tenant_b_user.id,
        )

        # Create contacts
        contact_a = Contact.objects.create(
            tenant_id=tenant_a_id,
            account_id=account_a.id,
            first_name="John",
            last_name="Doe",
            created_by=tenant_a_user.id,
        )

        contact_b = Contact.objects.create(
            tenant_id=tenant_b_id,
            account_id=account_b.id,
            first_name="Jane",
            last_name="Smith",
            created_by=tenant_b_user.id,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/crm/contacts/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        contact_ids = [str(contact["id"]) for contact in data]

        # User A should see tenant A's contact, but NOT tenant B's contact
        assert str(contact_a.id) in contact_ids
        assert str(contact_b.id) not in contact_ids


@pytest.mark.django_db
class TestOpportunityTenantIsolation:
    """Tenant isolation tests for Opportunity model."""

    def test_user_cannot_list_other_tenant_opportunities(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's opportunities in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create accounts
        account_a = Account.objects.create(
            tenant_id=tenant_a_id,
            name="Acme Corp",
            created_by=tenant_a_user.id,
        )

        account_b = Account.objects.create(
            tenant_id=tenant_b_id,
            name="Beta Corp",
            created_by=tenant_b_user.id,
        )

        # Create opportunities
        from decimal import Decimal

        opportunity_a = Opportunity.objects.create(
            tenant_id=tenant_a_id,
            account_id=account_a.id,
            name="Deal A",
            amount=Decimal("10000.00"),
            close_date=date.today() + timedelta(days=30),
            owner_id=tenant_a_user.id,
            created_by=tenant_a_user.id,
        )

        opportunity_b = Opportunity.objects.create(
            tenant_id=tenant_b_id,
            account_id=account_b.id,
            name="Deal B",
            amount=Decimal("20000.00"),
            close_date=date.today() + timedelta(days=30),
            owner_id=tenant_b_user.id,
            created_by=tenant_b_user.id,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/crm/opportunities/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        opportunity_ids = [str(opp["id"]) for opp in data]

        # User A should see tenant A's opportunity, but NOT tenant B's opportunity
        assert str(opportunity_a.id) in opportunity_ids
        assert str(opportunity_b.id) not in opportunity_ids


@pytest.mark.django_db
class TestActivityTenantIsolation:
    """Tenant isolation tests for Activity model."""

    def test_user_cannot_list_other_tenant_activities(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's activities in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create leads
        lead_a = Lead.objects.create(
            tenant_id=tenant_a_id,
            first_name="John",
            last_name="Doe",
            created_by=tenant_a_user.id,
        )

        lead_b = Lead.objects.create(
            tenant_id=tenant_b_id,
            first_name="Jane",
            last_name="Smith",
            created_by=tenant_b_user.id,
        )

        # Create activities
        from src.modules.crm.models import ActivityType, RelatedToType

        activity_a = Activity.objects.create(
            tenant_id=tenant_a_id,
            activity_type=ActivityType.CALL,
            related_to_type=RelatedToType.LEAD,
            related_to_id=lead_a.id,
            subject="Call with John",
            owner_id=tenant_a_user.id,
            created_by=tenant_a_user.id,
        )

        activity_b = Activity.objects.create(
            tenant_id=tenant_b_id,
            activity_type=ActivityType.CALL,
            related_to_type=RelatedToType.LEAD,
            related_to_id=lead_b.id,
            subject="Call with Jane",
            owner_id=tenant_b_user.id,
            created_by=tenant_b_user.id,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/crm/activities/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        activity_ids = [str(activity["id"]) for activity in data]

        # User A should see tenant A's activity, but NOT tenant B's activity
        assert str(activity_a.id) in activity_ids
        assert str(activity_b.id) not in activity_ids
