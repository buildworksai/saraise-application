import uuid

import pytest

from src.modules.performance_monitoring.extensions import MonitoringContribution, MonitoringExtensionRegistry
from src.modules.performance_monitoring.services import ConflictError


@pytest.mark.django_db
def test_paid_module_contribution_is_versioned_idempotent_and_tenant_safe():
    tenant, other = uuid.uuid4(), uuid.uuid4()
    contribution = MonitoringContribution(
        extension_key="healthcare.revenue_cycle",
        provider="saraise.healthcare",
        metric_namespaces=("healthcare.claims",),
        semantic_attributes={"claim.status": "string"},
        dashboard_templates=({"key": "claims-ops", "widgets": []},),
        slo_packs=({"key": "claim-latency", "objective": 99.9},),
        alert_rule_templates=({"key": "claim-errors", "condition": "above_threshold"},),
        drill_down_links=({"key": "claim", "path": "/paid/claims/{id}"},),
        event_consumers=("claims.submitted",),
    )
    registry = MonitoringExtensionRegistry()
    first = registry.register(tenant, contribution)
    assert registry.register(tenant, contribution).id == first.id
    assert registry.resolve(other).count() == 0
    changed = MonitoringContribution(**{**contribution.__dict__, "semantic_attributes": {"claim.id": "uuid"}})
    with pytest.raises(ConflictError):
        registry.register(tenant, changed)
