"""
API Endpoint Tests for CRM module.

Tests DRF ViewSets and API endpoints.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.modules.crm.models import (
    Account,
    AccountType,
    Activity,
    ActivityType,
    Contact,
    Lead,
    LeadStatus,
    Opportunity,
    OpportunityStage,
    OpportunityStatus,
    RelatedToType,
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

    def test_create_lead(self, api_client, authenticated_user):
        """Test creating a lead via API."""
        api_client.force_authenticate(user=authenticated_user)

        data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "company": "Acme Corp",
        }

        response = api_client.post("/api/v1/crm/leads/", data, format="json")
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

        response = api_client.post(f"/api/v1/crm/leads/{lead.id}/convert/", data, format="json")
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

        response = api_client.post("/api/v1/crm/opportunities/", data, format="json")
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

        response = api_client.post(f"/api/v1/crm/opportunities/{opportunity.id}/close-won/", {}, format="json")
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
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Try with loss_reason
        response = api_client.post(
            f"/api/v1/crm/opportunities/{opportunity.id}/close-lost/",
            {"loss_reason": "Customer chose competitor"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == OpportunityStatus.LOST


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
