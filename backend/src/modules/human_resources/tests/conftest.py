"""Shared fixtures for the human-resources contract suite.

Authentication always traverses Django's real session and CSRF stack.  The
authoritative policy dependency is replaced with an explicit allow decision
only in tests; entitlement and quota remain real persisted projections.
"""

from typing import Any
from uuid import UUID

import pytest

from src.core.access.decision import HttpPolicyEvaluator, PolicyEvaluation
from src.core.access.entitlements import Entitlement, Quota

from ..permissions import ACTION_ACCESS

pytest_plugins = ["src.core.testing.factories"]


@pytest.fixture
def allow_hr_access(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Return a helper that grants the complete governed HR surface to a tenant."""

    monkeypatch.setattr(
        HttpPolicyEvaluator,
        "evaluate",
        lambda self, tenant_id, identity, required_permission, request=None: PolicyEvaluation(
            allowed=True,
            reason_codes=("TEST_POLICY_ALLOW",),
            applied_policies=("human_resources_test_policy",),
        ),
    )

    def grant(raw_tenant_id: object) -> UUID:
        tenant_id = raw_tenant_id if isinstance(raw_tenant_id, UUID) else UUID(str(raw_tenant_id))
        Entitlement.objects.update_or_create(
            tenant_id=tenant_id,
            capability="human_resources",
            defaults={"enabled": True},
        )
        resources = {
            requirement.quota_resource
            for action_map in ACTION_ACCESS.values()
            for requirement in action_map.values()
        }
        for resource in resources:
            Quota.objects.update_or_create(
                tenant_id=tenant_id,
                resource=resource,
                defaults={"limit": 10_000, "remaining": 10_000},
            )
        return tenant_id

    return grant
