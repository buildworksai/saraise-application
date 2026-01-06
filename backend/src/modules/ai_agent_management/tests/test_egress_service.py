"""Tests for Egress Service.

Task: 402.1 - Egress Allowlisting & Secret Isolation
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from ..models import Agent, AgentExecution, AgentIdentityType
from ..egress_models import EgressRule, EgressRequest
from ..egress_service import EgressService


@pytest.mark.django_db
class TestEgressService:
    """Test EgressService."""

    def test_check_egress_allowed_with_rule(self) -> None:
        """Test checking egress allowed with matching rule."""
        service = EgressService()

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

        # Create allow rule
        EgressRule.objects.create(
            tenant_id=tenant_id,
            destination_pattern="api.example.com",
            protocol="https",
            port=443,
            is_allowed=True,
            is_active=True,
        )

        allowed, rule = service.check_egress_allowed(
            destination="https://api.example.com",
            tenant_id=tenant_id,
            agent_execution=execution,
        )

        assert allowed is True
        assert rule is not None

    def test_check_egress_denied_no_rule(self) -> None:
        """Test checking egress denied when no rule matches."""
        service = EgressService()

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

        allowed, rule = service.check_egress_allowed(
            destination="https://unauthorized.com",
            tenant_id=tenant_id,
            agent_execution=execution,
        )

        assert allowed is False
        assert rule is None

    def test_check_egress_denied_by_rule(self) -> None:
        """Test checking egress denied by explicit deny rule."""
        service = EgressService()

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

        # Create deny rule
        EgressRule.objects.create(
            tenant_id=tenant_id,
            destination_pattern="blocked.com",
            protocol="https",
            is_allowed=False,
            is_active=True,
        )

        allowed, rule = service.check_egress_allowed(
            destination="https://blocked.com",
            tenant_id=tenant_id,
            agent_execution=execution,
        )

        assert allowed is False
        assert rule is not None

    def test_create_egress_request(self) -> None:
        """Test creating egress request."""
        service = EgressService()

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

        request = service.create_egress_request(
            destination="https://api.example.com",
            tenant_id=tenant_id,
            agent_execution=execution,
            requested_by="user-1",
            justification="API access needed",
        )

        assert request is not None
        assert request.destination == "https://api.example.com"
        assert request.status == "pending"

    def test_get_egress_rules(self) -> None:
        """Test getting egress rules."""
        service = EgressService()

        tenant_id = "test-tenant-1"

        # Create rules
        EgressRule.objects.create(
            tenant_id=tenant_id,
            destination_pattern="api.example.com",
            protocol="https",
            is_allowed=True,
            is_active=True,
        )

        EgressRule.objects.create(
            tenant_id=tenant_id,
            destination_pattern="blocked.com",
            protocol="https",
            is_allowed=False,
            is_active=True,
        )

        rules = service.get_egress_rules(tenant_id=tenant_id)

        assert len(rules) >= 2

    def test_create_egress_rule(self) -> None:
        """Test creating egress rule."""
        service = EgressService()

        tenant_id = "test-tenant-1"

        rule = service.create_egress_rule(
            tenant_id=tenant_id,
            destination_pattern="api.example.com",
            protocol="https",
            port=443,
            is_allowed=True,
            description="Allow API access",
            created_by="user-1",
        )

        assert rule is not None
        assert rule.destination_pattern == "api.example.com"
        assert rule.is_allowed is True
        assert rule.is_active is True

    def test_update_egress_rule(self) -> None:
        """Test updating egress rule."""
        service = EgressService()

        tenant_id = "test-tenant-1"

        rule = EgressRule.objects.create(
            tenant_id=tenant_id,
            destination_pattern="api.example.com",
            protocol="https",
            is_allowed=True,
            is_active=True,
        )

        updated = service.update_egress_rule(
            rule_id=rule.id,
            tenant_id=tenant_id,
            is_allowed=False,
            updated_by="user-1",
        )

        assert updated.is_allowed is False

    def test_delete_egress_rule(self) -> None:
        """Test deleting egress rule."""
        service = EgressService()

        tenant_id = "test-tenant-1"

        rule = EgressRule.objects.create(
            tenant_id=tenant_id,
            destination_pattern="api.example.com",
            protocol="https",
            is_allowed=True,
            is_active=True,
        )

        service.delete_egress_rule(rule_id=rule.id, tenant_id=tenant_id)

        rule.refresh_from_db()
        assert rule.is_active is False

