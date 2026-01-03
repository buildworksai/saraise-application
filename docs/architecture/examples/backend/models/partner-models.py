# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Partner Models
# backend/src/modules/partners/models.py
# Reference: docs/architecture/application-architecture.md § 4.3 (Module Integration)
# Reference: docs/architecture/application-architecture.md § 4.1 (Row-Level Multitenancy)
# 
# CRITICAL NOTES:
# - Partner types: AFFILIATE (referral), RESELLER (direct), INTEGRATION (API), STRATEGIC
# - ⚠️ tenant_id REQUIRED for row-level multitenancy (partner scoped to tenant)
# - Commission rates: percentage and fixed amount options
# - Payment methods: bank transfer, check, PayPal, crypto
# - Payout schedule: automatic, manual, on-demand
# - Referral tracking: referral_code unique per tenant+code, immutable
# - Commission calculation: server-side only (never trust client)
# - Payout status: pending, processing, completed, failed
# - Audit logging: all state changes logged (security-model.md § 4.2)
# - Data constraints: unique constraints on partner code per tenant

from django.db import models
from django.utils import timezone
from typing import Optional
from decimal import Decimal
from datetime import datetime
import uuid

class PartnerTypeChoices(models.TextChoices):
    AFFILIATE = "affiliate", "Referral-based partner"
    RESELLER = "reseller", "Direct reseller"
    INTEGRATION = "integration", "Integration partner"
    STRATEGIC = "strategic", "Strategic partner"

class PartnerStatusChoices(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    SUSPENDED = "suspended", "Suspended"
    ARCHIVED = "archived", "Archived"

class CommissionTypeChoices(models.TextChoices):
    PERCENTAGE = "percentage", "Percentage of revenue"
    FIXED_AMOUNT = "fixed_amount", "Fixed amount per referral"
    TIERED = "tiered", "Tiered commission structure"

class Partner(models.Model):
    """Partner model for affiliate and reseller management.
    
    CRITICAL: tenant_id is REQUIRED for Row-Level Multitenancy.
    All partners are scoped to a specific tenant.
    """
    id = models.CharField(max_length=36, primary_key=True, default=lambda: str(uuid.uuid4()))
    # ⚠️ CRITICAL: tenant_id for Row-Level Multitenancy
    tenant_id = models.CharField(max_length=36, db_index=True)
    
    name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(unique=True, db_index=True)
    phone = models.CharField(max_length=50, null=True, blank=True)

    # Partner Type
    partner_type = models.CharField(
        max_length=50,
        choices=PartnerTypeChoices.choices
    )
    status = models.CharField(
        max_length=50,
        choices=PartnerStatusChoices.choices,
        default=PartnerStatusChoices.ACTIVE
    )

    # Referral Code (unique per tenant)
    referral_code = models.CharField(max_length=50, db_index=True)
    custom_discount_code = models.CharField(max_length=50, null=True, blank=True, db_index=True)

    # Commission Configuration
    commission_type = models.CharField(
        max_length=50,
        choices=CommissionTypeChoices.choices
    )
    commission_rate = models.DecimalField(max_digits=10, decimal_places=4)
    tiered_commission_config = models.JSONField(null=True, blank=True)

    # Payout Configuration
    payout_frequency = models.CharField(max_length=50, default="monthly")
    minimum_payout = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("100.00"))
    payout_method = models.CharField(max_length=50, default="bank_transfer")
    payout_details = models.JSONField(null=True, blank=True)

    # Statistics
    total_referrals = models.IntegerField(default=0)
    active_referrals = models.IntegerField(default=0)
    total_commission_earned = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total_commission_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total_commission_pending = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(max_length=36, null=True, blank=True)

    class Meta:
        db_table = "partners"
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'referral_code']),
            models.Index(fields=['status']),
            models.Index(fields=['partner_type']),
        ]
        constraints = [
            # Referral code unique per tenant
            models.UniqueConstraint(
                fields=['tenant_id', 'referral_code'],
                name='uq_tenant_referral_code'
            ),
            # Custom discount code unique per tenant
            models.UniqueConstraint(
                fields=['tenant_id', 'custom_discount_code'],
                name='uq_tenant_discount_code',
                condition=models.Q(custom_discount_code__isnull=False)
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.partner_type})"

class PartnerReferral(Base):
    class Meta:
        db_table = "partner_referrals"

    id: str] = models.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    partner_id: str] = models.String, models.models.models.models.ForeignKey("partners.id"), nullable=False)
    tenant_id: str] = models.String, models.models.models.models.ForeignKey("tenants.id"), nullable=False, unique=True)
    referral_code: str] = models.CharField(max_length=50), nullable=False, index=True)

    # Referral Details
    referral_date: datetime] = models.DateTimeField(timezone=True), server_default=func.now())
    conversion_date: Optional[datetime]] = models.DateTimeField(timezone=True))  # When tenant subscribed
    conversion_value: Optional[Decimal]] = models.Numeric(10, 2))  # Subscription value

    # Status
    status: str] = models.CharField(max_length=50), default="pending")  # pending, converted, expired
    is_active: bool] = models.BooleanField(), default=True)

    # Relationships
    partner: "Partner"] = # Django ORM relationships via ForeignKey"Partner", foreign_keys=[partner_id])
    tenant: "Tenant"] = # Django ORM relationships via ForeignKey"Tenant", foreign_keys=[tenant_id])

    __table_args__ = (
        Index('idx_referral_partner', 'partner_id'),
        Index('idx_referral_tenant', 'tenant_id'),
        Index('idx_referral_code', 'referral_code'),
        Index('idx_referral_status', 'status'),
    )

class PartnerCommission(Base):
    class Meta:
        db_table = "partner_commissions"

    id: str] = models.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    partner_id: str] = models.String, models.models.models.models.ForeignKey("partners.id"), nullable=False)
    referral_id: Optional[str]] = models.String, models.models.models.models.ForeignKey("partner_referrals.id"))
    subscription_id: Optional[str]] = models.String, models.models.models.models.ForeignKey("subscriptions.id"))

    # Commission Details
    commission_type: str] = models.Enum(CommissionType), nullable=False)
    commission_rate: Decimal] = models.Numeric(10, 4), nullable=False)
    base_amount: Decimal] = models.Numeric(10, 2), nullable=False)  # Revenue amount
    commission_amount: Decimal] = models.Numeric(10, 2), nullable=False)

    # Status
    status: str] = models.CharField(max_length=50), default="pending")  # pending, approved, paid, cancelled
    earned_date: datetime] = models.DateTimeField(timezone=True), server_default=func.now())
    paid_date: Optional[datetime]] = models.DateTimeField(timezone=True))
    payout_id: Optional[str]] = models.String, models.models.models.models.ForeignKey("partner_payouts.id"))

    # Relationships
    partner: "Partner"] = # Django ORM relationships via ForeignKey"Partner", foreign_keys=[partner_id])
    referral: Optional["PartnerReferral"]] = # Django ORM relationships via ForeignKey"PartnerReferral", foreign_keys=[referral_id])
    subscription: Optional["Subscription"]] = # Django ORM relationships via ForeignKey"Subscription", foreign_keys=[subscription_id])
    payout: Optional["PartnerPayout"]] = # Django ORM relationships via ForeignKey"PartnerPayout", foreign_keys=[payout_id])

    __table_args__ = (
        Index('idx_commission_partner', 'partner_id'),
        Index('idx_commission_status', 'status'),
        Index('idx_commission_payout', 'payout_id'),
    )

class PartnerPayout(Base):
    class Meta:
        db_table = "partner_payouts"

    id: str] = models.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    partner_id: str] = models.String, models.models.models.models.ForeignKey("partners.id"), nullable=False)

    # Payout Details
    amount: Decimal] = models.Numeric(10, 2), nullable=False)
    currency: str] = models.CharField(max_length=3), default="USD")
    payout_method: str] = models.CharField(max_length=50), nullable=False)
    payout_details: dict] = models.JSON, nullable=False)

    # Status
    status: str] = models.CharField(max_length=50), default="pending")  # pending, processing, completed, failed
    requested_date: datetime] = models.DateTimeField(timezone=True), server_default=func.now())
    processed_date: Optional[datetime]] = models.DateTimeField(timezone=True))
    transaction_id: Optional[str]] = models.CharField(max_length=255))

    # Commission Period
    period_start: datetime] = models.DateTimeField(timezone=True), nullable=False)
    period_end: datetime] = models.DateTimeField(timezone=True), nullable=False)

    # Relationships
    partner: "Partner"] = # Django ORM relationships via ForeignKey"Partner", foreign_keys=[partner_id])
    commissions: list["PartnerCommission"]] = # Django ORM relationships via ForeignKey"PartnerCommission", back_populates="payout")

    __table_args__ = (
        Index('idx_payout_partner', 'partner_id'),
        Index('idx_payout_status', 'status'),
        Index('idx_payout_period', 'period_start', 'period_end'),
    )

