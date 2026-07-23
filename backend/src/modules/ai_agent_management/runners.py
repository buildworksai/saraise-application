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
from .providers.resilience import resilient_provider_call
from .services import AgentServiceError, ConfigurationService, UsageService, _correlation_uuid


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
        runner_configuration = ConfigurationService.resolve(tenant)["runner"]
        allowed = set(runner_configuration["allowed_task_fields"])
        unknown = set(task) - allowed
        if unknown:
            raise ValidationError({key: "Unknown runner task field." for key in sorted(unknown)})
        messages = task.get("messages")
        maximum_messages = int(runner_configuration["maximum_messages"])
        if not isinstance(messages, list) or not messages or len(messages) > maximum_messages:
            raise ValidationError({"messages": f"Provide between 1 and {maximum_messages} messages."})
        normalized: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, Mapping) or set(message) != {"role", "content"}:
                raise ValidationError({"messages": "Each message must contain only role and content."})
            role, content = message["role"], message["content"]
            if role not in set(runner_configuration["allowed_roles"]) or not isinstance(content, str) or not content:
                raise ValidationError({"messages": "Each message requires a supported role and nonblank content."})
            normalized.append({"role": role, "content": content})
        resolved = get_provider_factory().resolve(tenant, provider_config_id)
        provider = resolved.unwrap()
        response = resilient_provider_call(
            tenant,
            _correlation_uuid(),
            provider,
            lambda: provider.call(
                normalized,
                temperature=task.get("temperature"),
                max_tokens=task.get("max_tokens"),
                stop_sequences=task.get("stop_sequences"),
            ),
        )
        usage_evidence = response.metadata.get("usage_evidence", "provider_reported")
        pricing_status = "unavailable"
        if usage_evidence == "provider_reported":
            UsageService.record_token_usage(
                tenant, execution.id, response.provider, response.model,
                response.usage.input_tokens, response.usage.output_tokens,
                {"pricing_version": provider.config.pricing_version},
            )
            try:
                amount = Decimal(str(provider.get_cost(response.usage)))
                cost = UsageService.record_cost(
                    tenant, amount, provider.config.pricing_version,
                    agent_execution=execution, cost_type="token", provider=response.provider,
                    currency="USD", metadata={},
                )
                if cost.status == "succeeded":
                    pricing_status = "available"
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
            "usage_evidence": usage_evidence,
            "pricing_status": pricing_status,
            "runner_version": self.version,
        }


published_provider_runner = PublishedProviderRunner()

__all__ = ["PublishedProviderRunner", "published_provider_runner"]
