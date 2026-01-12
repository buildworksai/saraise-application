"""
CRM Models.

Defines data models for customer relationship management.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class TenantBaseModel(models.Model):
    """Base model for tenant-scoped models with Row-Level Multitenancy.

    CRITICAL: All tenant-scoped models MUST inherit from this base class
    and include tenant_id. All queries MUST filter explicitly by tenant_id.
    """

    tenant_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class LeadStatus(models.TextChoices):
    """Lead status choices."""

    NEW = "new", "New"
    CONTACTED = "contacted", "Contacted"
    QUALIFIED = "qualified", "Qualified"
    CONVERTED = "converted", "Converted"
    LOST = "lost", "Lost"


class Lead(TenantBaseModel):
    """
    Lead model - Prospects who have shown interest.

    Tenant Isolation: REQUIRED (SARAISE-33001)
    Audit Fields: created_at, updated_at, created_by
    Soft Delete: is_deleted, deleted_at
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)  # CRITICAL: Tenant isolation

    # Contact Info
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=255, db_index=True, blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True)
    company = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=100, blank=True)

    # Scoring
    score = models.IntegerField(default=0, db_index=True)  # 0-100
    grade = models.CharField(max_length=2, blank=True)  # A, B, C, D

    # Source Tracking
    source = models.CharField(max_length=100, blank=True)  # web, social, event, referral, api
    campaign_id = models.UUIDField(null=True, blank=True)  # FK to campaign (if module installed)

    # Assignment & Status
    owner_id = models.UUIDField(db_index=True, null=True, blank=True)  # FK to User
    status = models.CharField(
        max_length=50, default=LeadStatus.NEW, db_index=True, choices=LeadStatus.choices
    )

    # Conversion
    converted_at = models.DateTimeField(null=True, blank=True)
    converted_to_opportunity_id = models.UUIDField(null=True, blank=True)

    # Custom Fields & BANT
    metadata = models.JSONField(default=dict, blank=True)  # {bant_qualification: {}, custom_fields: {}}

    # Audit Fields
    created_by = models.CharField(max_length=36, null=True, blank=True, db_index=True)

    # Soft Delete
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "crm_leads"
        indexes = [
            models.Index(fields=["tenant_id", "status"], name="idx_lead_tenant_status"),
            models.Index(fields=["tenant_id", "email"], name="idx_lead_tenant_email"),
            models.Index(fields=["score"], name="idx_lead_score"),
            models.Index(fields=["owner_id", "status"], name="idx_lead_owner_status"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "email"],
                condition=models.Q(is_deleted=False, email__isnull=False),
                name="unique_lead_email_per_tenant",
            )
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.company})"

    def clean(self):
        """Validate lead data."""
        if self.score < 0 or self.score > 100:
            raise ValidationError("Lead score must be between 0 and 100")


class AccountType(models.TextChoices):
    """Account type choices."""

    PROSPECT = "prospect", "Prospect"
    CUSTOMER = "customer", "Customer"
    PARTNER = "partner", "Partner"


class Account(TenantBaseModel):
    """
    Account model - Companies/Organizations.

    Supports hierarchy (parent/child accounts).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    # Company Info
    name = models.CharField(max_length=255, db_index=True)
    website = models.URLField(max_length=255, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    employees = models.IntegerField(null=True, blank=True)
    annual_revenue = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # Hierarchy
    parent_account_id = models.UUIDField(null=True, blank=True, db_index=True)

    # Address
    billing_street = models.TextField(blank=True)
    billing_city = models.CharField(max_length=100, blank=True)
    billing_state = models.CharField(max_length=100, blank=True)
    billing_postal_code = models.CharField(max_length=20, blank=True)
    billing_country = models.CharField(max_length=100, blank=True)

    # Assignment
    owner_id = models.UUIDField(db_index=True, null=True, blank=True)
    account_type = models.CharField(
        max_length=50, default=AccountType.PROSPECT, choices=AccountType.choices, db_index=True
    )

    # Custom Fields
    metadata = models.JSONField(default=dict, blank=True)

    # Audit Fields
    created_by = models.CharField(max_length=36, null=True, blank=True, db_index=True)

    # Soft Delete
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "crm_accounts"
        indexes = [
            models.Index(fields=["tenant_id", "name"], name="idx_account_tenant_name"),
            models.Index(fields=["owner_id"], name="idx_account_owner"),
            models.Index(fields=["parent_account_id"], name="idx_account_parent"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "name"],
                condition=models.Q(is_deleted=False),
                name="unique_account_name_per_tenant",
            )
        ]

    def clean(self):
        """Validate account hierarchy."""
        if self.parent_account_id:
            # Prevent self-reference
            if str(self.parent_account_id) == str(self.id):
                raise ValidationError("Account cannot be its own parent")

            # Check hierarchy depth
            depth = 0
            current_parent_id = self.parent_account_id
            visited = set()

            while current_parent_id:
                if current_parent_id in visited:
                    raise ValidationError("Circular hierarchy detected")
                visited.add(current_parent_id)
                depth += 1
                if depth >= 3:  # Max 3 levels: parent -> child -> grandchild (depth 0, 1, 2)
                    raise ValidationError("Account hierarchy cannot exceed 3 levels")

                parent = Account.objects.filter(
                    id=current_parent_id, tenant_id=self.tenant_id
                ).first()
                current_parent_id = parent.parent_account_id if parent else None

    def __str__(self):
        return self.name


class Contact(TenantBaseModel):
    """
    Contact model - Individual persons associated with accounts.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    account_id = models.UUIDField(db_index=True)  # REQUIRED: Contact must belong to account

    # Contact Info
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=255, db_index=True, blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True)
    mobile = models.CharField(max_length=50, blank=True)
    title = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)

    # Social
    linkedin = models.URLField(max_length=255, blank=True)
    twitter = models.CharField(max_length=100, blank=True)

    # Engagement
    last_contacted_at = models.DateTimeField(null=True, blank=True)
    engagement_score = models.IntegerField(default=0)

    # Assignment
    owner_id = models.UUIDField(db_index=True, null=True, blank=True)

    # Custom Fields
    metadata = models.JSONField(default=dict, blank=True)

    # Audit Fields
    created_by = models.CharField(max_length=36, null=True, blank=True, db_index=True)

    # Soft Delete
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "crm_contacts"
        indexes = [
            models.Index(fields=["tenant_id", "account_id"], name="idx_contact_tenant_account"),
            models.Index(fields=["email"], name="idx_contact_email"),
            models.Index(fields=["owner_id"], name="idx_contact_owner"),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class OpportunityStage(models.TextChoices):
    """Opportunity stage choices."""

    PROSPECTING = "prospecting", "Prospecting"
    QUALIFICATION = "qualification", "Qualification"
    NEEDS_ANALYSIS = "needs_analysis", "Needs Analysis"
    PROPOSAL = "proposal", "Proposal"
    NEGOTIATION = "negotiation", "Negotiation"
    CLOSED_WON = "closed_won", "Closed Won"
    CLOSED_LOST = "closed_lost", "Closed Lost"


class OpportunityStatus(models.TextChoices):
    """Opportunity status choices."""

    OPEN = "open", "Open"
    WON = "won", "Won"
    LOST = "lost", "Lost"


class Opportunity(TenantBaseModel):
    """
    Opportunity model - Sales deals in pipeline.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    account_id = models.UUIDField(db_index=True)  # REQUIRED
    primary_contact_id = models.UUIDField(null=True, blank=True)

    # Opportunity Info
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    probability = models.IntegerField(default=0)  # 0-100

    # Stage
    stage = models.CharField(
        max_length=100, db_index=True, choices=OpportunityStage.choices, default=OpportunityStage.PROSPECTING
    )
    close_date = models.DateField(db_index=True)

    # Products & Competition
    product_ids = models.JSONField(default=list, blank=True)  # List of product UUIDs
    competitors = models.JSONField(default=list, blank=True)  # List of competitor names

    # Assignment
    owner_id = models.UUIDField(db_index=True, null=True, blank=True)

    # Status
    status = models.CharField(
        max_length=50, default=OpportunityStatus.OPEN, db_index=True, choices=OpportunityStatus.choices
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    loss_reason = models.TextField(blank=True)

    # Conversion
    converted_to_order_id = models.UUIDField(null=True, blank=True)  # FK to sales-management module

    # Custom Fields
    metadata = models.JSONField(default=dict, blank=True)

    # Audit Fields
    created_by = models.CharField(max_length=36, null=True, blank=True, db_index=True)
    last_activity_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Soft Delete
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "crm_opportunities"
        indexes = [
            models.Index(fields=["tenant_id", "status"], name="idx_opp_tenant_status"),
            models.Index(fields=["owner_id", "stage"], name="idx_opp_owner_stage"),
            models.Index(fields=["close_date"], name="idx_opp_close_date"),
            models.Index(fields=["account_id"], name="idx_opp_account"),
        ]

    def clean(self):
        """Validate opportunity business rules."""
        if self.amount and self.amount <= 0:
            raise ValidationError("Opportunity amount must be positive")

        if self.probability < 0 or self.probability > 100:
            raise ValidationError("Probability must be between 0 and 100")

        if self.status == OpportunityStatus.WON and not self.account_id:
            raise ValidationError("Cannot close opportunity as won without account")

        if self.status == OpportunityStatus.LOST and not self.loss_reason:
            raise ValidationError("Loss reason required for lost opportunities")

    def __str__(self):
        return self.name


class ActivityType(models.TextChoices):
    """Activity type choices."""

    CALL = "call", "Call"
    EMAIL = "email", "Email"
    MEETING = "meeting", "Meeting"
    TASK = "task", "Task"
    NOTE = "note", "Note"


class RelatedToType(models.TextChoices):
    """Related entity type choices."""

    LEAD = "Lead", "Lead"
    CONTACT = "Contact", "Contact"
    ACCOUNT = "Account", "Account"
    OPPORTUNITY = "Opportunity", "Opportunity"


class Activity(TenantBaseModel):
    """
    Activity model - Interactions (calls, emails, meetings, tasks, notes).

    Polymorphic: Can relate to Lead, Contact, Account, or Opportunity.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    # Activity Type
    activity_type = models.CharField(
        max_length=50, db_index=True, choices=ActivityType.choices
    )

    # Polymorphic Relation
    related_to_type = models.CharField(
        max_length=50, choices=RelatedToType.choices
    )  # Lead, Contact, Account, Opportunity
    related_to_id = models.UUIDField(db_index=True)

    # Content
    subject = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    outcome = models.CharField(
        max_length=100, blank=True
    )  # For calls: connected, voicemail, no_answer

    # Scheduling
    due_date = models.DateTimeField(null=True, blank=True, db_index=True)
    completed = models.BooleanField(default=False, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Assignment
    owner_id = models.UUIDField(db_index=True, null=True, blank=True)

    # External Reference (for synced activities)
    external_id = models.CharField(
        max_length=255, blank=True, db_index=True
    )  # e.g., email_marketing event ID

    # Custom Fields
    metadata = models.JSONField(default=dict, blank=True)

    # Audit Fields
    created_by = models.CharField(max_length=36, null=True, blank=True, db_index=True)

    # Soft Delete
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "crm_activities"
        indexes = [
            models.Index(
                fields=["tenant_id", "related_to_type", "related_to_id"],
                name="idx_activity_relation",
            ),
            models.Index(fields=["owner_id", "due_date"], name="idx_activity_owner_due"),
            models.Index(fields=["activity_type"], name="idx_activity_type"),
            models.Index(fields=["external_id"], name="idx_activity_external"),
        ]

    def __str__(self):
        return f"{self.activity_type}: {self.subject}"
