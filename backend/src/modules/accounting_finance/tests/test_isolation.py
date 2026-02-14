"""
Tenant Isolation Tests for Accounting & Finance module.

CRITICAL: These tests verify that tenants cannot access each other's data.
This is the PRIMARY security mechanism for multi-tenant isolation.

Reference: saraise-documentation/rules/compliance-enforcement.md
Rule: ALL tenant-scoped queries MUST filter by tenant_id
"""

import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.modules.accounting_finance.models import Account, APInvoice, ARInvoice, JournalEntry

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
class TestAccountTenantIsolation:
    """CRITICAL: Tenant isolation tests for Account model."""

    def test_user_cannot_list_other_tenant_accounts(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's accounts in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create account for tenant A
        account_a = Account.objects.create(
            tenant_id=tenant_a_id,
            code="1000",
            name="Cash",
            account_type="asset",
        )

        # Create account for tenant B
        account_b = Account.objects.create(
            tenant_id=tenant_b_id,
            code="1000",
            name="Cash",
            account_type="asset",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/accounting-finance/accounts/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        account_ids = [a["id"] for a in data]

        # User A should see tenant A's account, but NOT tenant B's account
        assert str(account_a.id) in account_ids
        assert str(account_b.id) not in account_ids

    def test_user_cannot_get_other_tenant_account_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's account by ID (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create account for tenant B
        account_b = Account.objects.create(
            tenant_id=tenant_b_id,
            code="2000",
            name="Accounts Payable",
            account_type="liability",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's account
        response = api_client.get(f"/api/v1/accounting-finance/accounts/{account_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_update_other_tenant_account(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot UPDATE other tenant's account (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create account for tenant B
        account_b = Account.objects.create(
            tenant_id=tenant_b_id,
            code="3000",
            name="Equity",
            account_type="equity",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to update tenant B's account
        data = {"name": "Hacked Name"}
        response = api_client.patch(f"/api/v1/accounting-finance/accounts/{account_b.id}/", data, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify account was not modified
        account_b.refresh_from_db()
        assert account_b.name == "Equity"

    def test_user_cannot_delete_other_tenant_account(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot DELETE other tenant's account (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create account for tenant B
        account_b = Account.objects.create(
            tenant_id=tenant_b_id,
            code="4000",
            name="Revenue",
            account_type="revenue",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to delete tenant B's account
        response = api_client.delete(f"/api/v1/accounting-finance/accounts/{account_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify account still exists
        assert Account.objects.filter(id=account_b.id).exists()


@pytest.mark.django_db
class TestJournalEntryTenantIsolation:
    """CRITICAL: Tenant isolation tests for JournalEntry model."""

    def test_user_cannot_list_other_tenant_journal_entries(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's journal entries in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        from src.modules.accounting_finance.models import PostingPeriod
        from django.utils import timezone
        from datetime import date

        # Create posting periods
        period_a = PostingPeriod.objects.create(
            tenant_id=tenant_a_id,
            period_name="2024-01",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
        period_b = PostingPeriod.objects.create(
            tenant_id=tenant_b_id,
            period_name="2024-01",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        # Create journal entry for tenant A
        entry_a = JournalEntry.objects.create(
            tenant_id=tenant_a_id,
            entry_number="JE-001",
            posting_date=date(2024, 1, 15),
            posting_period=period_a,
            status="draft",
        )

        # Create journal entry for tenant B
        entry_b = JournalEntry.objects.create(
            tenant_id=tenant_b_id,
            entry_number="JE-001",
            posting_date=date(2024, 1, 15),
            posting_period=period_b,
            status="draft",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/accounting-finance/journal-entries/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        entry_ids = [e["id"] for e in data]

        # User A should see tenant A's entry, but NOT tenant B's entry
        assert str(entry_a.id) in entry_ids
        assert str(entry_b.id) not in entry_ids

    def test_user_cannot_get_other_tenant_journal_entry_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's journal entry by ID (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        from src.modules.accounting_finance.models import PostingPeriod
        from datetime import date

        period_b = PostingPeriod.objects.create(
            tenant_id=tenant_b_id,
            period_name="2024-01",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        entry_b = JournalEntry.objects.create(
            tenant_id=tenant_b_id,
            entry_number="JE-002",
            posting_date=date(2024, 1, 16),
            posting_period=period_b,
            status="draft",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's journal entry
        response = api_client.get(f"/api/v1/accounting-finance/journal-entries/{entry_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
