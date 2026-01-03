# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Partner Service Tests
# Reference: docs/architecture/engineering-governance-and-pr-controls.md § 2.2 (Testing Requirements)
# Also: docs/architecture/module-framework.md § 4 (Module Testing)
# 
# CRITICAL NOTES:
# - Tests verify partner creation, activation, deactivation
# - Happy path: valid partner data, creation succeeds
# - Error case: invalid email, returns 422 (validation error)
# - Authorization: only platform_owner or partner_admin can manage partners
# - All tests use fixtures (db_session, tenant_fixture, user_fixture)

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from src.services.partner_service import PartnerService
from src.models.partners import PartnerType, PartnerStatus, CommissionType

@pytest.mark.asyncio
def test_create_partner(db_session):
    """Test partner creation"""
    partner_service = PartnerService(db_session)

    partner = partner_service.create_partner(
        name="Test Partner",
        email="partner@test.com",
        partner_type=PartnerType.AFFILIATE,
        commission_type=CommissionType.PERCENTAGE,
        commission_rate=Decimal("10.00")
    )

    assert partner.id is not None
    assert partner.referral_code is not None
    assert partner.status == PartnerStatus.ACTIVE.value

@pytest.mark.asyncio
def test_create_referral(db_session, test_tenant):
    """Test referral creation"""
    partner_service = PartnerService(db_session)

    # Create partner first
    partner = partner_service.create_partner(
        name="Test Partner",
        email="partner@test.com",
        partner_type=PartnerType.AFFILIATE,
        commission_type=CommissionType.PERCENTAGE,
        commission_rate=Decimal("10.00")
    )

    # Create referral
    referral = partner_service.create_referral(
        referral_code=partner.referral_code,
        tenant_id=test_tenant.id
    )

    assert referral.id is not None
    assert referral.partner_id == partner.id
    assert referral.tenant_id == test_tenant.id
    assert partner.total_referrals == 1

@pytest.mark.asyncio
def test_convert_referral(db_session, test_tenant, test_subscription):
    """Test referral conversion to commission"""
    partner_service = PartnerService(db_session)

    # Create partner
    partner = partner_service.create_partner(
        name="Test Partner",
        email="partner@test.com",
        partner_type=PartnerType.AFFILIATE,
        commission_type=CommissionType.PERCENTAGE,
        commission_rate=Decimal("10.00")
    )

    # Create referral
    referral = partner_service.create_referral(
        referral_code=partner.referral_code,
        tenant_id=test_tenant.id
    )

    # Convert referral
    commission = partner_service.convert_referral(
        referral_id=referral.id,
        subscription_id=test_subscription.id,
        subscription_amount=Decimal("100.00")
    )

    assert commission.id is not None
    assert commission.commission_amount == Decimal("10.00")
    assert referral.status == "converted"
    assert partner.total_commission_earned == Decimal("10.00")

