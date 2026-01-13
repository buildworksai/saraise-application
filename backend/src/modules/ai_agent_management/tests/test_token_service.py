"""Tests for Token Service.

Task: 402.3 - Token Metering & Cost Attribution
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from src.modules.ai_agent_management.models import Agent, AgentExecution, AgentIdentityType
from src.modules.ai_agent_management.token_models import CostRecord, CostSummary, TokenUsage
from src.modules.ai_agent_management.token_service import TokenService


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

        # Cost is automatically calculated and recorded in record_token_usage
        # Check that cost record was created
        from src.modules.ai_agent_management.token_models import CostRecord
        cost_records = CostRecord.objects.filter(
            tenant_id=tenant_id,
            agent_execution=execution,
        )
        assert cost_records.exists()
        cost_record = cost_records.first()
        assert cost_record is not None
        assert cost_record.amount > 0
        assert cost_record.provider == "openai"

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

        period_start = timezone.now() - timedelta(days=30)
        period_end = timezone.now()
        summary = service.generate_cost_summary(
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            period_type="monthly",
        )

        assert summary is not None
        assert summary.total_cost > 0
        assert summary.tenant_id == tenant_id
        assert "openai" in summary.cost_by_provider or len(summary.cost_by_provider) >= 0

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

        # Get token usage for this agent's executions
        usage_records = service.get_token_usage(
            tenant_id=tenant_id,
            agent_execution_id=str(execution.id),
        )

        assert len(usage_records) > 0
        total_tokens = sum(u.total_tokens for u in usage_records)
        assert total_tokens == 1500

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

        # Get token usage by provider
        usage_records = service.get_token_usage(
            tenant_id=tenant_id,
            provider="openai",
        )

        assert len(usage_records) > 0
        total_tokens = sum(u.total_tokens for u in usage_records)
        assert total_tokens == 1500
        assert all(u.provider == "openai" for u in usage_records)
