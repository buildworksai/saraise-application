# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Integration Testing with Policy Engine and Multi-Tenancy
# backend/tests/test_integration.py
# Reference: docs/architecture/policy-engine-spec.md
#            docs/architecture/application-architecture.md § 2.1
# CRITICAL: SARAISE uses Django ORM exclusively
# - Use Django TestCase and Model.objects for test data
# - Use django.test.Client or APIClient for HTTP testing

import pytest
from rest_framework.test import APIClient
from django.test import TestCase
from django.db import transaction
from src.models.base import User, Tenant
from src.core.policy_engine import PolicyEngine
import json

@pytest.fixture
def client():
    """Create test client for integration tests.
    
    ✅ CORRECT: Django testing - use APIClient directly, no dependency injection needed
    """
    return APIClient()

@pytest.fixture
def authenticated_user(tenant_fixture):
    """Create authenticated user for integration tests.
    
    Uses tenant_fixture for proper Row-Level Multitenancy context.
    
    ✅ CORRECT: Django ORM - use Model.objects.create() instead of db_session.add()/commit()
    """
    user = User.objects.create(
        external_id="integration-user",
        email="integration@test.com",
        email_verified=True,
        tenant_id=tenant_fixture.id
    )
    # ✅ CORRECT: Django ORM - no refresh needed, object is already in memory
    return user

class TestAgentIntegration:
    """Integration tests for AI agent management"""

    @pytest.mark.asyncio
    def test_agent_lifecycle(self, client, authenticated_user):
        """Test complete agent lifecycle: create, get, update, delete"""
        # Login to get session
        login_response = self.client.post(
            "/api/v1/auth/login",
            json={"email": authenticated_user.email, "password": "test_password"}
        )

        assert login_response.status_code == 200

        # Create agent
        agent_data = {
            "name": "Integration Test Agent",
            "description": "Agent for integration testing",
            "agent_type": "openai",
            "configuration": json.dumps({
                "model": "gpt-4",
                "temperature": 0.7,
                "max_tokens": 1000
            })
        }

        create_response = self.client.post("/api/v1/agents", json=agent_data)

        assert create_response.status_code in [200, 201]

        if create_response.status_code in [200, 201]:
            agent_id = create_response.json()["id"]

            # Get agent
            get_response = self.client.get(f"/api/v1/agents/{agent_id}")
            assert get_response.status_code == 200

            # Update agent
            update_data = {
                "name": "Updated Integration Test Agent",
                "description": "Updated description"
            }

            update_response = client.put(
                f"/api/v1/agents/{agent_id}",
                json=update_data
            )
            assert update_response.status_code == 200

            # Delete agent
            delete_response = client.delete(f"/api/v1/agents/{agent_id}")
            assert delete_response.status_code in [200, 204]

class TestWorkflowIntegration:
    """Integration tests for workflow management"""

    @pytest.mark.asyncio
    def test_workflow_creation_and_execution(self, client, authenticated_user):
        """Test workflow creation and execution"""
        # Login to get session
        client.post(
            "/api/v1/auth/login",
            json={"email": authenticated_user.email, "password": "test_password"}
        )

        # Create workflow
        workflow_data = {
            "name": "Integration Test Workflow",
            "description": "Workflow for integration testing",
            "steps": [
                {
                    "type": "data_ingestion",
                    "config": {"source": "api", "endpoint": "https://api.example.com/data"}
                },
                {
                    "type": "ai_processing",
                    "config": {"agent_id": "test-agent", "prompt": "Process the data"}
                },
                {
                    "type": "data_output",
                    "config": {"destination": "database", "table": "processed_data"}
                }
            ]
        }

        create_response = self.client.post("/api/v1/workflows", json=workflow_data)

        assert create_response.status_code in [200, 201]

# Run integration tests with: pytest tests/test_integration.py -v

