"""Shared fixtures for the human-resources contract suite.

Authentication always traverses Django's real session and CSRF stack.  The
authoritative policy dependency is replaced with an explicit allow decision
only in tests; entitlement and quota remain real persisted projections.
"""

import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from rest_framework.test import APIClient

from src.core.access.decision import HttpPolicyEvaluator, PolicyEvaluation
from src.core.access.entitlements import Entitlement, Quota

from ..permissions import ACTION_ACCESS

pytest_plugins = ["src.core.testing.factories"]


@pytest.fixture(autouse=True)
def idempotent_hr_test_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give existing mutation scenarios a unique command key unless they specify one."""

    original_generic = APIClient.generic

    def generic(
        client: APIClient, method: str, path: str, data: Any = "", content_type: Any = None, **extra: Any
    ) -> Any:
        if method.upper() in {"POST", "PATCH", "DELETE"} and "HTTP_IDEMPOTENCY_KEY" not in extra:
            decoded: object = data
            if isinstance(data, bytes):
                try:
                    decoded = json.loads(data.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    decoded = {}
            body = decoded if isinstance(decoded, dict) else {}
            extra["HTTP_IDEMPOTENCY_KEY"] = str(body.get("idempotency_key") or body.get("transition_key") or uuid4())
        return original_generic(client, method, path, data, content_type, **extra)

    monkeypatch.setattr(APIClient, "generic", generic)


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
            requirement.quota_resource for action_map in ACTION_ACCESS.values() for requirement in action_map.values()
        }
        for resource in resources:
            Quota.objects.update_or_create(
                tenant_id=tenant_id,
                resource=resource,
                defaults={"limit": 10_000, "remaining": 10_000},
            )
        return tenant_id

    return grant
