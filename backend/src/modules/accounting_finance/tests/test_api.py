"""
API tests for Accounting & Finance module.
"""

import json
import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.modules.accounting_finance.models import Account

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


@pytest.mark.django_db
class TestAccountAPI:
    """Test Account API endpoints."""

    def test_list_accounts(self, api_client, authenticated_user):
        """Test listing accounts."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)

        Account.objects.create(
            tenant_id=tenant_id,
            code="1000",
            name="Cash",
            account_type="asset",
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v1/accounting-finance/accounts/")

        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)
        assert len(response.data) > 0

    def test_v2_list_accounts_uses_governed_paginated_envelope(self, api_client, authenticated_user):
        """V2 list responses must match the frontend governed pagination contract."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        Account.objects.create(
            tenant_id=tenant_id,
            code="1000",
            name="Cash",
            account_type="asset",
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v2/accounting-finance/accounts/?page=1&page_size=25")

        assert response.status_code == status.HTTP_200_OK
        assert response.data[0]["id"] == str(Account.objects.get(code="1000").id)
        assert response.data[0]["tenant_id"] == str(tenant_id)
        assert response.data[0]["code"] == "1000"
        assert response.data[0]["name"] == "Cash"

        rendered = response.render()

        payload = json.loads(rendered.content)
        assert payload["data"] == response.data
        assert payload["meta"]["pagination"] == {
            "count": 1,
            "page": 1,
            "page_size": 25,
            "total_pages": 1,
            "has_next": False,
            "has_previous": False,
        }
        assert payload["meta"]["correlation_id"]

    def test_v2_detail_accounts_uses_governed_envelope(self, api_client, authenticated_user):
        """V2 detail responses must carry data/meta while v1 remains raw."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)
        account = Account.objects.create(
            tenant_id=tenant_id,
            code="1100",
            name="Bank",
            account_type="asset",
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get(f"/api/v2/accounting-finance/accounts/{account.id}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == "1100"

        rendered = response.render()

        payload = json.loads(rendered.content)
        assert payload["data"]["id"] == str(account.id)
        assert payload["meta"]["correlation_id"]
        assert "pagination" not in payload["meta"]

    def test_create_account(self, api_client, authenticated_user):
        """Test creating an account."""
        api_client.force_authenticate(user=authenticated_user)

        data = {
            "code": "2000",
            "name": "Accounts Payable",
            "account_type": "liability",
        }

        response = api_client.post("/api/v1/accounting-finance/accounts/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["code"] == "2000"
        assert response.data["name"] == "Accounts Payable"
