"""Production reference runner over the published provider boundary.

The runner never reads provider ORM models or credentials.  A deployment (or
signed provider module) configures ``ProviderFactory`` with the published,
tenant-first configuration resolver and registers a resilient provider
adapter.  Missing pieces fail explicitly as capability-unavailable.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError

from .models import AgentExecution
from .providers.factory import get_provider_factory
from .services import AgentServiceError, UsageService


class PublishedProviderRunner:
    """Execute a closed chat task using one tenant-owned provider reference."""

    key = "published_provider"
    version = "1.0.0"

    def __call__(self, *, tenant_id: str, execution_id: str, task: Mapping[str, Any]) -> Mapping[str, Any]:
        tenant, execution_pk = UUID(tenant_id), UUID(execution_id)
        execution = AgentExecution.objects.select_related("agent").get(tenant_id=tenant, id=execution_pk)
        provider_config_id = execution.provider_config_id or execution.agent.provider_config_id
        if provider_config_id is None:
            raise AgentServiceError("PROVIDER_CONFIGURATION_REQUIRED", "The agent has no provider configuration.")
        allowed = {"messages", "temperature", "max_tokens", "stop_sequences"}
        unknown = set(task) - allowed
        if unknown:
            raise ValidationError({key: "Unknown runner task field." for key in sorted(unknown)})
        messages = task.get("messages")
        if not isinstance(messages, list) or not messages or len(messages) > 100:
            raise ValidationError({"messages": "Provide between 1 and 100 messages."})
        normalized: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, Mapping) or set(message) != {"role", "content"}:
                raise ValidationError({"messages": "Each message must contain only role and content."})
            role, content = message["role"], message["content"]
            if role not in {"system", "user", "assistant", "tool"} or not isinstance(content, str) or not content:
                raise ValidationError({"messages": "Each message requires a supported role and nonblank content."})
            normalized.append({"role": role, "content": content})
        resolved = get_provider_factory().resolve(tenant, provider_config_id)
        provider = resolved.unwrap()
        response = provider.call(
            normalized,
            temperature=task.get("temperature"),
            max_tokens=task.get("max_tokens"),
            stop_sequences=task.get("stop_sequences"),
        )
        UsageService.record_token_usage(
            tenant, execution.id, response.provider, response.model,
            response.usage.input_tokens, response.usage.output_tokens,
            {"pricing_version": provider.config.pricing_version},
        )
        pricing_status = "available"
        try:
            amount = Decimal(str(provider.get_cost(response.usage)))
            cost = UsageService.record_cost(
                tenant, amount, provider.config.pricing_version,
                agent_execution=execution, cost_type="token", provider=response.provider,
                currency="USD", metadata={},
            )
            if cost.status != "succeeded":
                pricing_status = "unavailable"
        except RuntimeError:
            pricing_status = "unavailable"
        return {
            "content": response.content,
            "provider": response.provider,
            "model": response.model,
            "finish_reason": response.finish_reason,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            "pricing_status": pricing_status,
            "runner_version": self.version,
        }


published_provider_runner = PublishedProviderRunner()

__all__ = ["PublishedProviderRunner", "published_provider_runner"]

