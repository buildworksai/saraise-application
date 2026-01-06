"""Token Metering & Cost Attribution Service.

Implements token counting, cost calculation, and tenant cost attribution.
Task: 402.3 - Token Metering & Cost Attribution
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from decimal import Decimal

from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Count, Q

from .models import AgentExecution
from .token_models import TokenUsage, CostRecord, CostSummary

logger = logging.getLogger(__name__)


# Default cost per token (USD) by provider and model
# These are placeholder values - should be updated from provider pricing
DEFAULT_TOKEN_COSTS: Dict[str, Dict[str, Dict[str, Decimal]]] = {
    "openai": {
        "gpt-4": {
            "input": Decimal("0.00003"),  # $0.03 per 1K tokens
            "output": Decimal("0.00006"),  # $0.06 per 1K tokens
        },
        "gpt-3.5-turbo": {
            "input": Decimal("0.0000015"),  # $0.0015 per 1K tokens
            "output": Decimal("0.000002"),  # $0.002 per 1K tokens
        },
    },
    "anthropic": {
        "claude-3-opus": {
            "input": Decimal("0.000015"),  # $0.015 per 1K tokens
            "output": Decimal("0.000075"),  # $0.075 per 1K tokens
        },
        "claude-3-sonnet": {
            "input": Decimal("0.000003"),  # $0.003 per 1K tokens
            "output": Decimal("0.000015"),  # $0.015 per 1K tokens
        },
    },
}


class TokenService:
    """Service for token metering and cost attribution."""

    def __init__(self) -> None:
        """Initialize token service."""
        self.token_costs = DEFAULT_TOKEN_COSTS.copy()

    def record_token_usage(
        self,
        tenant_id: str,
        agent_execution: AgentExecution,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TokenUsage:
        """Record token usage for an agent execution.

        Args:
            tenant_id: Tenant ID.
            agent_execution: Agent execution instance.
            provider: AI provider (openai, anthropic, etc.).
            model: Model name (gpt-4, claude-3, etc.).
            input_tokens: Input tokens consumed.
            output_tokens: Output tokens generated.
            metadata: Optional metadata.

        Returns:
            Created TokenUsage instance.
        """
        total_tokens = input_tokens + output_tokens

        token_usage = TokenUsage.objects.create(
            tenant_id=tenant_id,
            agent_execution=agent_execution,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            metadata=metadata or {},
        )

        logger.info(
            f"Recorded token usage: {total_tokens} tokens "
            f"({provider}/{model}) for execution {agent_execution.id}"
        )

        # Calculate and record cost
        cost = self._calculate_token_cost(
            provider, model, input_tokens, output_tokens
        )

        if cost > 0:
            self._record_cost(
                tenant_id=tenant_id,
                agent_execution=agent_execution,
                cost_type="token",
                provider=provider,
                amount=cost,
                metadata={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "model": model,
                },
            )

        return token_usage

    def get_token_usage(
        self,
        tenant_id: str,
        agent_execution_id: Optional[str] = None,
        provider: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[TokenUsage]:
        """Get token usage records.

        Args:
            tenant_id: Tenant ID.
            agent_execution_id: Optional agent execution ID filter.
            provider: Optional provider filter.
            start_time: Optional start time filter.
            end_time: Optional end time filter.

        Returns:
            List of TokenUsage instances.
        """
        query = TokenUsage.objects.filter(tenant_id=tenant_id)

        if agent_execution_id:
            query = query.filter(agent_execution_id=agent_execution_id)

        if provider:
            query = query.filter(provider=provider)

        if start_time:
            query = query.filter(usage_timestamp__gte=start_time)

        if end_time:
            query = query.filter(usage_timestamp__lte=end_time)

        return list(query.order_by("-usage_timestamp"))

    def get_total_tokens(
        self,
        tenant_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """Get total token count for tenant.

        Args:
            tenant_id: Tenant ID.
            start_time: Optional start time filter.
            end_time: Optional end time filter.

        Returns:
            Total token count.
        """
        query = TokenUsage.objects.filter(tenant_id=tenant_id)

        if start_time:
            query = query.filter(usage_timestamp__gte=start_time)

        if end_time:
            query = query.filter(usage_timestamp__lte=end_time)

        result = query.aggregate(total=Sum("total_tokens"))
        return result["total"] or 0

    def record_cost(
        self,
        tenant_id: str,
        cost_type: str,
        amount: Decimal,
        agent_execution: Optional[AgentExecution] = None,
        tool_invocation: Optional[Any] = None,
        module_name: Optional[str] = None,
        provider: Optional[str] = None,
        currency: str = "USD",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CostRecord:
        """Record a cost.

        Args:
            tenant_id: Tenant ID.
            cost_type: Type of cost (token, api_call, execution_time, etc.).
            amount: Cost amount.
            agent_execution: Optional agent execution instance.
            tool_invocation: Optional tool invocation instance.
            module_name: Optional module name.
            provider: Optional provider.
            currency: Currency code (default: USD).
            metadata: Optional metadata.

        Returns:
            Created CostRecord instance.
        """
        return self._record_cost(
            tenant_id=tenant_id,
            agent_execution=agent_execution,
            tool_invocation=tool_invocation,
            module_name=module_name,
            cost_type=cost_type,
            provider=provider,
            amount=amount,
            currency=currency,
            metadata=metadata,
        )

    def get_total_cost(
        self,
        tenant_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        cost_type: Optional[str] = None,
        module_name: Optional[str] = None,
    ) -> Decimal:
        """Get total cost for tenant.

        Args:
            tenant_id: Tenant ID.
            start_time: Optional start time filter.
            end_time: Optional end time filter.
            cost_type: Optional cost type filter.
            module_name: Optional module name filter.

        Returns:
            Total cost.
        """
        query = CostRecord.objects.filter(tenant_id=tenant_id)

        if start_time:
            query = query.filter(cost_timestamp__gte=start_time)

        if end_time:
            query = query.filter(cost_timestamp__lte=end_time)

        if cost_type:
            query = query.filter(cost_type=cost_type)

        if module_name:
            query = query.filter(module_name=module_name)

        result = query.aggregate(total=Sum("amount"))
        return Decimal(str(result["total"] or 0))

    def get_cost_breakdown(
        self,
        tenant_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get cost breakdown by type, module, and provider.

        Args:
            tenant_id: Tenant ID.
            start_time: Optional start time filter.
            end_time: Optional end time filter.

        Returns:
            Cost breakdown dictionary.
        """
        query = CostRecord.objects.filter(tenant_id=tenant_id)

        if start_time:
            query = query.filter(cost_timestamp__gte=start_time)

        if end_time:
            query = query.filter(cost_timestamp__lte=end_time)

        # Breakdown by type
        cost_by_type = {}
        for record in query.values("cost_type").annotate(
            total=Sum("amount")
        ):
            cost_by_type[record["cost_type"]] = float(record["total"])

        # Breakdown by module
        cost_by_module = {}
        for record in query.exclude(module_name__isnull=True).values(
            "module_name"
        ).annotate(total=Sum("amount")):
            cost_by_module[record["module_name"]] = float(record["total"])

        # Breakdown by provider
        cost_by_provider = {}
        for record in query.exclude(provider__isnull=True).values(
            "provider"
        ).annotate(total=Sum("amount")):
            cost_by_provider[record["provider"]] = float(record["total"])

        return {
            "by_type": cost_by_type,
            "by_module": cost_by_module,
            "by_provider": cost_by_provider,
        }

    def generate_cost_summary(
        self,
        tenant_id: str,
        period_start: datetime,
        period_end: datetime,
        period_type: str,
    ) -> CostSummary:
        """Generate cost summary for a period.

        Args:
            tenant_id: Tenant ID.
            period_start: Period start time.
            period_end: Period end time.
            period_type: Period type (hourly, daily, weekly, monthly).

        Returns:
            Created CostSummary instance.
        """
        # Get cost records for period
        cost_records = CostRecord.objects.filter(
            tenant_id=tenant_id,
            cost_timestamp__gte=period_start,
            cost_timestamp__lt=period_end,
        )

        # Calculate totals
        total_cost = cost_records.aggregate(total=Sum("amount"))["total"] or Decimal("0")

        # Breakdown by type
        cost_by_type = {}
        for record in cost_records.values("cost_type").annotate(
            total=Sum("amount")
        ):
            cost_by_type[record["cost_type"]] = float(record["total"])

        # Breakdown by module
        cost_by_module = {}
        for record in cost_records.exclude(module_name__isnull=True).values(
            "module_name"
        ).annotate(total=Sum("amount")):
            cost_by_module[record["module_name"]] = float(record["total"])

        # Breakdown by provider
        cost_by_provider = {}
        for record in cost_records.exclude(provider__isnull=True).values(
            "provider"
        ).annotate(total=Sum("amount")):
            cost_by_provider[record["provider"]] = float(record["total"])

        # Get token usage
        token_usage = TokenUsage.objects.filter(
            tenant_id=tenant_id,
            usage_timestamp__gte=period_start,
            usage_timestamp__lt=period_end,
        )
        total_tokens = token_usage.aggregate(total=Sum("total_tokens"))["total"] or 0

        # Get execution count
        executions = AgentExecution.objects.filter(
            tenant_id=tenant_id,
            created_at__gte=period_start,
            created_at__lt=period_end,
        )
        total_executions = executions.count()

        # Create or update summary
        summary, created = CostSummary.objects.update_or_create(
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            period_type=period_type,
            defaults={
                "total_cost": total_cost,
                "cost_by_type": cost_by_type,
                "cost_by_module": cost_by_module,
                "cost_by_provider": cost_by_provider,
                "total_tokens": total_tokens,
                "total_executions": total_executions,
            },
        )

        logger.info(
            f"Generated cost summary for tenant {tenant_id} "
            f"({period_type}): {total_cost} USD"
        )

        return summary

    def _calculate_token_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> Decimal:
        """Calculate token cost.

        Args:
            provider: AI provider.
            model: Model name.
            input_tokens: Input tokens.
            output_tokens: Output tokens.

        Returns:
            Calculated cost in USD.
        """
        # Get cost per token
        provider_costs = self.token_costs.get(provider, {})
        model_costs = provider_costs.get(model, {})

        input_cost_per_token = model_costs.get("input", Decimal("0"))
        output_cost_per_token = model_costs.get("output", Decimal("0"))

        # Calculate cost
        input_cost = Decimal(str(input_tokens)) * input_cost_per_token
        output_cost = Decimal(str(output_tokens)) * output_cost_per_token

        return input_cost + output_cost

    def _record_cost(
        self,
        tenant_id: str,
        cost_type: str,
        amount: Decimal,
        agent_execution: Optional[AgentExecution] = None,
        tool_invocation: Optional[Any] = None,
        module_name: Optional[str] = None,
        provider: Optional[str] = None,
        currency: str = "USD",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CostRecord:
        """Internal method to record cost.

        Args:
            tenant_id: Tenant ID.
            cost_type: Type of cost.
            amount: Cost amount.
            agent_execution: Optional agent execution.
            tool_invocation: Optional tool invocation.
            module_name: Optional module name.
            provider: Optional provider.
            currency: Currency code.
            metadata: Optional metadata.

        Returns:
            Created CostRecord instance.
        """
        cost_record = CostRecord.objects.create(
            tenant_id=tenant_id,
            agent_execution=agent_execution,
            tool_invocation=tool_invocation,
            module_name=module_name,
            cost_type=cost_type,
            provider=provider,
            amount=amount,
            currency=currency,
            metadata=metadata or {},
        )

        logger.debug(
            f"Recorded cost: {amount} {currency} ({cost_type}) "
            f"for tenant {tenant_id}"
        )

        return cost_record

    def update_token_costs(
        self, provider: str, model: str, input_cost: Decimal, output_cost: Decimal
    ) -> None:
        """Update token costs for a provider/model.

        Args:
            provider: AI provider.
            model: Model name.
            input_cost: Cost per input token.
            output_cost: Cost per output token.
        """
        if provider not in self.token_costs:
            self.token_costs[provider] = {}

        self.token_costs[provider][model] = {
            "input": input_cost,
            "output": output_cost,
        }

        logger.info(f"Updated token costs for {provider}/{model}")


# Global token service instance
token_service = TokenService()

