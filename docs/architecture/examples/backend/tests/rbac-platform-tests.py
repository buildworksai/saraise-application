# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Platform Resource RBAC Tests with Policy Engine
# backend/tests/test_rbac_platform.py
# Reference: docs/architecture/policy-engine-spec.md § 1, § 4

import pytest
from rest_framework.test import APIClient
from src.main import app
from src.core.policy_engine import PolicyEngine

class TestPlatformTenantManagement:
    """Test platform tenant management RBAC via Policy Engine.
    
    CRITICAL: Only platform_owner role can create tenants.
    Policy Engine evaluates at request time (no cached roles).
    See docs/architecture/policy-engine-spec.md § 4.
    """

    @pytest.mark.asyncio
    def test_platform_owner_can_create_tenant(
        self,
        policy_engine: PolicyEngine
    ):
        """Test platform_owner authorization for tenant creation"""
        decision = policy_engine.evaluate(
            user_id="platform-owner-id",
            tenant_id=None,  # Platform operation
            resource="platform.tenants",
            action="create",
            context={"tenant_name": "New Tenant"}
        )
        assert decision.allowed, "Platform owner should be authorized"

    @pytest.mark.asyncio
    def test_tenant_admin_cannot_create_tenant(
        self,
        policy_engine: PolicyEngine,
        tenant_fixture
    ):
        """Test that tenant_admin CANNOT create tenants (platform op)"""
        decision = policy_engine.evaluate(
            user_id="tenant-admin-id",
            tenant_id=tenant_fixture.id,  # Tenant user
            resource="platform.tenants",
            action="create",
            context={"tenant_name": "New Tenant"}
        )
        assert decision.allowed is False, "Tenant admin cannot create tenants"

    def test_unauthenticated_cannot_create_tenant(self):
        """Test that unauthenticated requests are rejected"""
        client = APIClient()
        response = self.client.post("/api/v1/tenants", json={
            "name": "New Tenant",
            "domain": "new.example.com"
        })
        assert response.status_code == 401

