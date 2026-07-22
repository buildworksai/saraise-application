"""Controlled policy dependency for module API integration tests."""

from __future__ import annotations

import uuid

import pytest

from src.core.access.decision import AccessDecision, AccessReasonCode


@pytest.fixture(autouse=True)
def configured_access_pipeline(monkeypatch):
    """Provide explicit policy/entitlement/quota approval in module tests."""

    def decide(self, tenant_id, identity, required_permission, **kwargs):
        del self, kwargs
        if not getattr(identity, "is_authenticated", False) or not required_permission or not tenant_id:
            return AccessDecision.deny(AccessReasonCode.DENY_DEFAULT, "Denied by test policy.")
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="Allowed by configured test policy.",
            tenant_id=uuid.UUID(str(tenant_id)),
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", decide)
