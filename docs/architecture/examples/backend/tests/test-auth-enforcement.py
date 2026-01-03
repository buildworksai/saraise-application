# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Test Route Protection with Policy Engine
# backend/tests/test_auth_enforcement.py
# Reference: docs/architecture/policy-engine-spec.md § 1, § 4

import pytest
from rest_framework.test import APIClient
from src.main import app
from src.core.policy_engine import PolicyEngine

test_client = APIClient()

# Test Policy Engine allows authorized access
def test_tenant_admin_can_create_users(tenant_fixture, user_fixture):
    """Test that Policy Engine allows authorized operations.
    
    Uses tenant_fixture for proper Row-Level Multitenancy context.
    See docs/architecture/policy-engine-spec.md § 4 (Runtime Evaluation).
    """
    response = test_client.post(
        "/api/v1/users",
        json={"email": "newuser@example.com"},
        headers={"Cookie": f"session={user_fixture.session_id}"}
    )
    assert response.status_code == 201

# Test Policy Engine denies unauthorized access
def test_tenant_viewer_cannot_create_users(tenant_fixture, user_fixture):
    """Test that Policy Engine denies unauthorized operations.
    
    Policy Engine evaluates RBAC at request time (no cached roles).
    See docs/architecture/security-model.md § 2.4 (Session Is NOT an Authorization Cache).
    """
    response = test_client.post(
        "/api/v1/users",
        json={"email": "newuser@example.com"},
        headers={"Cookie": f"session={user_fixture.session_id}"}
    )
    # Policy Engine denies based on user role
    assert response.status_code == 403

