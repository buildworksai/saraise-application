"""Unit contract tests for traceability capability projection."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from src.modules.blockchain_traceability.api import BlockchainTraceabilityConfigurationViewSet
from src.modules.blockchain_traceability.permissions import COMPLIANCE_FINALIZE, NETWORK_MANAGE


class _EntitlementResult:
    def __init__(self, entitled: bool) -> None:
        self.entitled = entitled


class _QuotaResult:
    def __init__(self, allowed: bool, remaining: int = 999) -> None:
        self.allowed = allowed
        self.remaining = remaining


class _PolicyEvaluator:
    def __init__(self, granted_permission: str) -> None:
        self.granted_permission = granted_permission

    def evaluate(self, tenant_id, identity, required_permission, *, request=None):
        del tenant_id, identity, request
        return required_permission == self.granted_permission


class _EntitlementService:
    def check(self, tenant_id, capability):
        del tenant_id, capability
        return _EntitlementResult(entitled=True)


class _QuotaService:
    def consume(self, tenant_id, resource, *, cost=1):
        del tenant_id, resource, cost
        return _QuotaResult(allowed=True)


def _capabilities_for(monkeypatch, granted_permission: str) -> dict[str, object]:
    from src.core.access import decision
    from src.modules.blockchain_traceability import api

    monkeypatch.setattr(
        api,
        "AccessDecisionPipeline",
        lambda: decision.AccessDecisionPipeline(
            policy_evaluator=_PolicyEvaluator(granted_permission),
            entitlement_service=_EntitlementService(),
            quota_service=_QuotaService(),
        ),
    )
    tenant_id = uuid4()
    view = BlockchainTraceabilityConfigurationViewSet()
    view.service = SimpleNamespace(
        document=lambda tenant_id, environment: {"tenant_id": str(tenant_id), "environment": environment},
    )
    request = SimpleNamespace(
        tenant_id=tenant_id,
        query_params={},
        user=SimpleNamespace(is_authenticated=True, pk=uuid4(), profile=SimpleNamespace(tenant_id=str(tenant_id))),
    )
    view.request = request

    return dict(view.capabilities(request).data)


def test_capabilities_expose_supersede_from_compliance_finalize_permission(monkeypatch) -> None:
    payload = _capabilities_for(monkeypatch, COMPLIANCE_FINALIZE)

    assert payload["can_mutate_resources"] is False
    assert payload["can_finalize_compliance_evidence"] is True
    assert payload["can_supersede_compliance_evidence"] is True


def test_capabilities_do_not_allow_supersede_from_network_manage_permission(monkeypatch) -> None:
    payload = _capabilities_for(monkeypatch, NETWORK_MANAGE)

    assert payload["can_mutate_resources"] is True
    assert payload["can_finalize_compliance_evidence"] is False
    assert payload["can_supersede_compliance_evidence"] is False
