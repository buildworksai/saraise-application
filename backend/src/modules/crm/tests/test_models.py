"""
Model Unit Tests for CRM module.

Tests model creation, validation, and relationships.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
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

User = get_user_model()


@pytest.mark.django_db
class TestLeadModel:
    """Test Lead model."""

    def test_create_lead(self, db):
        """Test creating a lead."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        lead = Lead.objects.create(
            tenant_id=tenant_id,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            company="Acme Corp",
            created_by=str(user_id),
        )
        assert lead.id is not None
        assert lead.first_name == "John"
        assert lead.last_name == "Doe"
        assert lead.tenant_id == tenant_id
        assert lead.status == LeadStatus.NEW

    def test_lead_score_validation(self, db):
        """Test lead score must be 0-100."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        lead = Lead(
            tenant_id=tenant_id,
            first_name="John",
            last_name="Doe",
            score=150,  # Invalid
            created_by=str(user_id),
        )

        with pytest.raises(ValidationError):
            lead.full_clean()

    def test_lead_str_representation(self, db):
        """Test lead string representation."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        lead = Lead.objects.create(
            tenant_id=tenant_id,
            first_name="John",
            last_name="Doe",
            company="Acme Corp",
            created_by=str(user_id),
        )
        assert "John" in str(lead)
        assert "Acme Corp" in str(lead)


@pytest.mark.django_db
class TestAccountModel:
    """Test Account model."""

    def test_create_account(self, db):
        """Test creating an account."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        account = Account.objects.create(
            tenant_id=tenant_id,
            name="Acme Corp",
            industry="Technology",
            created_by=str(user_id),
        )
        assert account.id is not None
        assert account.name == "Acme Corp"
        assert account.tenant_id == tenant_id
        assert account.account_type == AccountType.PROSPECT

    def test_account_hierarchy_validation(self, db):
        """Test account hierarchy depth validation (max 3 levels)."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Create parent account
        parent = Account.objects.create(
            tenant_id=tenant_id,
            name="Parent Corp",
            created_by=str(user_id),
        )

        # Create child account
        child = Account.objects.create(
            tenant_id=tenant_id,
            name="Child Corp",
            parent_account_id=parent.id,
            created_by=str(user_id),
        )

        # Create grandchild account
        grandchild = Account.objects.create(
            tenant_id=tenant_id,
            name="Grandchild Corp",
            parent_account_id=child.id,
            created_by=str(user_id),
        )

        # Try to create great-grandchild (should fail)
        great_grandchild = Account(
            tenant_id=tenant_id,
            name="Great Grandchild Corp",
            parent_account_id=grandchild.id,
            created_by=str(user_id),
        )

        with pytest.raises(ValidationError, match="cannot exceed 3 levels"):
            great_grandchild.full_clean()

    def test_account_circular_hierarchy(self, db):
        """Test account cannot reference itself as parent."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        account = Account.objects.create(
            tenant_id=tenant_id,
            name="Acme Corp",
            created_by=str(user_id),
        )

        # Try to set self as parent
        account.parent_account_id = account.id

        with pytest.raises(ValidationError):
            account.full_clean()


@pytest.mark.django_db
class TestContactModel:
    """Test Contact model."""

    def test_create_contact(self, db):
        """Test creating a contact."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Create account first
        account = Account.objects.create(
            tenant_id=tenant_id,
            name="Acme Corp",
            created_by=str(user_id),
        )

        contact = Contact.objects.create(
            tenant_id=tenant_id,
            account_id=account.id,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            created_by=str(user_id),
        )
        assert contact.id is not None
        assert contact.first_name == "John"
        assert contact.account_id == account.id


@pytest.mark.django_db
class TestOpportunityModel:
    """Test Opportunity model."""

    def test_create_opportunity(self, db):
        """Test creating an opportunity."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Create account first
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
        assert opportunity.id is not None
        assert opportunity.name == "Deal 1"
        assert opportunity.amount == Decimal("10000.00")
        assert opportunity.status == OpportunityStatus.OPEN

    def test_opportunity_amount_validation(self, db):
        """Test opportunity amount must be positive."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        account = Account.objects.create(
            tenant_id=tenant_id,
            name="Acme Corp",
            created_by=str(user_id),
        )

        opportunity = Opportunity(
            tenant_id=tenant_id,
            account_id=account.id,
            name="Deal 1",
            amount=Decimal("-1000.00"),  # Invalid
            close_date=date.today() + timedelta(days=30),
            owner_id=user_id,
            created_by=str(user_id),
        )

        with pytest.raises(ValidationError, match="must be positive"):
            opportunity.full_clean()

    def test_opportunity_probability_validation(self, db):
        """Test opportunity probability must be 0-100."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        account = Account.objects.create(
            tenant_id=tenant_id,
            name="Acme Corp",
            created_by=str(user_id),
        )

        opportunity = Opportunity(
            tenant_id=tenant_id,
            account_id=account.id,
            name="Deal 1",
            amount=Decimal("10000.00"),
            probability=150,  # Invalid
            close_date=date.today() + timedelta(days=30),
            owner_id=user_id,
            created_by=str(user_id),
        )

        with pytest.raises(ValidationError, match="must be between 0 and 100"):
            opportunity.full_clean()


@pytest.mark.django_db
class TestActivityModel:
    """Test Activity model."""

    def test_create_activity(self, db):
        """Test creating an activity."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Create lead first
        lead = Lead.objects.create(
            tenant_id=tenant_id,
            first_name="John",
            last_name="Doe",
            created_by=str(user_id),
        )

        activity = Activity.objects.create(
            tenant_id=tenant_id,
            activity_type=ActivityType.CALL,
            related_to_type=RelatedToType.LEAD,
            related_to_id=lead.id,
            subject="Call with John",
            owner_id=user_id,
            created_by=str(user_id),
        )
        assert activity.id is not None
        assert activity.activity_type == ActivityType.CALL
        assert activity.related_to_id == lead.id
