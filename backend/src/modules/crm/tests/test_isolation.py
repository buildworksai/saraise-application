"""
Tenant Isolation Tests for CRM module.

CRITICAL: These tests verify that tenants cannot access each other's data.
This is the PRIMARY security mechanism for multi-tenant isolation.

Reference: saraise-documentation/rules/compliance-enforcement.md
Rule: ALL tenant-scoped queries MUST filter by tenant_id
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.access.decision import AccessDecision, AccessDecisionPipeline, AccessReasonCode
from src.core.auth_utils import get_user_tenant_id
from src.modules.crm.models import Account, Activity, Contact, Lead, Opportunity

User = get_user_model()


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"


@pytest.fixture(autouse=True)
def authorized_access_decision(monkeypatch):
    """Authorize the request tenant so this suite exercises isolation, not RBAC setup."""

    def allow(
        unused_pipeline,
        tenant_id,
        unused_identity,
        unused_permission,
        **unused_context,
    ):
        assert tenant_id is not None
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="Tenant-isolation contract test authorization.",
            tenant_id=uuid.UUID(str(tenant_id)),
        )

    monkeypatch.setattr(AccessDecisionPipeline, "decide", allow)


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

    def test_user_cannot_create_lead_for_other_tenant(self, api_client, tenant_a_user, tenant_b_user):
        """A client-supplied foreign tenant is rejected and creates no row."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.post(
            "/api/v1/crm/leads/",
            {
                "tenant_id": str(tenant_b_id),
                "first_name": "Mallory",
                "last_name": "Spoofed",
                "email": "spoofed-lead@example.test",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="lead-cross-tenant-create",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Lead.objects.filter(
            tenant_id__in=(tenant_a_id, tenant_b_id), email="spoofed-lead@example.test"
        ).exists()

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
            HTTP_IDEMPOTENCY_KEY="lead-cross-tenant-update",
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
        response = api_client.delete(
            f"/api/v1/crm/leads/{lead_b.id}/",
            HTTP_IF_MATCH=str(lead_b.version),
            HTTP_IDEMPOTENCY_KEY="lead-cross-tenant-delete",
        )
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

    def test_user_cannot_spoof_account_tenant(self, api_client, tenant_a_user, tenant_b_user):
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.post(
            "/api/v1/crm/accounts/",
            {"tenant_id": str(tenant_b_id), "name": "Tenant Spoof Account"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="account-tenant-spoof",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Account.objects.filter(
            tenant_id__in=(tenant_a_id, tenant_b_id),
            name="Tenant Spoof Account",
        ).exists()

    def test_user_cannot_create_account_for_other_tenant_or_foreign_parent(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        foreign_parent = Account.objects.create(
            tenant_id=tenant_b_id,
            name="Foreign Parent",
            created_by=tenant_b_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.post(
            "/api/v1/crm/accounts/",
            {
                "name": "Spoofed Child",
                "parent_account_id": str(foreign_parent.id),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="account-cross-tenant-create",
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert not Account.objects.filter(tenant_id__in=(tenant_a_id, tenant_b_id), name="Spoofed Child").exists()

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

    def test_user_cannot_update_other_tenant_account(self, api_client, tenant_a_user, tenant_b_user):
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        account_b = Account.objects.create(
            tenant_id=tenant_b_id,
            name="Foreign Account",
            created_by=tenant_b_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.patch(
            f"/api/v1/crm/accounts/{account_b.id}/",
            {"name": "Tampered", "version": account_b.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="account-cross-tenant-update",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        account_b.refresh_from_db()
        assert account_b.name == "Foreign Account"

    def test_user_cannot_delete_other_tenant_account(self, api_client, tenant_a_user, tenant_b_user):
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        account_b = Account.objects.create(
            tenant_id=tenant_b_id,
            name="Foreign Account",
            created_by=tenant_b_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.delete(
            f"/api/v1/crm/accounts/{account_b.id}/",
            HTTP_IF_MATCH=str(account_b.version),
            HTTP_IDEMPOTENCY_KEY="account-cross-tenant-delete",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        account_b.refresh_from_db()
        assert account_b.is_deleted is False


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

    def test_user_cannot_spoof_contact_tenant(self, api_client, tenant_a_user, tenant_b_user):
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        account_a = Account.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Contact Account",
            created_by=tenant_a_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.post(
            "/api/v1/crm/contacts/",
            {
                "tenant_id": str(tenant_b_id),
                "account_id": str(account_a.id),
                "first_name": "Tenant",
                "last_name": "Spoof",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="contact-tenant-spoof",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Contact.objects.filter(
            tenant_id__in=(tenant_a_id, tenant_b_id),
            first_name="Tenant",
            last_name="Spoof",
        ).exists()

    def test_user_cannot_create_contact_for_other_tenant_or_foreign_account(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        foreign_account = Account.objects.create(
            tenant_id=tenant_b_id,
            name="Foreign Contact Account",
            created_by=tenant_b_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.post(
            "/api/v1/crm/contacts/",
            {
                "account_id": str(foreign_account.id),
                "first_name": "Mallory",
                "last_name": "Spoofed",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="contact-cross-tenant-create",
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert not Contact.objects.filter(
            tenant_id__in=(tenant_a_id, tenant_b_id), first_name="Mallory", last_name="Spoofed"
        ).exists()

    def test_user_cannot_get_other_tenant_contact_by_id(self, api_client, tenant_a_user, tenant_b_user):
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        account_b = Account.objects.create(
            tenant_id=tenant_b_id, name="Foreign Contact Account", created_by=tenant_b_user.id
        )
        contact_b = Contact.objects.create(
            tenant_id=tenant_b_id,
            account_id=account_b.id,
            first_name="Foreign",
            last_name="Contact",
            created_by=tenant_b_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get(f"/api/v1/crm/contacts/{contact_b.id}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_update_other_tenant_contact(self, api_client, tenant_a_user, tenant_b_user):
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        account_b = Account.objects.create(
            tenant_id=tenant_b_id, name="Foreign Contact Account", created_by=tenant_b_user.id
        )
        contact_b = Contact.objects.create(
            tenant_id=tenant_b_id,
            account_id=account_b.id,
            first_name="Foreign",
            last_name="Contact",
            created_by=tenant_b_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.patch(
            f"/api/v1/crm/contacts/{contact_b.id}/",
            {"first_name": "Tampered", "version": contact_b.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="contact-cross-tenant-update",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        contact_b.refresh_from_db()
        assert contact_b.first_name == "Foreign"

    def test_user_cannot_delete_other_tenant_contact(self, api_client, tenant_a_user, tenant_b_user):
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        account_b = Account.objects.create(
            tenant_id=tenant_b_id, name="Foreign Contact Account", created_by=tenant_b_user.id
        )
        contact_b = Contact.objects.create(
            tenant_id=tenant_b_id,
            account_id=account_b.id,
            first_name="Foreign",
            last_name="Contact",
            created_by=tenant_b_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.delete(
            f"/api/v1/crm/contacts/{contact_b.id}/",
            HTTP_IF_MATCH=str(contact_b.version),
            HTTP_IDEMPOTENCY_KEY="contact-cross-tenant-delete",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        contact_b.refresh_from_db()
        assert contact_b.is_deleted is False


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

    def test_user_cannot_spoof_opportunity_tenant(self, api_client, tenant_a_user, tenant_b_user):
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        account_a = Account.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Opportunity Account",
            created_by=tenant_a_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.post(
            "/api/v1/crm/opportunities/",
            {
                "tenant_id": str(tenant_b_id),
                "account_id": str(account_a.id),
                "name": "Tenant Spoof Opportunity",
                "amount": "100.00",
                "close_date": str(date.today() + timedelta(days=30)),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="opportunity-tenant-spoof",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Opportunity.objects.filter(
            tenant_id__in=(tenant_a_id, tenant_b_id),
            name="Tenant Spoof Opportunity",
        ).exists()

    def test_user_cannot_create_opportunity_for_other_tenant_or_foreign_references(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        account_b = Account.objects.create(
            tenant_id=tenant_b_id, name="Foreign Opportunity Account", created_by=tenant_b_user.id
        )
        contact_b = Contact.objects.create(
            tenant_id=tenant_b_id,
            account_id=account_b.id,
            first_name="Foreign",
            last_name="Buyer",
            created_by=tenant_b_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.post(
            "/api/v1/crm/opportunities/",
            {
                "account_id": str(account_b.id),
                "primary_contact_id": str(contact_b.id),
                "name": "Spoofed Opportunity",
                "amount": "100.00",
                "close_date": str(date.today() + timedelta(days=30)),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="opportunity-cross-tenant-create",
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert not Opportunity.objects.filter(
            tenant_id__in=(tenant_a_id, tenant_b_id), name="Spoofed Opportunity"
        ).exists()

    def test_user_cannot_get_other_tenant_opportunity_by_id(self, api_client, tenant_a_user, tenant_b_user):
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        account_b = Account.objects.create(
            tenant_id=tenant_b_id, name="Foreign Opportunity Account", created_by=tenant_b_user.id
        )
        opportunity_b = Opportunity.objects.create(
            tenant_id=tenant_b_id,
            account_id=account_b.id,
            name="Foreign Opportunity",
            amount=Decimal("200.00"),
            close_date=date.today() + timedelta(days=30),
            created_by=tenant_b_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get(f"/api/v1/crm/opportunities/{opportunity_b.id}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_update_other_tenant_opportunity(self, api_client, tenant_a_user, tenant_b_user):
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        account_b = Account.objects.create(
            tenant_id=tenant_b_id, name="Foreign Opportunity Account", created_by=tenant_b_user.id
        )
        opportunity_b = Opportunity.objects.create(
            tenant_id=tenant_b_id,
            account_id=account_b.id,
            name="Foreign Opportunity",
            amount=Decimal("200.00"),
            close_date=date.today() + timedelta(days=30),
            created_by=tenant_b_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.patch(
            f"/api/v1/crm/opportunities/{opportunity_b.id}/",
            {"name": "Tampered", "version": opportunity_b.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="opportunity-cross-tenant-update",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        opportunity_b.refresh_from_db()
        assert opportunity_b.name == "Foreign Opportunity"

    def test_user_cannot_delete_other_tenant_opportunity(self, api_client, tenant_a_user, tenant_b_user):
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        account_b = Account.objects.create(
            tenant_id=tenant_b_id, name="Foreign Opportunity Account", created_by=tenant_b_user.id
        )
        opportunity_b = Opportunity.objects.create(
            tenant_id=tenant_b_id,
            account_id=account_b.id,
            name="Foreign Opportunity",
            amount=Decimal("200.00"),
            close_date=date.today() + timedelta(days=30),
            created_by=tenant_b_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.delete(
            f"/api/v1/crm/opportunities/{opportunity_b.id}/",
            HTTP_IF_MATCH=str(opportunity_b.version),
            HTTP_IDEMPOTENCY_KEY="opportunity-cross-tenant-delete",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        opportunity_b.refresh_from_db()
        assert opportunity_b.is_deleted is False


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

    def test_user_cannot_spoof_activity_tenant(self, api_client, tenant_a_user, tenant_b_user):
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        lead_a = Lead.objects.create(
            tenant_id=tenant_a_id,
            first_name="Tenant",
            last_name="A Lead",
            created_by=tenant_a_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.post(
            "/api/v1/crm/activities/",
            {
                "tenant_id": str(tenant_b_id),
                "activity_type": "call",
                "related_to_type": "Lead",
                "related_to_id": str(lead_a.id),
                "subject": "Tenant Spoof Activity",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="activity-tenant-spoof",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Activity.objects.filter(
            tenant_id__in=(tenant_a_id, tenant_b_id),
            subject="Tenant Spoof Activity",
        ).exists()

    def test_user_cannot_create_activity_for_other_tenant_or_foreign_record(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        lead_b = Lead.objects.create(
            tenant_id=tenant_b_id,
            first_name="Foreign",
            last_name="Lead",
            created_by=tenant_b_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.post(
            "/api/v1/crm/activities/",
            {
                "activity_type": "call",
                "related_to_type": "Lead",
                "related_to_id": str(lead_b.id),
                "subject": "Spoofed Activity",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="activity-cross-tenant-create",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert not Activity.objects.filter(
            tenant_id__in=(tenant_a_id, tenant_b_id), subject="Spoofed Activity"
        ).exists()

    def test_user_cannot_get_other_tenant_activity_by_id(self, api_client, tenant_a_user, tenant_b_user):
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        lead_b = Lead.objects.create(
            tenant_id=tenant_b_id, first_name="Foreign", last_name="Lead", created_by=tenant_b_user.id
        )
        activity_b = Activity.objects.create(
            tenant_id=tenant_b_id,
            activity_type="call",
            related_to_type="Lead",
            related_to_id=lead_b.id,
            subject="Foreign Activity",
            created_by=tenant_b_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get(f"/api/v1/crm/activities/{activity_b.id}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_update_other_tenant_activity(self, api_client, tenant_a_user, tenant_b_user):
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        lead_b = Lead.objects.create(
            tenant_id=tenant_b_id, first_name="Foreign", last_name="Lead", created_by=tenant_b_user.id
        )
        activity_b = Activity.objects.create(
            tenant_id=tenant_b_id,
            activity_type="call",
            related_to_type="Lead",
            related_to_id=lead_b.id,
            subject="Foreign Activity",
            created_by=tenant_b_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.patch(
            f"/api/v1/crm/activities/{activity_b.id}/",
            {"subject": "Tampered", "version": activity_b.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="activity-cross-tenant-update",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        activity_b.refresh_from_db()
        assert activity_b.subject == "Foreign Activity"

    def test_user_cannot_delete_other_tenant_activity(self, api_client, tenant_a_user, tenant_b_user):
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))
        lead_b = Lead.objects.create(
            tenant_id=tenant_b_id, first_name="Foreign", last_name="Lead", created_by=tenant_b_user.id
        )
        activity_b = Activity.objects.create(
            tenant_id=tenant_b_id,
            activity_type="call",
            related_to_type="Lead",
            related_to_id=lead_b.id,
            subject="Foreign Activity",
            created_by=tenant_b_user.id,
        )
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.delete(
            f"/api/v1/crm/activities/{activity_b.id}/",
            HTTP_IF_MATCH=str(activity_b.version),
            HTTP_IDEMPOTENCY_KEY="activity-cross-tenant-delete",
        )

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        activity_b.refresh_from_db()
        assert activity_b.is_deleted is False
