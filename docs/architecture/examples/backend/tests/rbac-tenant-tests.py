# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Tenant Resource RBAC Tests with Policy Engine
# backend/tests/test_rbac_tenant.py
# Reference: docs/architecture/policy-engine-spec.md § 1, § 4
#            docs/architecture/application-architecture.md § 2.1

import pytest
from src.core.policy_engine import PolicyEngine

class TestTenantUserManagement:
    """Test tenant user management RBAC via Policy Engine.
    
    CRITICAL: tenant_admin can create users in their tenant.
    tenant_viewer cannot (read-only role).
    Policy Engine evaluates per-request (no cached roles).
    """

    @pytest.mark.asyncio
    def test_tenant_admin_can_create_user(
        self,
        tenant_fixture,
        policy_engine: PolicyEngine
    ):
        """Test that tenant_admin is authorized to create users"""
        decision = policy_engine.evaluate(
            user_id="tenant-admin-id",
            tenant_id=tenant_fixture.id,
            resource="tenant.users",
            action="create",
            context={"email": "newuser@test.com"}
        )
        assert decision.allowed, "Tenant admin should be authorized"

    @pytest.mark.asyncio
    def test_tenant_viewer_cannot_create_user(
        self,
        tenant_fixture,
        policy_engine: PolicyEngine
    ):
        """Test that tenant_viewer CANNOT create users (read-only)"""
        decision = policy_engine.evaluate(
            user_id="tenant-viewer-id",
            tenant_id=tenant_fixture.id,
            resource="tenant.users",
            action="create",
            context={"email": "newuser@test.com"}
        )
        assert decision.allowed is False, "Viewer cannot create users"

    @pytest.mark.asyncio
    def test_tenant_isolation_enforced(
        self,
        tenant_fixture,
        policy_engine: PolicyEngine
    ):
        """Test that users cannot access other tenants.
        
        Tenant isolation via explicit tenant_id filtering.
        User's session tenant_id is compared against requested tenant_id.
        """
        other_tenant_id = "other-tenant-id"
        
        decision = policy_engine.evaluate(
            user_id="tenant-admin-id",
            tenant_id=tenant_fixture.id,  # User's tenant
            resource="tenant.users",
            action="list",
            context={"requested_tenant_id": other_tenant_id}
        )
        # Cannot access other tenant's resources
        assert decision.allowed is False, "Cannot access other tenant"

