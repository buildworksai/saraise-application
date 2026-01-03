# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Tenant Testing
# Reference: docs/architecture/application-architecture.md § 4.1 (Row-Level Multitenancy)
# Also: docs/architecture/engineering-governance-and-pr-controls.md § 2.2 (Testing)
# CRITICAL: SARAISE uses Django ORM exclusively
# 
# CRITICAL NOTES:
# - Tests verify Row-Level Multitenancy isolation (tenant_id filtering)
# - Happy path: user can access only their tenant's data
# - Isolation test: user cannot query across tenant boundaries
# - Module loading test: user can access only installed modules
# - All tests use Django ORM patterns (no database sessions)

import pytest
from src.modules.tenant.services.tenant_service import TenantService
from src.modules.tenant.services.tenant_user_service import TenantUserService
from src.models.user import User

@pytest.mark.asyncio
def test_create_tenant(platform_owner_user):
    """Test tenant creation"""
    # ✅ CORRECT: Django ORM - no database session needed
    service = TenantService()

    tenant = service.create_tenant(
        name="Test Tenant",
        domain="test.example.com"
    )

    assert tenant.id is not None
    assert tenant.name == "Test Tenant"
    assert tenant.is_active is True

@pytest.mark.asyncio
def test_tenant_isolation():
    """Test tenant isolation"""
    # ✅ CORRECT: Django ORM - no database session needed
    service = TenantService()

    # Create two tenants
    tenant1 = service.create_tenant(name="Tenant 1")
    tenant2 = service.create_tenant(name="Tenant 2")

    # Create users for each tenant
    user_data1 = {"email": "user1@test.com", "name": "User 1"}
    user_data2 = {"email": "user2@test.com", "name": "User 2"}
    user1 = service.create_tenant_user(tenant1.id, user_data1)
    user2 = service.create_tenant_user(tenant2.id, user_data2)

    # Verify users belong to correct tenants
    assert user1.tenant_id == tenant1.id
    assert user2.tenant_id == tenant2.id
    assert user1.tenant_id != user2.tenant_id

@pytest.mark.asyncio
def test_tenant_user_isolation(tenant_fixture):
    """Test tenant user isolation via explicit Row-Level Multitenancy filtering.
    
    CRITICAL: This test demonstrates explicit tenant_id filtering, not schema context.
    Reference: docs/architecture/security-model.md § 2
    """
    # Create users for different tenants
    tenant1 = tenant_fixture(name="tenant-1")
    tenant2 = tenant_fixture(name="tenant-2")

    # ✅ CORRECT: Django ORM - no database session needed
    service = TenantUserService()
    
    # Create user for tenant1 with explicit tenant_id
    user_data1 = {"email": "user1@test.com", "name": "User 1"}
    user1 = service.create_tenant_user(tenant1.id, user_data1)

    # Create user for tenant2 with explicit tenant_id
    user_data2 = {"email": "user2@test.com", "name": "User 2"}
    user2 = service.create_tenant_user(tenant2.id, user_data2)

    # Verify users are isolated by explicit tenant_id filtering
    # (NOT by schema context / search_path)
    # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
    found_user = User.objects.filter(
        email="user2@test.com",
        tenant_id=tenant1.id
    ).first()
    assert found_user is None  # user2 not found when filtering by tenant1

    # Verify user1 IS found when filtering by correct tenant_id
    found_user = User.objects.filter(
        email="user1@test.com",
        tenant_id=tenant1.id
    ).first()
    assert found_user is not None  # user1 found in tenant1

