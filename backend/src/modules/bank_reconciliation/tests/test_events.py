"""Outbox event contract tests."""

from uuid import uuid4

import pytest

from ..events import SCHEMA_VERSION, publish_domain_event


@pytest.mark.django_db
def test_event_envelope_is_versioned_and_tenant_bound() -> None:
    tenant, aggregate, actor = uuid4(), uuid4(), uuid4()
    event = publish_domain_event(
        tenant,
        "bank_reconciliation.account.created",
        "bank_account",
        aggregate,
        actor_id=actor,
        payload={"currency": "USD"},
        correlation_id="req-test",
    )
    assert event.tenant_id == tenant
    assert event.payload["schema_version"] == SCHEMA_VERSION
    assert event.payload["correlation_id"] == "req-test"
    assert event.payload["payload"] == {"currency": "USD"}


@pytest.mark.django_db
def test_event_rejects_sensitive_or_unknown_payload_before_write() -> None:
    with pytest.raises(ValueError, match="non-allowlisted"):
        publish_domain_event(
            uuid4(),
            "bank_reconciliation.account.created",
            "bank_account",
            uuid4(),
            actor_id=uuid4(),
            payload={"account_number": "123456789"},
        )
