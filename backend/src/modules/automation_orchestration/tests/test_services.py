"""Business-engine coverage for definitions, schedules and durable execution."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, OutboxEvent

from ..models import (
    OrchestrationConfiguration,
    OrchestrationConfigurationAudit,
    OrchestrationConfigurationVersion,
    OrchestrationEvent,
    OrchestrationReconciliation,
    OrchestrationTaskRun,
    ReconciliationStatus,
    RetryAttempt,
)
from ..node_registry import (
    CORE_CAPABILITY,
    CommitState,
    NodeDescriptor,
    NodeExecutionContext,
    NodeExecutionResult,
    NodeResultStatus,
    RetrySafety,
    register_node,
    unregister_node,
)
from ..services import (
    _CIRCUITS,
    DEFAULT_CONFIGURATION,
    ConfigurationService,
    CronExpression,
    DefinitionQueryService,
    DefinitionService,
    ExecutionService,
    IdempotencyConflictError,
    ScheduleService,
    ServiceValidationError,
    StateConflictError,
    _edge_matches,
    _event,
    _execute_node_bounded,
    _published_contract_version,
    _resolve_data_mapping,
    _validate_mapping,
    _worker_authorized,
    _zone,
)

pytestmark = pytest.mark.django_db


RECONCILER_SHOULD_RESOLVE = True


def reconciliation_adapter(**_kwargs):
    return {"resolved": True, "provider_reference": "confirmed"} if RECONCILER_SHOULD_RESOLVE else {"resolved": False}


def _published_graph(tenant_id: uuid.UUID, actor_id: uuid.UUID, *, key: str = "order-import"):
    definition = DefinitionService.create_definition(
        tenant_id,
        actor_id,
        {
            "key": key,
            "name": "Order import",
            "input_schema": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
                "additionalProperties": False,
            },
            "output_schema": {"type": "object", "additionalProperties": True},
        },
    )
    node = DefinitionService.add_node(
        tenant_id,
        definition.id,
        actor_id,
        {
            "key": "load",
            "name": "Load order",
            "node_type": "internal",
            "handler_key": "core.passthrough",
            "config": {},
            "input_mapping": {"order_id": "$input.order_id"},
        },
    )
    published = DefinitionService.publish(tenant_id, definition.id, actor_id, "publish-1")
    return published, node


def _descriptor(handler_key: str, *, retry_safety: RetrySafety = RetrySafety.IDEMPOTENT) -> NodeDescriptor:
    object_schema = {"type": "object", "additionalProperties": True}
    return NodeDescriptor(
        key=handler_key,
        display_name="Test executor",
        category="Tests",
        description="Deterministic orchestration service test executor",
        configuration_schema={"type": "object", "additionalProperties": False},
        input_schema=object_schema,
        output_schema=object_schema,
        icon_key="test",
        capability=CORE_CAPABILITY,
        source_module="automation_orchestration",
        retry_safety=retry_safety,
    )


def _published_custom_graph(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    handler_key: str,
    *,
    max_attempts: int = 3,
    retry_initial_delay_seconds: int = 1,
):
    definition = DefinitionService.create_definition(
        tenant_id,
        actor_id,
        {
            "key": f"graph-{uuid.uuid4().hex[:12]}",
            "name": "Custom graph",
            "input_schema": {"type": "object", "additionalProperties": True},
            "output_schema": {"type": "object", "additionalProperties": True},
        },
    )
    node = DefinitionService.add_node(
        tenant_id,
        definition.id,
        actor_id,
        {
            "key": "root",
            "name": "Root",
            "node_type": "internal",
            "handler_key": handler_key,
            "max_attempts": max_attempts,
            "retry_initial_delay_seconds": retry_initial_delay_seconds,
            "retry_max_delay_seconds": retry_initial_delay_seconds,
        },
    )
    return DefinitionService.publish(tenant_id, definition.id, actor_id, f"publish-{uuid.uuid4()}"), node


def test_create_definition_accepts_required_input_schema_and_is_tenant_scoped() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    definition = DefinitionService.create_definition(
        tenant_id,
        actor_id,
        {
            "key": "required-input",
            "name": "Required input",
            "input_schema": {
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "string"}},
            },
        },
    )
    assert definition.tenant_id == tenant_id
    assert definition.status == "draft"
    assert OrchestrationEvent.objects.for_tenant(tenant_id).filter(event_type="definition.created").exists()
    with pytest.raises(ObjectDoesNotExist):
        DefinitionService.update_draft(uuid.uuid4(), definition.id, actor_id, {"name": "No"}, "cross-tenant")


def test_configuration_preview_update_rollback_and_disabled_scope_are_audited() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    preview = ConfigurationService.preview(
        tenant_id,
        {"document": {"defaults": {"max_parallel_tasks": 2}}},
        environment="development",
    )
    assert preview["valid"] is True
    assert preview["changed_sections"] == ["defaults"]

    first = ConfigurationService.update(
        tenant_id,
        actor_id,
        "cfg-create",
        {
            "document": {"defaults": {"max_parallel_tasks": 2}},
            "enabled": False,
            "rollout_percentage": 25,
            "allowed_roles": ["ops-admin"],
        },
        environment="development",
    )
    assert first.version == 1
    assert first.rollout_percentage == 25
    with pytest.raises(StateConflictError, match="disabled"):
        ConfigurationService.effective_document(tenant_id, environment="development")

    second = ConfigurationService.update(
        tenant_id,
        actor_id,
        "cfg-enable",
        {"document": {"defaults": {"max_parallel_tasks": 3}}, "enabled": True},
        environment="development",
    )
    assert second.version == 2
    assert (
        ConfigurationService.effective_document(tenant_id, environment="development")["defaults"]["max_parallel_tasks"]
        == 3
    )

    rolled_back = ConfigurationService.rollback(
        tenant_id,
        actor_id,
        "cfg-rollback",
        1,
        environment="development",
    )
    assert rolled_back.version == 3
    assert rolled_back.enabled is False
    assert OrchestrationConfigurationVersion.objects.for_tenant(tenant_id).filter(rollback_of__version=1).exists()
    assert OrchestrationConfigurationAudit.objects.for_tenant(tenant_id).filter(action="rollback").exists()


def test_configuration_validation_rejects_unsafe_limits_and_correlation_reuse() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(ServiceValidationError, match="cannot exceed"):
        ConfigurationService.validate_document({"limits": {"parallel_tasks_min": 10, "parallel_tasks_max": 2}})
    with pytest.raises(ServiceValidationError, match="rollout_percentage"):
        ConfigurationService.update(
            tenant_id,
            actor_id,
            "cfg-bad-rollout",
            {"document": {}, "rollout_percentage": 101},
            environment="development",
        )
    with pytest.raises(ServiceValidationError, match="correlation_id"):
        ConfigurationService.update(
            tenant_id,
            actor_id,
            "",
            {"document": {}},
            environment="development",
        )


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ([], "must be an object"),
        ({"unknown": {}}, "Unknown configuration field"),
        ({"limits": []}, "must be an object"),
        ({"limits": {"page_size_default": 200, "page_size_max": 100}}, "cannot exceed"),
        ({"limits": {"retry_multiplier_min": 0.5}}, "Retry multiplier limits"),
        ({"defaults": {"retry_jitter_ratio": 2}}, "Retry jitter ratio"),
        ({"defaults": {"retry_initial_delay_seconds": 60, "retry_max_delay_seconds": 10}}, "Retry maximum delay"),
        ({"defaults": {"edge_condition": "never"}}, "not allowed"),
        ({"integrations": {"allowed_source_modules": []}}, "source module"),
        ({"integrations": {"worker_authorized_capabilities": "all"}}, "allow-list"),
        ({"integrations": {"execution_timeout_seconds": 999999}}, "outside configured limits"),
        ({"integrations": {"circuit_failure_threshold": 0}}, "between 1 and 100"),
        ({"scheduler": {"cron_fields": 6}}, "five-field"),
        ({"scheduler": {"enqueue_misfire_policies": ["replay_all"]}}, "misfire policies"),
        ({"scheduler": {"forbid_overlap_policy": "queue"}}, "overlap policy"),
        ({"health": {"outbox_stale_seconds": 0}}, "Unknown configuration field"),
        ({"ui": {"zoom_default": 0}}, "ui.zoom_default"),
        ({"ui": {"zoom_min": 5, "zoom_default": 2, "zoom_max": 4}}, "UI zoom default"),
        ({"workflow": {"definition_transitions": []}}, "definition_transitions must be an object"),
    ],
)
def test_configuration_validation_rejects_contract_drift_and_unsafe_dependencies(payload, match) -> None:
    with pytest.raises(ServiceValidationError, match=match):
        ConfigurationService.validate_document(payload)


def test_configuration_export_defaults_and_existing_document_include_audit_metadata() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    default_export = ConfigurationService.export_configuration(tenant_id, environment="development")
    assert default_export["version"] == 0
    assert default_export["enabled"] is True
    assert default_export["document"] == DEFAULT_CONFIGURATION

    ConfigurationService.update(
        tenant_id,
        actor_id,
        "cfg-export",
        {
            "document": {"defaults": {"max_parallel_tasks": 4}},
            "allowed_roles": ["automation-admin"],
        },
        environment="development",
        cohort="beta",
    )

    exported = ConfigurationService.export_configuration(tenant_id, environment="development", cohort="beta")
    assert exported["version"] == 1
    assert exported["document"]["defaults"]["max_parallel_tasks"] == 4
    assert exported["allowed_roles"] == ["automation-admin"]
    assert exported["updated_by"] == str(actor_id)
    assert exported["correlation_id"] == "cfg-export"
    assert exported["updated_at"]


def test_event_enforcement_uses_disabled_configuration_document_without_failing_open() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    ConfigurationService.update(
        tenant_id,
        actor_id,
        "cfg-disable-for-events",
        {
            "document": {"limits": {"event_metadata_bytes": DEFAULT_CONFIGURATION["limits"]["event_metadata_bytes"]}},
            "enabled": False,
        },
        environment="development",
    )

    event = _event(
        tenant_id,
        "definition",
        uuid.uuid4(),
        "definition.created",
        actor_id=actor_id,
        correlation_id="disabled-event-policy",
        payload={"unsafe_secret": "do-not-store", "safe": "value"},  # pragma: allowlist secret
    )

    assert event.payload == {"unsafe_secret": "[REDACTED]", "safe": "value"}  # pragma: allowlist secret
    assert OrchestrationConfiguration.objects.for_tenant(tenant_id).get(environment="development").enabled is False


def test_event_enforcement_uses_disabled_runtime_scope_policy(settings) -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    settings.SARAISE_MODE = "saas"
    ConfigurationService.update(
        tenant_id,
        actor_id,
        "cfg-disable-prod-for-events",
        {
            "document": {"limits": {"event_metadata_bytes": DEFAULT_CONFIGURATION["limits"]["event_metadata_bytes"]}},
            "enabled": False,
        },
        environment="saas",
        cohort="all",
    )
    OrchestrationConfiguration.objects.for_tenant(tenant_id).filter(environment="saas", cohort="all").update(
        document=ConfigurationService.validate_document({"limits": {"event_metadata_bytes": 1}})
    )

    with pytest.raises(ServiceValidationError) as caught:
        _event(
            tenant_id,
            "definition",
            uuid.uuid4(),
            "definition.created",
            actor_id=actor_id,
            correlation_id="disabled-prod-event-policy",
            payload={"safe": "value"},
        )

    assert caught.value.code == "EVENT_TOO_LARGE"
    assert OrchestrationConfiguration.objects.for_tenant(tenant_id).get(environment="saas").enabled is False


def test_node_edit_increments_revision_and_unknown_handler_is_rejected() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    definition = DefinitionService.create_definition(tenant_id, actor_id, {"key": "graph", "name": "Graph"})
    with pytest.raises(ServiceValidationError, match="registered"):
        DefinitionService.add_node(
            tenant_id,
            definition.id,
            actor_id,
            {"key": "missing", "name": "Missing", "node_type": "extension", "handler_key": "missing.node"},
        )
    node = DefinitionService.add_node(
        tenant_id,
        definition.id,
        actor_id,
        {"key": "root", "name": "Root", "node_type": "internal", "handler_key": "core.passthrough"},
    )
    definition.refresh_from_db()
    assert definition.graph_revision == 2
    DefinitionService.update_node(tenant_id, node.id, actor_id, {"name": "Renamed"})
    definition.refresh_from_db()
    assert definition.graph_revision == 3


def test_definition_service_rejects_invalid_inputs_unknown_fields_and_revision_conflicts() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(ServiceValidationError, match="tenant_id"):
        DefinitionService.create_definition("not-a-uuid", actor_id, {"key": "bad", "name": "Bad"})
    with pytest.raises(ServiceValidationError, match="data must be an object"):
        DefinitionService.create_definition(tenant_id, actor_id, [])
    with pytest.raises(ServiceValidationError, match="name and key"):
        DefinitionService.create_definition(tenant_id, actor_id, {"key": "", "name": ""})
    with pytest.raises(ServiceValidationError, match="Unknown definition fields"):
        DefinitionService.create_definition(tenant_id, actor_id, {"key": "bad-field", "name": "Bad", "tenant_id": "x"})
    with pytest.raises(ServiceValidationError, match="labels"):
        DefinitionService.create_definition(
            tenant_id, actor_id, {"key": "labels", "name": "Labels", "labels": {"x": 1}}
        )

    definition = DefinitionService.create_definition(tenant_id, actor_id, {"key": "revision", "name": "Revision"})
    with pytest.raises(StateConflictError, match="expected"):
        DefinitionService.update_draft(
            tenant_id,
            definition.id,
            actor_id,
            {"name": "Revision v2"},
            "bad-revision",
            expected_revision=999,
        )
    with pytest.raises(ServiceValidationError, match="Protected or unknown fields"):
        DefinitionService.update_draft(tenant_id, definition.id, actor_id, {"status": "published"}, "bad-field")
    with pytest.raises(ServiceValidationError, match="Unsupported mapping"):
        DefinitionService.update_draft(
            tenant_id,
            definition.id,
            actor_id,
            {"output_mapping": {"bad": "$unsupported.source"}},
            "bad-mapping",
        )


def test_definition_query_service_applies_exact_boolean_version_and_search_filters() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    first = DefinitionService.create_definition(tenant_id, actor_id, {"key": "query-a", "name": "Alpha ledger"})
    second = DefinitionService.create_definition(tenant_id, actor_id, {"key": "query-b", "name": "Beta ledger"})
    type(first).objects.for_tenant(tenant_id).filter(id=first.id).update(is_current=True)

    queryset = DefinitionQueryService.list_queryset(
        tenant_id,
        {"key": "query-a", "status": "draft", "is_current": "true", "version": "1", "search": "Alpha"},
    )

    assert list(queryset.values_list("id", flat=True)) == [first.id]
    assert second.id not in queryset.values_list("id", flat=True)


def test_node_and_edge_service_guards_unknown_missing_cross_definition_and_removal_paths() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    definition = DefinitionService.create_definition(tenant_id, actor_id, {"key": "guarded-graph", "name": "Guarded"})
    other = DefinitionService.create_definition(tenant_id, actor_id, {"key": "other-graph", "name": "Other"})
    root = DefinitionService.add_node(
        tenant_id,
        definition.id,
        actor_id,
        {"key": "root", "name": "Root", "node_type": "internal", "handler_key": "core.passthrough"},
    )
    child = DefinitionService.add_node(
        tenant_id,
        definition.id,
        actor_id,
        {"key": "child", "name": "Child", "node_type": "internal", "handler_key": "core.passthrough"},
    )
    other_node = DefinitionService.add_node(
        tenant_id,
        other.id,
        actor_id,
        {"key": "other", "name": "Other", "node_type": "internal", "handler_key": "core.passthrough"},
    )
    with pytest.raises(ServiceValidationError, match="Unknown node fields"):
        DefinitionService.add_node(
            tenant_id,
            definition.id,
            actor_id,
            {
                "key": "bad-node",
                "name": "Bad",
                "node_type": "internal",
                "handler_key": "core.passthrough",
                "extra": True,
            },
        )
    with pytest.raises(ServiceValidationError, match="key, name and handler_key"):
        DefinitionService.add_node(
            tenant_id,
            definition.id,
            actor_id,
            {"key": "", "name": "", "node_type": "internal", "handler_key": ""},
        )
    with pytest.raises(ServiceValidationError, match="Unknown edge fields"):
        DefinitionService.add_edge(
            tenant_id,
            definition.id,
            actor_id,
            {"upstream_node_id": root.id, "downstream_node_id": child.id, "extra": True},
        )
    with pytest.raises(ServiceValidationError, match="endpoints"):
        DefinitionService.add_edge(
            tenant_id,
            definition.id,
            actor_id,
            {"upstream_node_id": root.id, "downstream_node_id": other_node.id},
        )

    edge = DefinitionService.add_edge(
        tenant_id,
        definition.id,
        actor_id,
        {"upstream_node_id": root.id, "downstream_node_id": child.id},
    )
    updated_edge = DefinitionService.update_edge(tenant_id, edge.id, actor_id, {"priority": 9})
    assert updated_edge.priority == 9
    assert DefinitionService.remove_edge(tenant_id, edge.id, actor_id).is_deleted is True
    assert DefinitionService.remove_node(tenant_id, child.id, actor_id).is_deleted is True


def test_graph_publication_and_lifecycle_guards_report_structured_issues() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    empty = DefinitionService.create_definition(tenant_id, actor_id, {"key": "empty", "name": "Empty"})
    report = DefinitionService.validate_graph(tenant_id, empty.id)
    assert report["valid"] is False
    assert report["issues"][0]["code"] == "GRAPH_EMPTY"
    with pytest.raises(ServiceValidationError, match="Graph validation failed"):
        DefinitionService.publish(tenant_id, empty.id, actor_id, "publish-empty")
    with pytest.raises(StateConflictError, match="published or retired"):
        DefinitionService.clone_version(tenant_id, empty.id, actor_id)
    with pytest.raises(StateConflictError, match="published"):
        DefinitionService.retire(tenant_id, empty.id, actor_id, "retire-draft")

    published, _ = _published_graph(tenant_id, actor_id, key="guard-retire")
    schedule = ScheduleService.create_schedule(
        tenant_id,
        actor_id,
        {"definition_id": published.id, "name": "Active guard", "input": {"order_id": "1"}},
    )
    with pytest.raises(StateConflictError, match="active schedules"):
        DefinitionService.retire(tenant_id, published.id, actor_id, "retire-active")
    with pytest.raises(StateConflictError, match="draft or retired"):
        DefinitionService.delete_draft(tenant_id, published.id, actor_id)
    type(schedule).objects.for_tenant(tenant_id).filter(id=schedule.id).update(status="paused")
    retired = DefinitionService.retire(tenant_id, published.id, actor_id, "retire-after-pause")
    assert DefinitionService.delete_draft(tenant_id, retired.id, actor_id).is_deleted is True


def test_cycle_is_rejected_and_rolled_back() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    definition = DefinitionService.create_definition(tenant_id, actor_id, {"key": "cycle", "name": "Cycle"})
    one = DefinitionService.add_node(
        tenant_id,
        definition.id,
        actor_id,
        {"key": "one", "name": "One", "node_type": "internal", "handler_key": "core.passthrough"},
    )
    two = DefinitionService.add_node(
        tenant_id,
        definition.id,
        actor_id,
        {"key": "two", "name": "Two", "node_type": "internal", "handler_key": "core.passthrough"},
    )
    DefinitionService.add_edge(
        tenant_id,
        definition.id,
        actor_id,
        {"upstream_node_id": one.id, "downstream_node_id": two.id},
    )
    with pytest.raises(ServiceValidationError, match="invalid graph"):
        DefinitionService.add_edge(
            tenant_id,
            definition.id,
            actor_id,
            {"upstream_node_id": two.id, "downstream_node_id": one.id},
        )
    assert definition.edges.filter(is_deleted=False).count() == 1


def test_publish_pins_contract_clone_preserves_graph_and_retire_is_guarded() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    published, _ = _published_graph(tenant_id, actor_id)
    assert published.contract_snapshot["node_contracts"]["load"]["handler_key"] == "core.passthrough"
    clone = DefinitionService.clone_version(tenant_id, published.id, actor_id)
    assert clone.version == 2
    assert clone.status == "draft"
    assert clone.nodes.count() == 1
    retired = DefinitionService.retire(tenant_id, published.id, actor_id, "retire-1")
    assert retired.status == "retired"
    with pytest.raises(StateConflictError):
        DefinitionService.update_draft(tenant_id, retired.id, actor_id, {"name": "No"}, "immutable")


def test_cron_timezone_and_schedule_lifecycle() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    published, _ = _published_graph(tenant_id, actor_id, key="scheduled")
    schedule = ScheduleService.create_schedule(
        tenant_id,
        actor_id,
        {
            "definition_id": published.id,
            "name": "Hourly",
            "cron_expression": "0 * * * *",
            "timezone": "Asia/Kolkata",
            "misfire_policy": "run_once",
            "concurrency_policy": "forbid",
            "input": {"order_id": "A-1"},
        },
    )
    assert schedule.next_run_at > timezone.now()
    paused = ScheduleService.pause_schedule(tenant_id, schedule.id, actor_id, "pause-1")
    assert paused.status == "paused"
    with pytest.raises(StateConflictError, match="Retire"):
        ScheduleService.delete_schedule(tenant_id, schedule.id, actor_id)
    ScheduleService.retire_schedule(tenant_id, schedule.id, actor_id, "retire-schedule")
    assert ScheduleService.delete_schedule(tenant_id, schedule.id, actor_id).is_deleted
    with pytest.raises(ServiceValidationError, match="IANA"):
        ScheduleService.create_schedule(
            tenant_id,
            actor_id,
            {
                "definition_id": published.id,
                "name": "Bad",
                "cron_expression": "* * * * *",
                "timezone": "Mars/Olympus",
                "input": {"order_id": "1"},
            },
        )


def test_due_claim_recomputes_next_occurrence_and_is_tenant_isolated() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    published, _ = _published_graph(tenant_id, actor_id, key="due")
    schedule = ScheduleService.create_schedule(
        tenant_id,
        actor_id,
        {
            "definition_id": published.id,
            "name": "Due",
            "cron_expression": "* * * * *",
            "timezone": "UTC",
            "misfire_policy": "run_once",
            "input": {"order_id": "1"},
        },
    )
    before = timezone.now() - timedelta(minutes=5)
    type(schedule).objects.for_tenant(tenant_id).filter(id=schedule.id).update(next_run_at=before)
    assert ScheduleService.claim_due_schedules(uuid.uuid4(), timezone.now(), 10) == []
    claims = ScheduleService.claim_due_schedules(tenant_id, timezone.now(), 10)
    assert claims[0].schedule_id == schedule.id
    schedule.refresh_from_db()
    assert schedule.next_run_at > timezone.now() - timedelta(seconds=2)


def test_due_schedule_enqueue_is_idempotent_and_skips_forbidden_overlap() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    published, _ = _published_graph(tenant_id, actor_id, key="due-enqueue")
    schedule = ScheduleService.create_schedule(
        tenant_id,
        actor_id,
        {
            "definition_id": published.id,
            "name": "Due enqueue",
            "cron_expression": "* * * * *",
            "timezone": "UTC",
            "misfire_policy": "run_once",
            "concurrency_policy": "allow",
            "input": {"order_id": "1"},
        },
    )
    scheduled_for = timezone.now()
    first = ScheduleService.enqueue_due_schedule(tenant_id, schedule.id, scheduled_for)
    duplicate = ScheduleService.enqueue_due_schedule(tenant_id, schedule.id, scheduled_for)
    assert first is not None
    assert duplicate is not None
    assert duplicate.id == first.id

    overlap_schedule = ScheduleService.create_schedule(
        tenant_id,
        actor_id,
        {
            "definition_id": published.id,
            "name": "Overlap",
            "cron_expression": "* * * * *",
            "timezone": "UTC",
            "misfire_policy": "run_once",
            "concurrency_policy": "forbid",
            "input": {"order_id": "1"},
        },
    )
    ExecutionService.start_run(
        tenant_id,
        published.id,
        actor_id,
        {"order_id": "1"},
        "overlap-existing",
        "schedule",
        schedule_id=overlap_schedule.id,
    )
    assert ScheduleService.enqueue_due_schedule(tenant_id, overlap_schedule.id, scheduled_for) is None
    assert (
        OrchestrationEvent.objects.for_tenant(tenant_id)
        .filter(aggregate_id=overlap_schedule.id, event_type="schedule.overlap_skipped")
        .exists()
    )
    with pytest.raises(ServiceValidationError, match="timezone-aware"):
        ScheduleService.enqueue_due_schedule(tenant_id, schedule.id, timezone.now().replace(tzinfo=None))


def test_schedule_update_and_claim_guards_invalid_state_and_inputs() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    published, _ = _published_graph(tenant_id, actor_id, key="schedule-guards")
    schedule = ScheduleService.create_schedule(
        tenant_id,
        actor_id,
        {"definition_id": published.id, "name": "Guard schedule", "input": {"order_id": "1"}},
    )
    with pytest.raises(ServiceValidationError, match="At least one change"):
        ScheduleService.update_schedule(tenant_id, schedule.id, actor_id, {})
    with pytest.raises(ServiceValidationError, match="Protected or unknown"):
        ScheduleService.update_schedule(tenant_id, schedule.id, actor_id, {"status": "paused"})
    draft = DefinitionService.clone_version(tenant_id, published.id, actor_id)
    with pytest.raises(StateConflictError, match="published definition"):
        ScheduleService.update_schedule(tenant_id, schedule.id, actor_id, {"definition_id": draft.id})
    with pytest.raises(ServiceValidationError, match="input"):
        ScheduleService.update_schedule(tenant_id, schedule.id, actor_id, {"input": []})
    paused = ScheduleService.pause_schedule(tenant_id, schedule.id, actor_id, "guard-pause")
    resumed = ScheduleService.resume_schedule(tenant_id, paused.id, actor_id, "guard-resume")
    assert resumed.status == "active"
    retired = ScheduleService.retire_schedule(tenant_id, resumed.id, actor_id, "guard-retire")
    with pytest.raises(StateConflictError, match="Retired"):
        ScheduleService.update_schedule(tenant_id, retired.id, actor_id, {"name": "No"})
    with pytest.raises(StateConflictError, match="Cannot transition"):
        ScheduleService.pause_schedule(tenant_id, retired.id, actor_id, "guard-pause-retired")
    with pytest.raises(ServiceValidationError, match="timezone-aware"):
        ScheduleService.claim_due_schedules(tenant_id, timezone.now().replace(tzinfo=None), 1)
    with pytest.raises(ServiceValidationError, match="batch_size"):
        ScheduleService.claim_due_schedules(tenant_id, timezone.now(), 0)


def test_start_run_is_idempotent_and_atomically_creates_job_outbox_and_tasks() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    published, _ = _published_graph(tenant_id, actor_id, key="execute")
    run = ExecutionService.start_run(tenant_id, published.id, actor_id, {"order_id": "42"}, "request-42", "manual")
    duplicate = ExecutionService.start_run(
        tenant_id, published.id, actor_id, {"order_id": "42"}, "request-42", "manual"
    )
    assert duplicate.id == run.id
    assert OrchestrationTaskRun.objects.for_tenant(tenant_id).filter(run=run).count() == 1
    job = AsyncJob.objects.for_tenant(tenant_id).get(command="automation_orchestration.execute_run")
    assert OutboxEvent.objects.for_tenant(tenant_id).filter(aggregate_id=job.id).exists()
    with pytest.raises(IdempotencyConflictError):
        ExecutionService.start_run(tenant_id, published.id, actor_id, {"order_id": "different"}, "request-42", "manual")


def test_start_and_execute_run_guard_invalid_inputs_states_and_schedule_mismatch() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    draft = DefinitionService.create_definition(tenant_id, actor_id, {"key": "draft-run", "name": "Draft run"})
    with pytest.raises(ServiceValidationError, match="idempotency_key"):
        ExecutionService.start_run(tenant_id, draft.id, actor_id, {}, "", "manual")
    with pytest.raises(ServiceValidationError, match="input"):
        ExecutionService.start_run(tenant_id, draft.id, actor_id, [], "bad-input", "manual")
    with pytest.raises(StateConflictError, match="published"):
        ExecutionService.start_run(tenant_id, draft.id, actor_id, {}, "draft-start", "manual")

    published, _ = _published_graph(tenant_id, actor_id, key="run-guards")
    other, _ = _published_graph(tenant_id, actor_id, key="run-guards-other")
    schedule = ScheduleService.create_schedule(
        tenant_id,
        actor_id,
        {"definition_id": other.id, "name": "Other schedule", "input": {"order_id": "1"}},
    )
    with pytest.raises(ServiceValidationError, match="schedule and definition"):
        ExecutionService.start_run(
            tenant_id,
            published.id,
            actor_id,
            {"order_id": "1"},
            "schedule-mismatch",
            "schedule",
            schedule_id=schedule.id,
        )

    run = ExecutionService.start_run(tenant_id, published.id, actor_id, {"order_id": "1"}, "terminal-run", "manual")
    ExecutionService.cancel_run(tenant_id, run.id, actor_id, "terminal-cancel")
    assert ExecutionService.execute_run(tenant_id, run.id).status == "cancelled"


def test_execution_resolves_task_persists_attempt_and_finalizes_output() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    published, _ = _published_graph(tenant_id, actor_id, key="complete")
    run = ExecutionService.start_run(tenant_id, published.id, actor_id, {"order_id": "42"}, "complete-42", "manual")
    ExecutionService.execute_run(tenant_id, run.id)
    task = OrchestrationTaskRun.objects.for_tenant(tenant_id).get(run=run)
    assert task.status == "queued"
    attempt = RetryAttempt.objects.for_tenant(tenant_id).get(task_run=task)
    operation_token = task.operation_token
    ExecutionService.execute_task(tenant_id, attempt.id)
    run.refresh_from_db()
    task.refresh_from_db()
    attempt.refresh_from_db()
    assert run.status == "succeeded"
    assert task.status == "succeeded"
    assert attempt.status == "succeeded"
    assert task.operation_token == operation_token
    assert attempt.request_fingerprint
    assert run.output == {"load": {"order_id": "42"}}


def test_ambiguous_external_commit_requires_reconciliation_before_retry() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    handler_key = f"tests.ambiguous.{uuid.uuid4().hex}"

    def ambiguous_executor(_context):
        return NodeExecutionResult.failure(
            "PROVIDER_TIMEOUT",
            "Provider timed out after an unknown commit boundary",
            transient=True,
            commit_state=CommitState.UNKNOWN,
            manual_retry_safe=False,
        )

    register_node(_descriptor(handler_key, retry_safety=RetrySafety.RECONCILABLE), ambiguous_executor)
    try:
        published, _ = _published_custom_graph(tenant_id, actor_id, handler_key, max_attempts=2)
        run = ExecutionService.start_run(tenant_id, published.id, actor_id, {}, "ambiguous-run", "manual")
        ExecutionService.execute_run(tenant_id, run.id)
        attempt = RetryAttempt.objects.for_tenant(tenant_id).get(task_run__run=run)

        result = ExecutionService.execute_task(tenant_id, attempt.id)

        result.refresh_from_db()
        task = OrchestrationTaskRun.objects.for_tenant(tenant_id).get(run=run)
        assert result.status == "failed"
        assert result.error_code == "AMBIGUOUS_COMMIT"
        assert task.status == "retry_wait"
        reconciliation = OrchestrationReconciliation.objects.for_tenant(tenant_id).get(attempt=result)
        assert reconciliation.status == ReconciliationStatus.REQUIRED
        assert reconciliation.evidence["commit_state"] == CommitState.UNKNOWN.value
        assert RetryAttempt.objects.for_tenant(tenant_id).filter(task_run=task).count() == 1
        with pytest.raises(StateConflictError, match="failed or cancelled"):
            ExecutionService.retry_task(tenant_id, task.id, actor_id, "manual-retry-before-reconcile")
    finally:
        unregister_node(handler_key)


def test_reconciliation_confirms_or_restores_required_state(settings) -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    handler_key = f"tests.reconcile.{uuid.uuid4().hex}"

    def ambiguous_executor(_context):
        return NodeExecutionResult.failure(
            "PROVIDER_TIMEOUT",
            "Provider timed out after an unknown commit boundary",
            transient=True,
            commit_state=CommitState.UNKNOWN,
            manual_retry_safe=False,
        )

    register_node(_descriptor(handler_key, retry_safety=RetrySafety.RECONCILABLE), ambiguous_executor)
    settings.AUTOMATION_ORCHESTRATION_RECONCILER = (
        "src.modules.automation_orchestration.tests.test_services.reconciliation_adapter"
    )
    global RECONCILER_SHOULD_RESOLVE
    try:
        published, _ = _published_custom_graph(tenant_id, actor_id, handler_key, max_attempts=1)
        run = ExecutionService.start_run(tenant_id, published.id, actor_id, {}, "reconcile-run", "manual")
        ExecutionService.execute_run(tenant_id, run.id)
        attempt = RetryAttempt.objects.for_tenant(tenant_id).get(task_run__run=run)
        ExecutionService.execute_task(tenant_id, attempt.id)
        task = OrchestrationTaskRun.objects.for_tenant(tenant_id).get(run=run)

        RECONCILER_SHOULD_RESOLVE = False
        with pytest.raises(StateConflictError, match="unresolved"):
            ExecutionService.reconcile_task(tenant_id, task.id, actor_id, "reconcile", {"operator": "ops"})

        RECONCILER_SHOULD_RESOLVE = True
        reconciled = ExecutionService.reconcile_task(tenant_id, task.id, actor_id, "compensate", {"operator": "ops"})

        assert reconciled.status == "failed"
        assert reconciled.error_code == "EXTERNAL_COMMIT_COMPENSATED"
        run.refresh_from_db()
        assert run.status == "failed"
    finally:
        RECONCILER_SHOULD_RESOLVE = True
        unregister_node(handler_key)


def test_transient_retry_reuses_queued_attempt_and_preserves_original_attempt_evidence() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    handler_key = f"tests.transient.{uuid.uuid4().hex}"

    def transient_executor(_context):
        return NodeExecutionResult.failure(
            "TEMPORARY_BACKEND",
            "Backend is temporarily unavailable",
            transient=True,
            commit_state=CommitState.NOT_STARTED,
            manual_retry_safe=True,
        )

    register_node(_descriptor(handler_key), transient_executor)
    try:
        published, _ = _published_custom_graph(
            tenant_id,
            actor_id,
            handler_key,
            max_attempts=2,
            retry_initial_delay_seconds=1,
        )
        run = ExecutionService.start_run(tenant_id, published.id, actor_id, {}, "transient-run", "manual")
        ExecutionService.execute_run(tenant_id, run.id)
        first_attempt = RetryAttempt.objects.for_tenant(tenant_id).get(task_run__run=run)

        ExecutionService.execute_task(tenant_id, first_attempt.id)

        task = OrchestrationTaskRun.objects.for_tenant(tenant_id).get(run=run)
        queued_retry = RetryAttempt.objects.for_tenant(tenant_id).get(task_run=task, attempt_number=2)
        replay = ExecutionService.enqueue_task(tenant_id, task.id)
        first_attempt.refresh_from_db()
        assert replay.id == queued_retry.id
        assert task.status == "queued"
        assert first_attempt.status == "failed"
        assert first_attempt.commit_outcome["state"] == CommitState.NOT_STARTED.value
        assert queued_retry.available_at > timezone.now()
    finally:
        unregister_node(handler_key)


def test_pause_resume_cancel_and_retry_lineage_are_durable() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    published, _ = _published_graph(tenant_id, actor_id, key="control")
    run = ExecutionService.start_run(tenant_id, published.id, actor_id, {"order_id": "42"}, "control-42", "manual")
    ExecutionService.execute_run(tenant_id, run.id)
    assert ExecutionService.pause_run(tenant_id, run.id, actor_id, "pause-run").status == "paused"
    assert ExecutionService.resume_run(tenant_id, run.id, actor_id, "resume-run").status == "running"
    cancelled = ExecutionService.cancel_run(tenant_id, run.id, actor_id, "cancel-run")
    assert cancelled.status == "cancelled"
    retried = ExecutionService.retry_run(tenant_id, run.id, actor_id, "retry-control-42")
    assert retried.parent_run_id == run.id
    assert retried.id != run.id


def test_cron_expression_supports_ranges_steps_and_rejects_invalid_values() -> None:
    expression = CronExpression("*/15 9-17 * * 1-5")
    next_run = expression.next_after(timezone.now(), __import__("zoneinfo").ZoneInfo("UTC"))
    assert next_run.minute in {0, 15, 30, 45}
    with pytest.raises(ServiceValidationError, match="five fields"):
        CronExpression("* * *")


def test_bounded_node_execution_tracks_failures_opens_and_recovers_circuit(monkeypatch) -> None:
    handler_key = f"tests.circuit.{uuid.uuid4().hex}"
    context = NodeExecutionContext(
        tenant_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        task_run_id=uuid.uuid4(),
        attempt_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        correlation_id="corr-circuit",
        input={},
        validated_config={},
        cancellation_probe=lambda: False,
        operation_token="operation-token",
        delivery_token="delivery-token",
        handler_key=handler_key,
        descriptor_version="1",
        request_fingerprint="fingerprint",
    )
    resilience = {"circuit_failure_threshold": 2, "circuit_recovery_seconds": 60}

    def unavailable(_context):
        return NodeExecutionResult.unavailable("DOWNSTREAM_DOWN", "downstream failed")

    monkeypatch.setattr("src.modules.automation_orchestration.services.execute_registered_node", unavailable)
    _CIRCUITS.pop(handler_key, None)
    first = _execute_node_bounded(context, 1, resilience)
    second = _execute_node_bounded(context, 1, resilience)
    opened = _execute_node_bounded(context, 1, resilience)

    assert first.status == NodeResultStatus.UNAVAILABLE
    assert second.error_code == "DOWNSTREAM_DOWN"
    assert opened.error_code == "DEPENDENCY_CIRCUIT_OPEN"
    assert opened.evidence["provider"] == handler_key

    def succeeds(_context):
        return NodeExecutionResult.success({"ok": True})

    monkeypatch.setattr("src.modules.automation_orchestration.services.execute_registered_node", succeeds)
    failures, opened_at = _CIRCUITS[handler_key]
    _CIRCUITS[handler_key] = (failures, opened_at - 120)

    recovered = _execute_node_bounded(context, 1, resilience)

    assert recovered.status == NodeResultStatus.SUCCEEDED
    assert handler_key not in _CIRCUITS


def test_mapping_validation_resolution_and_cron_guards_fail_closed() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    published, node = _published_graph(tenant_id, actor_id, key="mapping-contracts")
    run = ExecutionService.start_run(
        tenant_id,
        published.id,
        actor_id,
        {"order_id": "A-1"},
        "mapping-contract-run",
        "manual",
    )
    task = OrchestrationTaskRun.objects.for_tenant(tenant_id).get(run=run)
    task.node = node
    task.node.input_mapping = {
        "order_id": "$input.order_id",
        "run_id": "$run.id",
        "nested": ["literal", {"corr": "$run.correlation_id"}],
    }

    resolved = _resolve_data_mapping(run, [], task.node.input_mapping)

    assert resolved["order_id"] == "A-1"
    assert resolved["run_id"] == str(run.id)
    assert resolved["nested"][1]["corr"] == run.correlation_id
    _validate_mapping({"from_task": "$tasks.load.output.value"}, known_nodes={"load"})
    with pytest.raises(ServiceValidationError, match="unknown node"):
        _validate_mapping({"from_task": "$tasks.missing.output.value"}, known_nodes={"load"})
    with pytest.raises(ServiceValidationError, match="not JSON-compatible"):
        _validate_mapping({"bad": object()})
    with pytest.raises(ServiceValidationError, match="unavailable"):
        _resolve_data_mapping(run, [], {"missing": "$input.unknown"})
    with pytest.raises(ServiceValidationError, match="IANA"):
        _zone("Not/AZone")
    with pytest.raises(ServiceValidationError, match="empty term"):
        CronExpression("*, 1 * * *")
    with pytest.raises(ServiceValidationError, match="positive integer"):
        CronExpression("*/0 * * * *")
    with pytest.raises(ServiceValidationError, match="outside"):
        CronExpression("61 * * * *")
    with pytest.raises(ServiceValidationError, match="timezone-aware"):
        CronExpression("* * * * *").next_after(timezone.now().replace(tzinfo=None), _zone("UTC"))


def test_worker_authorization_falls_back_to_configured_authorizer(settings) -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    descriptor = _descriptor("tests.external.authorized")
    descriptor = NodeDescriptor(
        key=descriptor.key,
        display_name=descriptor.display_name,
        category=descriptor.category,
        description=descriptor.description,
        configuration_schema=descriptor.configuration_schema,
        input_schema=descriptor.input_schema,
        output_schema=descriptor.output_schema,
        icon_key=descriptor.icon_key,
        capability="external.capability",
        source_module="external_module",
    )

    assert _worker_authorized(tenant_id, actor_id, descriptor) is False

    def authorizer(received_tenant, received_actor, capability, quota_resource, quota_cost):
        assert received_tenant == tenant_id
        assert received_actor == actor_id
        assert capability == "external.capability"
        assert quota_resource is None
        assert quota_cost == 0
        return True

    settings.AUTOMATION_ORCHESTRATION_WORKER_AUTHORIZER = authorizer

    assert _worker_authorized(tenant_id, actor_id, descriptor) is True


def test_mapping_resolution_and_validation_cover_supported_sources_and_failures() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    published, _ = _published_graph(tenant_id, actor_id, key="mapping")
    run = ExecutionService.start_run(tenant_id, published.id, actor_id, {"order_id": "42"}, "mapping-run", "manual")
    ExecutionService.execute_run(tenant_id, run.id)
    attempt = RetryAttempt.objects.for_tenant(tenant_id).get(task_run__run=run)
    ExecutionService.execute_task(tenant_id, attempt.id)
    task = OrchestrationTaskRun.objects.for_tenant(tenant_id).get(run=run)

    resolved = _resolve_data_mapping(
        run,
        [task],
        {
            "from_input": "$input.order_id",
            "from_task": "$tasks.load.output.order_id",
            "from_node": "$nodes.load.output.order_id",
            "from_run": "$run.correlation_id",
            "literal": ["ok", 3],
        },
    )
    assert resolved["from_input"] == "42"
    assert resolved["from_task"] == "42"
    assert resolved["from_node"] == "42"
    assert resolved["from_run"] == run.correlation_id

    _validate_mapping({"nested": ["$input.order_id"]})
    with pytest.raises(ServiceValidationError, match="Unsupported mapping"):
        _validate_mapping({"bad": "$bad.source"})
    with pytest.raises(ServiceValidationError, match="unknown node"):
        _validate_mapping({"bad": "$tasks.missing.output.value"}, known_nodes={"load"})
    with pytest.raises(ServiceValidationError, match="unavailable"):
        _resolve_data_mapping(run, [task], {"missing": "$input.missing"})

    assert _edge_matches("always", "failed") is True
    assert _edge_matches("on_failure", "failed") is True
    assert _edge_matches("on_success", "failed") is False
    assert _published_contract_version(published, "missing", "fallback") == "fallback"
    assert _worker_authorized(tenant_id, actor_id, _descriptor("core.passthrough")) is True
