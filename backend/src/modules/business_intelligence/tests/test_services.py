"""Service-layer behavior for declarative, idempotent BI definitions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from src.core.api import OperationFailed
from src.modules.business_intelligence import services as bi_services
from src.modules.business_intelligence.datasets import DatasetResult, ValidatedQuery
from src.modules.business_intelligence.models import QueryExecution
from src.modules.business_intelligence.services import (
    BIConflict,
    CapabilityUnavailable,
    DashboardService,
    DatasetCatalogService,
    ExecutionService,
    QueryService,
    ReportService,
)


class PlainDescriptor:
    def __init__(self) -> None:
        self.key = "business_intelligence.execution_audit"
        self.module = "business_intelligence"
        self.version = "plain-v1"
        self._private = "redacted"


def query_payload() -> dict[str, object]:
    return {
        "query_code": "EXECUTION_SUMMARY",
        "name": "Execution summary",
        "dataset_key": "business_intelligence.execution_audit",
        "dimensions": ["status"],
        "measures": [{"key": "execution_count"}],
        "row_limit": 100,
    }


@dataclass(frozen=True)
class MappingDescriptor:
    key: str = "business_intelligence.execution_audit"
    module: str = "business_intelligence"
    label: str = "Execution audit"
    description: str = "Execution audit rows"
    version: str = "2026.1"
    dimensions: tuple[object, ...] = ()
    measures: tuple[object, ...] = ()
    max_row_limit: int = 100
    locked: bool = False


class MappingProvider:
    def __init__(self, *, locked: bool = False, fail_execute: bool = False) -> None:
        self.locked = locked
        self.fail_execute = fail_execute
        self.executions = 0

    def describe(self) -> MappingDescriptor:
        return MappingDescriptor(locked=self.locked)

    def validate(self, tenant_id, spec):  # noqa: ANN001, ANN201
        return ValidatedQuery(
            dataset_key=str(spec["dataset_key"]),
            dimensions=tuple(spec.get("dimensions", ())),
            measures=tuple(spec.get("measures", ())),
            filters=tuple(spec.get("filters", ())),
            grouping=tuple(spec.get("grouping", ())),
            ordering=tuple(spec.get("ordering", ())),
            row_limit=int(spec.get("row_limit", 100)),
            fingerprint="validated-fingerprint",
        )

    def execute(self, tenant_id, validated, parameters):  # noqa: ANN001, ANN201
        self.executions += 1
        if self.fail_execute:
            raise RuntimeError("provider unavailable")
        return DatasetResult(
            columns=({"key": "status", "label": "Status"},),
            rows=({"status": parameters.get("status", "queued"), "count": 3},),
            row_count=1,
            truncated=False,
            freshness_token="fresh-1",
            data_as_of=timezone.now(),
        )

    def freshness_token(self, tenant_id):  # noqa: ANN001, ANN201
        return "fresh-1"


class ProviderWithoutFreshness(MappingProvider):
    freshness_token = None


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


@pytest.mark.django_db
def test_duplicate_query_code_requires_same_idempotency_key() -> None:
    tenant_id = uuid.uuid4()
    QueryService.create(tenant_id, "actor", query_payload(), "correlation", "create-key")

    with pytest.raises(BIConflict) as exc:
        QueryService.create(tenant_id, "actor", query_payload(), "correlation", "different-key")

    assert exc.value.error_code == "DUPLICATE_CODE"


@pytest.mark.django_db
def test_query_parameter_validation_rejects_unknown_missing_and_wrong_type() -> None:
    tenant_id = uuid.uuid4()
    payload = {
        **query_payload(),
        "parameters_schema": {
            "from_date": {"type": "date", "required": True},
            "limit": {"type": "integer"},
        },
        "filters": [{"field": "status", "operator": "eq", "parameter": "from_date"}],
    }
    query = QueryService.create(tenant_id, "actor", payload, "correlation", "create-with-params")

    with pytest.raises(ValidationError) as exc:
        QueryService.validate(tenant_id, query.id, {"limit": True, "unknown": "value"})

    detail = exc.value.detail["parameters"]
    assert detail["from_date"] == "This parameter is required."
    assert detail["unknown"] == "Unknown parameter."

    with pytest.raises(ValidationError) as exc:
        QueryService.validate(tenant_id, query.id, {"from_date": "2026-01-01", "limit": True})

    assert exc.value.detail["parameters"]["limit"] == "Expected integer."


@pytest.mark.django_db
def test_report_publish_requires_published_query_definition() -> None:
    tenant_id = uuid.uuid4()
    query = QueryService.create(tenant_id, "actor", query_payload(), "correlation", "create-query")
    report = ReportService.create(
        tenant_id,
        "actor",
        {
            "report_code": "STATUS_REPORT",
            "report_name": "Status report",
            "report_type": "table",
            "query_definition_id": query.id,
            "visualization": {"type": "table"},
        },
        "correlation",
        "create-report",
    )

    with pytest.raises(BIConflict) as exc:
        ReportService.publish(tenant_id, report.id, "actor", report.version, "correlation", "publish-report")

    assert exc.value.error_code == "PUBLISH_GUARD_FAILED"


@pytest.mark.django_db
def test_dashboard_widget_layout_collision_is_rejected() -> None:
    tenant_id = uuid.uuid4()
    query = QueryService.create(tenant_id, "owner", query_payload(), "correlation", "create-query")
    query = QueryService.publish(tenant_id, query.id, "owner", query.version, "correlation", "publish-query")
    dashboard = DashboardService.create(
        tenant_id,
        "owner",
        {"dashboard_code": "OPS", "dashboard_name": "Operations"},
        "correlation",
        "create-dashboard",
    )
    DashboardService.add_widget(
        tenant_id,
        dashboard.id,
        "owner",
        {
            "query_definition_id": query.id,
            "widget_type": "table",
            "title": "Status",
            "x": 0,
            "y": 0,
            "width": 6,
            "height": 4,
            "visualization": {"type": "table"},
            "filters": [],
            "display_order": 0,
        },
        "correlation",
        "add-widget",
    )

    with pytest.raises(BIConflict) as exc:
        DashboardService.add_widget(
            tenant_id,
            dashboard.id,
            "owner",
            {
                "query_definition_id": query.id,
                "widget_type": "table",
                "title": "Duplicate slot",
                "x": 4,
                "y": 2,
                "width": 4,
                "height": 4,
                "visualization": {"type": "table"},
                "filters": [],
            },
            "correlation",
            "add-overlap",
        )

    assert exc.value.error_code == "LAYOUT_COLLISION"


@pytest.mark.django_db
def test_query_create_reports_dataset_provider_validation_failure(monkeypatch) -> None:
    class RejectingProvider:
        def describe(self) -> dict[str, object]:
            return {
                "key": "business_intelligence.execution_audit",
                "module": "business_intelligence",
                "version": "1",
                "max_row_limit": 100,
            }

        def validate(self, tenant_id, spec):  # noqa: ANN001, ANN201
            raise RuntimeError("provider dependency unavailable")

    monkeypatch.setattr(bi_services, "_registry_get", lambda key: RejectingProvider())

    with pytest.raises(ValidationError) as exc:
        QueryService.create(uuid.uuid4(), "actor", query_payload(), "correlation", "provider-failure")

    assert exc.value.detail["query"] == "The dataset rejected this query definition."


@pytest.mark.django_db
def test_query_execution_requires_publication_and_reuses_idempotency_key() -> None:
    tenant_id = uuid.uuid4()
    actor_id = "actor"
    query = QueryService.create(tenant_id, actor_id, query_payload(), "correlation", "query-create")
    with pytest.raises(BIConflict) as exc:
        QueryService.enqueue_execution(tenant_id, query.id, actor_id, {}, "correlation", "execution-1")
    assert exc.value.error_code == "NOT_PUBLISHED"

    query = QueryService.publish(tenant_id, query.id, actor_id, query.version, "correlation", "query-publish")
    execution = QueryService.enqueue_execution(tenant_id, query.id, actor_id, {}, "correlation", "execution-1")
    assert execution.status == "queued"
    assert execution.async_job.payload["execution_id"] == str(execution.id)
    replay = ExecutionService.enqueue(tenant_id, query, actor_id, {}, "correlation", "execution-1")
    assert replay.id == execution.id
    with pytest.raises(BIConflict) as exc:
        ExecutionService.enqueue(tenant_id, query, actor_id, {"changed": True}, "correlation", "execution-1")
    assert exc.value.error_code == "IDEMPOTENCY_CONFLICT"
    assert QueryExecution.objects.for_tenant(tenant_id).count() == 1


def test_dataset_catalog_redacts_locked_entries_and_denies_detail(monkeypatch) -> None:
    provider = MappingProvider(locked=True)
    monkeypatch.setattr(bi_services.dataset_registry, "descriptors", lambda: (provider.describe(),))
    monkeypatch.setattr(bi_services, "_registry_get", lambda key: provider)
    tenant_id = uuid.uuid4()

    assert DatasetCatalogService.list_datasets(tenant_id, object()) == []
    locked = DatasetCatalogService.list_datasets(tenant_id, object(), include_locked=True)
    assert locked == [
        {
            "key": "business_intelligence.execution_audit",
            "module": "business_intelligence",
            "owning_module": "business_intelligence",
            "label": "Execution audit",
            "description": "Execution audit rows",
            "version": "2026.1",
            "required_entitlement": None,
            "upgrade_url": None,
            "locked": True,
        }
    ]
    with pytest.raises(OperationFailed) as exc:
        DatasetCatalogService.get_dataset(tenant_id, object(), "business_intelligence.execution_audit")

    assert exc.value.error_code == "ENTITLEMENT_REQUIRED"


def test_helper_guardrails_fail_closed_and_normalize_descriptor_forms(monkeypatch) -> None:
    tenant_id = uuid.uuid4()

    with pytest.raises(ValidationError) as exc:
        bi_services._tenant_uuid("not-a-uuid")
    assert exc.value.detail["tenant_id"] == "A valid tenant UUID is required."

    with pytest.raises(ValidationError) as exc:
        bi_services._required_text(" ", "actor_id")
    assert exc.value.detail["actor_id"] == "A non-empty value up to 255 characters is required."

    with pytest.raises(ValidationError) as exc:
        bi_services._validate_visualization("table", [])
    assert exc.value.detail["visualization"] == "Visualization configuration must be an object."

    with pytest.raises(ValidationError) as exc:
        bi_services._validate_visualization("table", {"type": "pie"})
    assert exc.value.detail["visualization"] == "Visualization type is incompatible with the resource type."

    assert bi_services._descriptor_dict(PlainDescriptor()) == {
        "key": "business_intelligence.execution_audit",
        "module": "business_intelligence",
        "version": "plain-v1",
    }
    with pytest.raises(CapabilityUnavailable):
        bi_services._descriptor_dict(object())

    provider = MappingProvider()
    monkeypatch.delattr(bi_services.dataset_registry, "descriptors", raising=False)
    monkeypatch.setattr(bi_services.dataset_registry, "providers", lambda: {"execution": provider}, raising=False)
    datasets = DatasetCatalogService.list_datasets(tenant_id, object())
    assert datasets[0]["key"] == "business_intelligence.execution_audit"

    monkeypatch.setattr(
        bi_services.dataset_registry,
        "get",
        lambda key: (_ for _ in ()).throw(RuntimeError("registry down")),
        raising=False,
    )
    with pytest.raises(CapabilityUnavailable):
        bi_services._registry_get("business_intelligence.execution_audit")


@pytest.mark.django_db
def test_query_validation_rejects_row_limit_schema_bindings_and_scalar_types(monkeypatch) -> None:
    monkeypatch.setattr(bi_services, "_registry_get", lambda key: MappingProvider())
    tenant_id = uuid.uuid4()
    actor_id = "actor"

    with pytest.raises(ValidationError) as exc:
        QueryService.create(tenant_id, actor_id, {**query_payload(), "row_limit": 101}, "correlation", "row-limit")
    assert exc.value.detail["row_limit"] == "This dataset permits at most 100 rows."

    with pytest.raises(ValidationError) as exc:
        QueryService.create(
            tenant_id,
            actor_id,
            {**query_payload(), "parameters_schema": []},
            "correlation",
            "bad-schema",
        )
    assert exc.value.detail["parameters_schema"] == "Parameter schema must be an object."

    with pytest.raises(ValidationError) as exc:
        QueryService.create(
            tenant_id,
            actor_id,
            {
                **query_payload(),
                "parameters_schema": {},
                "filters": [{"field": "status", "operator": "eq", "parameter": "missing"}],
            },
            "correlation",
            "bad-binding",
        )
    assert exc.value.detail["filters"] == "Every parameter binding must exist in parameters_schema."

    query = QueryService.create(
        tenant_id,
        actor_id,
        {
            **query_payload(),
            "parameters_schema": {
                "as_of": {"type": "date"},
                "captured_at": {"type": "datetime"},
                "owner_id": {"type": "uuid"},
                "ratio": {"type": "number"},
                "enabled": {"type": "boolean"},
            },
        },
        "correlation",
        "typed-query",
    )

    with pytest.raises(ValidationError) as exc:
        QueryService.validate(
            tenant_id,
            query.id,
            {
                "as_of": "bad-date",
                "captured_at": "bad-datetime",
                "owner_id": "bad-uuid",
                "ratio": True,
                "enabled": "yes",
            },
        )

    assert exc.value.detail["parameters"] == {
        "as_of": "Expected date.",
        "captured_at": "Expected datetime.",
        "owner_id": "Expected uuid.",
        "ratio": "Expected number.",
        "enabled": "Expected boolean.",
    }


@pytest.mark.django_db
def test_definition_lifecycle_replay_and_delete_conflicts(monkeypatch) -> None:
    monkeypatch.setattr(bi_services, "_registry_get", lambda key: MappingProvider())
    tenant_id = uuid.uuid4()
    query = QueryService.create(tenant_id, "actor", query_payload(), "correlation", "create-lifecycle")

    published = QueryService.publish(tenant_id, query.id, "actor", query.version, "correlation", "publish-key")
    replayed = QueryService.publish(tenant_id, query.id, "actor", query.version, "correlation", "publish-key")
    assert replayed.id == published.id
    assert replayed.version == published.version

    with pytest.raises(BIConflict) as exc:
        QueryService.archive(tenant_id, query.id, "actor", published.version, "correlation", "publish-key")
    assert exc.value.error_code == "IDEMPOTENCY_CONFLICT"

    archived = QueryService.archive(tenant_id, query.id, "actor", published.version, "correlation", "archive-key")
    restored = QueryService.restore(tenant_id, query.id, "actor", archived.version, "correlation", "restore-key")
    deleted = QueryService.soft_delete(tenant_id, query.id, "actor", restored.version, "correlation", "delete-key")
    assert deleted.deleted_at is not None
    assert QueryService.soft_delete(tenant_id, query.id, "actor", restored.version, "correlation", "delete-key").id == (
        deleted.id
    )

    with pytest.raises(NotFound):
        QueryService.soft_delete(tenant_id, query.id, "actor", deleted.version, "correlation", "delete-again")


@pytest.mark.django_db
def test_dashboard_layout_and_share_guards_cover_invalid_mutations(monkeypatch) -> None:
    monkeypatch.setattr(bi_services, "_registry_get", lambda key: MappingProvider())
    tenant_id = uuid.uuid4()
    owner_id = "owner"
    query = QueryService.create(tenant_id, owner_id, query_payload(), "correlation", "guard-query-create")
    query = QueryService.publish(tenant_id, query.id, owner_id, query.version, "correlation", "guard-query-publish")
    dashboard = DashboardService.create(
        tenant_id,
        owner_id,
        {"dashboard_code": "GUARDS", "dashboard_name": "Guarded dashboard"},
        "correlation",
        "guard-dashboard-create",
    )

    with pytest.raises(ValidationError) as exc:
        DashboardService.add_widget(
            tenant_id,
            dashboard.id,
            owner_id,
            {
                "query_definition_id": query.id,
                "widget_type": "table",
                "title": "Invalid source",
                "x": "bad",
                "y": 0,
                "width": 6,
                "height": 4,
                "visualization": {"type": "table"},
                "filters": [],
            },
            "correlation",
            "bad-layout-type",
        )
    assert exc.value.detail["layout"] == "x, y, width, and height must be integers."

    widget = DashboardService.add_widget(
        tenant_id,
        dashboard.id,
        owner_id,
        {
            "query_definition_id": query.id,
            "widget_type": "table",
            "title": "Status",
            "x": 0,
            "y": 0,
            "width": 6,
            "height": 4,
            "visualization": {"type": "table"},
            "filters": [],
        },
        "correlation",
        "valid-widget",
    )
    dashboard.refresh_from_db()

    with pytest.raises(ValidationError) as exc:
        DashboardService.reorder_widgets(
            tenant_id,
            dashboard.id,
            owner_id,
            dashboard.version,
            [],
            "correlation",
            "incomplete-layout",
        )
    assert exc.value.detail["widgets"] == "The complete active widget layout is required."

    with pytest.raises(ValidationError) as exc:
        DashboardService.share(
            tenant_id,
            dashboard.id,
            owner_id,
            {"subject_type": "team", "subject_id": "analyst", "access_level": "view"},
            "correlation",
            "bad-share-subject",
        )
    assert exc.value.detail["subject_type"] == "Use user or role."

    with pytest.raises(ValidationError) as exc:
        DashboardService.update_widget(
            tenant_id,
            dashboard.id,
            widget.id,
            owner_id,
            widget.version,
            {"filters": [{"field": "unknown", "operator": "eq", "value": "x"}]},
            "correlation",
            "bad-filter",
        )
    assert exc.value.detail["filters"] == "A filter references a field unavailable from the dataset."


@pytest.mark.django_db
def test_execution_helpers_bound_rows_cache_fallback_and_missing_records(monkeypatch) -> None:
    monkeypatch.setattr(bi_services, "_registry_get", lambda key: MappingProvider())
    tenant_id = uuid.uuid4()
    query = QueryService.create(tenant_id, "actor", query_payload(), "correlation", "helper-query-create")

    rows, truncated = ExecutionService._bound_rows([{"index": index} for index in range(1005)])
    assert len(rows) == 1000
    assert truncated is True

    provider = ProviderWithoutFreshness()
    key = ExecutionService.cache_key(tenant_id, provider, query, {"b": 2, "a": 1})
    assert key.startswith(f"bi:{tenant_id}:2026.1:{query.version}:2026.1:")

    with pytest.raises(NotFound):
        ExecutionService.execute_job(tenant_id, uuid.uuid4())

    with pytest.raises(NotFound):
        ExecutionService.cancel(tenant_id, uuid.uuid4(), "actor", "correlation", "cancel-missing")


@pytest.mark.django_db
def test_query_validation_defaults_and_provider_execution_success_failure_cache_and_purge(monkeypatch) -> None:
    cache.clear()
    provider = MappingProvider()
    monkeypatch.setattr(bi_services, "_registry_get", lambda key: provider)
    tenant_id = uuid.uuid4()
    payload = {
        **query_payload(),
        "parameters_schema": {"status": {"type": "string", "default": "queued"}},
        "cache_ttl_seconds": 60,
    }
    query = QueryService.create(tenant_id, "actor", payload, "correlation", "query-cache-create")
    query = QueryService.publish(tenant_id, query.id, "actor", query.version, "correlation", "query-cache-publish")
    execution = QueryService.enqueue_execution(tenant_id, query.id, "actor", {}, "correlation", "exec-cache")

    succeeded = ExecutionService.execute_job(tenant_id, execution.id)
    assert succeeded.status == "succeeded"
    assert succeeded.result_rows == [{"status": "queued", "count": 3}]
    assert succeeded.effective_query_fingerprint == "validated-fingerprint"
    assert provider.executions == 1
    replay = ExecutionService.execute_job(tenant_id, execution.id)
    assert replay.id == succeeded.id
    assert replay.status == "succeeded"
    assert ExecutionService.get_result(tenant_id, execution.id).row_count == 1

    cached_execution = QueryService.enqueue_execution(
        tenant_id,
        query.id,
        "actor",
        {"status": "queued"},
        "correlation",
        "exec-cache-hit",
    )
    cached = ExecutionService.execute_job(tenant_id, cached_execution.id)
    assert cached.cache_hit is True
    assert provider.executions == 1

    purged = ExecutionService.purge_expired_results(tenant_id, timezone.now() + timedelta(seconds=1))
    assert purged == 2
    succeeded.refresh_from_db()
    assert succeeded.result_rows == []
    assert succeeded.result_purged_at is not None

    failing = MappingProvider(fail_execute=True)
    monkeypatch.setattr(bi_services, "_registry_get", lambda key: failing)
    failed_execution = QueryService.enqueue_execution(
        tenant_id,
        query.id,
        "actor",
        {"status": "failed"},
        "correlation",
        "exec-fail",
    )
    with pytest.raises(CapabilityUnavailable):
        ExecutionService.execute_job(tenant_id, failed_execution.id)
    failed_execution.refresh_from_db()
    assert failed_execution.status == "failed"
    assert failed_execution.error_code == "PROVIDER_FAILURE"


@pytest.mark.django_db
def test_execution_cancel_result_guards_and_completed_replay(monkeypatch) -> None:
    monkeypatch.setattr(bi_services, "_registry_get", lambda key: MappingProvider())
    tenant_id = uuid.uuid4()
    query = QueryService.create(tenant_id, "actor", query_payload(), "correlation", "query-cancel-create")
    query = QueryService.publish(tenant_id, query.id, "actor", query.version, "correlation", "query-cancel-publish")
    execution = QueryService.enqueue_execution(tenant_id, query.id, "actor", {}, "correlation", "exec-cancel")

    with pytest.raises(BIConflict) as exc:
        ExecutionService.get_result(tenant_id, execution.id)
    assert exc.value.error_code == "RESULT_NOT_READY"

    cancelled = ExecutionService.cancel(tenant_id, execution.id, "actor", "correlation", "cancel-key")
    assert cancelled.status == "cancelled"
    assert (
        ExecutionService.cancel(tenant_id, execution.id, "actor", "correlation", "cancel-key-2").status == "cancelled"
    )
    assert ExecutionService.execute_job(tenant_id, execution.id).status == "cancelled"


@pytest.mark.django_db
def test_report_update_archive_restore_and_soft_delete_are_version_guarded() -> None:
    tenant_id = uuid.uuid4()
    actor_id = "owner"
    query = QueryService.create(tenant_id, actor_id, query_payload(), "correlation", "query-create")
    query = QueryService.publish(tenant_id, query.id, actor_id, query.version, "correlation", "query-publish")
    report = ReportService.create(
        tenant_id,
        actor_id,
        {
            "report_code": "OPS_STATUS",
            "report_name": "Ops status",
            "report_type": "table",
            "query_definition_id": query.id,
            "visualization": {"type": "table"},
        },
        "correlation",
        "report-create",
    )
    report = ReportService.publish(tenant_id, report.id, actor_id, report.version, "correlation", "report-publish")
    updated = ReportService.update(
        tenant_id,
        report.id,
        actor_id,
        report.version,
        {"report_name": "Updated status"},
        "correlation",
        "report-update",
    )
    assert updated.state == "draft"
    with pytest.raises(BIConflict) as exc:
        ReportService.archive(tenant_id, updated.id, actor_id, 1, "correlation", "report-archive-stale")
    assert exc.value.error_code == "VERSION_CONFLICT"

    republished = ReportService.publish(
        tenant_id,
        updated.id,
        actor_id,
        updated.version,
        "correlation",
        "report-republish",
    )
    archived = ReportService.archive(
        tenant_id,
        republished.id,
        actor_id,
        republished.version,
        "correlation",
        "report-archive",
    )
    restored = ReportService.restore(
        tenant_id,
        archived.id,
        actor_id,
        archived.version,
        "correlation",
        "report-restore",
    )
    deleted = ReportService.soft_delete(
        tenant_id,
        restored.id,
        actor_id,
        restored.version,
        "correlation",
        "report-delete",
    )
    assert deleted.deleted_at is not None
    assert deleted.state == "archived"


@pytest.mark.django_db
def test_dashboard_share_reorder_and_execution_deduplicate_widget_queries() -> None:
    tenant_id = uuid.uuid4()
    owner_id = "owner"
    editor_id = "editor"
    query = QueryService.create(tenant_id, owner_id, query_payload(), "correlation", "query-create")
    query = QueryService.publish(tenant_id, query.id, owner_id, query.version, "correlation", "query-publish")
    dashboard = DashboardService.create(
        tenant_id,
        owner_id,
        {"dashboard_code": "OPS_SHARED", "dashboard_name": "Operations"},
        "correlation",
        "dashboard-create",
    )
    widget_one = DashboardService.add_widget(
        tenant_id,
        dashboard.id,
        owner_id,
        {
            "query_definition_id": query.id,
            "widget_type": "table",
            "title": "Status A",
            "x": 0,
            "y": 0,
            "width": 6,
            "height": 4,
            "visualization": {"type": "table"},
            "filters": [],
            "display_order": 0,
        },
        "correlation",
        "widget-a",
    )
    widget_two = DashboardService.add_widget(
        tenant_id,
        dashboard.id,
        owner_id,
        {
            "query_definition_id": query.id,
            "widget_type": "table",
            "title": "Status B",
            "x": 6,
            "y": 0,
            "width": 6,
            "height": 4,
            "visualization": {"type": "table"},
            "filters": [],
            "display_order": 1,
        },
        "correlation",
        "widget-b",
    )
    share = DashboardService.share(
        tenant_id,
        dashboard.id,
        owner_id,
        {"subject_type": "user", "subject_id": editor_id, "access_level": "edit"},
        "correlation",
        "share-editor",
    )
    assert (
        DashboardService.update_share(
            tenant_id,
            dashboard.id,
            share.id,
            owner_id,
            {"access_level": "view"},
            "correlation",
            "share-update",
        ).access_level
        == "view"
    )

    with pytest.raises(Exception):
        DashboardService.update(
            tenant_id,
            dashboard.id,
            "stranger",
            dashboard.version,
            {"dashboard_name": "Denied"},
            "correlation",
            "dashboard-update-denied",
        )

    dashboard.refresh_from_db()
    reordered = DashboardService.reorder_widgets(
        tenant_id,
        dashboard.id,
        owner_id,
        dashboard.version,
        [
            {"id": str(widget_two.id), "x": 6, "y": 4, "width": 6, "height": 4},
            {"id": str(widget_one.id), "x": 0, "y": 4, "width": 6, "height": 4},
        ],
        "correlation",
        "widget-reorder",
    )
    published = DashboardService.publish(
        tenant_id,
        dashboard.id,
        owner_id,
        reordered.version,
        "correlation",
        "dashboard-publish",
    )
    executions = DashboardService.enqueue_execution(
        tenant_id,
        published.id,
        owner_id,
        {},
        "correlation",
        "dashboard-execution",
    )
    assert len(executions) == 1
    assert executions[0].dashboard_id == dashboard.id
    revoked = DashboardService.revoke_share(
        tenant_id,
        dashboard.id,
        share.id,
        owner_id,
        "correlation",
        "share-revoke",
    )
    assert revoked.revoked_at is not None


@pytest.mark.django_db
def test_dashboard_widget_update_remove_share_reuse_and_publish_guards() -> None:
    tenant_id = uuid.uuid4()
    actor_id = "owner"
    query = QueryService.create(tenant_id, actor_id, query_payload(), "correlation", "dash-query-create")
    query = QueryService.publish(tenant_id, query.id, actor_id, query.version, "correlation", "dash-query-publish")
    dashboard = DashboardService.create(
        tenant_id,
        actor_id,
        {"dashboard_code": "OPS_WIDGETS", "dashboard_name": "Operations widgets"},
        "correlation",
        "dash-create",
    )

    with pytest.raises(BIConflict) as exc:
        DashboardService.publish(
            tenant_id,
            dashboard.id,
            actor_id,
            dashboard.version,
            "correlation",
            "dash-publish-empty",
        )
    assert exc.value.error_code == "PUBLISH_GUARD_FAILED"
    report = ReportService.create(
        tenant_id,
        actor_id,
        {
            "report_code": "WIDGET_REPORT",
            "report_name": "Widget report",
            "report_type": "table",
            "query_definition_id": query.id,
            "visualization": {"type": "table"},
        },
        "correlation",
        "widget-report-create",
    )

    widget = DashboardService.add_widget(
        tenant_id,
        dashboard.id,
        actor_id,
        {
            "query_definition_id": query.id,
            "widget_type": "table",
            "title": "Status",
            "x": 0,
            "y": 0,
            "width": 6,
            "height": 4,
            "visualization": {"type": "table"},
            "filters": [],
        },
        "correlation",
        "widget-create",
    )
    with pytest.raises(ValidationError):
        DashboardService.update_widget(
            tenant_id,
            dashboard.id,
            widget.id,
            actor_id,
            widget.version,
            {"query_definition_id": query.id, "report_id": report.id},
            "correlation",
            "widget-invalid-source",
        )

    updated = DashboardService.update_widget(
        tenant_id,
        dashboard.id,
        widget.id,
        actor_id,
        widget.version,
        {"title": "Renamed", "x": 6, "y": 0, "width": 6, "height": 4},
        "correlation",
        "widget-update",
    )
    assert updated.title == "Renamed"
    removed = DashboardService.remove_widget(
        tenant_id, dashboard.id, widget.id, actor_id, "correlation", "widget-remove"
    )
    assert removed.deleted_at is not None
    with pytest.raises(BIConflict):
        DashboardService.publish(
            tenant_id,
            dashboard.id,
            actor_id,
            dashboard.version + 3,
            "correlation",
            "dash-publish-stale-after-remove",
        )

    share = DashboardService.share(
        tenant_id,
        dashboard.id,
        actor_id,
        {"subject_type": "role", "subject_id": "Analyst", "access_level": "view"},
        "correlation",
        "share-role",
    )
    reused = DashboardService.share(
        tenant_id,
        dashboard.id,
        actor_id,
        {"subject_type": "role", "subject_id": "Analyst", "access_level": "edit"},
        "correlation",
        "share-role-reuse",
    )
    assert reused.id == share.id
    assert reused.access_level == "edit"
    with pytest.raises(ValidationError):
        DashboardService.update_share(
            tenant_id,
            dashboard.id,
            share.id,
            actor_id,
            {"expires_at": timezone.now() - timedelta(seconds=1)},
            "correlation",
            "share-expired",
        )
    DashboardService.revoke_share(tenant_id, dashboard.id, share.id, actor_id, "correlation", "share-revoke-once")
    assert (
        DashboardService.revoke_share(
            tenant_id, dashboard.id, share.id, actor_id, "correlation", "share-revoke-replay"
        ).revoked_at
        is not None
    )
