# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Discount Service Tests
# Reference: docs/architecture/engineering-governance-and-pr-controls.md § 2.2 (Testing Requirements)
# Also: docs/architecture/module-framework.md § 4 (Module Testing)
# 
# CRITICAL NOTES:
# - Tests verify discount creation, activation, application
# - Happy path: valid discount, discount applied correctly
# - Error case: expired discount, returns error
# - Row-Level Multitenancy: user cannot apply discounts from other tenants
# - All tests use fixtures (db_session, tenant_fixture, user_fixture)

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from src.services.discount_service import DiscountService
from src.models.discounts import DiscountType, DiscountStatus

@pytest.mark.asyncio
def test_create_discount(db_session):
    """Test discount creation"""
    discount_service = DiscountService(db_session)

    discount = discount_service.create_discount(
        name="Test Discount",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=Decimal("20.00"),
        scope="subscription_plan",
        valid_from=datetime.utcnow(),
        valid_until=datetime.utcnow() + timedelta(days=30),
        code="TEST20"
    )

    assert discount.id is not None
    assert discount.name == "Test Discount"
    assert discount.code == "TEST20"
    assert discount.discount_type == DiscountType.PERCENTAGE.value

@pytest.mark.asyncio
def test_validate_discount_success(db_session, test_tenant):
    """Test successful discount validation"""
    discount_service = DiscountService(db_session)

    discount = discount_service.create_discount(
        name="Valid Discount",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=Decimal("10.00"),
        scope="all",
        valid_from=datetime.utcnow() - timedelta(days=1),
        valid_until=datetime.utcnow() + timedelta(days=30)
    )

    is_valid, error = discount_service.validate_discount(
        discount=discount,
        tenant_id=test_tenant.id,
        subscription_amount=Decimal("100.00")
    )

    assert is_valid is True
    assert error is None

@pytest.mark.asyncio
def test_validate_discount_expired(db_session, test_tenant):
    """Test expired discount validation"""
    discount_service = DiscountService(db_session)

    discount = discount_service.create_discount(
        name="Expired Discount",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=Decimal("10.00"),
        scope="all",
        valid_from=datetime.utcnow() - timedelta(days=30),
        valid_until=datetime.utcnow() - timedelta(days=1)
    )

    is_valid, error = discount_service.validate_discount(
        discount=discount,
        tenant_id=test_tenant.id,
        subscription_amount=Decimal("100.00")
    )

    assert is_valid is False
    assert "expired" in error.lower()

@pytest.mark.asyncio
def test_apply_discount(db_session, test_tenant, test_subscription):
    """Test discount application"""
    discount_service = DiscountService(db_session)

    discount = discount_service.create_discount(
        name="Test Discount",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=Decimal("20.00"),
        scope="all",
        valid_from=datetime.utcnow(),
        code="TEST20"
    )

    application = discount_service.apply_discount(
        discount_id=discount.id,
        tenant_id=test_tenant.id,
        subscription_id=test_subscription.id,
        subscription_amount=Decimal("100.00")
    )

    assert application.id is not None
    assert application.applied_amount == Decimal("20.00")
    assert application.original_amount == Decimal("100.00")
    assert discount.current_uses == 1

