"""Service-layer behavior for declarative, idempotent BI definitions."""

from __future__ import annotations

import uuid

import pytest
from rest_framework.exceptions import ValidationError

from src.modules.business_intelligence.services import QueryService


def query_payload() -> dict[str, object]:
    return {
        "query_code": "EXECUTION_SUMMARY",
        "name": "Execution summary",
        "dataset_key": "business_intelligence.execution_audit",
        "dimensions": ["status"],
        "measures": [{"key": "execution_count"}],
        "row_limit": 100,
    }


@pytest.mark.django_db
def test_create_is_tenant_scoped_and_idempotent() -> None:
    tenant_id = uuid.uuid4()
    created = QueryService.create(tenant_id, "actor", query_payload(), "correlation", "create-key")
    replay = QueryService.create(tenant_id, "actor", query_payload(), "correlation", "create-key")
    assert replay.id == created.id
    assert created.tenant_id == tenant_id
    assert created.transition_history[0]["idempotency_key"] == "create-key"


@pytest.mark.django_db
def test_service_rejects_executable_tenant_input() -> None:
    payload = query_payload()
    payload["sql"] = "select 1"
    with pytest.raises(ValidationError):
        QueryService.create(uuid.uuid4(), "actor", payload, "correlation", "unsafe")


@pytest.mark.django_db
def test_published_definition_edit_returns_to_draft() -> None:
    tenant_id = uuid.uuid4()
    query = QueryService.create(tenant_id, "actor", query_payload(), "correlation", "create")
    query = QueryService.publish(tenant_id, query.id, "actor", 1, "correlation", "publish")
    updated = QueryService.update(
        tenant_id,
        query.id,
        "actor",
        query.version,
        {"name": "Changed"},
        "correlation",
        "update",
    )
    assert updated.state == "draft"
    assert updated.version == 3
