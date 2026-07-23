"""Black-box governed API v2, serializer, and controller-authority tests."""

from __future__ import annotations

import inspect
import uuid

import pytest
from rest_framework.test import APIClient

from src.core.access.decision import AccessDecision, AccessDecisionPipeline, AccessReasonCode
from src.core.testing import TEST_PASSWORD
from src.modules.master_data_management import api
from src.modules.master_data_management.permissions import PERMISSIONS
from src.modules.master_data_management.serializers import (
    DataQualityRuleWriteSerializer,
    MatchingRuleWriteSerializer,
    MasterDataEntityCreateSerializer,
    MasterDataEntityDetailSerializer,
    MasterDataEntityUpdateSerializer,
    MasterEntityTypeCreateSerializer,
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
    """Allow policy after real session/tenant authentication for HTTP behavior tests."""

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
            reason="test policy projection",
            tenant_id=uuid.UUID(str(tenant_id)),
        )

    monkeypatch.setattr(AccessDecisionPipeline, "decide", decide)


def envelope(response: object) -> dict[str, object]:
    payload = response.json()  # type: ignore[attr-defined]
    assert set(payload) == {"data", "meta"}
    assert payload["meta"]["correlation_id"]  # type: ignore[index]
    assert payload["meta"]["timestamp"]  # type: ignore[index]
    return payload


@pytest.mark.parametrize(
    "path",
    [
        f"{BASE}/entity-types/",
        f"{BASE}/entities/",
        f"{BASE}/quality-rules/",
        f"{BASE}/quality-issues/",
        f"{BASE}/matching-rules/",
        f"{BASE}/match-candidates/",
        f"{BASE}/merges/",
        f"{BASE}/dashboard/",
        f"{BASE}/jobs/{uuid.uuid4()}/",
    ],
)
def test_every_governed_surface_requires_a_real_session(api_client: APIClient, path: str) -> None:
    response = api_client.get(path)
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "AUTHENTICATION_REQUIRED"
    assert error["correlation_id"]


def test_csrf_is_enforced_for_unsafe_requests(tenant_a_user: object) -> None:
    client = APIClient(enforce_csrf_checks=True)
    assert client.login(username=tenant_a_user.username, password=TEST_PASSWORD)  # type: ignore[attr-defined]
    response = client.post(
        f"{BASE}/entity-types/",
        {
            "key": "customer",
            "display_name": "Customer",
            "json_schema": {"type": "object", "properties": {}},
            "idempotency_key": "csrf-missing",
        },
        format="json",
    )
    assert response.status_code == 403


def test_policy_or_entitlement_denial_is_stable_403(
    authenticated_tenant_a_client: APIClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny(
        self: AccessDecisionPipeline,
        tenant_id: object,
        identity: object,
        required_permission: str,
        **kwargs: object,
    ) -> AccessDecision:
        del self, identity, required_permission, kwargs
        return AccessDecision.deny(
            AccessReasonCode.POLICY_DENIED,
            "Denied by tenant policy",
            tenant_id=uuid.UUID(str(tenant_id)),
        )

    monkeypatch.setattr(AccessDecisionPipeline, "decide", deny)
    response = authenticated_tenant_a_client.get(f"{BASE}/entities/")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "POLICY_DENIED"
    assert response.json()["error"]["correlation_id"]


def test_every_viewset_action_has_one_known_permission_and_unknown_actions_deny() -> None:
    viewsets = [
        api.MasterEntityTypeViewSet,
        api.MasterDataEntityViewSet,
        api.DataQualityRuleViewSet,
        api.DataQualityIssueViewSet,
        api.QualityScanViewSet,
        api.MatchingRuleViewSet,
        api.MatchingOperationsViewSet,
        api.MatchCandidateViewSet,
        api.MergeViewSet,
        api.DashboardViewSet,
        api.AsyncJobViewSet,
    ]
    for viewset in viewsets:
        assert viewset.access_map, viewset.__name__
        assert all(rule.permission and rule.entitlement for rule in viewset.access_map.values())
        assert all(rule.permission in PERMISSIONS for rule in viewset.access_map.values())
    assert api.QualityScanViewSet.access_map["create"].permission == "mdm.quality:scan"
    # The base class has no permissive fallback declaration.
    assert api.GovernedMDMViewSet.access_map == {}


def test_serializers_reject_unknown_and_server_owned_overposting() -> None:
    create_payload = {
        "entity_type_id": str(uuid.uuid4()),
        "entity_code": "CUST-001",
        "entity_name": "Customer",
        "data": {},
        "idempotency_key": "strict-create",
    }
    for field, value in (
        ("tenant_id", str(uuid.uuid4())),
        ("created_by", str(uuid.uuid4())),
        ("status", "merged"),
        ("quality_score", "100.00"),
        ("is_deleted", True),
        ("golden_record", str(uuid.uuid4())),
        ("unknown_field", "value"),
    ):
        serializer = MasterDataEntityCreateSerializer(data={**create_payload, field: value})
        assert serializer.is_valid() is False
        assert field in serializer.errors

    update = MasterDataEntityUpdateSerializer(
        data={
            "expected_version": 1,
            "reason": "Edit",
            "idempotency_key": "strict-update",
            "version": 99,
        }
    )
    assert update.is_valid() is False and "version" in update.errors
    type_serializer = MasterEntityTypeCreateSerializer(
        data={
            "key": "customer",
            "display_name": "Customer",
            "json_schema": {"type": "object"},
            "idempotency_key": "strict-type",
            "schema_version": 99,
        }
    )
    assert type_serializer.is_valid() is False and "schema_version" in type_serializer.errors
    owner_serializer = MasterEntityTypeCreateSerializer(
        data={
            "key": "customer",
            "display_name": "Customer",
            "json_schema": {"type": "object"},
            "owner_module": "spoofed_module",
            "idempotency_key": "strict-owner",
        }
    )
    assert owner_serializer.is_valid() is False and "owner_module" in owner_serializer.errors
    weight = DataQualityRuleWriteSerializer(data={"idempotency_key": "weight-zero", "weight": "0.0000"})
    assert weight.is_valid() is False and "weight" in weight.errors


@pytest.mark.parametrize(
    ("serializer_class", "required_fields"),
    [
        (
            DataQualityRuleWriteSerializer,
            {
                "entity_type_id",
                "name",
                "rule_type",
                "configuration",
                "dimension",
                "severity",
                "weight",
            },
        ),
        (
            MatchingRuleWriteSerializer,
            {
                "entity_type_id",
                "name",
                "algorithm",
                "field_weights",
                "blocking_fields",
                "review_threshold",
                "auto_confirm_threshold",
            },
        ),
    ],
)
def test_rule_write_serializers_authoritatively_require_create_fields(
    serializer_class: type[object],
    required_fields: set[str],
) -> None:
    serializer = serializer_class(data={"idempotency_key": "required-fields"})  # type: ignore[call-arg]
    assert serializer.is_valid() is False  # type: ignore[attr-defined]
    assert required_fields <= set(serializer.errors)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "viewset_class",
    [
        api.MasterEntityTypeViewSet,
        api.MasterDataEntityViewSet,
        api.DataQualityRuleViewSet,
        api.DataQualityIssueViewSet,
        api.MatchingRuleViewSet,
        api.MatchCandidateViewSet,
        api.MergeViewSet,
        api.AsyncJobViewSet,
    ],
)
def test_every_queryset_returns_none_when_tenant_is_absent(
    viewset_class: type[api.GovernedMDMViewSet],
) -> None:
    view = viewset_class()
    view._get_tenant_id = lambda: None  # type: ignore[method-assign]
    assert view.get_queryset().query.is_empty()


def test_entity_detail_masks_nested_sensitive_values_unless_field_policy_allows() -> None:
    tenant = uuid.uuid4()
    entity_type = make_entity_type(
        tenant,
        sensitive_fields=["tax_id", "bank.account_number"],
    )
    entity = make_entity(
        tenant,
        entity_type=entity_type,
        data={
            "name": "Acme",
            "tax_id": "TAX-SECRET",
            "bank": {"account_number": "BANK-SECRET", "branch": "Pune"},
        },
    )
    masked = MasterDataEntityDetailSerializer(entity).data["data"]
    assert masked == {
        "name": "Acme",
        "tax_id": "••••••",
        "bank": {"account_number": "••••••", "branch": "Pune"},
    }

    request = type("RequestPolicy", (), {"allowed_sensitive_fields": {"tax_id"}})()
    authorized = MasterDataEntityDetailSerializer(entity, context={"request": request}).data["data"]
    assert authorized["tax_id"] == "TAX-SECRET"
    assert authorized["bank"]["account_number"] == "••••••"
    assert entity.data["tax_id"] == "TAX-SECRET", "serialization must not mutate the model JSON"


def test_entity_type_list_envelope_filters_search_order_and_bounded_pagination(
    authenticated_tenant_a_client: APIClient,
    tenant_a: object,
    tenant_b: object,
) -> None:
    own_customer = make_entity_type(  # type: ignore[attr-defined]
        tenant_a.id, key="customer", display_name="Acme Customer"
    )
    make_entity_type(  # type: ignore[attr-defined]
        tenant_a.id,
        key="supplier",
        display_name="Vendor",
        owner_module="purchase_management",
    )
    foreign = make_entity_type(  # type: ignore[attr-defined]
        tenant_b.id, key="customer", display_name="Foreign Customer"
    )
    response = authenticated_tenant_a_client.get(
        f"{BASE}/entity-types/?key=customer&owner_module=master_data_management"
        "&is_active=true&search=acme&ordering=-updated_at&page_size=1000"
    )
    assert response.status_code == 200, response.content
    payload = envelope(response)
    assert [item["id"] for item in payload["data"]] == [str(own_customer.id)]  # type: ignore[index]
    assert str(foreign.id) not in {item["id"] for item in payload["data"]}  # type: ignore[union-attr]
    assert payload["meta"]["pagination"]["page_size"] == 100  # type: ignore[index]


@pytest.mark.parametrize(
    "path",
    [
        f"{BASE}/entity-types/?secret=value",
        f"{BASE}/entities/?tenant_id={uuid.uuid4()}",
        f"{BASE}/quality-rules/?ordering=configuration",
        f"{BASE}/matching-rules/?ordering=field_weights",
        f"{BASE}/match-candidates/?ordering=evidence",
        f"{BASE}/merges/?ordering=golden_snapshot_after",
        f"{BASE}/dashboard/?global=true",
    ],
)
def test_unknown_query_or_ordering_is_rejected(
    authenticated_tenant_a_client: APIClient,
    path: str,
) -> None:
    response = authenticated_tenant_a_client.get(path)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["correlation_id"]


def test_cross_tenant_detail_patch_delete_and_actions_are_exact_404(
    authenticated_tenant_a_client: APIClient,
    tenant_b: object,
) -> None:
    entity = make_entity(tenant_b.id)  # type: ignore[attr-defined]
    before = {
        "name": entity.entity_name,
        "status": entity.status,
        "version": entity.version,
        "is_deleted": entity.is_deleted,
    }
    detail = f"{BASE}/entities/{entity.id}/"
    assert authenticated_tenant_a_client.get(detail).status_code == 404
    assert authenticated_tenant_a_client.patch(
        detail,
        {
            "expected_version": entity.version,
            "entity_name": "Spoofed",
            "reason": "Cross tenant",
            "idempotency_key": "foreign-patch",
        },
        format="json",
    ).status_code == 404
    assert authenticated_tenant_a_client.delete(
        detail,
        {
            "expected_version": entity.version,
            "reason": "Cross tenant",
            "idempotency_key": "foreign-delete",
        },
        format="json",
    ).status_code == 404
    assert authenticated_tenant_a_client.post(
        f"{detail}restore/",
        {
            "expected_version": entity.version,
            "reason": "Cross tenant",
            "idempotency_key": "foreign-restore",
        },
        format="json",
    ).status_code == 404
    entity.refresh_from_db()
    assert {
        "name": entity.entity_name,
        "status": entity.status,
        "version": entity.version,
        "is_deleted": entity.is_deleted,
    } == before


def test_complete_entity_http_workflow_uses_v2_services_and_204_archive(
    authenticated_tenant_a_client: APIClient,
) -> None:
    client = authenticated_tenant_a_client
    type_response = client.post(
        f"{BASE}/entity-types/",
        {
            "key": "customer",
            "display_name": "Customer",
            "description": "Authoritative customer",
            "json_schema": {
                "type": "object",
                "properties": {"email": {"type": "string", "format": "email"}},
                "required": ["email"],
                "additionalProperties": False,
            },
            "required_fields": ["email"],
            "sensitive_fields": [],
            "searchable_fields": ["email"],
            "idempotency_key": "http-create-type",
        },
        format="json",
    )
    assert type_response.status_code == 201, type_response.content
    entity_type = envelope(type_response)["data"]

    create = client.post(
        f"{BASE}/entities/",
        {
            "entity_type_id": entity_type["id"],  # type: ignore[index]
            "entity_code": "CUST-HTTP",
            "entity_name": "HTTP Customer",
            "data": {"email": "http@example.test"},
            "source_system": "manual",
            "source_record_id": "http-1",
            "idempotency_key": "http-create-entity",
        },
        format="json",
    )
    assert create.status_code == 201, create.content
    entity = envelope(create)["data"]
    entity_id = entity["id"]  # type: ignore[index]

    type_identifier = entity_type["id"] if isinstance(entity_type, dict) else ""
    listing = client.get(f"{BASE}/entities/?search=HTTP&type={type_identifier}")
    # `type` is intentionally not accepted; only the declared `entity_type` key is.
    assert listing.status_code == 400
    listing = client.get(
        f"{BASE}/entities/?search=HTTP&entity_type={entity_type['id']}&status=active"
        "&source_system=manual&quality_min=0&quality_max=100&ordering=-updated_at"
    )  # type: ignore[index]
    assert listing.status_code == 200
    assert [row["id"] for row in envelope(listing)["data"]] == [entity_id]  # type: ignore[union-attr]
    assert envelope(client.get(f"{BASE}/entities/{entity_id}/"))["data"]["id"] == entity_id  # type: ignore[index]

    patch = client.patch(
        f"{BASE}/entities/{entity_id}/",
        {
            "expected_version": 1,
            "entity_name": "Updated HTTP Customer",
            "reason": "Verified name",
            "idempotency_key": "http-update-entity",
        },
        format="json",
    )
    assert patch.status_code == 200, patch.content
    assert envelope(patch)["data"]["version"] == 2  # type: ignore[index]

    versions = client.get(f"{BASE}/entities/{entity_id}/versions/")
    assert versions.status_code == 200
    assert {item["version_number"] for item in envelope(versions)["data"]} == {1, 2}  # type: ignore[union-attr]
    snapshot = client.get(f"{BASE}/entities/{entity_id}/versions/1/")
    assert snapshot.status_code == 200
    assert envelope(snapshot)["data"]["version_number"] == 1  # type: ignore[index]

    archived = client.delete(
        f"{BASE}/entities/{entity_id}/",
        {
            "expected_version": 2,
            "reason": "Retired",
            "idempotency_key": "http-archive",
        },
        format="json",
    )
    assert archived.status_code == 204
    assert archived.content == b""
    restored = client.post(
        f"{BASE}/entities/{entity_id}/restore/",
        {
            "expected_version": 3,
            "reason": "Reactivated",
            "idempotency_key": "http-restore",
        },
        format="json",
    )
    assert restored.status_code == 200
    assert envelope(restored)["data"]["version"] == 4  # type: ignore[index]
    rollback = client.post(
        f"{BASE}/entities/{entity_id}/rollback/",
        {
            "version_number": 1,
            "expected_version": 4,
            "reason": "Restore original",
            "idempotency_key": "http-rollback",
        },
        format="json",
    )
    assert rollback.status_code == 200
    assert envelope(rollback)["data"]["version"] == 5  # type: ignore[index]
    validation = client.post(
        f"{BASE}/entities/{entity_id}/validate/",
        {"reason": "Manual rescore", "idempotency_key": "http-validate"},
        format="json",
    )
    assert validation.status_code == 200
    assert envelope(validation)["data"]["evaluated"] is False  # type: ignore[index]


def test_rule_issue_match_job_dashboard_and_health_surfaces(
    authenticated_tenant_a_client: APIClient,
    tenant_a: object,
) -> None:
    tenant = tenant_a.id  # type: ignore[attr-defined]
    entity_type = make_entity_type(tenant, key="customer")
    entity = make_entity(tenant, entity_type=entity_type, data={"email": "x@example.test"})
    quality_rule = make_quality_rule(tenant, entity_type=entity_type)
    issue = make_issue(tenant, entity=entity, rule=quality_rule)
    matching_rule = make_matching_rule(
        tenant,
        entity_type=entity_type,
        field_weights={"email": "1.0000"},
        blocking_fields=[],
    )
    other = make_entity(tenant, entity_type=entity_type, data={"email": "x@example.test"})
    candidate = make_candidate(tenant, matching_rule=matching_rule, first=entity, second=other)
    merge = make_merge(tenant, golden_record=entity)
    client = authenticated_tenant_a_client

    quality_rules = client.get(
        f"{BASE}/quality-rules/?entity_type={entity_type.id}&rule_type=required"
        "&dimension=completeness&severity=error&is_active=true&search=Email"
    )
    assert envelope(quality_rules)["data"]
    quality_issues = client.get(
        f"{BASE}/quality-issues/?entity={entity.id}&entity_type={entity_type.id}"
        "&status=open&severity=error&dimension=completeness"
    )
    assert envelope(quality_issues)["data"]
    assign = client.post(
        f"{BASE}/quality-issues/{issue.id}/assign/",
        {"assignee_id": str(actor_id("api-assignee")), "transition_key": "api-assign"},
        format="json",
    )
    assert assign.status_code == 200 and envelope(assign)["data"]["status"] == "in_review"  # type: ignore[index]
    resolve = client.post(
        f"{BASE}/quality-issues/{issue.id}/resolve/",
        {"resolution": "Verified", "transition_key": "api-resolve"},
        format="json",
    )
    assert resolve.status_code == 200 and envelope(resolve)["data"]["status"] == "resolved"  # type: ignore[index]

    preview = client.post(
        f"{BASE}/matching/preview/",
        {"left_entity_id": str(entity.id), "right_entity_id": str(other.id), "rule_id": str(matching_rule.id)},
        format="json",
    )
    assert preview.status_code == 200 and envelope(preview)["data"]["confidence"] == "1.0000"  # type: ignore[index]
    review = client.post(
        f"{BASE}/match-candidates/{candidate.id}/review/",
        {"decision": "confirm", "note": "Duplicate", "transition_key": "api-review"},
        format="json",
    )
    assert review.status_code == 200 and envelope(review)["data"]["status"] == "confirmed"  # type: ignore[index]
    candidates = client.get(
        f"{BASE}/match-candidates/?entity_type={entity_type.id}&status=confirmed"
        f"&rule={matching_rule.id}&confidence_min=0.5&confidence_max=1"
    )
    assert envelope(candidates)["data"]
    merges = envelope(client.get(f"{BASE}/merges/?status=applied&golden_record={entity.id}"))
    assert merges["data"][0]["id"] == str(merge.id)  # type: ignore[index]

    quality_scan = client.post(
        f"{BASE}/quality-scans/",
        {"entity_type_id": str(entity_type.id), "idempotency_key": "api-quality-scan"},
        format="json",
    )
    assert quality_scan.status_code == 202
    job = envelope(quality_scan)["data"]
    assert job["status"] == "queued"  # type: ignore[index]
    assert envelope(client.get(f"{BASE}/jobs/{job['id']}/"))["data"]["id"] == job["id"]  # type: ignore[index]
    dashboard = envelope(client.get(f"{BASE}/dashboard/?entity_type={entity_type.id}"))["data"]
    assert dashboard["entity_count"] == 2  # type: ignore[index]

    live = client.get(f"{BASE}/health/live/")
    assert live.status_code == 200
    assert envelope(live)["data"]["status"] == "live"  # type: ignore[index]
    ready = client.get(f"{BASE}/health/ready/")
    assert ready.status_code in {200, 503}
    ready_payload = envelope(ready)
    serialized = str(ready_payload).lower()
    assert "password" not in serialized and "select " not in serialized


def test_legacy_v1_route_put_and_hard_delete_are_not_exposed(
    authenticated_tenant_a_client: APIClient,
    tenant_a: object,
) -> None:
    entity = make_entity(tenant_a.id)  # type: ignore[attr-defined]
    assert authenticated_tenant_a_client.get("/api/v1/master-data-management/entities/").status_code == 404
    assert authenticated_tenant_a_client.put(
        f"{BASE}/entities/{entity.id}/",
        {},
        format="json",
    ).status_code == 405
    assert authenticated_tenant_a_client.post(
        f"{BASE}/entities/{entity.id}/hard-delete/",
        {},
        format="json",
    ).status_code == 404


def test_viewsets_contain_no_direct_model_mutation_bypass() -> None:
    source = inspect.getsource(api)
    forbidden = ("serializer.save(", ".objects.create(", ".delete()")
    assert all(token not in source for token in forbidden)
    assert "RelaxedCsrfSessionAuthentication" not in source
    assert api.MasterDataEntityViewSet.__mro__[:3] == (
        api.MasterDataEntityViewSet,
        api.GovernedMDMViewSet,
        api.GovernedAPIViewMixin,
    )
