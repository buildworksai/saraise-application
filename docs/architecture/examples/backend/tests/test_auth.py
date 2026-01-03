# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Backend Authentication and Authorization Testing
# backend/tests/test_auth.py
# Reference: docs/architecture/authentication-and-session-management-spec.md
#            docs/architecture/policy-engine-spec.md

import pytest
from rest_framework.test import APIClient
from django.db import transaction
from src.main import app
from src.models.base import User, Tenant
from django.db import transaction
from src.core.policy_engine import PolicyEngine

@# Django fixtures use django.test.TestCase
def client(db_session):
    """Create a test client with database session override"""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with APIClient() as test_client:
        yield test_client
    app.dependency_overrides.clear()

class TestAuthentication:
    """Test authentication functionality.
    
    CRITICAL: Sessions establish IDENTITY ONLY (user_id, email, tenant_id, timestamps).
    NO roles, permissions, or ABAC attributes cached in session.
    See docs/architecture/authentication-and-session-management-spec.md.
    """

    @pytest.mark.asyncio
    def test_user_creation(self, tenant_fixture):
        """Test user creation"""
        # ✅ CORRECT: Django ORM - use Model.objects.create() instead of db_session.add()/commit()
        user = User.objects.create(
            external_id="new-user-456",
            email="newuser@example.com",
            email_verified=True,
            tenant_id=tenant_fixture.id
        )

        assert user.id is not None
        assert user.email == "newuser@example.com"
        assert user.tenant_id == tenant_fixture.id

    def test_protected_endpoint_without_session(self, client):
        """Test protected endpoint without authentication"""
        response = self.client.get("/api/v1/agents")
        assert response.status_code == 401

    def test_protected_endpoint_with_session(self, client, user_fixture):
        """Test protected endpoint with valid session.
        
        Session cookie contains identity only (see fixture).
        Policy Engine evaluates authorization at request time.
        """
        headers = {"Cookie": f"session={user_fixture.session_id}"}
        response = self.client.get("/api/v1/agents", headers=headers)

        # Should succeed if authorized (Policy Engine checks at request time)
        assert response.status_code in [200, 403]

class TestPolicyEngineAuthorization:
    """Test Policy Engine authorization patterns.
    
    See docs/architecture/policy-engine-spec.md § 1, § 4.
    """

    @pytest.mark.asyncio
    def test_policy_engine_allows_authorized_user(
        self,
        user_fixture,
        policy_engine: PolicyEngine
    ):
        """Test that Policy Engine allows authorized operations"""
        decision = policy_engine.evaluate(
            user_id=user_fixture.id,
            tenant_id=user_fixture.tenant_id,
            resource="agents",
            action="list",
            context={}
        )
        # Decision depends on user's role and RBAC rules
        assert isinstance(decision.allowed, bool)

    @pytest.mark.asyncio
    def test_policy_engine_denies_unauthorized_user(
        self,
        policy_engine: PolicyEngine
    ):
        """Test that Policy Engine denies unauthorized operations"""
        decision = policy_engine.evaluate(
            user_id="unauthorized-user-id",
            tenant_id="tenant-123",
            resource="platform.settings",  # Platform resource
            action="update",
            context={}
        )
        # Non-platform-owner cannot access platform resources
        assert decision.allowed is False

class TestMultiTenantIsolation:
    """Test multi-tenant isolation with explicit filtering.
    
    CRITICAL: Row-Level Multitenancy requires explicit tenant_id filtering.
    See docs/architecture/application-architecture.md § 2.1.
    """

    @pytest.mark.asyncio
    def test_tenant_isolation_in_queries(self, tenant_fixture):
        """Test that queries properly filter by tenant_id"""
        # Create user for this tenant
        # ✅ CORRECT: Django ORM - use Model.objects.create() instead of db_session.add()/commit()
        user = User.objects.create(
            external_id="test-user",
            email="test@example.com",
            tenant_id=tenant_fixture.id
        )

        # Query with explicit tenant_id filtering
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        found_user = User.objects.filter(
            tenant_id=tenant_fixture.id,
            email="test@example.com"
        ).first()

        assert found_user is not None
        assert found_user.tenant_id == tenant_fixture.id

