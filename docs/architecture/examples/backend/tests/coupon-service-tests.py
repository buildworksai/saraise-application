# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Coupon Service Tests
# backend/src/tests/test_coupon_service.py
# Reference: docs/architecture/engineering-governance-and-pr-controls.md § 2.2 (Test Coverage)
# CRITICAL NOTES:
# - Test coverage ≥90% for coupon service (engineering-governance-and-pr-controls.md § 2.2)
# - Test coupon creation: valid code, discount type, validity period
# - Test coupon validation: valid coupon, expired coupon, invalid code
# - Test coupon application: discount calculation, subscription context
# - Test coupon limits: usage_limit enforcement, per-user limits
# - Test coupon types: percentage discount, fixed amount, free trial
# - Test error cases: duplicate code, invalid discount value, expired coupon
# - Test authorization: tenant isolation, admin-only operations
# - Test concurrent use: atomic usage counter updates
# - Test edge cases: 0% discount, 100% discount, negative amounts (validation)
# Source: docs/architecture/engineering-governance-and-pr-controls.md § 3

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from src.services.coupon_service import CouponService
from src.models.coupons import CouponType, CouponStatus, CouponUsageType
from rest_framework.exceptions import ValidationError, APIException

@pytest.mark.asyncio
def test_create_coupon(db_session):
    """Test coupon creation"""
    coupon_service = CouponService(db_session)

    coupon = coupon_service.create_coupon(
        code="TEST20",
        name="Test Coupon",
        coupon_type=CouponType.STANDALONE,
        discount_type="percentage",
        discount_value=Decimal("20.00"),
        scope="all",
        valid_from=datetime.utcnow()
    )

    assert coupon.id is not None
    assert coupon.code == "TEST20"
    assert coupon.coupon_type == CouponType.STANDALONE.value

@pytest.mark.asyncio
def test_validate_coupon_success(db_session, test_tenant):
    """Test successful coupon validation"""
    coupon_service = CouponService(db_session)

    coupon = coupon_service.create_coupon(
        code="VALID20",
        name="Valid Coupon",
        coupon_type=CouponType.STANDALONE,
        discount_type="percentage",
        discount_value=Decimal("20.00"),
        scope="all",
        valid_from=datetime.utcnow()
    )

    is_valid, error = coupon_service.validate_coupon(
        coupon=coupon,
        tenant_id=test_tenant.id,
        subscription_amount=Decimal("100.00")
    )

    assert is_valid is True
    assert error is None

@pytest.mark.asyncio
def test_apply_coupon_single_use(db_session, test_tenant, test_subscription):
    """Test single-use coupon application"""
    coupon_service = CouponService(db_session)

    coupon = coupon_service.create_coupon(
        code="SINGLE20",
        name="Single Use Coupon",
        coupon_type=CouponType.STANDALONE,
        discount_type="percentage",
        discount_value=Decimal("20.00"),
        scope="all",
        valid_from=datetime.utcnow(),
        usage_type=CouponUsageType.SINGLE_USE
    )

    # First application succeeds
    application1 = coupon_service.apply_coupon(
        coupon_code="SINGLE20",
        tenant_id=test_tenant.id,
        subscription_id=test_subscription.id,
        subscription_amount=Decimal("100.00")
    )

    assert application1.id is not None
    assert coupon.status == CouponStatus.ARCHIVED.value

    # Second application fails
    # ✅ CORRECT: Test for DRF exception (NOT HTTPException)
    with pytest.raises(ValidationError) as exc_info:
        coupon_service.apply_coupon(
            coupon_code="SINGLE20",
            tenant_id=test_tenant.id,
            subscription_id=test_subscription.id,
            subscription_amount=Decimal("100.00")
        )

    assert exc_info.value.status_code == 400

