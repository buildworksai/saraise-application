"""
Tenant Isolation Tests for AI Agent Management

CRITICAL: These tests verify that tenants cannot access each other's data.
This is the PRIMARY security mechanism for multi-tenant isolation.

Reference: saraise-documentation/rules/compliance-enforcement.md
Rule: ALL tenant-scoped queries MUST filter by tenant_id
"""

import pytest
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
import uuid
from datetime import timedelta

from ..models import (
    Agent,
    AgentExecution,
    AgentSchedulerTask,
    AgentLifecycleState,
    AgentIdentityType,
)
from ..approval_models import ApprovalRequest, SoDPolicy, SoDViolation, ApprovalStatus
from ..quota_models import TenantQuota, QuotaUsage, QuotaType, QuotaPeriod
from ..tool_models import Tool, ToolInvocation

User = get_user_model()


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def tenant_a_user(db):
    """Create user for tenant A."""
    from src.core.user_models import UserProfile
    from unittest.mock import patch

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_a",
        email="usera@example.com",
        password="testpass123",
    )
    # Create UserProfile with tenant_id (skip tenant validation for tests)
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = "tenant_admin"
            profile.save()
    # Force reload profile
    user = User.objects.get(pk=user.pk)
    return user


@pytest.fixture
def tenant_b_user(db):
    """Create user for tenant B."""
    from src.core.user_models import UserProfile
    from unittest.mock import patch

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_b",
        email="userb@example.com",
        password="testpass123",
    )
    # Create UserProfile with tenant_id (skip tenant validation for tests)
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = "tenant_admin"
            profile.save()
    # Force reload profile
    user = User.objects.get(pk=user.pk)
    return user


@pytest.mark.django_db
class TestAgentTenantIsolation:
    """
    CRITICAL: Tenant isolation tests for Agent model.
    These tests verify that tenants cannot access each other's agents.
    """

    def test_user_cannot_list_other_tenant_agents(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User sees only their tenant's agents in list."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create agent for tenant A
        agent_a = Agent.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Agent",
            description="Agent for tenant A",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id=str(tenant_a_user.id),
            framework="langgraph",
            config={},
            created_by=str(tenant_a_user.id),
        )

        # Create agent for tenant B
        agent_b = Agent.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Agent",
            description="Agent for tenant B",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id=str(tenant_b_user.id),
            framework="langgraph",
            config={},
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/ai-agents/agents/")

        assert response.status_code == status.HTTP_200_OK
        data = (
            response.data
            if isinstance(response.data, list)
            else response.data.get("results", [])
        )
        agent_ids = [a["id"] for a in data]

        # User A should see tenant A's agent, but NOT tenant B's agent
        assert agent_a.id in agent_ids
        assert agent_b.id not in agent_ids

    def test_user_cannot_access_other_tenant_agent(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User cannot GET other tenant's agent by ID."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create agent for tenant B
        other_agent = Agent.objects.create(
            tenant_id=tenant_b_id,
            name="Other Tenant Agent",
            description="Agent for tenant B",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id=str(tenant_b_user.id),
            framework="langgraph",
            config={},
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get(f"/api/v1/ai-agents/agents/{other_agent.id}/")

        # MUST return 404 (not 403) to hide existence
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_update_other_tenant_agent(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User cannot PUT/PATCH other tenant's agent."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create agent for tenant B
        other_agent = Agent.objects.create(
            tenant_id=tenant_b_id,
            name="Original Name",
            description="Original description",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id=str(tenant_b_user.id),
            framework="langgraph",
            config={},
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.patch(
            f"/api/v1/ai-agents/agents/{other_agent.id}/",
            {"name": "Hacked Name"},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify data unchanged
        other_agent.refresh_from_db()
        assert other_agent.name == "Original Name"

    def test_user_cannot_delete_other_tenant_agent(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User cannot DELETE other tenant's agent."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create agent for tenant B
        other_agent = Agent.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Agent",
            description="Agent for tenant B",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id=str(tenant_b_user.id),
            framework="langgraph",
            config={},
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.delete(f"/api/v1/ai-agents/agents/{other_agent.id}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify agent still exists
        assert Agent.objects.filter(id=other_agent.id).exists()

    def test_user_cannot_execute_other_tenant_agent(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User cannot execute other tenant's agent."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create agent for tenant B
        other_agent = Agent.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Agent",
            description="Agent for tenant B",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id=str(tenant_b_user.id),
            framework="langgraph",
            config={},
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.post(
            f"/api/v1/ai-agents/agents/{other_agent.id}/execute/",
            {"task_definition": {"goal": "test"}},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestAgentExecutionTenantIsolation:
    """
    CRITICAL: Tenant isolation tests for AgentExecution model.
    """

    def test_user_cannot_list_other_tenant_executions(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User sees only their tenant's executions."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create agents for each tenant
        agent_a = Agent.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Agent",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id=str(tenant_a_user.id),
            framework="langgraph",
            config={},
            created_by=str(tenant_a_user.id),
        )

        agent_b = Agent.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Agent",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id=str(tenant_b_user.id),
            framework="langgraph",
            config={},
            created_by=str(tenant_b_user.id),
        )

        # Create executions
        execution_a = AgentExecution.objects.create(
            tenant_id=tenant_a_id,
            agent=agent_a,
            state=AgentLifecycleState.RUNNING,
            task_definition={"goal": "test"},
        )

        execution_b = AgentExecution.objects.create(
            tenant_id=tenant_b_id,
            agent=agent_b,
            state=AgentLifecycleState.RUNNING,
            task_definition={"goal": "test"},
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/ai-agents/executions/")

        assert response.status_code == status.HTTP_200_OK
        data = (
            response.data
            if isinstance(response.data, list)
            else response.data.get("results", [])
        )
        execution_ids = [e["id"] for e in data]

        assert execution_a.id in execution_ids
        assert execution_b.id not in execution_ids

    def test_user_cannot_access_other_tenant_execution(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User cannot GET other tenant's execution."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_b_id = get_user_tenant_id(tenant_b_user)

        agent_b = Agent.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Agent",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id=str(tenant_b_user.id),
            framework="langgraph",
            config={},
            created_by=str(tenant_b_user.id),
        )

        other_execution = AgentExecution.objects.create(
            tenant_id=tenant_b_id,
            agent=agent_b,
            state=AgentLifecycleState.RUNNING,
            task_definition={"goal": "test"},
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get(
            f"/api/v1/ai-agents/executions/{other_execution.id}/"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestToolTenantIsolation:
    """
    CRITICAL: Tenant isolation tests for Tool model.
    """

    def test_user_cannot_list_other_tenant_tools(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User sees only their tenant's tools."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create tools for each tenant
        tool_a = Tool.objects.create(
            tenant_id=tenant_a_id,
            name="tenant_a_tool",
            owning_module="test_module",
            required_permissions=["test.permission"],
            input_schema={},
            output_schema={},
            side_effect_class="read",
            registered_by=str(tenant_a_user.id),
        )

        tool_b = Tool.objects.create(
            tenant_id=tenant_b_id,
            name="tenant_b_tool",
            owning_module="test_module",
            required_permissions=["test.permission"],
            input_schema={},
            output_schema={},
            side_effect_class="read",
            registered_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/ai-agents/tools/")

        assert response.status_code == status.HTTP_200_OK
        data = (
            response.data
            if isinstance(response.data, list)
            else response.data.get("results", [])
        )
        tool_ids = [t["id"] for t in data]

        assert tool_a.id in tool_ids
        assert tool_b.id not in tool_ids

    def test_user_cannot_access_other_tenant_tool(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User cannot GET other tenant's tool."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_b_id = get_user_tenant_id(tenant_b_user)

        other_tool = Tool.objects.create(
            tenant_id=tenant_b_id,
            name="other_tool",
            owning_module="test_module",
            required_permissions=["test.permission"],
            input_schema={},
            output_schema={},
            side_effect_class="read",
            registered_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get(f"/api/v1/ai-agents/tools/{other_tool.id}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_update_other_tenant_tool(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User cannot UPDATE other tenant's tool."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_b_id = get_user_tenant_id(tenant_b_user)

        other_tool = Tool.objects.create(
            tenant_id=tenant_b_id,
            name="original_tool",
            owning_module="test_module",
            required_permissions=["test.permission"],
            input_schema={},
            output_schema={},
            side_effect_class="read",
            registered_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.patch(
            f"/api/v1/ai-agents/tools/{other_tool.id}/",
            {"name": "hacked_tool"},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify data unchanged
        other_tool.refresh_from_db()
        assert other_tool.name == "original_tool"

    def test_user_cannot_delete_other_tenant_tool(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User cannot DELETE other tenant's tool."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_b_id = get_user_tenant_id(tenant_b_user)

        other_tool = Tool.objects.create(
            tenant_id=tenant_b_id,
            name="tenant_b_tool",
            owning_module="test_module",
            required_permissions=["test.permission"],
            input_schema={},
            output_schema={},
            side_effect_class="read",
            registered_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.delete(f"/api/v1/ai-agents/tools/{other_tool.id}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify tool still exists
        assert Tool.objects.filter(id=other_tool.id).exists()


@pytest.mark.django_db
class TestApprovalRequestTenantIsolation:
    """
    CRITICAL: Tenant isolation tests for ApprovalRequest model.
    """

    def test_user_cannot_list_other_tenant_approvals(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User sees only their tenant's approval requests."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create agents and tools for each tenant
        agent_a = Agent.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Agent",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id=str(tenant_a_user.id),
            framework="langgraph",
            config={},
            created_by=str(tenant_a_user.id),
        )

        agent_b = Agent.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Agent",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id=str(tenant_b_user.id),
            framework="langgraph",
            config={},
            created_by=str(tenant_b_user.id),
        )

        execution_a = AgentExecution.objects.create(
            tenant_id=tenant_a_id,
            agent=agent_a,
            state=AgentLifecycleState.RUNNING,
            task_definition={},
        )

        execution_b = AgentExecution.objects.create(
            tenant_id=tenant_b_id,
            agent=agent_b,
            state=AgentLifecycleState.RUNNING,
            task_definition={},
        )

        tool_a = Tool.objects.create(
            tenant_id=tenant_a_id,
            name="tool_a",
            owning_module="test",
            required_permissions=[],
            input_schema={},
            output_schema={},
            side_effect_class="write",
            registered_by=str(tenant_a_user.id),
        )

        tool_b = Tool.objects.create(
            tenant_id=tenant_b_id,
            name="tool_b",
            owning_module="test",
            required_permissions=[],
            input_schema={},
            output_schema={},
            side_effect_class="write",
            registered_by=str(tenant_b_user.id),
        )

        # Create approval requests
        approval_a = ApprovalRequest.objects.create(
            tenant_id=tenant_a_id,
            tool=tool_a,
            agent_execution=execution_a,
            requested_by=str(tenant_a_user.id),
            requested_for=str(tenant_a_user.id),
            status=ApprovalStatus.PENDING,
            tool_input={},
        )

        approval_b = ApprovalRequest.objects.create(
            tenant_id=tenant_b_id,
            tool=tool_b,
            agent_execution=execution_b,
            requested_by=str(tenant_b_user.id),
            requested_for=str(tenant_b_user.id),
            status=ApprovalStatus.PENDING,
            tool_input={},
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/ai-agents/approvals/")

        assert response.status_code == status.HTTP_200_OK
        data = (
            response.data
            if isinstance(response.data, list)
            else response.data.get("results", [])
        )
        approval_ids = [a["id"] for a in data]

        assert approval_a.id in approval_ids
        assert approval_b.id not in approval_ids

    def test_user_cannot_approve_other_tenant_request(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User cannot approve other tenant's approval request."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_b_id = get_user_tenant_id(tenant_b_user)

        agent_b = Agent.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Agent",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id=str(tenant_b_user.id),
            framework="langgraph",
            config={},
            created_by=str(tenant_b_user.id),
        )

        execution_b = AgentExecution.objects.create(
            tenant_id=tenant_b_id,
            agent=agent_b,
            state=AgentLifecycleState.RUNNING,
            task_definition={},
        )

        tool_b = Tool.objects.create(
            tenant_id=tenant_b_id,
            name="tool_b",
            owning_module="test",
            required_permissions=[],
            input_schema={},
            output_schema={},
            side_effect_class="write",
            registered_by=str(tenant_b_user.id),
        )

        other_approval = ApprovalRequest.objects.create(
            tenant_id=tenant_b_id,
            tool=tool_b,
            agent_execution=execution_b,
            requested_by=str(tenant_b_user.id),
            requested_for=str(tenant_b_user.id),
            status=ApprovalStatus.PENDING,
            tool_input={},
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.post(
            f"/api/v1/ai-agents/approvals/{other_approval.id}/approve/"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify approval unchanged
        other_approval.refresh_from_db()
        assert other_approval.status == ApprovalStatus.PENDING


@pytest.mark.django_db
class TestSoDPolicyTenantIsolation:
    """
    CRITICAL: Tenant isolation tests for SoDPolicy model.
    """

    def test_user_cannot_list_other_tenant_sod_policies(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User sees only their tenant's SoD policies."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create SoD policies
        policy_a = SoDPolicy.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Policy",
            description="Policy for tenant A",
            action_1="action1",
            action_2="action2",
            created_by=str(tenant_a_user.id),
        )

        policy_b = SoDPolicy.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Policy",
            description="Policy for tenant B",
            action_1="action1",
            action_2="action2",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/ai-agents/sod-policies/")

        assert response.status_code == status.HTTP_200_OK
        data = (
            response.data
            if isinstance(response.data, list)
            else response.data.get("results", [])
        )
        policy_ids = [p["id"] for p in data]

        assert policy_a.id in policy_ids
        assert policy_b.id not in policy_ids

    def test_user_cannot_access_other_tenant_sod_policy(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User cannot GET other tenant's SoD policy."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_b_id = get_user_tenant_id(tenant_b_user)

        other_policy = SoDPolicy.objects.create(
            tenant_id=tenant_b_id,
            name="Other Policy",
            description="Policy for tenant B",
            action_1="action1",
            action_2="action2",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get(
            f"/api/v1/ai-agents/sod-policies/{other_policy.id}/"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_update_other_tenant_sod_policy(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User cannot UPDATE other tenant's SoD policy."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_b_id = get_user_tenant_id(tenant_b_user)

        other_policy = SoDPolicy.objects.create(
            tenant_id=tenant_b_id,
            name="Original Policy",
            description="Original description",
            action_1="action1",
            action_2="action2",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.patch(
            f"/api/v1/ai-agents/sod-policies/{other_policy.id}/",
            {"name": "Hacked Policy"},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify data unchanged
        other_policy.refresh_from_db()
        assert other_policy.name == "Original Policy"

    def test_user_cannot_delete_other_tenant_sod_policy(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User cannot DELETE other tenant's SoD policy."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_b_id = get_user_tenant_id(tenant_b_user)

        other_policy = SoDPolicy.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Policy",
            description="Policy for tenant B",
            action_1="action1",
            action_2="action2",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.delete(
            f"/api/v1/ai-agents/sod-policies/{other_policy.id}/"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify policy still exists
        assert SoDPolicy.objects.filter(id=other_policy.id).exists()


@pytest.mark.django_db
class TestQuotaTenantIsolation:
    """
    CRITICAL: Tenant isolation tests for TenantQuota and QuotaUsage models.
    """

    def test_user_cannot_list_other_tenant_quotas(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User sees only their tenant's quotas."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create quotas
        quota_a = TenantQuota.objects.create(
            tenant_id=tenant_a_id,
            quota_type=QuotaType.REQUEST_COUNT,
            period=QuotaPeriod.DAILY,
            limit_value=100,
            reset_at=timezone.now() + timedelta(days=1),
            is_active=True,
        )

        quota_b = TenantQuota.objects.create(
            tenant_id=tenant_b_id,
            quota_type=QuotaType.REQUEST_COUNT,
            period=QuotaPeriod.DAILY,
            limit_value=200,
            reset_at=timezone.now() + timedelta(days=1),
            is_active=True,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/ai-agents/quotas/")

        assert response.status_code == status.HTTP_200_OK
        data = (
            response.data
            if isinstance(response.data, list)
            else response.data.get("results", [])
        )
        quota_ids = [q["id"] for q in data]

        assert quota_a.id in quota_ids
        assert quota_b.id not in quota_ids

    def test_user_cannot_access_other_tenant_quota(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User cannot GET other tenant's quota."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_b_id = get_user_tenant_id(tenant_b_user)

        other_quota = TenantQuota.objects.create(
            tenant_id=tenant_b_id,
            quota_type=QuotaType.REQUEST_COUNT,
            period=QuotaPeriod.DAILY,
            limit_value=200,
            reset_at=timezone.now() + timedelta(days=1),
            is_active=True,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get(f"/api/v1/ai-agents/quotas/{other_quota.id}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND

