"""Tests for Audit Service.

Task: 403.1 - AI Audit Trail
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from src.modules.ai_agent_management.audit_models import AuditEvent, AuditEventType, AuditTrail
from src.modules.ai_agent_management.audit_service import AuditService
from src.modules.ai_agent_management.models import Agent, AgentExecution, AgentIdentityType


@pytest.mark.django_db
class TestAuditService:
    """Test AuditService."""

    def test_create_audit_trail(self) -> None:
        """Test creating audit trail."""
        service = AuditService()

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

        trail = service.create_audit_trail(
            tenant_id=tenant_id,
            request_id="req-123",
            agent_execution=execution,
            initiating_principal="user-1",
        )

        assert trail is not None
        assert trail.tenant_id == tenant_id
        assert trail.request_id == "req-123"
        assert trail.agent_execution_id == execution.id

    def test_add_audit_event(self) -> None:
        """Test adding audit event."""
        service = AuditService()

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

        trail = AuditTrail.objects.create(
            tenant_id=tenant_id,
            request_id="req-123",
            agent_execution=execution,
            initiating_principal="user-1",
        )

        event = service.record_event(
            tenant_id=tenant_id,
            event_type=AuditEventType.TOOL_INVOKED,
            initiating_principal="user-1",
            subject_id="user-1",
            outcome="success",
            agent_execution=execution,
            request_id="req-123",
            outcome_details={"tool": "create_invoice", "input": {"amount": 100}},
        )

        assert event is not None
        assert event.event_type == AuditEventType.TOOL_INVOKED
        assert event.outcome_details.get("tool") == "create_invoice"

    def test_get_audit_trail(self) -> None:
        """Test getting audit trail."""
        service = AuditService()

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

        trail = AuditTrail.objects.create(
            tenant_id=tenant_id,
            request_id="req-123",
            agent_execution=execution,
            initiating_principal="user-1",
        )

        retrieved = service.get_audit_trail(request_id="req-123", tenant_id=tenant_id)

        assert retrieved is not None
        assert retrieved.id == trail.id
        assert retrieved.request_id == "req-123"

    def test_get_audit_trail_by_request_id(self) -> None:
        """Test getting audit trail by request ID."""
        service = AuditService()

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

        AuditTrail.objects.create(
            tenant_id=tenant_id,
            request_id="req-123",
            agent_execution=execution,
            initiating_principal="user-1",
        )

        retrieved = service.get_audit_trail(request_id="req-123", tenant_id=tenant_id)

        assert retrieved is not None
        assert retrieved.request_id == "req-123"

    def test_get_audit_events(self) -> None:
        """Test getting audit events."""
        service = AuditService()

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

        trail = AuditTrail.objects.create(
            tenant_id=tenant_id,
            request_id="req-123",
            agent_execution=execution,
            initiating_principal="user-1",
        )

        # Create events using service
        service.record_event(
            tenant_id=tenant_id,
            event_type=AuditEventType.TOOL_INVOKED,
            initiating_principal="user-1",
            subject_id="user-1",
            outcome="success",
            agent_execution=execution,
            request_id="req-123",
            outcome_details={"tool": "tool1"},
        )

        service.record_event(
            tenant_id=tenant_id,
            event_type="tool_result",
            initiating_principal="user-1",
            subject_id="user-1",
            outcome="success",
            agent_execution=execution,
            request_id="req-123",
            outcome_details={"result": "success"},
        )

        events = service.query_audit_events(tenant_id=tenant_id, limit=100)

        assert len(events) >= 2
        assert all(e.tenant_id == tenant_id for e in events)

    def test_search_audit_trails(self) -> None:
        """Test searching audit trails."""
        service = AuditService()

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

        AuditTrail.objects.create(
            tenant_id=tenant_id,
            request_id="req-123",
            agent_execution=execution,
            initiating_principal="user-1",
        )

        result = service.get_audit_trail(request_id="req-123", tenant_id=tenant_id)

        assert result is not None
        assert result.request_id == "req-123"
