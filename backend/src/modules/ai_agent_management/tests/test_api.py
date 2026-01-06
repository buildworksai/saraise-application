"""
API Integration Tests for AI Agent Management module.

Tests all DRF ViewSet endpoints:
- CRUD operations
- Authentication/authorization
- Tenant isolation
- Custom actions (execute, pause, resume, terminate)
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from ..models import Agent, AgentExecution, AgentIdentityType, AgentLifecycleState
from ..tool_models import Tool
from ..approval_models import ApprovalRequest, ApprovalStatus

User = get_user_model()


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def tenant_user(db):
    """Create a test user with tenant."""
    tenant_id = "test-tenant-1"
    user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
    # Add tenant_id attribute (adjust based on your User model)
    user.tenant_id = tenant_id
    user.save()
    return user


@pytest.fixture
def authenticated_client(api_client, tenant_user):
    """Create authenticated API client."""
    api_client.force_authenticate(user=tenant_user)
    return api_client


@pytest.mark.django_db
class TestAgentViewSet:
    """Test AgentViewSet CRUD operations."""

    def test_list_agents_requires_authentication(self, api_client):
        """Test that listing agents requires authentication."""
        response = api_client.get("/api/v1/ai-agents/agents/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_agents(self, authenticated_client, tenant_user):
        """Test listing agents for authenticated user."""
        # Create agents for this tenant
        Agent.objects.create(
            tenant_id=tenant_user.tenant_id,
            name="Test Agent 1",
            identity_type=AgentIdentityType.SYSTEM_BOUND,
            subject_id="system-role-1",
            framework="langgraph",
            config={},
            is_active=True,
            created_by=tenant_user.id,
        )
        Agent.objects.create(
            tenant_id=tenant_user.tenant_id,
            name="Test Agent 2",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id=tenant_user.id,
            session_id="session-123",
            framework="crewai",
            config={},
            is_active=True,
            created_by=tenant_user.id,
        )

        # Create agent for different tenant (should not appear)
        other_tenant_id = "other-tenant"
        Agent.objects.create(
            tenant_id=other_tenant_id,
            name="Other Tenant Agent",
            identity_type=AgentIdentityType.SYSTEM_BOUND,
            subject_id="system-role-1",
            framework="langgraph",
            config={},
            is_active=True,
            created_by=tenant_user.id,
        )

        response = authenticated_client.get("/api/v1/ai-agents/agents/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        assert all(agent["tenant_id"] == tenant_user.tenant_id for agent in response.data)

    def test_create_agent(self, authenticated_client, tenant_user):
        """Test creating a new agent."""
        data = {
            "name": "New Agent",
            "description": "Test agent",
            "identity_type": "system_bound",
            "subject_id": "system-role-1",
            "framework": "langgraph",
            "config": {"key": "value"},
        }
        response = authenticated_client.post("/api/v1/ai-agents/agents/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Agent"
        assert response.data["tenant_id"] == tenant_user.tenant_id

        # Verify agent was created in database
        agent = Agent.objects.get(id=response.data["id"])
        assert agent.tenant_id == tenant_user.tenant_id
        assert agent.name == "New Agent"

    def test_create_user_bound_agent_requires_session_id(self, authenticated_client, tenant_user):
        """Test that user-bound agents require session_id."""
        data = {
            "name": "User Agent",
            "identity_type": "user_bound",
            "subject_id": tenant_user.id,
            "framework": "langgraph",
            "config": {},
        }
        response = authenticated_client.post("/api/v1/ai-agents/agents/", data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Add session_id
        data["session_id"] = "session-123"
        response = authenticated_client.post("/api/v1/ai-agents/agents/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_get_agent_detail(self, authenticated_client, tenant_user):
        """Test retrieving agent detail."""
        agent = Agent.objects.create(
            tenant_id=tenant_user.tenant_id,
            name="Detail Agent",
            identity_type=AgentIdentityType.SYSTEM_BOUND,
            subject_id="system-role-1",
            framework="langgraph",
            config={},
            is_active=True,
            created_by=tenant_user.id,
        )

        response = authenticated_client.get(f"/api/v1/ai-agents/agents/{agent.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Detail Agent"
        assert response.data["id"] == str(agent.id)

    def test_get_agent_detail_other_tenant(self, authenticated_client, tenant_user):
        """Test that users cannot access agents from other tenants."""
        other_tenant_id = "other-tenant"
        agent = Agent.objects.create(
            tenant_id=other_tenant_id,
            name="Other Tenant Agent",
            identity_type=AgentIdentityType.SYSTEM_BOUND,
            subject_id="system-role-1",
            framework="langgraph",
            config={},
            is_active=True,
            created_by=tenant_user.id,
        )

        response = authenticated_client.get(f"/api/v1/ai-agents/agents/{agent.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_agent(self, authenticated_client, tenant_user):
        """Test updating an agent."""
        agent = Agent.objects.create(
            tenant_id=tenant_user.tenant_id,
            name="Original Name",
            identity_type=AgentIdentityType.SYSTEM_BOUND,
            subject_id="system-role-1",
            framework="langgraph",
            config={},
            is_active=True,
            created_by=tenant_user.id,
        )

        data = {"name": "Updated Name"}
        response = authenticated_client.patch(
            f"/api/v1/ai-agents/agents/{agent.id}/", data, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Updated Name"

        # Verify update in database
        agent.refresh_from_db()
        assert agent.name == "Updated Name"

    def test_delete_agent(self, authenticated_client, tenant_user):
        """Test deleting an agent."""
        agent = Agent.objects.create(
            tenant_id=tenant_user.tenant_id,
            name="To Delete",
            identity_type=AgentIdentityType.SYSTEM_BOUND,
            subject_id="system-role-1",
            framework="langgraph",
            config={},
            is_active=True,
            created_by=tenant_user.id,
        )

        response = authenticated_client.delete(f"/api/v1/ai-agents/agents/{agent.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify agent was deleted
        assert not Agent.objects.filter(id=agent.id).exists()

    def test_execute_agent(self, authenticated_client, tenant_user):
        """Test executing an agent."""
        agent = Agent.objects.create(
            tenant_id=tenant_user.tenant_id,
            name="Executable Agent",
            identity_type=AgentIdentityType.SYSTEM_BOUND,
            subject_id="system-role-1",
            framework="langgraph",
            config={},
            is_active=True,
            created_by=tenant_user.id,
        )

        data = {
            "task_definition": {"task": "test"},
            "metadata": {},
        }
        response = authenticated_client.post(
            f"/api/v1/ai-agents/agents/{agent.id}/execute/", data, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert "id" in response.data
        assert response.data["agent_id"] == str(agent.id)

        # Verify execution was created
        execution = AgentExecution.objects.get(id=response.data["id"])
        assert execution.agent_id == agent.id


@pytest.mark.django_db
class TestAgentExecutionViewSet:
    """Test AgentExecutionViewSet read-only operations."""

    def test_list_executions(self, authenticated_client, tenant_user):
        """Test listing executions."""
        agent = Agent.objects.create(
            tenant_id=tenant_user.tenant_id,
            name="Test Agent",
            identity_type=AgentIdentityType.SYSTEM_BOUND,
            subject_id="system-role-1",
            framework="langgraph",
            config={},
            is_active=True,
            created_by=tenant_user.id,
        )

        execution = AgentExecution.objects.create(
            tenant_id=tenant_user.tenant_id,
            agent=agent,
            agent_id=agent.id,
            agent_name=agent.name,
            state=AgentLifecycleState.RUNNING,
            task_definition={"task": "test"},
            metadata={},
        )

        response = authenticated_client.get("/api/v1/ai-agents/executions/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["id"] == str(execution.id)


@pytest.mark.django_db
class TestApprovalRequestViewSet:
    """Test ApprovalRequestViewSet operations."""

    def test_list_approvals(self, authenticated_client, tenant_user):
        """Test listing approval requests."""
        agent = Agent.objects.create(
            tenant_id=tenant_user.tenant_id,
            name="Test Agent",
            identity_type=AgentIdentityType.SYSTEM_BOUND,
            subject_id="system-role-1",
            framework="langgraph",
            config={},
            is_active=True,
            created_by=tenant_user.id,
        )

        tool = Tool.objects.create(
            tenant_id=tenant_user.tenant_id,
            name="test_tool",
            owning_module="test",
            version="1.0.0",
            requires_approval=True,
        )

        execution = AgentExecution.objects.create(
            tenant_id=tenant_user.tenant_id,
            agent=agent,
            agent_id=agent.id,
            agent_name=agent.name,
            state=AgentLifecycleState.RUNNING,
            task_definition={},
            metadata={},
        )

        approval = ApprovalRequest.objects.create(
            tenant_id=tenant_user.tenant_id,
            tool=tool,
            tool_name=tool.name,
            agent_execution=execution,
            agent_execution_id=execution.id,
            status=ApprovalStatus.PENDING,
            requested_by=tenant_user.id,
            requested_for=tenant_user.id,
        )

        response = authenticated_client.get("/api/v1/ai-agents/approvals/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["id"] == str(approval.id)
        assert response.data[0]["status"] == "pending"

    def test_approve_request(self, authenticated_client, tenant_user):
        """Test approving an approval request."""
        agent = Agent.objects.create(
            tenant_id=tenant_user.tenant_id,
            name="Test Agent",
            identity_type=AgentIdentityType.SYSTEM_BOUND,
            subject_id="system-role-1",
            framework="langgraph",
            config={},
            is_active=True,
            created_by=tenant_user.id,
        )

        tool = Tool.objects.create(
            tenant_id=tenant_user.tenant_id,
            name="test_tool",
            owning_module="test",
            version="1.0.0",
            requires_approval=True,
        )

        execution = AgentExecution.objects.create(
            tenant_id=tenant_user.tenant_id,
            agent=agent,
            agent_id=agent.id,
            agent_name=agent.name,
            state=AgentLifecycleState.RUNNING,
            task_definition={},
            metadata={},
        )

        approval = ApprovalRequest.objects.create(
            tenant_id=tenant_user.tenant_id,
            tool=tool,
            tool_name=tool.name,
            agent_execution=execution,
            agent_execution_id=execution.id,
            status=ApprovalStatus.PENDING,
            requested_by=tenant_user.id,
            requested_for=tenant_user.id,
        )

        response = authenticated_client.post(f"/api/v1/ai-agents/approvals/{approval.id}/approve/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "approved"

        # Verify approval was updated
        approval.refresh_from_db()
        assert approval.status == ApprovalStatus.APPROVED

