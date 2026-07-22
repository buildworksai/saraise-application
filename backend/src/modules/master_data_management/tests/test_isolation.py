"""Production-faithful cross-tenant HTTP, worker, outbox, and RLS tests."""

from __future__ import annotations

import uuid
from typing import Any, Mapping

import pytest
from django.db import connection

from src.core.access.decision import AccessDecision, AccessDecisionPipeline, AccessReasonCode
from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.tenancy import tenant_context
from src.core.testing import TenantIsolationContract
from src.modules.master_data_management.models import (
    DataQualityRule,
    MasterDataEntity,
    MasterEntityType,
    MatchingRule,
)

from .factories import (
    actor_id,
    make_candidate,
    make_entity,
    make_entity_type,
    make_issue,
    make_matching_rule,
    make_merge,
    make_quality_rule,
)

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db

BASE = "/api/v2/master-data-management"


@pytest.fixture(autouse=True)
def allow_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def decide(
        self: AccessDecisionPipeline,
        tenant_id: object,
        identity: object,
        required_permission: str,
        **kwargs: object,
    ) -> AccessDecision:
        del self, identity, required_permission, kwargs
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="isolation test access projection",
            tenant_id=uuid.UUID(str(tenant_id)),
        )

    monkeypatch.setattr(AccessDecisionPipeline, "decide", decide)


class V2IsolationContract(TenantIsolationContract):
    """Tighten core contract denial and extract governed v2 list rows."""

    read_denial_statuses = frozenset({404})

    def get_list_items(self, response: Any) -> list[Mapping[str, Any]]:
        payload = response.json()
        assert set(payload) == {"data", "meta"}
        assert payload["meta"]["correlation_id"]
        assert isinstance(payload["data"], list)
        return payload["data"]

    def _request(self, method: str, url: str, data: Any) -> Any:
        if method.lower() == "delete" and data is None:
            row = self.get_tenant_b_row()
            data = {"reason": "Cross-tenant isolation attempt", "idempotency_key": f"isolation-delete-{row.pk}"}
            if isinstance(row, MasterDataEntity):
                data["expected_version"] = row.version
        return super()._request(method, url, data)


class TestMasterEntityTypeIsolation(V2IsolationContract):
    model = MasterEntityType
    list_url = f"{BASE}/entity-types/"
    detail_url_template = f"{BASE}/entity-types/{{pk}}/"

    @pytest.fixture(autouse=True)
    def isolation_context(
        self,
        authenticated_tenant_a_client: Any,
        tenant_a: Any,
        tenant_b: Any,
    ) -> None:
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = make_entity_type(tenant_a.id, key="customer")
        self.tenant_b_row = make_entity_type(tenant_b.id, key="customer")

    def get_create_payload(self) -> dict[str, object]:
        return {
            "key": "location",
            "display_name": "Location",
            "json_schema": {"type": "object", "properties": {}},
            "idempotency_key": "spoof-type-create",
        }

    def get_update_payload(self) -> dict[str, object]:
        return {
            "expected_schema_version": self.tenant_b_row.schema_version,
            "display_name": "Spoofed type",
            "idempotency_key": "spoof-type-update",
        }

    def test_cross_tenant_delete_is_denied_and_unchanged(self) -> None:
        before = self._row_snapshot(self.tenant_b_row)
        response = self.client.post(
            f"{BASE}/entity-types/{self.tenant_b_row.id}/deactivate/",
            {"reason": "Spoof", "idempotency_key": "spoof-type-deactivate"},
            format="json",
        )
        assert response.status_code == 404
        assert self._row_snapshot(self.tenant_b_row) == before


class TestMasterEntityIsolation(V2IsolationContract):
    model = MasterDataEntity
    list_url = f"{BASE}/entities/"
    detail_url_template = f"{BASE}/entities/{{pk}}/"

    @pytest.fixture(autouse=True)
    def isolation_context(
        self,
        authenticated_tenant_a_client: Any,
        tenant_a: Any,
        tenant_b: Any,
    ) -> None:
        self.client = authenticated_tenant_a_client
        self.type_a = make_entity_type(tenant_a.id, key="customer")
        self.type_b = make_entity_type(tenant_b.id, key="customer")
        self.tenant_a_row = make_entity(tenant_a.id, entity_type=self.type_a)
        self.tenant_b_row = make_entity(tenant_b.id, entity_type=self.type_b)

    def get_create_payload(self) -> dict[str, object]:
        return {
            "entity_type_id": str(self.type_a.id),
            "entity_code": f"SPOOF-{uuid.uuid4().hex[:8]}",
            "entity_name": "Spoof create",
            "data": {"email": "spoof@example.test"},
            "idempotency_key": f"spoof-entity-{uuid.uuid4()}",
        }

    def get_update_payload(self) -> dict[str, object]:
        return {
            "expected_version": self.tenant_b_row.version,
            "entity_name": "Spoofed entity",
            "reason": "Cross-tenant attempt",
            "idempotency_key": "spoof-entity-update",
        }


class TestQualityRuleIsolation(V2IsolationContract):
    model = DataQualityRule
    list_url = f"{BASE}/quality-rules/"
    detail_url_template = f"{BASE}/quality-rules/{{pk}}/"

    @pytest.fixture(autouse=True)
    def isolation_context(
        self,
        authenticated_tenant_a_client: Any,
        tenant_a: Any,
        tenant_b: Any,
    ) -> None:
        self.client = authenticated_tenant_a_client
        self.type_a = make_entity_type(tenant_a.id, key="customer")
        self.type_b = make_entity_type(tenant_b.id, key="customer")
        self.tenant_a_row = make_quality_rule(tenant_a.id, entity_type=self.type_a)
        self.tenant_b_row = make_quality_rule(tenant_b.id, entity_type=self.type_b)

    def get_create_payload(self) -> dict[str, object]:
        return {
            "entity_type_id": str(self.type_a.id),
            "name": f"Spoof rule {uuid.uuid4().hex[:8]}",
            "field_path": "email",
            "rule_type": "required",
            "configuration": {},
            "dimension": "completeness",
            "severity": "error",
            "weight": "1.0000",
            "idempotency_key": f"spoof-quality-rule-{uuid.uuid4()}",
        }

    def get_update_payload(self) -> dict[str, object]:
        return {
            "severity": "critical",
            "idempotency_key": "spoof-quality-update",
        }


class TestMatchingRuleIsolation(V2IsolationContract):
    model = MatchingRule
    list_url = f"{BASE}/matching-rules/"
    detail_url_template = f"{BASE}/matching-rules/{{pk}}/"

    @pytest.fixture(autouse=True)
    def isolation_context(
        self,
        authenticated_tenant_a_client: Any,
        tenant_a: Any,
        tenant_b: Any,
    ) -> None:
        self.client = authenticated_tenant_a_client
        self.type_a = make_entity_type(tenant_a.id, key="customer")
        self.type_b = make_entity_type(tenant_b.id, key="customer")
        self.tenant_a_row = make_matching_rule(tenant_a.id, entity_type=self.type_a)
        self.tenant_b_row = make_matching_rule(tenant_b.id, entity_type=self.type_b)

    def get_create_payload(self) -> dict[str, object]:
        return {
            "entity_type_id": str(self.type_a.id),
            "name": f"Spoof match rule {uuid.uuid4().hex[:8]}",
            "algorithm": "normalized",
            "field_weights": {"email": "1.0000"},
            "blocking_fields": [],
            "review_threshold": "0.7000",
            "auto_confirm_threshold": "0.9500",
            "idempotency_key": f"spoof-match-rule-{uuid.uuid4()}",
        }

    def get_update_payload(self) -> dict[str, object]:
        return {
            "review_threshold": "0.7500",
            "idempotency_key": "spoof-match-update",
        }


def snapshot(instance: Any) -> tuple[tuple[str, object], ...]:
    instance.refresh_from_db()
    return tuple(
        (field.attname, getattr(instance, field.attname))
        for field in instance._meta.concrete_fields
    )


def test_all_cross_tenant_entity_actions_return_404_and_leave_target_unchanged(
    authenticated_tenant_a_client: Any,
    tenant_b: Any,
) -> None:
    entity = make_entity(tenant_b.id)
    before = snapshot(entity)
    detail = f"{BASE}/entities/{entity.id}"
    actions = [
        (
            f"{detail}/restore/",
            {"expected_version": 1, "reason": "Spoof", "idempotency_key": "foreign-restore"},
        ),
        (
            f"{detail}/rollback/",
            {"version_number": 1, "expected_version": 1, "reason": "Spoof", "idempotency_key": "foreign-rollback"},
        ),
        (
            f"{detail}/validate/",
            {"reason": "Spoof", "idempotency_key": "foreign-validation"},
        ),
    ]
    for url, payload in actions:
        response = authenticated_tenant_a_client.post(url, payload, format="json")
        assert response.status_code == 404, (url, response.content)
        assert snapshot(entity) == before
    assert authenticated_tenant_a_client.get(f"{detail}/versions/").status_code == 404
    assert authenticated_tenant_a_client.get(f"{detail}/versions/1/").status_code == 404


def test_all_cross_tenant_stewardship_actions_return_404_and_preserve_rows(
    authenticated_tenant_a_client: Any,
    tenant_b: Any,
) -> None:
    entity_type = make_entity_type(tenant_b.id)
    first = make_entity(tenant_b.id, entity_type=entity_type)
    second = make_entity(tenant_b.id, entity_type=entity_type)
    quality_rule = make_quality_rule(tenant_b.id, entity_type=entity_type)
    issue = make_issue(tenant_b.id, entity=first, rule=quality_rule)
    matching_rule = make_matching_rule(
        tenant_b.id,
        entity_type=entity_type,
        field_weights={"email": "1.0000"},
        blocking_fields=[],
    )
    candidate = make_candidate(
        tenant_b.id,
        matching_rule=matching_rule,
        first=first,
        second=second,
    )
    merge = make_merge(tenant_b.id, golden_record=first)
    controls = {row.pk: snapshot(row) for row in (issue, candidate, merge)}
    requests = [
        (
            f"{BASE}/quality-issues/{issue.id}/assign/",
            {"assignee_id": str(actor_id()), "transition_key": "foreign-assign"},
        ),
        (f"{BASE}/quality-issues/{issue.id}/resolve/", {"resolution": "Spoof", "transition_key": "foreign-resolve"}),
        (f"{BASE}/quality-issues/{issue.id}/waive/", {"resolution": "Spoof", "transition_key": "foreign-waive"}),
        (
            f"{BASE}/match-candidates/{candidate.id}/review/",
            {"decision": "confirm", "note": "Spoof", "transition_key": "foreign-review"},
        ),
        (f"{BASE}/merges/{merge.id}/reverse/", {"reason": "Spoof", "transition_key": "foreign-reverse"}),
    ]
    for url, payload in requests:
        response = authenticated_tenant_a_client.post(url, payload, format="json")
        assert response.status_code == 404, (url, response.content)
    assert snapshot(issue) == controls[issue.pk]
    assert snapshot(candidate) == controls[candidate.pk]
    assert snapshot(merge) == controls[merge.pk]


def test_cross_tenant_relation_inputs_are_rejected_without_mutating_tenant_b(
    authenticated_tenant_a_client: Any,
    tenant_a: Any,
    tenant_b: Any,
) -> None:
    type_a = make_entity_type(tenant_a.id, key="customer")
    type_b = make_entity_type(tenant_b.id, key="customer")
    entity_a = make_entity(tenant_a.id, entity_type=type_a)
    entity_b = make_entity(tenant_b.id, entity_type=type_b)
    rule_b = make_matching_rule(
        tenant_b.id,
        entity_type=type_b,
        field_weights={"email": "1.0000"},
        blocking_fields=[],
    )
    b_before = snapshot(entity_b)

    create = authenticated_tenant_a_client.post(
        f"{BASE}/entities/",
        {
            "entity_type_id": str(type_b.id),
            "entity_code": "CROSS-TYPE",
            "entity_name": "Cross tenant type",
            "data": {},
            "idempotency_key": "cross-type-create",
        },
        format="json",
    )
    assert create.status_code in {404, 422}
    preview = authenticated_tenant_a_client.post(
        f"{BASE}/matching/preview/",
        {
            "left_entity_id": str(entity_a.id),
            "right_entity_id": str(entity_b.id),
            "rule_id": str(rule_b.id),
        },
        format="json",
    )
    assert preview.status_code == 404
    merge = authenticated_tenant_a_client.post(
        f"{BASE}/merges/preview/",
        {
            "entity_ids": [str(entity_a.id), str(entity_b.id)],
            "survivorship_overrides": {},
        },
        format="json",
    )
    assert merge.status_code == 404
    assert snapshot(entity_b) == b_before
    assert not MasterDataEntity.objects.for_tenant(tenant_b.id).filter(entity_code="CROSS-TYPE").exists()


def test_cross_tenant_job_lookup_is_404(
    authenticated_tenant_a_client: Any,
    tenant_b: Any,
) -> None:
    job = AsyncJob.objects.create(
        tenant_id=tenant_b.id,
        actor_id=str(actor_id()),
        command="master_data_management.quality_scan",
        status="queued",
        idempotency_key="foreign-job",
        payload={"entity_type_id": str(uuid.uuid4())},
        correlation_id="foreign-job-correlation",
    )
    before = snapshot(job)
    response = authenticated_tenant_a_client.get(f"{BASE}/jobs/{job.id}/")
    assert response.status_code == 404
    assert snapshot(job) == before


def test_outbox_queries_are_explicitly_tenant_scoped(tenant_a: Any, tenant_b: Any) -> None:
    aggregate = uuid.uuid4()
    event_a = OutboxEvent.objects.create(
        tenant_id=tenant_a.id,
        aggregate_type="master_data_entity",
        aggregate_id=aggregate,
        event_type="mdm.entity.created",
        payload={"tenant_id": str(tenant_a.id)},
    )
    event_b = OutboxEvent.objects.create(
        tenant_id=tenant_b.id,
        aggregate_type="master_data_entity",
        aggregate_id=aggregate,
        event_type="mdm.entity.created",
        payload={"tenant_id": str(tenant_b.id)},
    )
    assert list(OutboxEvent.objects.for_tenant(tenant_a.id).values_list("id", flat=True)) == [event_a.id]
    assert event_b.id not in OutboxEvent.objects.for_tenant(tenant_a.id).values_list("id", flat=True)


@pytest.mark.postgresql
def test_postgresql_force_rls_blocks_unscoped_cross_tenant_orm_access(
    tenant_a: Any,
    tenant_b: Any,
) -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Forced RLS requires PostgreSQL")
    own = make_entity(tenant_a.id)
    foreign = make_entity(tenant_b.id)
    with tenant_context(tenant_a.id):
        visible = set(MasterDataEntity.objects.all().values_list("id", flat=True))
    assert own.id in visible
    assert foreign.id not in visible
