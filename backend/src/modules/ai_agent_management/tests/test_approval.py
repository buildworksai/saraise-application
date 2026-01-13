"""Tests for Approval Service.

Task: 401.3 - Human Approval Gates
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from src.modules.ai_agent_management.approval_models import ApprovalRequest, ApprovalStatus, SoDPolicy
from src.modules.ai_agent_management.approval_service import ApprovalService
from src.modules.ai_agent_management.models import Agent, AgentExecution, AgentIdentityType
from src.modules.ai_agent_management.tool_models import Tool
from src.modules.ai_agent_management.tool_registry import ToolSideEffectClass


@pytest.mark.django_db
class TestApprovalService:
    """Test approval service."""

    def test_requires_approval_data_mutation(self) -> None:
        """Test that data mutation tools require approval."""
        tenant_id = "test-tenant-1"
        tool = Tool.objects.create(
            tenant_id=tenant_id,
            name="create_invoice",
            owning_module="finance",
            version="1.0.0",
            description="Create invoice",
            required_permissions=["finance.invoice:create"],
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            side_effect_class=ToolSideEffectClass.DATA_MUTATION.value,
            registered_by="user-1",
        )

        service = ApprovalService()
        assert service.requires_approval(tool, tenant_id, "user-1", "user-1") is True

    def test_requires_approval_external_integration(self) -> None:
        """Test that external integration tools with write require approval."""
        tenant_id = "test-tenant-1"
        tool = Tool.objects.create(
            tenant_id=tenant_id,
            name="send_email",
            owning_module="integration",
            version="1.0.0",
            description="Send email",
            required_permissions=["integration.email:send"],
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            side_effect_class=ToolSideEffectClass.EXTERNAL_INTEGRATION.value,
            metadata={"write_capability": True},
            registered_by="user-1",
        )

        service = ApprovalService()
        assert service.requires_approval(tool, tenant_id, "user-1", "user-1") is True

    def test_create_approval_request(self) -> None:
        """Test creating approval request."""
        tenant_id = "test-tenant-1"
        agent = Agent.objects.create(
            tenant_id=tenant_id,
            name="Test Agent",
            description="Test agent",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id="user-1",
            session_id="session-1",
            framework="langgraph",
            config={},
            created_by="user-1",
        )

        execution = AgentExecution.objects.create(
            tenant_id=tenant_id,
            agent=agent,
            state="running",
            task_definition={"goal": "test"},
        )

        tool = Tool.objects.create(
            tenant_id=tenant_id,
            name="test_tool",
            owning_module="test_module",
            version="1.0.0",
            description="Test tool",
            required_permissions=["test.permission"],
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            side_effect_class=ToolSideEffectClass.DATA_MUTATION.value,
            registered_by="user-1",
        )

        service = ApprovalService()
        approval = service.create_approval_request(
            tool=tool,
            agent_execution=execution,
            tool_invocation=None,
            tenant_id=tenant_id,
            requested_by="user-1",
            requested_for="user-1",
            tool_input={"input": "test"},
            justification="Test approval",
        )

        assert approval is not None
        assert approval.status == ApprovalStatus.PENDING
        assert approval.tool_id == tool.id
        assert approval.agent_execution_id == execution.id
        assert approval.expires_at is not None

    def test_approve_request(self) -> None:
        """Test approving request."""
        tenant_id = "test-tenant-1"
        agent = Agent.objects.create(
            tenant_id=tenant_id,
            name="Test Agent",
            description="Test agent",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id="user-1",
            session_id="session-1",
            framework="langgraph",
            config={},
            created_by="user-1",
        )

        execution = AgentExecution.objects.create(
            tenant_id=tenant_id,
            agent=agent,
            state="running",
            task_definition={"goal": "test"},
        )

        tool = Tool.objects.create(
            tenant_id=tenant_id,
            name="test_tool",
            owning_module="test_module",
            version="1.0.0",
            description="Test tool",
            required_permissions=["test.permission"],
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            side_effect_class=ToolSideEffectClass.DATA_MUTATION.value,
            registered_by="user-1",
        )

        service = ApprovalService()
        approval = service.create_approval_request(
            tool=tool,
            agent_execution=execution,
            tool_invocation=None,
            tenant_id=tenant_id,
            requested_by="user-1",
            requested_for="user-1",
            tool_input={"input": "test"},
        )

        approved = service.approve_request(approval.id, tenant_id, "approver-1", "Approved")

        assert approved.status == ApprovalStatus.APPROVED
        assert approved.approver_id == "approver-1"
        assert approved.decided_at is not None

    def test_reject_request(self) -> None:
        """Test rejecting request."""
        tenant_id = "test-tenant-1"
        agent = Agent.objects.create(
            tenant_id=tenant_id,
            name="Test Agent",
            description="Test agent",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id="user-1",
            session_id="session-1",
            framework="langgraph",
            config={},
            created_by="user-1",
        )

        execution = AgentExecution.objects.create(
            tenant_id=tenant_id,
            agent=agent,
            state="running",
            task_definition={"goal": "test"},
        )

        tool = Tool.objects.create(
            tenant_id=tenant_id,
            name="test_tool",
            owning_module="test_module",
            version="1.0.0",
            description="Test tool",
            required_permissions=["test.permission"],
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            side_effect_class=ToolSideEffectClass.DATA_MUTATION.value,
            registered_by="user-1",
        )

        service = ApprovalService()
        approval = service.create_approval_request(
            tool=tool,
            agent_execution=execution,
            tool_invocation=None,
            tenant_id=tenant_id,
            requested_by="user-1",
            requested_for="user-1",
            tool_input={"input": "test"},
        )

        rejected = service.reject_request(approval.id, tenant_id, "approver-1", "Not approved")

        assert rejected.status == ApprovalStatus.REJECTED
        assert rejected.approver_id == "approver-1"
        assert rejected.rejection_reason == "Not approved"
