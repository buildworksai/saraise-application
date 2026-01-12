"""Tests for Token Service.

Task: 402.3 - Token Metering & Cost Attribution
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from ..models import Agent, AgentExecution, AgentIdentityType
from ..token_models import CostRecord, CostSummary, TokenUsage
from ..token_service import TokenService


@pytest.mark.django_db
class TestTokenService:
    """Test TokenService."""

    def test_record_token_usage(self) -> None:
        """Test recording token usage."""
        service = TokenService()

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

        usage = service.record_token_usage(
            tenant_id=tenant_id,
            agent_execution=execution,
            provider="openai",
            model="gpt-4",
            input_tokens=1000,
            output_tokens=500,
        )

        assert usage is not None
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 500
        assert usage.total_tokens == 1500

    def test_calculate_cost(self) -> None:
        """Test calculating cost from token usage."""
        service = TokenService()

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

        usage = service.record_token_usage(
            tenant_id=tenant_id,
            agent_execution=execution,
            provider="openai",
            model="gpt-4",
            input_tokens=1000,
            output_tokens=500,
        )

        cost = service.calculate_cost(usage)

        assert cost is not None
        assert cost.total_cost > 0
        assert cost.provider == "openai"
        assert cost.model == "gpt-4"

    def test_get_tenant_cost_summary(self) -> None:
        """Test getting tenant cost summary."""
        service = TokenService()

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

        # Record usage
        service.record_token_usage(
            tenant_id=tenant_id,
            agent_execution=execution,
            provider="openai",
            model="gpt-4",
            input_tokens=1000,
            output_tokens=500,
        )

        summary = service.get_tenant_cost_summary(
            tenant_id=tenant_id,
            start_date=timezone.now() - timedelta(days=30),
            end_date=timezone.now(),
        )

        assert summary is not None
        assert summary["total_cost"] > 0
        assert summary["tenant_id"] == tenant_id
        assert "cost_by_provider" in summary
        assert "cost_by_model" in summary

    def test_get_token_usage_by_agent(self) -> None:
        """Test getting token usage by agent."""
        service = TokenService()

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

        service.record_token_usage(
            tenant_id=tenant_id,
            agent_execution=execution,
            provider="openai",
            model="gpt-4",
            input_tokens=1000,
            output_tokens=500,
        )

        usage = service.get_token_usage_by_agent(
            tenant_id=tenant_id,
            agent_id=str(agent.id),
        )

        assert usage is not None
        assert usage["total_tokens"] == 1500
        assert usage["agent_id"] == str(agent.id)

    def test_get_token_usage_by_provider(self) -> None:
        """Test getting token usage by provider."""
        service = TokenService()

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

        service.record_token_usage(
            tenant_id=tenant_id,
            agent_execution=execution,
            provider="openai",
            model="gpt-4",
            input_tokens=1000,
            output_tokens=500,
        )

        usage = service.get_token_usage_by_provider(
            tenant_id=tenant_id,
            provider="openai",
        )

        assert usage is not None
        assert usage["total_tokens"] == 1500
        assert usage["provider"] == "openai"
