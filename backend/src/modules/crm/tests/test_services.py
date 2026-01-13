"""
Service Layer Tests for CRM module.

Tests business logic, workflows, and service methods.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

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
from src.modules.crm.services import (
    AccountService,
    ActivityService,
    ContactService,
    ForecastingService,
    IntegrationService,
    LeadService,
    OpportunityService,
)


@pytest.mark.django_db
class TestLeadService:
    """Test LeadService."""

    def test_create_lead(self, db):
        """Test creating a lead via service."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        service = LeadService()
        lead = service.create_lead(
            tenant_id=tenant_id,
            data={
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com",
                "company": "Acme Corp",
            },
            created_by=str(user_id),
        )

        assert lead.id is not None
        assert lead.first_name == "John"
        assert lead.score >= 0  # Score should be calculated

    def test_score_lead(self, db):
        """Test lead scoring."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        lead = Lead.objects.create(
            tenant_id=tenant_id,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            company="Acme Corp",
            source="referral",
            created_by=str(user_id),
        )

        service = LeadService()
        updated_lead = service.score_lead(lead_id=lead.id, tenant_id=tenant_id)

        assert updated_lead.score > 0
        assert updated_lead.grade in ["A", "B", "C", "D"]


@pytest.mark.django_db
class TestAccountService:
    """Test AccountService."""

    def test_create_account(self, db):
        """Test creating an account via service."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        service = AccountService()
        account = service.create_account(
            tenant_id=tenant_id,
            data={
                "name": "Acme Corp",
                "industry": "Technology",
            },
            created_by=str(user_id),
        )

        assert account.id is not None
        assert account.name == "Acme Corp"

    def test_delete_account_with_open_opportunities(self, db):
        """Test cannot delete account with open opportunities."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        account = Account.objects.create(
            tenant_id=tenant_id,
            name="Acme Corp",
            created_by=str(user_id),
        )

        # Create open opportunity
        Opportunity.objects.create(
            tenant_id=tenant_id,
            account_id=account.id,
            name="Deal 1",
            amount=Decimal("10000.00"),
            close_date=date.today() + timedelta(days=30),
            owner_id=user_id,
            created_by=str(user_id),
        )

        service = AccountService()
        with pytest.raises(ValidationError, match="open opportunities"):
            service.delete_account(account_id=account.id, tenant_id=tenant_id)


@pytest.mark.django_db
class TestOpportunityService:
    """Test OpportunityService."""

    def test_close_won(self, db):
        """Test closing opportunity as won."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        account = Account.objects.create(
            tenant_id=tenant_id,
            name="Acme Corp",
            account_type=AccountType.PROSPECT,
            created_by=str(user_id),
        )

        opportunity = Opportunity.objects.create(
            tenant_id=tenant_id,
            account_id=account.id,
            name="Deal 1",
            amount=Decimal("10000.00"),
            close_date=date.today() + timedelta(days=30),
            owner_id=user_id,
            created_by=str(user_id),
        )

        service = OpportunityService()
        updated_opportunity = service.close_won(
            opportunity_id=opportunity.id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        assert updated_opportunity.status == OpportunityStatus.WON
        assert updated_opportunity.stage == OpportunityStage.CLOSED_WON
        assert updated_opportunity.probability == 100

        # Verify account type updated to customer
        account.refresh_from_db()
        assert account.account_type == AccountType.CUSTOMER

    def test_close_lost_requires_reason(self, db):
        """Test closing opportunity as lost requires loss_reason."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        account = Account.objects.create(
            tenant_id=tenant_id,
            name="Acme Corp",
            created_by=str(user_id),
        )

        opportunity = Opportunity.objects.create(
            tenant_id=tenant_id,
            account_id=account.id,
            name="Deal 1",
            amount=Decimal("10000.00"),
            close_date=date.today() + timedelta(days=30),
            owner_id=user_id,
            created_by=str(user_id),
        )

        service = OpportunityService()
        with pytest.raises(ValidationError, match="Loss reason is required"):
            service.close_lost(
                opportunity_id=opportunity.id,
                tenant_id=tenant_id,
                loss_reason="",  # Empty reason
                user_id=user_id,
            )


@pytest.mark.django_db
class TestIntegrationService:
    """Test IntegrationService."""

    def test_convert_lead_to_opportunity(self, db):
        """Test lead to opportunity conversion workflow."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Create lead
        lead = Lead.objects.create(
            tenant_id=tenant_id,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            company="Acme Corp",
            created_by=str(user_id),
        )

        service = IntegrationService()
        result = service.convert_lead_to_opportunity(
            lead_id=lead.id,
            tenant_id=tenant_id,
            opportunity_data={
                "amount": Decimal("10000.00"),
                "close_date": date.today() + timedelta(days=30),
            },
            user_id=user_id,
        )

        assert result["opportunity"] is not None
        assert result["account"] is not None
        assert result["contact"] is not None

        # Verify lead status updated
        lead.refresh_from_db()
        assert lead.status == LeadStatus.CONVERTED
        assert lead.converted_to_opportunity_id == result["opportunity"].id

    def test_convert_lead_without_email_or_company(self, db):
        """Test cannot convert lead without email or company."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        lead = Lead.objects.create(
            tenant_id=tenant_id,
            first_name="John",
            last_name="Doe",
            # No email or company
            created_by=str(user_id),
        )

        service = IntegrationService()
        with pytest.raises(ValidationError, match="email or company"):
            service.convert_lead_to_opportunity(
                lead_id=lead.id,
                tenant_id=tenant_id,
                opportunity_data={
                    "amount": Decimal("10000.00"),
                    "close_date": date.today() + timedelta(days=30),
                },
                user_id=user_id,
            )


@pytest.mark.django_db
class TestForecastingService:
    """Test ForecastingService."""

    def test_get_weighted_pipeline(self, db):
        """Test weighted pipeline calculation."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        account = Account.objects.create(
            tenant_id=tenant_id,
            name="Acme Corp",
            created_by=str(user_id),
        )

        # Create opportunities with different probabilities
        Opportunity.objects.create(
            tenant_id=tenant_id,
            account_id=account.id,
            name="Deal 1",
            amount=Decimal("10000.00"),
            probability=50,
            close_date=date.today() + timedelta(days=30),
            owner_id=user_id,
            created_by=str(user_id),
        )

        Opportunity.objects.create(
            tenant_id=tenant_id,
            account_id=account.id,
            name="Deal 2",
            amount=Decimal("20000.00"),
            probability=80,
            close_date=date.today() + timedelta(days=30),
            owner_id=user_id,
            created_by=str(user_id),
        )

        service = ForecastingService()
        result = service.get_weighted_pipeline(tenant_id=tenant_id, period_days=90)

        assert result["total_pipeline_value"] == 30000.0
        assert result["weighted_pipeline_value"] == 21000.0  # (10000 * 0.5) + (20000 * 0.8)
        assert result["opportunity_count"] == 2
