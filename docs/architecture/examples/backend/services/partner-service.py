# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Partner Service
# backend/src/modules/partners/services/partner_service.py
# Reference: docs/architecture/policy-engine-spec.md (Platform Operations)

from django.db import transaction
from src.models.partners import Partner, PartnerReferral, PartnerCommission, PartnerPayout, PartnerType, PartnerStatus, CommissionType
from src.models.tenants import Tenant
from src.models.subscriptions import Subscription
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional, List
import secrets
import string

class PartnerService:
    """Partner management service (platform-level).
    
    CRITICAL: Only platform_owner can manage partners.
    Partners are platform-wide and shared across tenants.
    Authorization is evaluated by Policy Engine at request time.
    See docs/architecture/policy-engine-spec.md (Platform Operations).
    CRITICAL: SARAISE uses Django ORM exclusively
    """
    
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        pass

    def generate_referral_code(self, length: int = 8) -> str:
        """Generate unique referral code"""
        characters = string.ascii_uppercase + string.digits
        while True:
            code = ''.join(secrets.choice(characters) for _ in range(length))
            # Check uniqueness (will be checked in create_partner)
            return code

    def create_partner(
        self,
        name: str,
        email: str,
        partner_type: PartnerType,
        commission_type: CommissionType,
        commission_rate: Decimal,
        **kwargs
    ) -> Partner:
        """Create a new partner"""
        # Validate email uniqueness
        existing = self.get_partner_by_email(email)
        if existing:
            raise Response(status=status.HTTP_400, detail="Partner with this email already exists")

        # Generate unique referral code
        referral_code = kwargs.get('referral_code') or self.generate_referral_code()
        while self.get_partner_by_referral_code(referral_code):
            referral_code = self.generate_referral_code()

        # Generate custom discount code if not provided
        custom_discount_code = kwargs.get('custom_discount_code')
        if custom_discount_code:
            # Validate uniqueness
            existing = self.get_partner_by_discount_code(custom_discount_code)
            if existing:
                raise Response(status=status.HTTP_400, detail="Discount code already exists")

        # ✅ CORRECT: Django ORM - use Model.objects.create() for creating records
        partner = Partner.objects.create(
            name=name,
            email=email,
            partner_type=partner_type.value,
            commission_type=commission_type.value,
            commission_rate=commission_rate,
            referral_code=referral_code,
            custom_discount_code=custom_discount_code,
            status=PartnerStatus.ACTIVE.value,
            **kwargs
        )
        return partner

    def get_partner_by_email(self, email: str) -> Optional[Partner]:
        """Get partner by email"""
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        return Partner.objects.filter(email=email).first()

    def get_partner_by_referral_code(self, referral_code: str) -> Optional[Partner]:
        """Get partner by referral code"""
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        return Partner.objects.filter(referral_code=referral_code).first()

    def get_partner_by_discount_code(self, discount_code: str) -> Optional[Partner]:
        """Get partner by custom discount code"""
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        return Partner.objects.filter(custom_discount_code=discount_code).first()

    def create_referral(
        self,
        referral_code: str,
        tenant_id: str
    ) -> PartnerReferral:
        """Create a partner referral

        NOTE: PartnerReferral is platform-level data (tracks tenant-partner relationships).
        tenant_id filtering is appropriate here as this is in the platform schema.
        """
        # Get partner by referral code
        partner = self.get_partner_by_referral_code(referral_code)
        if not partner:
            raise Response(status=status.HTTP_404, detail="Invalid referral code")

        if partner.status != PartnerStatus.ACTIVE.value:
            raise Response(status=status.HTTP_400, detail="Partner is not active")

        # Check if tenant already has a referral
        # NOTE: PartnerReferral is platform-level tracking, tenant_id filtering is appropriate
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        existing = PartnerReferral.objects.filter(tenant_id=tenant_id).first()
        if existing:
            raise Response(status=status.HTTP_400, detail="Tenant already has a referral")

        # Update partner statistics
        partner.total_referrals += 1
        partner.save()

        # Create referral
        # ✅ CORRECT: Django ORM - use Model.objects.create() for creating records
        referral = PartnerReferral.objects.create(
            partner_id=partner.id,
            tenant_id=tenant_id,
            referral_code=referral_code,
            status="pending",
            is_active=True
        )

        return referral

    def convert_referral(
        self,
        referral_id: str,
        subscription_id: str,
        subscription_amount: Decimal
    ) -> PartnerCommission:
        """Convert referral to commission when tenant subscribes"""
        # Get referral
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        referral = PartnerReferral.objects.filter(id=referral_id).first()

        if not referral:
            raise Response(status=status.HTTP_404, detail="Referral not found")

        if referral.status == "converted":
            raise Response(status=status.HTTP_400, detail="Referral already converted")

        # Get partner
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        partner = Partner.objects.filter(id=referral.partner_id).first()

        if not partner:
            raise Response(status=status.HTTP_404, detail="Partner not found")

        # Calculate commission
        if partner.commission_type == CommissionType.PERCENTAGE.value:
            commission_amount = subscription_amount * (partner.commission_rate / 100)
        elif partner.commission_type == CommissionType.FIXED_AMOUNT.value:
            commission_amount = partner.commission_rate
        else:
            # Tiered commission (simplified - would need more complex logic)
            commission_amount = subscription_amount * (partner.commission_rate / 100)

        # Update referral
        referral.status = "converted"
        referral.conversion_date = datetime.utcnow()
        referral.conversion_value = subscription_amount
        referral.save()

        # Update partner statistics
        partner.active_referrals += 1
        partner.total_commission_earned += commission_amount
        partner.total_commission_pending += commission_amount
        partner.save()

        # Create commission
        # ✅ CORRECT: Django ORM - use Model.objects.create() for creating records
        commission = PartnerCommission.objects.create(
            partner_id=partner.id,
            referral_id=referral.id,
            subscription_id=subscription_id,
            commission_type=partner.commission_type,
            commission_rate=partner.commission_rate,
            base_amount=subscription_amount,
            commission_amount=commission_amount,
            status="pending"
        )

        return commission

    def create_payout(
        self,
        partner_id: str,
        period_start: datetime,
        period_end: datetime
    ) -> PartnerPayout:
        """Create partner payout for commission period"""
        # Get partner
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        partner = Partner.objects.filter(id=partner_id).first()

        if not partner:
            raise Response(status=status.HTTP_404, detail="Partner not found")

        # Get pending commissions for period
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        commissions = PartnerCommission.objects.filter(
            partner_id=partner_id,
            status="pending",
            earned_date__gte=period_start,
            earned_date__lte=period_end
        )

        if not commissions:
            raise Response(status=status.HTTP_400, detail="No pending commissions for this period")

        # Calculate total payout amount
        total_amount = sum(commission.commission_amount for commission in commissions)

        if total_amount < partner.minimum_payout:
            # ✅ CORRECT: Raise DRF exception (NOT HTTPException)
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                detail=f"Payout amount {total_amount} is below minimum {partner.minimum_payout}"
            )

        # Create payout
        payout = PartnerPayout(
            partner_id=partner_id,
            amount=total_amount,
            currency="USD",
            payout_method=partner.payout_method,
            payout_details=partner.payout_details or {},
            status="pending",
            period_start=period_start,
            period_end=period_end
        )

        # Create payout
        # ✅ CORRECT: Django ORM - use Model.objects.create() for creating records
        payout = PartnerPayout.objects.create(
            partner_id=partner_id,
            amount=total_amount,
            currency="USD",
            payout_method=partner.payout_method,
            payout_details=partner.payout_details or {},
            status="pending",
            period_start=period_start,
            period_end=period_end
        )

        # Link commissions to payout
        commissions.update(payout_id=payout.id, status="approved")

        # Update partner statistics
        partner.total_commission_pending -= total_amount
        partner.save()

        return payout

    def process_payout(
        self,
        payout_id: str,
        transaction_id: str
    ) -> PartnerPayout:
        """Process payout (mark as completed)"""
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        payout = PartnerPayout.objects.filter(id=payout_id).first()

        if not payout:
            raise Response(status=status.HTTP_404, detail="Payout not found")

        if payout.status != "pending":
            raise Response(status=status.HTTP_400, detail="Payout already processed")

        # Update payout
        payout.status = "completed"
        payout.processed_date = datetime.utcnow()
        payout.transaction_id = transaction_id
        payout.save()

        # Update commissions
        # ✅ CORRECT: Django ORM - use Model.objects.filter().update() for bulk updates
        PartnerCommission.objects.filter(payout_id=payout_id).update(
            status="paid",
            paid_date=datetime.utcnow()
        )

        # Update partner statistics
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        partner = Partner.objects.filter(id=payout.partner_id).first()

        if partner:
            partner.total_commission_paid += payout.amount
            partner.save()

        return payout

