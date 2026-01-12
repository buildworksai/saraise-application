"""
CRM Services.

High-level service layer for CRM business logic.
Implements workflows, business rules, and cross-module integrations.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
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

logger = logging.getLogger(__name__)


class LeadService:
    """Service for managing lead lifecycle."""

    def create_lead(
        self,
        tenant_id: UUID,
        data: Dict[str, Any],
        created_by: Optional[str],
    ) -> Lead:
        """Create a new lead.

        Args:
            tenant_id: Tenant ID.
            data: Lead data (first_name, last_name, email, company, etc.).
            created_by: User ID who created the lead.

        Returns:
            Created Lead instance.
        """
        lead = Lead.objects.create(
            tenant_id=tenant_id,
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            email=data.get("email"),
            phone=data.get("phone", ""),
            company=data.get("company", ""),
            title=data.get("title", ""),
            source=data.get("source", ""),
            campaign_id=data.get("campaign_id"),
            owner_id=data.get("owner_id"),
            status=data.get("status", LeadStatus.NEW),
            metadata=data.get("metadata", {}),
            created_by=created_by,
        )

        # Calculate initial score (rule-based for now, AI can be added later)
        self._calculate_lead_score(lead)

        logger.info(f"Created lead {lead.id} for tenant {tenant_id}")
        return lead

    def update_lead(
        self,
        lead_id: UUID,
        tenant_id: UUID,
        data: Dict[str, Any],
    ) -> Lead:
        """Update an existing lead.

        Args:
            lead_id: Lead ID.
            tenant_id: Tenant ID.
            data: Updated lead data.

        Returns:
            Updated Lead instance.

        Raises:
            Lead.DoesNotExist: If lead not found.
        """
        lead = Lead.objects.get(id=lead_id, tenant_id=tenant_id, is_deleted=False)

        # Update fields
        for field, value in data.items():
            if hasattr(lead, field) and field not in ["id", "tenant_id", "created_at", "created_by"]:
                setattr(lead, field, value)

        lead.full_clean()
        lead.save()

        # Recalculate score if relevant fields changed
        if any(field in data for field in ["company", "title", "email", "source", "metadata"]):
            self._calculate_lead_score(lead)

        return lead

    def delete_lead(self, lead_id: UUID, tenant_id: UUID) -> None:
        """Soft delete a lead.

        Args:
            lead_id: Lead ID.
            tenant_id: Tenant ID.

        Raises:
            Lead.DoesNotExist: If lead not found.
        """
        lead = Lead.objects.get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
        lead.is_deleted = True
        lead.deleted_at = timezone.now()
        lead.save()

    def score_lead(self, lead_id: UUID, tenant_id: UUID) -> Lead:
        """Calculate and update lead score using AI or rule-based logic.

        Args:
            lead_id: Lead ID.
            tenant_id: Tenant ID.

        Returns:
            Updated Lead instance with new score.

        Raises:
            Lead.DoesNotExist: If lead not found.
        """
        lead = Lead.objects.get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
        self._calculate_lead_score(lead)
        return lead

    def _calculate_lead_score(self, lead: Lead) -> None:
        """Calculate lead score (0-100) using rule-based logic.

        TODO: Replace with AI scoring when AI infrastructure is ready.

        Args:
            lead: Lead instance to score.
        """
        score = 0

        # Demographic scoring
        if lead.company:
            score += 20
        if lead.email:
            score += 10
        if lead.phone:
            score += 10
        if lead.title:
            score += 10

        # Source scoring
        source_scores = {
            "referral": 30,
            "event": 20,
            "web": 15,
            "social": 10,
            "api": 5,
        }
        score += source_scores.get(lead.source, 0)

        # BANT scoring (from metadata)
        bant = lead.metadata.get("bant_qualification", {})
        if bant.get("budget") == "yes":
            score += 10
        if bant.get("authority") == "yes":
            score += 10
        if bant.get("need") == "yes":
            score += 10
        if bant.get("timeline") in ["immediate", "1-3 months"]:
            score += 10

        # Cap at 100
        score = min(score, 100)

        # Calculate grade
        if score >= 80:
            grade = "A"
        elif score >= 60:
            grade = "B"
        elif score >= 40:
            grade = "C"
        else:
            grade = "D"

        lead.score = score
        lead.grade = grade
        lead.save(update_fields=["score", "grade"])

    def assign_lead(self, lead_id: UUID, tenant_id: UUID, owner_id: UUID) -> Lead:
        """Assign lead to owner (CRM-BR-001: Auto-assign high-scoring leads).

        Args:
            lead_id: Lead ID.
            tenant_id: Tenant ID.
            owner_id: User ID to assign to.

        Returns:
            Updated Lead instance.

        Raises:
            Lead.DoesNotExist: If lead not found.
        """
        lead = Lead.objects.get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
        lead.owner_id = owner_id
        lead.save(update_fields=["owner_id"])
        return lead


class AccountService:
    """Service for managing accounts and hierarchies."""

    def create_account(
        self,
        tenant_id: UUID,
        data: Dict[str, Any],
        created_by: Optional[str],
    ) -> Account:
        """Create a new account.

        Args:
            tenant_id: Tenant ID.
            data: Account data.
            created_by: User ID who created the account.

        Returns:
            Created Account instance.

        Raises:
            ValidationError: If hierarchy validation fails.
        """
        account = Account(
            tenant_id=tenant_id,
            name=data.get("name", ""),
            website=data.get("website", ""),
            industry=data.get("industry", ""),
            employees=data.get("employees"),
            annual_revenue=data.get("annual_revenue"),
            parent_account_id=data.get("parent_account_id"),
            billing_street=data.get("billing_street", ""),
            billing_city=data.get("billing_city", ""),
            billing_state=data.get("billing_state", ""),
            billing_postal_code=data.get("billing_postal_code", ""),
            billing_country=data.get("billing_country", ""),
            owner_id=data.get("owner_id"),
            account_type=data.get("account_type", AccountType.PROSPECT),
            metadata=data.get("metadata", {}),
            created_by=created_by,
        )

        account.full_clean()  # Validates hierarchy
        account.save()

        logger.info(f"Created account {account.id} for tenant {tenant_id}")
        return account

    def update_account(
        self,
        account_id: UUID,
        tenant_id: UUID,
        data: Dict[str, Any],
    ) -> Account:
        """Update an existing account.

        Args:
            account_id: Account ID.
            tenant_id: Tenant ID.
            data: Updated account data.

        Returns:
            Updated Account instance.

        Raises:
            Account.DoesNotExist: If account not found.
            ValidationError: If hierarchy validation fails.
        """
        account = Account.objects.get(id=account_id, tenant_id=tenant_id, is_deleted=False)

        # Update fields
        for field, value in data.items():
            if hasattr(account, field) and field not in ["id", "tenant_id", "created_at", "created_by"]:
                setattr(account, field, value)

        account.full_clean()  # Validates hierarchy
        account.save()

        return account

    def delete_account(self, account_id: UUID, tenant_id: UUID) -> None:
        """Soft delete an account (CRM-BR-005: Cannot delete with open opportunities).

        Args:
            account_id: Account ID.
            tenant_id: Tenant ID.

        Raises:
            Account.DoesNotExist: If account not found.
            ValidationError: If account has open opportunities.
        """
        account = Account.objects.get(id=account_id, tenant_id=tenant_id, is_deleted=False)

        # Check for open opportunities
        open_opportunities = Opportunity.objects.filter(
            account_id=account_id, tenant_id=tenant_id, status=OpportunityStatus.OPEN, is_deleted=False
        ).exists()

        if open_opportunities:
            raise ValidationError("Cannot delete account with open opportunities")

        account.is_deleted = True
        account.deleted_at = timezone.now()
        account.save()

    def get_account_hierarchy(self, account_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """Get account hierarchy tree.

        Args:
            account_id: Account ID.
            tenant_id: Tenant ID.

        Returns:
            Dictionary with account and children.

        Raises:
            Account.DoesNotExist: If account not found.
        """
        account = Account.objects.get(id=account_id, tenant_id=tenant_id, is_deleted=False)

        def build_tree(acc: Account) -> Dict[str, Any]:
            children = Account.objects.filter(
                parent_account_id=acc.id, tenant_id=tenant_id, is_deleted=False
            )
            return {
                "id": str(acc.id),
                "name": acc.name,
                "account_type": acc.account_type,
                "children": [build_tree(child) for child in children],
            }

        return build_tree(account)


class ContactService:
    """Service for managing contacts."""

    def create_contact(
        self,
        tenant_id: UUID,
        data: Dict[str, Any],
        created_by: Optional[str],
    ) -> Contact:
        """Create a new contact.

        Args:
            tenant_id: Tenant ID.
            data: Contact data (must include account_id).
            created_by: User ID who created the contact.

        Returns:
            Created Contact instance.

        Raises:
            ValidationError: If account_id missing or account not found.
        """
        account_id = data.get("account_id")
        if not account_id:
            raise ValidationError("Contact must have account_id")

        # Verify account exists
        Account.objects.get(id=account_id, tenant_id=tenant_id, is_deleted=False)

        contact = Contact.objects.create(
            tenant_id=tenant_id,
            account_id=account_id,
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            email=data.get("email"),
            phone=data.get("phone", ""),
            mobile=data.get("mobile", ""),
            title=data.get("title", ""),
            department=data.get("department", ""),
            linkedin=data.get("linkedin", ""),
            twitter=data.get("twitter", ""),
            owner_id=data.get("owner_id"),
            metadata=data.get("metadata", {}),
            created_by=created_by,
        )

        logger.info(f"Created contact {contact.id} for tenant {tenant_id}")
        return contact

    def update_contact(
        self,
        contact_id: UUID,
        tenant_id: UUID,
        data: Dict[str, Any],
    ) -> Contact:
        """Update an existing contact.

        Args:
            contact_id: Contact ID.
            tenant_id: Tenant ID.
            data: Updated contact data.

        Returns:
            Updated Contact instance.

        Raises:
            Contact.DoesNotExist: If contact not found.
        """
        contact = Contact.objects.get(id=contact_id, tenant_id=tenant_id, is_deleted=False)

        # Update fields
        for field, value in data.items():
            if hasattr(contact, field) and field not in ["id", "tenant_id", "account_id", "created_at", "created_by"]:
                setattr(contact, field, value)

        contact.save()
        return contact

    def delete_contact(self, contact_id: UUID, tenant_id: UUID) -> None:
        """Soft delete a contact.

        Args:
            contact_id: Contact ID.
            tenant_id: Tenant ID.

        Raises:
            Contact.DoesNotExist: If contact not found.
        """
        contact = Contact.objects.get(id=contact_id, tenant_id=tenant_id, is_deleted=False)
        contact.is_deleted = True
        contact.deleted_at = timezone.now()
        contact.save()

    def update_engagement_score(self, contact_id: UUID, tenant_id: UUID) -> Contact:
        """Update contact engagement score based on activities.

        Args:
            contact_id: Contact ID.
            tenant_id: Tenant ID.

        Returns:
            Updated Contact instance.
        """
        contact = Contact.objects.get(id=contact_id, tenant_id=tenant_id, is_deleted=False)

        # Count recent activities
        thirty_days_ago = timezone.now() - timedelta(days=30)
        activity_count = Activity.objects.filter(
            tenant_id=tenant_id,
            related_to_type=RelatedToType.CONTACT,
            related_to_id=contact_id,
            created_at__gte=thirty_days_ago,
            is_deleted=False,
        ).count()

        # Simple scoring: 10 points per activity, max 100
        contact.engagement_score = min(activity_count * 10, 100)
        contact.last_contacted_at = timezone.now()
        contact.save(update_fields=["engagement_score", "last_contacted_at"])

        return contact


class OpportunityService:
    """Service for managing opportunities and pipeline."""

    def create_opportunity(
        self,
        tenant_id: UUID,
        data: Dict[str, Any],
        created_by: Optional[str],
    ) -> Opportunity:
        """Create a new opportunity.

        Args:
            tenant_id: Tenant ID.
            data: Opportunity data (must include account_id, amount, close_date).
            created_by: User ID who created the opportunity.

        Returns:
            Created Opportunity instance.

        Raises:
            ValidationError: If required fields missing or invalid.
        """
        account_id = data.get("account_id")
        if not account_id:
            raise ValidationError("Opportunity must have account_id")

        # Verify account exists
        Account.objects.get(id=account_id, tenant_id=tenant_id, is_deleted=False)

        opportunity = Opportunity(
            tenant_id=tenant_id,
            account_id=account_id,
            primary_contact_id=data.get("primary_contact_id"),
            name=data.get("name", ""),
            description=data.get("description", ""),
            amount=data.get("amount"),
            currency=data.get("currency", "USD"),
            probability=data.get("probability", 0),
            stage=data.get("stage", OpportunityStage.PROSPECTING),
            close_date=data.get("close_date"),
            product_ids=data.get("product_ids", []),
            competitors=data.get("competitors", []),
            owner_id=data.get("owner_id"),  # Can be None since field is nullable
            status=OpportunityStatus.OPEN,
            metadata=data.get("metadata", {}),
            created_by=created_by,
        )

        opportunity.full_clean()
        opportunity.save()

        logger.info(f"Created opportunity {opportunity.id} for tenant {tenant_id}")
        return opportunity

    def update_opportunity(
        self,
        opportunity_id: UUID,
        tenant_id: UUID,
        data: Dict[str, Any],
    ) -> Opportunity:
        """Update an existing opportunity.

        Args:
            opportunity_id: Opportunity ID.
            tenant_id: Tenant ID.
            data: Updated opportunity data.

        Returns:
            Updated Opportunity instance.

        Raises:
            Opportunity.DoesNotExist: If opportunity not found.
            ValidationError: If validation fails.
        """
        opportunity = Opportunity.objects.get(
            id=opportunity_id, tenant_id=tenant_id, is_deleted=False
        )

        # Update fields
        for field, value in data.items():
            if hasattr(opportunity, field) and field not in [
                "id",
                "tenant_id",
                "account_id",
                "created_at",
                "created_by",
                "status",
                "closed_at",
            ]:
                setattr(opportunity, field, value)

        opportunity.full_clean()
        opportunity.save()

        return opportunity

    def close_won(
        self,
        opportunity_id: UUID,
        tenant_id: UUID,
        user_id: Optional[str],
    ) -> Opportunity:
        """Close opportunity as won (Workflow 6.1.2).

        Args:
            opportunity_id: Opportunity ID.
            tenant_id: Tenant ID.
            user_id: User ID performing the action.

        Returns:
            Updated Opportunity instance.

        Raises:
            Opportunity.DoesNotExist: If opportunity not found.
            ValidationError: If opportunity cannot be closed.
        """
        with transaction.atomic():
            opportunity = Opportunity.objects.get(
                id=opportunity_id, tenant_id=tenant_id, is_deleted=False
            )

            if opportunity.status != OpportunityStatus.OPEN:
                raise ValidationError("Opportunity is already closed")

            # Update opportunity
            opportunity.status = OpportunityStatus.WON
            opportunity.stage = OpportunityStage.CLOSED_WON
            opportunity.probability = 100
            opportunity.closed_at = timezone.now()
            opportunity.save()

            # Update account type to customer
            account = Account.objects.get(id=opportunity.account_id, tenant_id=tenant_id)
            if account.account_type != AccountType.CUSTOMER:
                account.account_type = AccountType.CUSTOMER
                account.save(update_fields=["account_type"])

            # Create activity log
            # Note: user_id is a string, but owner_id needs to be UUID or None
            # For now, we'll set owner_id to None since user_id is not a valid UUID
            ActivityService().create_activity(
                tenant_id=tenant_id,
                data={
                    "activity_type": ActivityType.NOTE,
                    "related_to_type": RelatedToType.OPPORTUNITY,
                    "related_to_id": opportunity_id,
                    "subject": "Opportunity closed as won",
                    "description": f"Opportunity {opportunity.name} was closed as won.",
                    "owner_id": None,  # user_id is string, not UUID
                },
                created_by=user_id,
            )

            # TODO: Trigger sales order creation (if sales-management installed)
            # TODO: Emit event: crm.opportunity.closed_won
            # TODO: Send notifications

        logger.info(f"Closed opportunity {opportunity_id} as won")
        return opportunity

    def close_lost(
        self,
        opportunity_id: UUID,
        tenant_id: UUID,
        loss_reason: str,
        user_id: Optional[str],
    ) -> Opportunity:
        """Close opportunity as lost (CRM-BR-004: Requires loss_reason).

        Args:
            opportunity_id: Opportunity ID.
            tenant_id: Tenant ID.
            loss_reason: Reason for loss (required).
            user_id: User ID performing the action.

        Returns:
            Updated Opportunity instance.

        Raises:
            Opportunity.DoesNotExist: If opportunity not found.
            ValidationError: If loss_reason missing or opportunity already closed.
        """
        if not loss_reason:
            raise ValidationError("Loss reason is required for lost opportunities")

        with transaction.atomic():
            opportunity = Opportunity.objects.get(
                id=opportunity_id, tenant_id=tenant_id, is_deleted=False
            )

            if opportunity.status != OpportunityStatus.OPEN:
                raise ValidationError("Opportunity is already closed")

            # Update opportunity
            opportunity.status = OpportunityStatus.LOST
            opportunity.stage = OpportunityStage.CLOSED_LOST
            opportunity.probability = 0
            opportunity.loss_reason = loss_reason
            opportunity.closed_at = timezone.now()
            opportunity.save()

            # Create activity log
            # Note: user_id is a string, but owner_id needs to be UUID or None
            ActivityService().create_activity(
                tenant_id=tenant_id,
                data={
                    "activity_type": ActivityType.NOTE,
                    "related_to_type": RelatedToType.OPPORTUNITY,
                    "related_to_id": opportunity_id,
                    "subject": "Opportunity closed as lost",
                    "description": f"Opportunity {opportunity.name} was closed as lost. Reason: {loss_reason}",
                    "owner_id": None,  # user_id is string, not UUID
                },
                created_by=user_id,
            )

            # TODO: Emit event: crm.opportunity.closed_lost

        logger.info(f"Closed opportunity {opportunity_id} as lost")
        return opportunity

    def delete_opportunity(self, opportunity_id: UUID, tenant_id: UUID) -> None:
        """Soft delete an opportunity.

        Args:
            opportunity_id: Opportunity ID.
            tenant_id: Tenant ID.

        Raises:
            Opportunity.DoesNotExist: If opportunity not found.
        """
        opportunity = Opportunity.objects.get(
            id=opportunity_id, tenant_id=tenant_id, is_deleted=False
        )
        opportunity.is_deleted = True
        opportunity.deleted_at = timezone.now()
        opportunity.save()


class ActivityService:
    """Service for managing activities."""

    def create_activity(
        self,
        tenant_id: UUID,
        data: Dict[str, Any],
        created_by: Optional[str],
    ) -> Activity:
        """Create a new activity.

        Args:
            tenant_id: Tenant ID.
            data: Activity data.
            created_by: User ID who created the activity.

        Returns:
            Created Activity instance.
        """
        # Handle owner_id - convert to UUID if it's a string, or set to None if invalid
        owner_id = data.get("owner_id")
        if owner_id:
            try:
                if isinstance(owner_id, str):
                    owner_id = uuid.UUID(owner_id)
                elif not isinstance(owner_id, uuid.UUID):
                    owner_id = None  # Invalid type, set to None
            except (ValueError, TypeError):
                owner_id = None  # Invalid UUID string, set to None
        
        activity = Activity.objects.create(
            tenant_id=tenant_id,
            activity_type=data.get("activity_type", ActivityType.NOTE),
            related_to_type=data.get("related_to_type"),
            related_to_id=data.get("related_to_id"),
            subject=data.get("subject", ""),
            description=data.get("description", ""),
            outcome=data.get("outcome", ""),
            due_date=data.get("due_date"),
            owner_id=owner_id,
            external_id=data.get("external_id", ""),
            metadata=data.get("metadata", {}),
            created_by=created_by,
        )

        # Update last_activity_at on related opportunity (CRM-BR-008)
        if activity.related_to_type == RelatedToType.OPPORTUNITY:
            try:
                opportunity = Opportunity.objects.get(
                    id=activity.related_to_id, tenant_id=tenant_id, is_deleted=False
                )
                opportunity.last_activity_at = timezone.now()
                opportunity.save(update_fields=["last_activity_at"])
            except Opportunity.DoesNotExist:
                pass

        # Recalculate lead score if activity is for a lead (CRM-BR-008)
        if activity.related_to_type == RelatedToType.LEAD:
            try:
                lead = Lead.objects.get(id=activity.related_to_id, tenant_id=tenant_id, is_deleted=False)
                LeadService()._calculate_lead_score(lead)
            except Lead.DoesNotExist:
                pass

        logger.info(f"Created activity {activity.id} for tenant {tenant_id}")
        return activity

    def update_activity(
        self,
        activity_id: UUID,
        tenant_id: UUID,
        data: Dict[str, Any],
    ) -> Activity:
        """Update an existing activity.

        Args:
            activity_id: Activity ID.
            tenant_id: Tenant ID.
            data: Updated activity data.

        Returns:
            Updated Activity instance.

        Raises:
            Activity.DoesNotExist: If activity not found.
            ValidationError: If activity is completed (CRM-BR-007).
        """
        activity = Activity.objects.get(id=activity_id, tenant_id=tenant_id, is_deleted=False)

        # Check if activity is completed (read-only)
        if activity.completed:
            raise ValidationError("Completed activities cannot be edited")

        # Update fields
        for field, value in data.items():
            if hasattr(activity, field) and field not in [
                "id",
                "tenant_id",
                "related_to_type",
                "related_to_id",
                "created_at",
                "created_by",
            ]:
                setattr(activity, field, value)

        activity.save()
        return activity

    def complete_activity(self, activity_id: UUID, tenant_id: UUID) -> Activity:
        """Mark activity as completed.

        Args:
            activity_id: Activity ID.
            tenant_id: Tenant ID.

        Returns:
            Updated Activity instance.

        Raises:
            Activity.DoesNotExist: If activity not found.
        """
        activity = Activity.objects.get(id=activity_id, tenant_id=tenant_id, is_deleted=False)
        activity.completed = True
        activity.completed_at = timezone.now()
        activity.save(update_fields=["completed", "completed_at"])
        return activity

    def delete_activity(self, activity_id: UUID, tenant_id: UUID) -> None:
        """Soft delete an activity.

        Args:
            activity_id: Activity ID.
            tenant_id: Tenant ID.

        Raises:
            Activity.DoesNotExist: If activity not found.
        """
        activity = Activity.objects.get(id=activity_id, tenant_id=tenant_id, is_deleted=False)
        activity.is_deleted = True
        activity.deleted_at = timezone.now()
        activity.save()

    def get_activity_timeline(
        self,
        related_to_type: str,
        related_to_id: UUID,
        tenant_id: UUID,
    ) -> List[Activity]:
        """Get activity timeline for an entity.

        Args:
            related_to_type: Entity type (Lead, Contact, Account, Opportunity).
            related_to_id: Entity ID.
            tenant_id: Tenant ID.

        Returns:
            List of activities ordered by created_at descending.
        """
        return list(
            Activity.objects.filter(
                tenant_id=tenant_id,
                related_to_type=related_to_type,
                related_to_id=related_to_id,
                is_deleted=False,
            ).order_by("-created_at")
        )


class ForecastingService:
    """Service for pipeline forecasting and analytics."""

    def get_weighted_pipeline(
        self,
        tenant_id: UUID,
        owner_id: Optional[UUID] = None,
        period_days: int = 90,
    ) -> Dict[str, Any]:
        """Calculate weighted pipeline value.

        Args:
            tenant_id: Tenant ID.
            owner_id: Optional owner ID to filter by.
            period_days: Number of days to look ahead.

        Returns:
            Dictionary with pipeline metrics.
        """
        end_date = date.today() + timedelta(days=period_days)

        queryset = Opportunity.objects.filter(
            tenant_id=tenant_id,
            status=OpportunityStatus.OPEN,
            close_date__lte=end_date,
            is_deleted=False,
        )

        if owner_id:
            queryset = queryset.filter(owner_id=owner_id)

        opportunities = queryset.all()

        total_value = sum(opp.amount for opp in opportunities)
        weighted_value = sum(opp.amount * Decimal(opp.probability) / 100 for opp in opportunities)

        return {
            "total_pipeline_value": float(total_value),
            "weighted_pipeline_value": float(weighted_value),
            "opportunity_count": len(opportunities),
            "period_days": period_days,
        }

    def get_win_rate(
        self,
        tenant_id: UUID,
        owner_id: Optional[UUID] = None,
        period_days: int = 90,
    ) -> Dict[str, Any]:
        """Calculate historical win rate.

        Args:
            tenant_id: Tenant ID.
            owner_id: Optional owner ID to filter by.
            period_days: Number of days to look back.

        Returns:
            Dictionary with win rate metrics.
        """
        start_date = date.today() - timedelta(days=period_days)

        queryset = Opportunity.objects.filter(
            tenant_id=tenant_id,
            closed_at__gte=datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc),
            is_deleted=False,
        )

        if owner_id:
            queryset = queryset.filter(owner_id=owner_id)

        closed_opportunities = queryset.filter(
            status__in=[OpportunityStatus.WON, OpportunityStatus.LOST]
        ).all()

        won_count = sum(1 for opp in closed_opportunities if opp.status == OpportunityStatus.WON)
        total_count = len(closed_opportunities)

        win_rate = (won_count / total_count * 100) if total_count > 0 else 0

        return {
            "win_rate": float(win_rate),
            "won_count": won_count,
            "lost_count": total_count - won_count,
            "total_closed": total_count,
            "period_days": period_days,
        }

    def get_ai_prediction(
        self,
        tenant_id: UUID,
        period_days: int = 90,
    ) -> Dict[str, Any]:
        """Get AI-predicted revenue (placeholder for Phase 8).

        Args:
            tenant_id: Tenant ID.
            period_days: Number of days to predict.

        Returns:
            Dictionary with AI predictions.

        Note:
            This is a placeholder. Full AI integration will be in Phase 9.
        """
        # For now, return weighted pipeline as prediction
        pipeline = self.get_weighted_pipeline(tenant_id=tenant_id, period_days=period_days)

        return {
            "predicted_revenue": pipeline["weighted_pipeline_value"],
            "confidence": 0.75,  # Placeholder
            "factors": ["historical_win_rate", "pipeline_velocity", "deal_stage_distribution"],
            "period_days": period_days,
        }


class IntegrationService:
    """Service for cross-module integrations."""

    def convert_lead_to_opportunity(
        self,
        lead_id: UUID,
        tenant_id: UUID,
        opportunity_data: Dict[str, Any],
        user_id: Optional[str],
    ) -> Dict[str, Any]:
        """Convert lead to opportunity (Workflow 6.1.1).

        Args:
            lead_id: Lead ID to convert.
            tenant_id: Tenant ID.
            opportunity_data: Opportunity data (amount, close_date, etc.).
            user_id: User ID performing the conversion.

        Returns:
            Dictionary with created entities (opportunity, account, contact).

        Raises:
            Lead.DoesNotExist: If lead not found.
            ValidationError: If lead cannot be converted.
        """
        with transaction.atomic():
            lead = Lead.objects.get(id=lead_id, tenant_id=tenant_id, is_deleted=False)

            # Validation
            if lead.status == LeadStatus.CONVERTED:
                raise ValidationError("Lead is already converted")

            if not lead.email and not lead.company:
                raise ValidationError("Cannot convert lead without email or company")

            # Step 1: Create or select account
            account = None
            if lead.company:
                # Try to find existing account (fuzzy match)
                existing_accounts = Account.objects.filter(
                    tenant_id=tenant_id, name__icontains=lead.company, is_deleted=False
                )[:1]

                if existing_accounts:
                    account = existing_accounts[0]
                else:
                    # Create new account
                    account = AccountService().create_account(
                        tenant_id=tenant_id,
                        data={
                            "name": lead.company,
                            "owner_id": lead.owner_id,
                            "account_type": AccountType.PROSPECT,
                        },
                        created_by=user_id,
                    )

            if not account:
                raise ValidationError("Cannot create opportunity without account")

            # Step 2: Create contact from lead
            contact = None
            if lead.email or lead.first_name or lead.last_name:
                # Check if contact already exists
                existing_contacts = Contact.objects.filter(
                    tenant_id=tenant_id,
                    account_id=account.id,
                    email=lead.email,
                    is_deleted=False,
                )[:1]

                if existing_contacts:
                    contact = existing_contacts[0]
                else:
                    contact = ContactService().create_contact(
                        tenant_id=tenant_id,
                        data={
                            "account_id": account.id,
                            "first_name": lead.first_name,
                            "last_name": lead.last_name,
                            "email": lead.email,
                            "phone": lead.phone,
                            "title": lead.title,
                            "owner_id": lead.owner_id,
                        },
                        created_by=user_id,
                    )

            # Step 3: Create opportunity
            opportunity_name = opportunity_data.get(
                "name", f"{lead.company} - {lead.first_name} {lead.last_name}"
            )
            # Use lead's owner_id if available, otherwise generate a default UUID
            # Note: In production, this should use the actual user's UUID, not a generated one
            owner_id = lead.owner_id if lead.owner_id else uuid.uuid4()
            opportunity = OpportunityService().create_opportunity(
                tenant_id=tenant_id,
                data={
                    "account_id": account.id,
                    "primary_contact_id": contact.id if contact else None,
                    "name": opportunity_name,
                    "amount": opportunity_data.get("amount"),
                    "close_date": opportunity_data.get("close_date", date.today() + timedelta(days=30)),
                    "stage": OpportunityStage.QUALIFICATION,
                    "probability": 20,
                    "owner_id": owner_id,
                },
                created_by=user_id,
            )

            # Step 4: Update lead status
            lead.status = LeadStatus.CONVERTED
            lead.converted_at = timezone.now()
            lead.converted_to_opportunity_id = opportunity.id
            lead.save(update_fields=["status", "converted_at", "converted_to_opportunity_id"])

            # Step 5: Create activity log
            # Note: user_id is a string, but owner_id needs to be UUID or None
            ActivityService().create_activity(
                tenant_id=tenant_id,
                data={
                    "activity_type": ActivityType.NOTE,
                    "related_to_type": RelatedToType.LEAD,
                    "related_to_id": lead_id,
                    "subject": "Lead converted to opportunity",
                    "description": f"Lead was converted to opportunity {opportunity.name}",
                    "owner_id": None,  # user_id is string, not UUID
                },
                created_by=user_id,
            )

            # TODO: Emit event: crm.lead.converted
            # TODO: Send notifications

        logger.info(f"Converted lead {lead_id} to opportunity {opportunity.id}")

        return {
            "opportunity": opportunity,
            "account": account,
            "contact": contact,
        }
