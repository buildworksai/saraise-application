"""Deterministic service and algorithm behavior."""

import hashlib
import io
import json
import uuid
from dataclasses import FrozenInstanceError
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from src.core.api.results import OperationFailed
from src.core.async_jobs.models import OutboxEvent
from src.core.state_machine import IdempotencyConflictError, IllegalTransitionError, StateMachineError

from .. import services as process_services
from ..adapters import (
    AdapterMetadata,
    CanonicalEvent,
    CSVExportFormatter,
    HeuristicMiner,
    InductiveMiner,
    InvalidAdapterResult,
    JSONExportFormatter,
    TokenReplayConformance,
    TransitionDurationAnalyzer,
    XESExportFormatter,
    canonical_events,
)
from ..models import (
    AnalysisStatus,
    BottleneckAnalysis,
    BottleneckFinding,
    ConformanceCaseMetric,
    ConformanceCheck,
    EventExportJob,
    ExportArtifactDeletion,
    ExportStatus,
    ProcessDiscoveryJob,
    ProcessEvent,
    ProcessEventRetentionTombstone,
    ProcessMiningConfiguration,
    ProcessModel,
    ProcessModelVersion,
)
from ..services import (
    DEFAULT_CONFIGURATION,
    BottleneckService,
    CapabilityUnavailable,
    ConformanceService,
    EventLogService,
    ExportService,
    ProcessDiscoveryService,
    ProcessMiningConfigurationService,
    ProcessMiningQueryService,
    ProcessModelService,
)
from .factories import (
    AnalysisFactory,
    CaseMetricFactory,
    ConformanceFactory,
    DeviationFactory,
    EventFactory,
    ExportFactory,
    FindingFactory,
    VariantFactory,
    VersionFactory,
    event_log,
    graph,
)

pytestmark = pytest.mark.django_db


def test_adapter_metadata_is_immutable_and_slot_backed() -> None:
    metadata = AdapterMetadata(
        "process_mining.adapter",
        "1.0",
        "2.0.0",
        ("discovery",),
    )

    assert not hasattr(metadata, "__dict__")
    with pytest.raises(FrozenInstanceError):
        metadata.adapter_id = "mutated"  # type: ignore[misc]


def test_ingestion_validates_deduplicates_and_publishes():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    occurred = timezone.now() - timedelta(hours=1)
    payload = {"case_id": "c1", "activity": "Created", "occurred_at": occurred, "source_event_id": "s1"}
    service = EventLogService()
    first = service.ingest_events(tenant, actor, "canonical", "orders", [payload])
    second = service.ingest_events(tenant, actor, "canonical", "orders", [payload])
    assert (first.accepted, first.rejected, first.duplicates) == (1, 0, 0)
    assert second.duplicates == 1 and ProcessEvent.objects.for_tenant(tenant).count() == 1


def test_ingestion_rejects_unsafe_attributes_and_batch_duplicate_source_ids() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    occurred = timezone.now() - timedelta(minutes=5)
    result = EventLogService().ingest_events(
        tenant,
        actor,
        "canonical",
        "orders",
        [
            {
                "case_id": "case-1",
                "activity": "Created",
                "occurred_at": occurred,
                "source_event_id": "same-source",
                "attributes": {"token": "redacted"},
            },
            {
                "case_id": "case-1",
                "activity": "Created",
                "occurred_at": occurred,
                "source_event_id": "same-source",
            },
            {
                "case_id": "case-2",
                "activity": "Approved",
                "occurred_at": occurred + timedelta(seconds=1),
                "source_event_id": "same-source",
            },
        ],
    )

    assert (result.accepted, result.rejected, result.duplicates) == (1, 1, 1)
    assert [row.status for row in result.rows] == ["rejected", "accepted", "duplicate"]
    assert ProcessEvent.objects.for_tenant(tenant).count() == 1


@pytest.mark.parametrize("offset", [timedelta(minutes=1), -timedelta(days=731)])
def test_ingestion_rejects_timestamp_bounds(offset):
    occurred = timezone.now() + offset
    result = EventLogService().ingest_events(
        uuid.uuid4(), uuid.uuid4(), "canonical", "orders", [{"case_id": "c", "activity": "a", "occurred_at": occurred}]
    )
    assert result.rejected == 1 and result.accepted == 0


def test_event_query_requires_bounded_range():
    with pytest.raises(ValidationError):
        EventLogService().query_events(uuid.uuid4(), {"process_name": "orders"})


def test_event_query_filters_and_retention_purge_records_authorization() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    EventFactory(
        tenant_id=tenant,
        created_by=actor,
        process_name="orders",
        case_id="case-expired",
        activity="Approve",
        occurred_at=timezone.now() - timedelta(days=400),
        resource="team-a",
    )
    EventFactory(
        tenant_id=tenant,
        created_by=actor,
        process_name="orders",
        case_id="case-complete",
        activity="Complete",
        occurred_at=timezone.now() - timedelta(days=2),
        resource="team-b",
    )

    with pytest.raises(ValidationError):
        EventLogService().purge_expired_events(tenant, retention_days=1, actor_id=actor)

    assert EventLogService().purge_expired_events(tenant, retention_days=365, actor_id=actor) == 1
    tombstone = ProcessEventRetentionTombstone.objects.for_tenant(tenant).get()
    assert tombstone.created_by == actor
    assert tombstone.event_count == 1

    results = EventLogService().query_events(
        tenant,
        {
            "process_name": "orders",
            "start": timezone.now() - timedelta(days=30),
            "end": timezone.now(),
            "activity": "Complete",
            "resource": "team-b",
        },
    )
    assert list(results.values_list("case_id", flat=True)) == ["case-complete"]


def test_local_algorithms_derive_real_graph_and_conformance():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    rows = event_log(tenant, actor)
    events = canonical_events(rows)
    discovered = InductiveMiner().discover(events, {"noise_threshold": 0})
    traces = {f"case-{index}": [event for event in events if event.case_id == f"case-{index}"] for index in range(10)}
    result = TokenReplayConformance().evaluate(discovered, traces)
    assert len(discovered["nodes"]) == 5
    assert result.fitness == 1 and not result.deviations


def test_heuristic_miner_filters_edges_by_configured_threshold():
    now = timezone.now()
    events = [
        CanonicalEvent("case-1", "Create", now, source_event_id="1"),
        CanonicalEvent("case-1", "Approve", now + timedelta(minutes=1), source_event_id="2"),
        CanonicalEvent("case-2", "Create", now, source_event_id="3"),
        CanonicalEvent("case-2", "Reject", now + timedelta(minutes=1), source_event_id="4"),
    ]

    graph_data = HeuristicMiner().discover(events, {"dependency_threshold": "0.75"})
    create_node_id = next(node["id"] for node in graph_data["nodes"] if node["label"] == "Create")

    assert [(edge["source"], edge["target"], edge["frequency"]) for edge in graph_data["edges"]] == [
        ("start", create_node_id, 2)
    ]


def test_discovery_thresholds_are_inclusive_and_filter_rare_transitions():
    occurred = timezone.now()
    events = [
        CanonicalEvent("case-1", "Create", occurred, source_event_id="1"),
        CanonicalEvent("case-1", "Approve", occurred + timedelta(minutes=1), source_event_id="2"),
        CanonicalEvent("case-2", "Create", occurred + timedelta(minutes=2), source_event_id="3"),
        CanonicalEvent("case-2", "Reject", occurred + timedelta(minutes=3), source_event_id="4"),
    ]

    inclusive = HeuristicMiner().discover(events, {"dependency_threshold": 0.5})
    strict = HeuristicMiner().discover(events, {"dependency_threshold": 0.51})

    assert len(inclusive["edges"]) == 5
    assert len(strict["edges"]) == 1
    assert strict["edges"][0]["source"] == "start"
    assert strict["edges"][0]["frequency"] == 2


def test_mining_configuration_numeric_values_are_required():
    now = timezone.now()
    events = [CanonicalEvent("case-1", "Create", now)]
    traces = {
        "case-1": [
            CanonicalEvent("case-1", "Create", now),
            CanonicalEvent("case-1", "Approve", now + timedelta(seconds=1)),
        ],
        "case-2": [
            CanonicalEvent("case-2", "Create", now),
            CanonicalEvent("case-2", "Approve", now + timedelta(seconds=10)),
        ],
    }

    with pytest.raises(ValueError, match="dependency_threshold must be numeric"):
        HeuristicMiner().discover(events, {"dependency_threshold": object()})

    with pytest.raises(ValueError, match="bottleneck_critical_ratio must be numeric"):
        TransitionDurationAnalyzer().analyze(
            traces,
            (now - timedelta(seconds=1), now + timedelta(seconds=1)),
            {
                "tail_duration_percentile": 0.95,
                "bottleneck_medium_ratio": 1.5,
                "bottleneck_high_ratio": 3,
                "bottleneck_critical_ratio": object(),
                "resource_concentration_threshold": 0.5,
                "variant_grouping_percentage": 70,
            },
        )

    with pytest.raises(InvalidAdapterResult, match="removed every observed transition"):
        HeuristicMiner().discover(events, {"dependency_threshold": 1.01})


def test_transition_duration_analyzer_reports_ranked_bottlenecks_and_grouped_variants():
    now = timezone.now()
    traces = {
        "case-1": [
            CanonicalEvent("case-1", "Create", now, source_event_id="1"),
            CanonicalEvent("case-1", "Approve", now + timedelta(seconds=10), resource="sam", source_event_id="2"),
            CanonicalEvent("case-1", "Complete", now + timedelta(seconds=110), source_event_id="3"),
        ],
        "case-2": [
            CanonicalEvent("case-2", "Create", now, source_event_id="4"),
            CanonicalEvent("case-2", "Approve", now + timedelta(seconds=20), resource="sam", source_event_id="5"),
            CanonicalEvent("case-2", "Complete", now + timedelta(seconds=30), source_event_id="6"),
        ],
        "case-3": [
            CanonicalEvent("case-3", "Create", now, source_event_id="7"),
            CanonicalEvent("case-3", "Rework", now + timedelta(seconds=5), resource="lee", source_event_id="8"),
            CanonicalEvent("case-3", "Complete", now + timedelta(seconds=15), source_event_id="9"),
        ],
    }

    result = TransitionDurationAnalyzer().analyze(
        traces,
        (now - timedelta(seconds=1), now + timedelta(minutes=3)),
        {
            "tail_duration_percentile": "0.95",
            "bottleneck_critical_ratio": "5",
            "bottleneck_high_ratio": "3",
            "bottleneck_medium_ratio": "1.5",
            "resource_concentration_threshold": "0.5",
            "variant_grouping_percentage": "70",
        },
    )

    first = result.findings[0]
    assert first["from_activity"] == "Approve"
    assert first["to_activity"] == "Complete"
    assert first["severity"] == "medium"
    assert result.findings[1]["resource_bottleneck"] == "sam"
    assert result.variants == (
        {
            "variant_key": result.variants[0]["variant_key"],
            "activities": ["Other variants"],
            "case_count": 3,
            "percentage": Decimal("100.0"),
            "avg_duration_seconds": Decimal("51.67"),
            "is_happy_path": False,
            "is_grouped_other": True,
        },
    )
    assert result.total_cases == 3


def test_bottleneck_analysis_preserves_percentile_severity_and_resource_evidence():
    start = timezone.now()
    traces = {
        "case-1": [
            CanonicalEvent("case-1", "Create", start, source_event_id="1"),
            CanonicalEvent("case-1", "Approve", start + timedelta(seconds=10), resource="alice", source_event_id="2"),
            CanonicalEvent("case-1", "Complete", start + timedelta(seconds=50), resource="ops", source_event_id="3"),
        ],
        "case-2": [
            CanonicalEvent("case-2", "Create", start + timedelta(minutes=1), source_event_id="4"),
            CanonicalEvent(
                "case-2",
                "Approve",
                start + timedelta(minutes=1, seconds=20),
                resource="bob",
                source_event_id="5",
            ),
            CanonicalEvent(
                "case-2",
                "Complete",
                start + timedelta(minutes=3),
                resource="ops",
                source_event_id="6",
            ),
        ],
        "case-3": [
            CanonicalEvent("case-3", "Create", start + timedelta(minutes=4), source_event_id="7"),
            CanonicalEvent(
                "case-3",
                "Approve",
                start + timedelta(minutes=4, seconds=20),
                resource="carol",
                source_event_id="8",
            ),
            CanonicalEvent(
                "case-3",
                "Complete",
                start + timedelta(minutes=7, seconds=40),
                resource="qa",
                source_event_id="9",
            ),
        ],
    }

    result = TransitionDurationAnalyzer().analyze(
        traces,
        (start - timedelta(seconds=1), start + timedelta(minutes=8)),
        {
            "tail_duration_percentile": 0.95,
            "bottleneck_medium_ratio": 1.1,
            "bottleneck_high_ratio": 1.5,
            "bottleneck_critical_ratio": 1.9,
            "resource_concentration_threshold": 0.5,
            "variant_grouping_percentage": 1.0,
        },
    )

    top = result.findings[0]
    assert top["from_activity"] == "Approve"
    assert top["to_activity"] == "Complete"
    assert top["median_duration_seconds"] == Decimal("100.0")
    assert top["p95_duration_seconds"] == Decimal("200.0")
    assert top["severity"] == "critical"
    assert top["resource_bottleneck"] == "ops"
    assert top["rank"] == 1
    assert result.total_cases == 3
    assert result.average_case_duration_seconds == Decimal("130.0")
    assert result.variants == (
        {
            "variant_key": result.variants[0]["variant_key"],
            "activities": ["Create", "Approve", "Complete"],
            "case_count": 3,
            "percentage": Decimal("100.0"),
            "avg_duration_seconds": Decimal("130.0"),
            "is_happy_path": True,
            "is_grouped_other": False,
        },
    )


def test_bottleneck_severity_critical_threshold_is_strictly_exceeded():
    start = timezone.now()
    traces = {
        "case-1": [
            CanonicalEvent("case-1", "Create", start, source_event_id="1"),
            CanonicalEvent("case-1", "Approve", start + timedelta(seconds=10), source_event_id="2"),
        ],
        "case-2": [
            CanonicalEvent("case-2", "Create", start, source_event_id="3"),
            CanonicalEvent("case-2", "Approve", start + timedelta(seconds=10), source_event_id="4"),
        ],
        "case-3": [
            CanonicalEvent("case-3", "Create", start, source_event_id="5"),
            CanonicalEvent("case-3", "Approve", start + timedelta(seconds=20), source_event_id="6"),
        ],
    }
    configuration = {
        "tail_duration_percentile": 1.0,
        "bottleneck_medium_ratio": 1.1,
        "bottleneck_high_ratio": 1.5,
        "bottleneck_critical_ratio": 2.0,
        "resource_concentration_threshold": 0.5,
        "variant_grouping_percentage": 1.0,
    }

    boundary = TransitionDurationAnalyzer().analyze(
        traces,
        (start - timedelta(seconds=1), start + timedelta(seconds=21)),
        configuration,
    )
    above_boundary = TransitionDurationAnalyzer().analyze(
        {
            "case-1": traces["case-1"],
            "case-2": traces["case-2"],
            "case-3": [
                CanonicalEvent("case-3", "Create", start, source_event_id="7"),
                CanonicalEvent("case-3", "Approve", start + timedelta(seconds=21), source_event_id="8"),
            ],
        },
        (start - timedelta(seconds=1), start + timedelta(seconds=22)),
        configuration,
    )

    assert boundary.findings[0]["severity"] == "high"
    assert above_boundary.findings[0]["severity"] == "critical"


def test_transition_duration_analyzer_rejects_invalid_time_range():
    now = timezone.now()

    with pytest.raises(ValueError, match="time range end must follow start"):
        TransitionDurationAnalyzer().analyze({}, (now, now), {})


@pytest.mark.parametrize("formatter", [CSVExportFormatter(), XESExportFormatter()])
def test_exports_are_deterministic_and_count_rows(formatter):
    event = EventFactory()
    first, second = io.StringIO(), io.StringIO()
    assert formatter.write(canonical_events([event]), first) == 1
    formatter.write(canonical_events([event]), second)
    assert first.getvalue() == second.getvalue()


def test_json_export_is_deterministic_parseable_and_counts_rows():
    event = EventFactory(attributes={"z": 1, "a": {"nested": True}})
    first, second = io.StringIO(), io.StringIO()

    assert JSONExportFormatter().write(canonical_events([event]), first) == 1
    assert JSONExportFormatter().write(canonical_events([event]), second) == 1

    assert first.getvalue() == second.getvalue()
    exported = json.loads(first.getvalue())
    assert exported == [
        {
            "activity": "Approve",
            "attributes": {"a": {"nested": True}, "z": 1},
            "case_id": event.case_id,
            "occurred_at": event.occurred_at.isoformat(),
            "resource": "team-a",
            "source_event_id": event.source_event_id,
            "source_module": "canonical",
        }
    ]


def test_imported_model_publishes_immutable_version():
    model = ProcessModelService().create_imported_model(uuid.uuid4(), uuid.uuid4(), "Reference", "orders", "", graph())
    assert model.versions.count() == 1 and model.versions.get().model_data["schema_version"] == "1.0"


def test_configuration_preview_update_export_import_and_rollback():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    service = ProcessMiningConfigurationService()
    document = {**DEFAULT_CONFIGURATION, "retention_days": 180}

    preview = service.preview(tenant, document)
    assert preview["valid"] is True
    assert preview["changes"]["retention_days"]["to"] == 180

    updated = service.update(tenant, actor, "corr-process-config", document)
    assert updated.version == 2
    assert updated.document["retention_days"] == 180

    exported = service.export_document(tenant)
    assert exported["module"] == "process_mining"
    assert exported["version"] == 2

    imported = service.import_document(
        tenant,
        actor,
        "corr-process-import",
        {**exported, "document": {**DEFAULT_CONFIGURATION, "retention_days": 365}},
    )
    assert imported.version == 3
    assert imported.document["retention_days"] == 365

    rolled_back = service.rollback(tenant, actor, "corr-process-rollback", 2)
    assert rolled_back.version == 4
    assert rolled_back.document["retention_days"] == 180


@pytest.mark.parametrize(
    ("patch", "field"),
    [
        ({"retention_days": 10, "retention_min_days": 30}, "retention_days"),
        ({"algorithm_threshold_min": 0.9, "algorithm_threshold_max": 0.2}, "algorithm_threshold_max"),
        ({"bottleneck_critical_ratio": 2.0, "bottleneck_high_ratio": 3.0}, "bottleneck_critical_ratio"),
        ({"visual_zoom_min": 2.0, "visual_zoom_max": 1.0}, "visual_zoom_max"),
        ({"forbidden_attribute_keys": []}, "forbidden_attribute_keys"),
        ({"environment": "production"}, "environment"),
    ],
)
def test_configuration_validation_rejects_inconsistent_policy(patch, field):
    with pytest.raises(ValidationError) as exc:
        ProcessMiningConfigurationService.validate_document({**DEFAULT_CONFIGURATION, **patch})
    assert field in exc.value.detail


def test_configuration_import_rejects_wrong_module_document():
    with pytest.raises(ValidationError) as exc:
        ProcessMiningConfigurationService().import_document(
            uuid.uuid4(),
            uuid.uuid4(),
            "corr-process-invalid-import",
            {"schema_version": "1.0", "module": "other", "document": DEFAULT_CONFIGURATION},
        )
    assert "configuration" in exc.value.detail


def test_configuration_get_fails_closed_for_corrupt_persisted_policy() -> None:
    tenant = uuid.uuid4()
    ProcessMiningConfiguration.objects.create(
        tenant_id=tenant,
        document={**DEFAULT_CONFIGURATION, "enabled": "yes"},
        version=1,
        updated_by=uuid.uuid4(),
    )

    with pytest.raises(ValidationError) as exc:
        ProcessMiningConfigurationService().get_configuration(tenant)
    assert "enabled" in exc.value.detail


@pytest.mark.parametrize(
    ("document", "field"),
    [
        ([], "document"),
        ({key: value for key, value in DEFAULT_CONFIGURATION.items() if key != "enabled"}, "document"),
        ({**DEFAULT_CONFIGURATION, "unknown": True}, "document"),
        ({**DEFAULT_CONFIGURATION, "max_batch_events": True}, "max_batch_events"),
        ({**DEFAULT_CONFIGURATION, "heuristic_default_threshold": True}, "heuristic_default_threshold"),
        ({**DEFAULT_CONFIGURATION, "default_discovery_algorithm": "unsupported"}, "default_discovery_algorithm"),
        ({**DEFAULT_CONFIGURATION, "rollout_roles": [""]}, "rollout_roles"),
        ({**DEFAULT_CONFIGURATION, "analysis_terminal_states": ["unsupported"]}, "analysis_terminal_states"),
        (
            {
                **DEFAULT_CONFIGURATION,
                "analysis_terminal_states": ["completed"],
                "analysis_transitions": {**DEFAULT_CONFIGURATION["analysis_transitions"], "completed": ["queued"]},
            },
            "analysis_terminal_states",
        ),
        (
            {
                **DEFAULT_CONFIGURATION,
                "export_transitions": {**DEFAULT_CONFIGURATION["export_transitions"], "queued": ["unsupported"]},
            },
            "export_transitions",
        ),
    ],
)
def test_configuration_validation_rejects_malformed_policy_shapes(document, field) -> None:
    with pytest.raises(ValidationError) as exc:
        ProcessMiningConfigurationService.validate_document(document)
    assert field in exc.value.detail


def test_configuration_update_noop_history_and_rollback_not_found() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    service = ProcessMiningConfigurationService()

    initialized = service.get_configuration(tenant, actor, "corr-config-init")
    unchanged = service.update(tenant, actor, "corr-config-noop", DEFAULT_CONFIGURATION)

    assert unchanged.version == initialized.version
    assert list(service.history(tenant).values_list("version", flat=True)) == [1]
    with pytest.raises(NotFound):
        service.rollback(tenant, actor, "corr-config-missing", 99)


def test_configuration_rejects_oversized_correlation_id() -> None:
    with pytest.raises(ValidationError) as exc:
        ProcessMiningConfigurationService().update(
            uuid.uuid4(),
            uuid.uuid4(),
            "x" * 129,
            DEFAULT_CONFIGURATION,
        )
    assert "correlation_id" in exc.value.detail


def test_low_level_process_mining_helpers_fail_closed(monkeypatch) -> None:
    tenant = uuid.uuid4()

    with pytest.raises(ValidationError):
        process_services._tenant("not-a-uuid")
    with pytest.raises(ValidationError):
        process_services._actor("not-a-uuid")
    with pytest.raises(ValidationError):
        process_services._identifier("not-a-uuid", "event_id")
    assert process_services._correlation_id("") == "missing-context"
    with pytest.raises(ValidationError):
        process_services._correlation_id("x" * 129)

    with pytest.raises(ValidationError):
        process_services._config_int({"limit": True}, "limit")
    with pytest.raises(ValidationError):
        process_services._config_float({"ratio": True}, "ratio")
    with pytest.raises(ValidationError):
        process_services._config_str_list({"keys": "token"}, "keys")
    with pytest.raises(ValidationError):
        process_services._config_str_list({"keys": ["safe", 1]}, "keys")
    with pytest.raises(ValidationError):
        process_services._config_workflow({"workflow": []}, "workflow")
    with pytest.raises(ValidationError):
        process_services._config_workflow({"workflow": {"queued": "running"}}, "workflow")
    with pytest.raises(ValidationError):
        process_services._workflow_machine(tenant, "unsupported")


@pytest.mark.parametrize(
    ("raised", "expected_code", "expected_status"),
    [
        (IdempotencyConflictError("duplicate"), "IDEMPOTENCY_CONFLICT", 409),
        (IllegalTransitionError("illegal"), "ILLEGAL_TRANSITION", 409),
        (StateMachineError("broken"), "STATE_TRANSITION_FAILED", 422),
    ],
)
def test_process_mining_transition_errors_are_translated(monkeypatch, raised, expected_code, expected_status) -> None:
    class FailingMachine:
        def apply(self, *args, **kwargs):
            raise raised

    monkeypatch.setattr(process_services, "_workflow_machine", lambda tenant_id, workflow_kind: FailingMachine())

    with pytest.raises(OperationFailed) as exc:
        process_services._apply_workflow_transition(
            uuid.uuid4(),
            "export",
            object(),
            "start",
            transition_key="transition-key",
            metadata={},
        )

    assert exc.value.error_code == expected_code
    assert exc.value.status_code == expected_status


def test_discovery_cancel_uses_configured_workflow_and_replays_transition_key():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    record = ProcessDiscoveryJob.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_name="orders",
        algorithm="inductive_miner",
        parameters={},
        idempotency_key="discover-orders",
    )
    service = ProcessDiscoveryService()

    cancelled = service.cancel_discovery(tenant, record.id, actor, "cancel-orders", "operator cancelled")
    replay = service.cancel_discovery(tenant, record.id, actor, "cancel-orders", "operator cancelled")

    assert cancelled.status == AnalysisStatus.CANCELLED
    assert replay.status == AnalysisStatus.CANCELLED
    assert replay.transition_history == cancelled.transition_history
    assert replay.transition_history[0]["metadata"]["reason"] == "operator cancelled"


def test_discovery_retry_is_allowed_only_from_failed_or_timed_out_state() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    queued = ProcessDiscoveryJob.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_name="orders",
        algorithm="inductive_miner",
        parameters={},
        idempotency_key="retry-queued",
    )

    with pytest.raises(OperationFailed) as exc:
        ProcessDiscoveryService().retry_discovery(tenant, queued.id, actor, "retry-queued", "retry-job")
    assert exc.value.error_code == "ILLEGAL_TRANSITION"

    ProcessDiscoveryJob.objects.for_tenant(tenant).filter(id=queued.id).update(status=AnalysisStatus.FAILED)
    retried = ProcessDiscoveryService().retry_discovery(tenant, queued.id, actor, "retry-failed", "retry-job")
    assert retried.status == AnalysisStatus.QUEUED
    assert retried.async_job_id is not None


def test_discovery_request_validates_configured_thresholds_and_replays_idempotency() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    event_log(tenant, actor, cases=2)
    ProcessMiningConfigurationService().update(
        tenant,
        actor,
        "corr-discovery-request-config",
        {**DEFAULT_CONFIGURATION, "discovery_min_events": 1, "discovery_min_cases": 1},
    )
    service = ProcessDiscoveryService()

    first = service.request_discovery(
        tenant,
        actor,
        "order_to_cash",
        "inductive_miner",
        {"noise_threshold": "0.1"},
        "request-discovery",
    )
    replay = service.request_discovery(tenant, actor, "order_to_cash", "inductive_miner", {}, "request-discovery")

    assert replay.id == first.id
    assert first.async_job_id is not None
    assert first.parameters["noise_threshold"] == 0.1

    with pytest.raises(ValidationError) as exc:
        service.request_discovery(tenant, actor, "order_to_cash", "unknown", {}, "unknown-discovery")
    assert "algorithm" in exc.value.detail

    with pytest.raises(ValidationError) as exc:
        service.request_discovery(
            tenant,
            actor,
            "order_to_cash",
            "inductive_miner",
            {"noise_threshold": True},
            "bad-threshold",
        )
    assert "noise_threshold" in exc.value.detail


def test_export_request_enforces_limits_and_replays_idempotency() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    event_log(tenant, actor, cases=2)
    service = ExportService()

    first = service.request_export(tenant, actor, "order_to_cash", "json", {}, "export-once")
    replay = service.request_export(tenant, actor, "order_to_cash", "json", {}, "export-once")

    assert replay.id == first.id
    assert replay.async_job_id == first.async_job_id

    document = {**DEFAULT_CONFIGURATION, "max_export_events": 1}
    ProcessMiningConfigurationService().update(tenant, actor, "tight-export-limit", document)

    with pytest.raises(OperationFailed) as exc:
        service.request_export(tenant, actor, "order_to_cash", "json", {}, "export-too-large")
    assert exc.value.error_code == "EXPORT_TOO_LARGE"
    assert exc.value.error_detail["projected_rows"] == 6

    with pytest.raises(ValidationError):
        service.request_export(tenant, actor, "order_to_cash", "pdf", {}, "bad-format")


def test_export_worker_persists_verified_artifact_and_download_rechecks_checksum() -> None:
    tenant, actor, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    event_log(tenant, actor, cases=1)
    export = EventExportJob.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_name="order_to_cash",
        format="json",
        event_filter={},
        async_job_id=job_id,
        idempotency_key="run-export",
    )

    completed = ExportService().run_export(tenant, export.id, job_id)
    assert completed.status == ExportStatus.COMPLETED
    assert completed.row_count == 3
    assert completed.artifact_key
    assert completed.sha256

    record, stream = ExportService().open_download(tenant, export.id)
    try:
        assert record.id == completed.id
        assert json.loads(stream.read().decode("utf-8"))[0]["case_id"] == "case-0"
    finally:
        stream.close()

    EventExportJob.objects.for_tenant(tenant).filter(id=export.id).update(sha256="0" * 64)
    with pytest.raises(OperationFailed) as exc:
        ExportService().open_download(tenant, export.id)
    assert exc.value.error_code == "ARTIFACT_INTEGRITY_FAILED"

    if completed.artifact_key and default_storage.exists(completed.artifact_key):
        default_storage.delete(completed.artifact_key)


def test_export_worker_marks_failure_and_cleans_partial_artifact(monkeypatch) -> None:
    tenant, actor, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    event_log(tenant, actor, cases=1)
    export = EventExportJob.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_name="order_to_cash",
        format="json",
        event_filter={},
        async_job_id=job_id,
        idempotency_key="run-export-failure",
    )

    def unavailable_storage(*args, **kwargs):
        raise OSError("storage down")

    monkeypatch.setattr(default_storage, "save", unavailable_storage)

    with pytest.raises(CapabilityUnavailable) as exc:
        ExportService().run_export(tenant, export.id, job_id)

    export.refresh_from_db()
    assert exc.value.capability == "export_storage"
    assert export.status == ExportStatus.FAILED
    assert export.error_code == "EXPORT_STORAGE_FAILED"
    assert OutboxEvent.objects.for_tenant(tenant).filter(event_type="process.export.failed").exists()


def test_export_lifecycle_expire_and_delete_records_artifact_deletion() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    artifact_key = f"process_mining/tests/{tenant}/completed.json"
    stored_key = default_storage.save(artifact_key, ContentFile(b"[]"))
    export = EventExportJob.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_name="orders",
        format="json",
        event_filter={},
        status=ExportStatus.COMPLETED,
        transition_history=[
            {
                "command": "complete",
                "from": "running",
                "to": "completed",
                "transition_key": "seed-completed",
                "metadata": {},
            }
        ],
        idempotency_key="delete-export",
        artifact_key=stored_key,
        sha256=hashlib.sha256(b"[]").hexdigest(),
    )

    expired = ExportService().expire_export(tenant, export.id, actor, "expire-export")
    assert expired.status == ExportStatus.EXPIRED
    assert not default_storage.exists(stored_key)

    ExportService().delete_export(tenant, export.id, actor)
    export.refresh_from_db()
    deletion = ExportArtifactDeletion.objects.for_tenant(tenant).get(export_job=export)
    assert export.is_deleted is True
    assert deletion.artifact_key == stored_key


def test_query_services_filter_order_and_find_fail_closed() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    version = VersionFactory(process_model__tenant_id=tenant, process_model__created_by=actor)
    export = ExportFactory(tenant_id=tenant, created_by=actor, process_name="order_to_cash", format="csv")
    discovery = ProcessDiscoveryJob.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_name="order_to_cash",
        algorithm="inductive_miner",
        parameters={},
        idempotency_key="query-discovery",
        event_count=3,
        case_count=1,
        activity_count=3,
    )
    check = ConformanceFactory(process_model_version=version, idempotency_key="query-check", fitness=Decimal("0.5"))
    metric = CaseMetricFactory(conformance_check=check, case_id="case-query")
    deviation = DeviationFactory(conformance_check=check, case_id="case-query")
    analysis = AnalysisFactory(tenant_id=tenant, created_by=actor, process_name="order_to_cash")
    finding = FindingFactory(analysis=analysis, resource_bottleneck="team-a")
    variant = VariantFactory(analysis=analysis, case_count=7, is_happy_path=True)

    assert ProcessMiningQueryService.find(ProcessMiningQueryService.exports(tenant, {}), export.id) == export
    assert ProcessMiningQueryService.find(ProcessMiningQueryService.exports(tenant, {}), "not-a-uuid") is None
    assert not ProcessMiningQueryService.exists(ProcessMiningQueryService.exports(tenant, {}), "not-a-uuid")
    assert list(ProcessMiningQueryService.model_versions(tenant, version.process_model_id)) == [version]
    assert list(ProcessMiningQueryService.discoveries(tenant, {"algorithm": "inductive_miner"})) == [discovery]
    assert list(ProcessMiningQueryService.conformance(tenant, {"fitness_min": "0"})) == [check]
    assert list(ConformanceService().list_deviations(tenant, check.id, {"case_id": "case-query"})) == [deviation]
    assert list(ConformanceService().get_fitness(tenant, check.id)[1]) == [metric]
    assert list(ProcessMiningQueryService.bottlenecks(tenant, {"process_name": "order_to_cash"})) == [analysis]
    assert list(BottleneckService().get_findings(tenant, analysis.id, {"resource": "team-a"})) == [finding]
    assert list(BottleneckService().get_variants(tenant, analysis.id, {"is_happy_path": "true"})) == [variant]

    with pytest.raises(ValidationError):
        ProcessMiningQueryService.exports(tenant, {"ordering": "artifact_key"})
    with pytest.raises(ValidationError):
        BottleneckService().get_variants(tenant, analysis.id, {"ordering": "created_at"})


def test_discovery_worker_publishes_model_version_and_lookup_guards() -> None:
    tenant, actor, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    event_log(tenant, actor, cases=3)
    discovery = ProcessDiscoveryJob.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_name="order_to_cash",
        algorithm="inductive_miner",
        parameters={"noise_threshold": 0.0},
        async_job_id=job_id,
        idempotency_key="run-discovery",
    )

    with pytest.raises(NotFound):
        ProcessDiscoveryService().run_discovery(tenant, discovery.id, uuid.uuid4())
    with pytest.raises(ValidationError):
        ProcessDiscoveryService().get_discovered_model(tenant, discovery.id)

    completed = ProcessDiscoveryService().run_discovery(tenant, discovery.id, job_id)
    version = ProcessDiscoveryService().get_discovered_model(tenant, discovery.id)

    assert completed.status == AnalysisStatus.COMPLETED
    assert version.discovery_job_id == discovery.id
    assert version.case_count == 3
    assert ProcessModel.objects.for_tenant(tenant).filter(process_name="order_to_cash").exists()


def test_conformance_worker_persists_metrics_deviations_and_low_fitness_event() -> None:
    tenant, actor, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rows = event_log(tenant, actor, cases=1)
    ProcessMiningConfigurationService().update(
        tenant,
        actor,
        "corr-low-fitness-threshold",
        {**DEFAULT_CONFIGURATION, "low_fitness_threshold": 1.0},
    )
    model = ProcessModel.objects.create(
        tenant_id=tenant,
        created_by=actor,
        name="Reference",
        process_name="order_to_cash",
        source_kind="imported",
    )
    version = ProcessModelVersion.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_model=model,
        version=1,
        model_data=InductiveMiner().discover(canonical_events(rows[:2]), {"noise_threshold": 0}),
        event_count=2,
        case_count=1,
        activity_count=2,
        published_at=timezone.now(),
    )
    check = ConformanceCheck.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_model_version=version,
        event_filter={},
        async_job_id=job_id,
        idempotency_key="run-conformance",
    )

    completed = ConformanceService().run_check(tenant, check.id, job_id)

    assert completed.status == AnalysisStatus.COMPLETED
    assert completed.total_cases == 1
    assert ConformanceCaseMetric.objects.for_tenant(tenant).filter(conformance_check=check).count() == 1
    assert completed.deviating_cases == 1
    assert OutboxEvent.objects.filter(
        tenant_id=tenant,
        aggregate_id=check.id,
        event_type="process.conformance.low_fitness",
    ).exists()


def test_conformance_request_enforces_limits_empty_filters_and_replays_idempotency() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    rows = event_log(tenant, actor, cases=1)
    model = ProcessModel.objects.create(
        tenant_id=tenant,
        created_by=actor,
        name="Reference",
        process_name="order_to_cash",
        source_kind="imported",
    )
    version = ProcessModelVersion.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_model=model,
        version=1,
        model_data=InductiveMiner().discover(canonical_events(rows), {"noise_threshold": 0}),
        event_count=3,
        case_count=1,
        activity_count=3,
        published_at=timezone.now(),
    )
    service = ConformanceService()

    first = service.request_check(tenant, actor, version.id, {}, "request-check")
    replay = service.request_check(tenant, actor, version.id, {}, "request-check")
    assert replay.id == first.id
    assert first.async_job_id is not None

    with pytest.raises(ValidationError) as exc:
        service.request_check(tenant, actor, version.id, {"case_id": "missing"}, "empty-check")
    assert "event_filter" in exc.value.detail

    ProcessMiningConfigurationService().update(
        tenant,
        actor,
        "corr-conformance-limit",
        {**DEFAULT_CONFIGURATION, "max_conformance_events": 1},
    )
    with pytest.raises(ValidationError) as exc:
        service.request_check(tenant, actor, version.id, {}, "limited-check")
    assert "event_filter" in exc.value.detail


def test_bottleneck_request_reuses_recent_completed_analysis_and_worker_persists_evidence() -> None:
    tenant, actor, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rows = event_log(tenant, actor, cases=3)
    start = rows[0].occurred_at - timedelta(seconds=1)
    end = rows[-1].occurred_at + timedelta(seconds=1)
    completed = BottleneckAnalysis.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_name="order_to_cash",
        time_range_start=start,
        time_range_end=end,
        status=AnalysisStatus.COMPLETED,
        completed_at=timezone.now(),
        idempotency_key="completed-analysis",
    )

    reused = BottleneckService().request_analysis(tenant, actor, "order_to_cash", (start, end), "reuse-analysis")
    assert reused.id == completed.id

    analysis = BottleneckAnalysis.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_name="order_to_cash",
        time_range_start=start,
        time_range_end=end,
        async_job_id=job_id,
        idempotency_key="run-analysis",
    )
    finished = BottleneckService().run_analysis(tenant, analysis.id, job_id)

    assert finished.status == AnalysisStatus.COMPLETED
    assert finished.total_cases == 3
    finding = BottleneckFinding.objects.for_tenant(tenant).filter(analysis=analysis).order_by("rank").first()
    assert finding is not None
    assert list(BottleneckService().get_findings(tenant, analysis.id, {"severity": finding.severity}))


def test_bottleneck_request_enqueues_and_validates_bounds_and_case_minimum() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    rows = event_log(tenant, actor, cases=1)
    start = rows[0].occurred_at - timedelta(seconds=1)
    end = rows[-1].occurred_at + timedelta(seconds=1)
    ProcessMiningConfigurationService().update(
        tenant,
        actor,
        "corr-bottleneck-request-config",
        {**DEFAULT_CONFIGURATION, "bottleneck_min_cases": 1},
    )
    service = BottleneckService()

    first = service.request_analysis(tenant, actor, "order_to_cash", (start, end), "request-analysis")
    replay = service.request_analysis(tenant, actor, "order_to_cash", (start, end), "request-analysis")
    assert replay.id == first.id
    assert first.async_job_id is not None

    with pytest.raises(ValidationError) as exc:
        service.request_analysis(tenant, actor, "order_to_cash", (end, start), "bad-window")
    assert "time_range_end" in exc.value.detail

    with pytest.raises(ValidationError) as exc:
        service.request_analysis(uuid.uuid4(), actor, "order_to_cash", (start, end), "missing-events")
    assert "process_name" in exc.value.detail


def test_terminal_analysis_metadata_deletion_is_lifecycle_gated() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    discovery = ProcessDiscoveryJob.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_name="order_to_cash",
        algorithm="inductive_miner",
        parameters={},
        idempotency_key="delete-discovery",
    )
    check = ConformanceFactory(process_model_version__process_model__tenant_id=tenant, idempotency_key="delete-check")
    analysis = AnalysisFactory(tenant_id=tenant, created_by=actor, idempotency_key="delete-analysis")

    with pytest.raises(ValidationError):
        ProcessDiscoveryService().delete_discovery(tenant, discovery.id, actor)
    with pytest.raises(ValidationError):
        ConformanceService().delete_check(tenant, check.id, actor)
    with pytest.raises(ValidationError):
        BottleneckService().delete_analysis(tenant, analysis.id, actor)

    ProcessDiscoveryService().cancel_discovery(tenant, discovery.id, actor, "delete-discovery-cancel")
    ConformanceService().cancel_check(tenant, check.id, actor, "delete-check-cancel")
    BottleneckService().cancel_analysis(tenant, analysis.id, actor, "delete-analysis-cancel")

    ProcessDiscoveryService().delete_discovery(tenant, discovery.id, actor)
    ConformanceService().delete_check(tenant, check.id, actor)
    BottleneckService().delete_analysis(tenant, analysis.id, actor)

    discovery.refresh_from_db()
    check.refresh_from_db()
    analysis.refresh_from_db()
    assert discovery.is_deleted and check.is_deleted and analysis.is_deleted


def test_default_configuration_and_limits_have_exact_documented_values() -> None:
    """Every numeric/string/boolean literal in the tenant policy defaults and their
    validated bounds is pinned exactly. A single mutated literal anywhere in these
    three module-level constants must fail this test."""
    assert DEFAULT_CONFIGURATION == {
        "environment": "default",
        "max_batch_events": 10_000,
        "max_export_events": 1_000_000,
        "max_export_bytes": 524_288_000,
        "max_conformance_events": 100_000,
        "text_max_length": 255,
        "attributes_max_bytes": 65_536,
        "forbidden_attribute_keys": ["password", "secret", "token", "authorization", "api_key", "credential"],
        "source_module_max_length": 100,
        "max_event_age_days": 730,
        "future_clock_skew_seconds": -120,
        "bulk_insert_batch_size": 1_000,
        "event_query_max_days": 366,
        "retention_days": 365,
        "retention_min_days": 30,
        "export_projection_bytes_per_event": 512,
        "export_iterator_chunk_size": 1_000,
        "checksum_chunk_bytes": 1_048_576,
        "export_expiry_days": 7,
        "discovery_min_events": 100,
        "discovery_min_cases": 10,
        "alpha_max_activities": 50,
        "heuristic_default_threshold": 0.8,
        "inductive_default_threshold": 0.2,
        "default_discovery_algorithm": "inductive_miner",
        "algorithm_threshold_step": 0.01,
        "algorithm_threshold_min": 0.0,
        "algorithm_threshold_max": 1.0,
        "low_fitness_threshold": 0.5,
        "bottleneck_reuse_minutes": 60,
        "bottleneck_min_cases": 50,
        "bottleneck_critical_ratio": 10.0,
        "bottleneck_high_ratio": 5.0,
        "bottleneck_medium_ratio": 2.0,
        "tail_duration_percentile": 0.95,
        "resource_concentration_threshold": 0.5,
        "variant_grouping_percentage": 1.0,
        "outbox_freshness_seconds": 300,
        "analysis_transitions": {
            "queued": ["running", "cancelled"],
            "running": ["completed", "failed", "timed_out", "cancelled"],
            "failed": ["queued"],
            "timed_out": ["queued"],
            "completed": [],
            "cancelled": [],
        },
        "analysis_terminal_states": ["completed", "cancelled"],
        "export_transitions": {
            "queued": ["running", "cancelled"],
            "running": ["completed", "failed", "timed_out", "cancelled"],
            "failed": ["queued"],
            "timed_out": ["queued"],
            "completed": ["expired"],
            "expired": [],
            "cancelled": [],
        },
        "export_terminal_states": ["cancelled", "expired"],
        "default_time_window_days": 30,
        "list_page_size": 25,
        "detail_page_size": 100,
        "polling_interval_ms": 5_000,
        "visual_zoom_min": 0.6,
        "visual_zoom_max": 1.8,
        "visual_zoom_step": 0.2,
        "visual_edge_width_min": 1.0,
        "visual_edge_width_max": 8.0,
        "visual_frequency_divisor": 10.0,
        "visual_duration_divisor": 60.0,
        "visual_canvas_width": 900,
        "visual_canvas_height": 600,
        "visual_node_width": 110,
        "visual_node_height": 50,
        "visual_layout_columns": 4,
        "visual_horizontal_gap": 210,
        "visual_vertical_gap": 150,
        "visual_layout_padding": 90,
        "download_timeout_ms": 30_000,
        "download_retry_attempts": 3,
        "download_retry_base_ms": 250,
        "download_circuit_failure_threshold": 5,
        "download_circuit_reset_ms": 30_000,
        "enabled": True,
        "rollout_roles": [],
        "rollout_cohorts": [],
    }
    assert process_services.INTEGER_LIMITS == {
        "max_batch_events": (1, 100_000),
        "max_export_events": (1, 10_000_000),
        "max_export_bytes": (1_048_576, 5_368_709_120),
        "max_conformance_events": (1, 1_000_000),
        "text_max_length": (32, 4_096),
        "attributes_max_bytes": (1_024, 1_048_576),
        "source_module_max_length": (16, 512),
        "max_event_age_days": (1, 3_650),
        "future_clock_skew_seconds": (-3_600, 86_400),
        "bulk_insert_batch_size": (1, 10_000),
        "event_query_max_days": (1, 3_650),
        "retention_days": (1, 3_650),
        "retention_min_days": (1, 365),
        "export_projection_bytes_per_event": (1, 65_536),
        "export_iterator_chunk_size": (1, 10_000),
        "checksum_chunk_bytes": (4_096, 16_777_216),
        "export_expiry_days": (1, 365),
        "discovery_min_events": (1, 1_000_000),
        "discovery_min_cases": (1, 100_000),
        "alpha_max_activities": (2, 10_000),
        "bottleneck_reuse_minutes": (0, 10_080),
        "bottleneck_min_cases": (1, 100_000),
        "outbox_freshness_seconds": (1, 86_400),
        "default_time_window_days": (1, 3_650),
        "list_page_size": (1, 100),
        "detail_page_size": (1, 100),
        "polling_interval_ms": (1_000, 300_000),
        "download_timeout_ms": (1_000, 300_000),
        "visual_canvas_width": (320, 10_000),
        "visual_canvas_height": (240, 10_000),
        "visual_node_width": (20, 1_000),
        "visual_node_height": (20, 1_000),
        "visual_layout_columns": (1, 100),
        "visual_horizontal_gap": (20, 2_000),
        "visual_vertical_gap": (20, 2_000),
        "visual_layout_padding": (0, 1_000),
        "download_retry_attempts": (0, 10),
        "download_retry_base_ms": (10, 60_000),
        "download_circuit_failure_threshold": (1, 100),
        "download_circuit_reset_ms": (1_000, 600_000),
    }
    assert process_services.FLOAT_LIMITS == {
        "heuristic_default_threshold": (0.0, 1.0),
        "inductive_default_threshold": (0.0, 1.0),
        "algorithm_threshold_step": (0.0001, 1.0),
        "algorithm_threshold_min": (0.0, 1.0),
        "algorithm_threshold_max": (0.0, 1.0),
        "low_fitness_threshold": (0.0, 1.0),
        "bottleneck_critical_ratio": (1.0, 1000.0),
        "bottleneck_high_ratio": (1.0, 1000.0),
        "bottleneck_medium_ratio": (1.0, 1000.0),
        "tail_duration_percentile": (0.5, 0.9999),
        "resource_concentration_threshold": (0.0, 1.0),
        "variant_grouping_percentage": (0.0, 100.0),
        "visual_zoom_min": (0.1, 10.0),
        "visual_zoom_max": (0.1, 10.0),
        "visual_zoom_step": (0.01, 2.0),
        "visual_edge_width_min": (0.1, 100.0),
        "visual_edge_width_max": (0.1, 100.0),
        "visual_frequency_divisor": (0.01, 1_000_000.0),
        "visual_duration_divisor": (0.01, 1_000_000.0),
    }


# Fields whose numeric bound is validated independently of every other field in the
# document (no cross-field ordering/coupling rule). Used to exhaustively probe the
# inclusive INTEGER_LIMITS/FLOAT_LIMITS boundaries without tripping unrelated
# cross-field invariants (retention pairing, threshold/ratio/zoom ordering, ...).
_INDEPENDENT_INTEGER_FIELDS = [
    "max_batch_events",
    "max_export_events",
    "max_export_bytes",
    "max_conformance_events",
    "text_max_length",
    "attributes_max_bytes",
    "source_module_max_length",
    "max_event_age_days",
    "future_clock_skew_seconds",
    "bulk_insert_batch_size",
    "event_query_max_days",
    "export_projection_bytes_per_event",
    "export_iterator_chunk_size",
    "checksum_chunk_bytes",
    "export_expiry_days",
    "discovery_min_events",
    "discovery_min_cases",
    "alpha_max_activities",
    "bottleneck_reuse_minutes",
    "bottleneck_min_cases",
    "outbox_freshness_seconds",
    "default_time_window_days",
    "list_page_size",
    "detail_page_size",
    "polling_interval_ms",
    "download_timeout_ms",
    "visual_canvas_width",
    "visual_canvas_height",
    "visual_node_width",
    "visual_node_height",
    "visual_layout_columns",
    "visual_horizontal_gap",
    "visual_vertical_gap",
    "visual_layout_padding",
    "download_retry_attempts",
    "download_retry_base_ms",
    "download_circuit_failure_threshold",
    "download_circuit_reset_ms",
]
_INDEPENDENT_FLOAT_FIELDS = [
    "tail_duration_percentile",
    "resource_concentration_threshold",
    "variant_grouping_percentage",
    "visual_frequency_divisor",
    "visual_duration_divisor",
]


@pytest.mark.parametrize("field", _INDEPENDENT_INTEGER_FIELDS)
def test_configuration_integer_limits_are_inclusive_at_both_boundaries(field) -> None:
    minimum, maximum = process_services.INTEGER_LIMITS[field]
    ProcessMiningConfigurationService.validate_document({**DEFAULT_CONFIGURATION, field: minimum})
    ProcessMiningConfigurationService.validate_document({**DEFAULT_CONFIGURATION, field: maximum})
    with pytest.raises(ValidationError):
        ProcessMiningConfigurationService.validate_document({**DEFAULT_CONFIGURATION, field: minimum - 1})
    with pytest.raises(ValidationError):
        ProcessMiningConfigurationService.validate_document({**DEFAULT_CONFIGURATION, field: maximum + 1})


@pytest.mark.parametrize("field", _INDEPENDENT_FLOAT_FIELDS)
def test_configuration_float_limits_are_inclusive_at_both_boundaries(field) -> None:
    minimum, maximum = process_services.FLOAT_LIMITS[field]
    ProcessMiningConfigurationService.validate_document({**DEFAULT_CONFIGURATION, field: minimum})
    ProcessMiningConfigurationService.validate_document({**DEFAULT_CONFIGURATION, field: maximum})
    with pytest.raises(ValidationError):
        ProcessMiningConfigurationService.validate_document({**DEFAULT_CONFIGURATION, field: minimum - 0.01})
    with pytest.raises(ValidationError):
        ProcessMiningConfigurationService.validate_document({**DEFAULT_CONFIGURATION, field: maximum + 0.01})


def test_configuration_reports_precisely_missing_or_unknown_keys() -> None:
    missing_only = {key: value for key, value in DEFAULT_CONFIGURATION.items() if key != "enabled"}
    with pytest.raises(ValidationError) as exc:
        ProcessMiningConfigurationService.validate_document(missing_only)
    assert exc.value.detail["document"] == {"missing": ["enabled"]}

    unknown_only = {**DEFAULT_CONFIGURATION, "surprise_field": True}
    with pytest.raises(ValidationError) as exc:
        ProcessMiningConfigurationService.validate_document(unknown_only)
    assert exc.value.detail["document"] == {"unknown": ["surprise_field"]}

    both = {key: value for key, value in DEFAULT_CONFIGURATION.items() if key != "enabled"}
    both["surprise_field"] = True
    with pytest.raises(ValidationError) as exc:
        ProcessMiningConfigurationService.validate_document(both)
    assert exc.value.detail["document"] == {"missing": ["enabled"], "unknown": ["surprise_field"]}


def test_configuration_retention_days_boundary_equal_to_minimum_is_valid() -> None:
    normalized = ProcessMiningConfigurationService.validate_document(
        {**DEFAULT_CONFIGURATION, "retention_days": 30, "retention_min_days": 30}
    )
    assert normalized["retention_days"] == 30
    with pytest.raises(ValidationError):
        ProcessMiningConfigurationService.validate_document(
            {**DEFAULT_CONFIGURATION, "retention_days": 29, "retention_min_days": 30}
        )


def test_configuration_algorithm_threshold_min_equal_to_max_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        ProcessMiningConfigurationService.validate_document(
            {**DEFAULT_CONFIGURATION, "algorithm_threshold_min": 0.5, "algorithm_threshold_max": 0.5}
        )
    assert "algorithm_threshold_max" in exc.value.detail
    normalized = ProcessMiningConfigurationService.validate_document(
        {
            **DEFAULT_CONFIGURATION,
            "algorithm_threshold_min": 0.4999,
            "algorithm_threshold_max": 0.5,
            "heuristic_default_threshold": 0.5,
            "inductive_default_threshold": 0.4999,
        }
    )
    assert normalized["algorithm_threshold_min"] == 0.4999


def test_configuration_default_thresholds_are_valid_exactly_at_range_edges() -> None:
    normalized = ProcessMiningConfigurationService.validate_document(
        {
            **DEFAULT_CONFIGURATION,
            "algorithm_threshold_min": 0.2,
            "algorithm_threshold_max": 0.8,
            "heuristic_default_threshold": 0.8,
            "inductive_default_threshold": 0.2,
        }
    )
    assert normalized["heuristic_default_threshold"] == 0.8
    assert normalized["inductive_default_threshold"] == 0.2
    with pytest.raises(ValidationError) as exc:
        ProcessMiningConfigurationService.validate_document(
            {
                **DEFAULT_CONFIGURATION,
                "algorithm_threshold_min": 0.2,
                "algorithm_threshold_max": 0.8,
                "heuristic_default_threshold": 0.199999,
            }
        )
    assert "heuristic_default_threshold" in exc.value.detail


def test_configuration_severity_ratio_ties_are_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        ProcessMiningConfigurationService.validate_document(
            {
                **DEFAULT_CONFIGURATION,
                "bottleneck_critical_ratio": 5.0,
                "bottleneck_high_ratio": 5.0,
                "bottleneck_medium_ratio": 2.0,
            }
        )
    assert "bottleneck_critical_ratio" in exc.value.detail

    with pytest.raises(ValidationError) as exc:
        ProcessMiningConfigurationService.validate_document(
            {
                **DEFAULT_CONFIGURATION,
                "bottleneck_critical_ratio": 10.0,
                "bottleneck_high_ratio": 3.0,
                "bottleneck_medium_ratio": 3.0,
            }
        )
    assert "bottleneck_critical_ratio" in exc.value.detail


def test_configuration_visual_zoom_and_edge_width_ties_are_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        ProcessMiningConfigurationService.validate_document(
            {**DEFAULT_CONFIGURATION, "visual_zoom_min": 1.0, "visual_zoom_max": 1.0}
        )
    assert "visual_zoom_max" in exc.value.detail

    with pytest.raises(ValidationError) as exc:
        ProcessMiningConfigurationService.validate_document(
            {**DEFAULT_CONFIGURATION, "visual_edge_width_min": 2.0, "visual_edge_width_max": 2.0}
        )
    assert "visual_edge_width_max" in exc.value.detail


def test_configuration_forbidden_attribute_keys_boundary_length_and_count() -> None:
    exactly_100 = [f"key-{i}" for i in range(100)]
    normalized = ProcessMiningConfigurationService.validate_document(
        {**DEFAULT_CONFIGURATION, "forbidden_attribute_keys": exactly_100}
    )
    assert len(normalized["forbidden_attribute_keys"]) == 100

    too_many = [f"key-{i}" for i in range(101)]
    with pytest.raises(ValidationError) as exc:
        ProcessMiningConfigurationService.validate_document(
            {**DEFAULT_CONFIGURATION, "forbidden_attribute_keys": too_many}
        )
    assert "forbidden_attribute_keys" in exc.value.detail

    exactly_64_chars = "k" * 64
    normalized = ProcessMiningConfigurationService.validate_document(
        {**DEFAULT_CONFIGURATION, "forbidden_attribute_keys": [exactly_64_chars]}
    )
    assert normalized["forbidden_attribute_keys"] == [exactly_64_chars]

    too_long = "k" * 65
    with pytest.raises(ValidationError):
        ProcessMiningConfigurationService.validate_document(
            {**DEFAULT_CONFIGURATION, "forbidden_attribute_keys": [too_long]}
        )
    with pytest.raises(ValidationError):
        ProcessMiningConfigurationService.validate_document(
            {**DEFAULT_CONFIGURATION, "forbidden_attribute_keys": ["   "]}
        )


def test_correlation_id_boundary_at_exactly_128_characters_passes() -> None:
    value = "x" * 128
    assert process_services._correlation_id(value) == value
    with pytest.raises(ValidationError):
        process_services._correlation_id("x" * 129)


def test_preview_excludes_unchanged_fields_from_the_diff() -> None:
    tenant = uuid.uuid4()
    service = ProcessMiningConfigurationService()
    service.get_configuration(tenant)

    preview = service.preview(tenant, {**DEFAULT_CONFIGURATION, "retention_days": 200})

    assert preview["changes"] == {"retention_days": {"from": 365, "to": 200}}
    assert "list_page_size" not in preview["changes"]
    assert "environment" not in preview["changes"]


def test_import_document_rejects_wrong_schema_version_and_wrong_module_independently() -> None:
    service = ProcessMiningConfigurationService()
    valid_envelope = {"schema_version": "1.0", "module": "process_mining", "document": DEFAULT_CONFIGURATION}

    with pytest.raises(ValidationError) as exc:
        service.import_document(uuid.uuid4(), uuid.uuid4(), "corr-a", {**valid_envelope, "schema_version": "2.0"})
    assert "configuration" in exc.value.detail

    with pytest.raises(ValidationError) as exc:
        service.import_document(uuid.uuid4(), uuid.uuid4(), "corr-b", {**valid_envelope, "module": "other_module"})
    assert "configuration" in exc.value.detail


def test_self_validate_workflow_rejects_missing_state_extra_state_and_bad_targets() -> None:
    states = {"a", "b"}

    with pytest.raises(ValidationError):
        process_services.self_validate_workflow({"a": []}, states, "wf")
    with pytest.raises(ValidationError):
        process_services.self_validate_workflow({"a": [], "b": [], "c": []}, states, "wf")
    with pytest.raises(ValidationError):
        process_services.self_validate_workflow({"a": "b", "b": []}, states, "wf")
    with pytest.raises(ValidationError):
        process_services.self_validate_workflow({"a": ["not-a-state"], "b": []}, states, "wf")

    process_services.self_validate_workflow({"a": ["b"], "b": ["a"]}, states, "wf")


def test_config_workflow_rejects_non_string_targets_in_the_list() -> None:
    with pytest.raises(ValidationError):
        process_services._config_workflow({"workflow": {"queued": ["running", 5]}}, "workflow")
    with pytest.raises(ValidationError):
        process_services._config_workflow({"workflow": {5: ["running"]}}, "workflow")
    workflow = process_services._config_workflow({"workflow": {"queued": ["running"]}}, "workflow")
    assert workflow == {"queued": ("running",)}


def test_required_text_boundary_exact_limit_passes_and_over_limit_fails() -> None:
    at_limit = "x" * 10
    assert process_services._required_text(at_limit, "field", 10) == at_limit
    with pytest.raises(ValidationError):
        process_services._required_text("x" * 11, "field", 10)
    with pytest.raises(ValidationError):
        process_services._required_text("   ", "field", 10)
    with pytest.raises(ValidationError):
        process_services._required_text(None, "field", 10)


def test_aware_datetime_rejects_invalid_iso_strings_naive_and_non_datetime_values() -> None:
    with pytest.raises(ValidationError):
        process_services._aware_datetime("not-a-real-date", "field")
    with pytest.raises(ValidationError):
        process_services._aware_datetime(timezone.now().replace(tzinfo=None), "field")
    with pytest.raises(ValidationError):
        process_services._aware_datetime(12345, "field")
    parsed = process_services._aware_datetime("2024-01-01T00:00:00Z", "field")
    assert parsed.year == 2024


def test_get_helper_skips_is_deleted_filter_for_models_without_the_field() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    event = EventFactory(tenant_id=tenant, created_by=actor)

    found = process_services._get(ProcessEvent, tenant, event.id, active=True)

    assert found.id == event.id
    with pytest.raises(NotFound):
        process_services._get(ProcessEvent, tenant, uuid.uuid4(), active=True)


def test_safe_attributes_rejects_non_dict_values_and_enforces_exact_byte_boundary() -> None:
    configuration = {**DEFAULT_CONFIGURATION, "forbidden_attribute_keys": ["secret"]}
    assert process_services._safe_attributes(None, configuration) == {}
    with pytest.raises(ValidationError):
        process_services._safe_attributes("not-a-dict", configuration)

    payload = {"a": "1234"}
    encoded_length = len(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
    at_limit_configuration = {**configuration, "attributes_max_bytes": encoded_length}
    assert process_services._safe_attributes(payload, at_limit_configuration) == payload

    over_limit_configuration = {**configuration, "attributes_max_bytes": encoded_length - 1}
    with pytest.raises(ValidationError):
        process_services._safe_attributes(payload, over_limit_configuration)


def test_ingestion_rejects_non_sequence_events_and_enforces_batch_size_boundary() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(ValidationError):
        EventLogService().ingest_events(tenant, actor, "canonical", "orders", "not-a-sequence")
    with pytest.raises(ValidationError):
        EventLogService().ingest_events(tenant, actor, "canonical", "orders", [])

    ProcessMiningConfigurationService().update(
        tenant, actor, "corr-batch-limit", {**DEFAULT_CONFIGURATION, "max_batch_events": 1}
    )
    occurred = timezone.now() - timedelta(hours=1)
    two_events = [
        {"case_id": "c1", "activity": "a", "occurred_at": occurred},
        {"case_id": "c2", "activity": "a", "occurred_at": occurred},
    ]
    with pytest.raises(ValidationError):
        EventLogService().ingest_events(tenant, actor, "canonical", "orders", two_events)


def test_ingestion_accepts_event_exactly_at_the_cutoff_boundaries() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    max_age_days = DEFAULT_CONFIGURATION["max_event_age_days"]
    skew_seconds = DEFAULT_CONFIGURATION["future_clock_skew_seconds"]
    now = timezone.now()
    at_age_cutoff = now - timedelta(days=max_age_days) + timedelta(seconds=5)
    at_future_cutoff = now + timedelta(seconds=skew_seconds) - timedelta(seconds=5)

    result = EventLogService().ingest_events(
        tenant,
        actor,
        "canonical",
        "orders",
        [
            {"case_id": "c1", "activity": "a", "occurred_at": at_age_cutoff},
            {"case_id": "c2", "activity": "a", "occurred_at": at_future_cutoff},
        ],
    )
    assert result.accepted == 2 and result.rejected == 0


def test_ingestion_defaults_missing_resource_and_source_event_id_to_none() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    occurred = timezone.now() - timedelta(hours=2)
    result = EventLogService().ingest_events(
        tenant, actor, "canonical", "orders", [{"case_id": "c1", "activity": "a", "occurred_at": occurred}]
    )
    assert result.accepted == 1
    event = ProcessEvent.objects.for_tenant(tenant).get()
    assert event.resource is None
    assert event.source_event_id is None


def test_event_query_rejects_zero_width_range_and_accepts_boundary_max_days() -> None:
    tenant = uuid.uuid4()
    now = timezone.now()
    with pytest.raises(ValidationError):
        EventLogService().query_events(tenant, {"process_name": "orders", "start": now, "end": now})

    maximum_days = DEFAULT_CONFIGURATION["event_query_max_days"]
    results = EventLogService().query_events(
        tenant,
        {"process_name": "orders", "start": now - timedelta(days=maximum_days), "end": now},
    )
    assert list(results) == []


def test_purge_expired_events_defaults_actor_and_accepts_boundary_retention() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    EventFactory(
        tenant_id=tenant,
        created_by=actor,
        process_name="orders",
        occurred_at=timezone.now() - timedelta(days=40),
    )

    purged_with_default_actor = EventLogService().purge_expired_events(tenant, retention_days=None)
    tombstone = ProcessEventRetentionTombstone.objects.for_tenant(tenant).get()
    assert tombstone.created_by == uuid.UUID(int=0)
    assert purged_with_default_actor == 0

    minimum = DEFAULT_CONFIGURATION["retention_min_days"]
    assert EventLogService().purge_expired_events(tenant, retention_days=minimum, actor_id=actor) == 1


def test_query_service_models_search_matches_description_alone_and_filters_by_reference() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    described = ProcessModelService().create_imported_model(
        tenant, actor, "Widget Pipeline", "widget_process", "quarterly billing reconciliation", graph()
    )
    ProcessModelService().create_imported_model(tenant, actor, "Other Model", "other_process", "", graph())

    by_description_only = ProcessMiningQueryService.models(tenant, {"search": "reconciliation"})
    assert list(by_description_only) == [described]

    without_reference = ProcessMiningQueryService.models(tenant, {"has_reference": "false"})
    assert list(without_reference.order_by("name")) == list(ProcessModel.objects.for_tenant(tenant).order_by("name"))

    version = described.versions.get()
    ProcessModelService().set_reference_version(tenant, described.id, version.id, actor, "ref-v1")

    with_reference = ProcessMiningQueryService.models(tenant, {"has_reference": "true"})
    assert list(with_reference) == [described]
    without_reference_after = ProcessMiningQueryService.models(tenant, {"has_reference": "false"})
    assert described not in list(without_reference_after)


def test_process_overview_search_matches_process_name_and_has_reference_filters() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    event_log(tenant, actor, cases=1)
    model = ProcessModelService().create_imported_model(tenant, actor, "Reference", "order_to_cash", "", graph())

    matched = ProcessModelService().get_process_overview(tenant, {"search": "order_to"})
    assert [row["process_name"] for row in matched] == ["order_to_cash"]

    not_yet_referenced = ProcessModelService().get_process_overview(tenant, {"has_reference": "true"})
    assert not_yet_referenced == []
    still_unreferenced = ProcessModelService().get_process_overview(tenant, {"has_reference": "false"})
    assert [row["process_name"] for row in still_unreferenced] == ["order_to_cash"]

    version = model.versions.get()
    ProcessModelService().set_reference_version(tenant, model.id, version.id, actor, "ref-v1")
    with_reference = ProcessModelService().get_process_overview(tenant, {"has_reference": "true"})
    assert [row["process_name"] for row in with_reference] == ["order_to_cash"]
    now_excluded = ProcessModelService().get_process_overview(tenant, {"has_reference": "false"})
    assert now_excluded == []


def test_process_overview_sorts_stably_when_ordering_key_is_none() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    EventFactory(tenant_id=tenant, created_by=actor, process_name="alpha_process")
    EventFactory(tenant_id=tenant, created_by=actor, process_name="beta_process")

    ascending = ProcessModelService().get_process_overview(tenant, {"ordering": "last_discovery"})
    descending = ProcessModelService().get_process_overview(tenant, {"ordering": "-last_discovery"})

    assert {row["process_name"] for row in ascending} == {"alpha_process", "beta_process"}
    assert {row["process_name"] for row in descending} == {"alpha_process", "beta_process"}
    with pytest.raises(ValidationError):
        ProcessModelService().get_process_overview(tenant, {"ordering": "unsupported"})


def test_set_reference_version_reports_not_found_for_missing_model_and_missing_version() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    model = ProcessModelService().create_imported_model(tenant, actor, "Reference", "orders", "", graph())
    version = model.versions.get()

    with pytest.raises(NotFound):
        ProcessModelService().set_reference_version(tenant, uuid.uuid4(), version.id, actor, "key-1")
    with pytest.raises(NotFound):
        ProcessModelService().set_reference_version(tenant, model.id, uuid.uuid4(), actor, "key-2")


def test_discovery_request_enforces_event_case_and_alpha_activity_boundaries() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    event_log(tenant, actor, cases=2)  # 2 cases, 6 events, 3 distinct activities
    ProcessMiningConfigurationService().update(
        tenant,
        actor,
        "corr-discovery-boundary",
        {
            **DEFAULT_CONFIGURATION,
            "discovery_min_events": 6,
            "discovery_min_cases": 2,
            "alpha_max_activities": 3,
        },
    )
    service = ProcessDiscoveryService()

    at_boundary = service.request_discovery(tenant, actor, "order_to_cash", "alpha_miner", {}, "alpha-at-boundary")
    assert at_boundary.async_job_id is not None

    ProcessMiningConfigurationService().update(
        tenant,
        actor,
        "corr-discovery-events-boundary",
        {
            **DEFAULT_CONFIGURATION,
            "discovery_min_events": 7,
            "discovery_min_cases": 2,
            "alpha_max_activities": 3,
        },
    )
    with pytest.raises(ValidationError) as exc:
        service.request_discovery(tenant, actor, "order_to_cash", "inductive_miner", {}, "events-below-minimum")
    assert "process_name" in exc.value.detail


def test_discovery_request_alpha_miner_rejects_exceeding_activity_count() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    event_log(tenant, actor, cases=2)
    ProcessMiningConfigurationService().update(
        tenant,
        actor,
        "corr-alpha-exceeded",
        {
            **DEFAULT_CONFIGURATION,
            "discovery_min_events": 1,
            "discovery_min_cases": 1,
            "alpha_max_activities": 2,
        },
    )
    with pytest.raises(ValidationError) as exc:
        ProcessDiscoveryService().request_discovery(tenant, actor, "order_to_cash", "alpha_miner", {}, "alpha-too-many")
    assert "algorithm" in exc.value.detail


def test_discovery_worker_computes_exact_average_case_duration() -> None:
    tenant, actor, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    event_log(tenant, actor, cases=3)
    discovery = ProcessDiscoveryJob.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_name="order_to_cash",
        algorithm="inductive_miner",
        parameters={"noise_threshold": 0.0},
        async_job_id=job_id,
        idempotency_key="run-discovery-duration",
    )

    ProcessDiscoveryService().run_discovery(tenant, discovery.id, job_id)
    version = ProcessDiscoveryService().get_discovered_model(tenant, discovery.id)

    assert version.avg_case_duration_seconds == Decimal("120.00")


def test_discovery_worker_marks_failure_and_transitions_out_of_running_on_unavailable_algorithm(monkeypatch) -> None:
    tenant, actor, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    event_log(tenant, actor, cases=3)
    discovery = ProcessDiscoveryJob.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_name="order_to_cash",
        algorithm="inductive_miner",
        parameters={},
        async_job_id=job_id,
        idempotency_key="run-discovery-unavailable",
    )
    monkeypatch.setattr(process_services.registry, "get", lambda name: object())

    with pytest.raises(OperationFailed) as exc:
        ProcessDiscoveryService().run_discovery(tenant, discovery.id, job_id)

    assert exc.value.error_code == "DISCOVERY_FAILED"
    discovery.refresh_from_db()
    assert discovery.status == AnalysisStatus.FAILED
    assert discovery.error_code == "DISCOVERY_FAILED"


def test_conformance_worker_marks_failure_and_transitions_out_of_running_on_unavailable_algorithm(monkeypatch) -> None:
    tenant, actor, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rows = event_log(tenant, actor, cases=1)
    model = ProcessModel.objects.create(
        tenant_id=tenant, created_by=actor, name="Reference", process_name="order_to_cash", source_kind="imported"
    )
    version = ProcessModelVersion.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_model=model,
        version=1,
        model_data=graph(),
        event_count=len(rows),
        case_count=1,
        activity_count=3,
        published_at=timezone.now(),
    )
    check = ConformanceCheck.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_model_version=version,
        event_filter={},
        async_job_id=job_id,
        idempotency_key="run-conformance-unavailable",
    )
    monkeypatch.setattr(process_services.registry, "get", lambda name: object())

    with pytest.raises(OperationFailed) as exc:
        ConformanceService().run_check(tenant, check.id, job_id)

    assert exc.value.error_code == "CONFORMANCE_FAILED"
    check.refresh_from_db()
    assert check.status == AnalysisStatus.FAILED
    assert check.error_code == "CONFORMANCE_FAILED"


def test_bottleneck_worker_marks_failure_and_transitions_out_of_running_on_unavailable_algorithm(monkeypatch) -> None:
    tenant, actor, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rows = event_log(tenant, actor, cases=1)
    start = rows[0].occurred_at - timedelta(seconds=1)
    end = rows[-1].occurred_at + timedelta(seconds=1)
    analysis = BottleneckAnalysis.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_name="order_to_cash",
        time_range_start=start,
        time_range_end=end,
        async_job_id=job_id,
        idempotency_key="run-bottleneck-unavailable",
    )
    monkeypatch.setattr(process_services.registry, "get", lambda name: object())

    with pytest.raises(OperationFailed) as exc:
        BottleneckService().run_analysis(tenant, analysis.id, job_id)

    assert exc.value.error_code == "BOTTLENECK_FAILED"
    analysis.refresh_from_db()
    assert analysis.status == AnalysisStatus.FAILED
    assert analysis.error_code == "BOTTLENECK_FAILED"


def test_export_request_boundary_at_exact_event_limit_succeeds() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    event_log(tenant, actor, cases=2)  # 6 events
    ProcessMiningConfigurationService().update(
        tenant,
        actor,
        "corr-export-boundary",
        {**DEFAULT_CONFIGURATION, "max_export_events": 6},
    )

    record = ExportService().request_export(tenant, actor, "order_to_cash", "json", {}, "export-at-boundary")
    assert record.async_job_id is not None


def test_conformance_request_boundary_at_exact_event_limit_succeeds() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    rows = event_log(tenant, actor, cases=1)
    model = ProcessModel.objects.create(
        tenant_id=tenant, created_by=actor, name="Reference", process_name="order_to_cash", source_kind="imported"
    )
    version = ProcessModelVersion.objects.create(
        tenant_id=tenant,
        created_by=actor,
        process_model=model,
        version=1,
        model_data=graph(),
        event_count=len(rows),
        case_count=1,
        activity_count=3,
        published_at=timezone.now(),
    )
    ProcessMiningConfigurationService().update(
        tenant, actor, "corr-conformance-boundary", {**DEFAULT_CONFIGURATION, "max_conformance_events": len(rows)}
    )

    record = ConformanceService().request_check(tenant, actor, version.id, {}, "conformance-at-boundary")
    assert record.async_job_id is not None


def test_bottleneck_request_boundary_at_exact_case_minimum_succeeds() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    rows = event_log(tenant, actor, cases=3)
    start = rows[0].occurred_at - timedelta(seconds=1)
    end = rows[-1].occurred_at + timedelta(seconds=1)
    ProcessMiningConfigurationService().update(
        tenant, actor, "corr-bottleneck-boundary", {**DEFAULT_CONFIGURATION, "bottleneck_min_cases": 3}
    )

    record = BottleneckService().request_analysis(
        tenant, actor, "order_to_cash", (start, end), "bottleneck-at-boundary"
    )
    assert record.async_job_id is not None


@pytest.mark.parametrize(
    ("run_once", "second_call"),
    [
        ("export", "export"),
        ("discovery", "discovery"),
        ("conformance", "conformance"),
        ("bottleneck", "bottleneck"),
    ],
)
def test_worker_run_is_idempotent_when_record_is_already_completed(run_once, second_call) -> None:
    tenant, actor, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    if run_once != "bottleneck":
        event_log(tenant, actor, cases=1)

    if run_once == "export":
        export = EventExportJob.objects.create(
            tenant_id=tenant,
            created_by=actor,
            process_name="order_to_cash",
            format="json",
            event_filter={},
            async_job_id=job_id,
            idempotency_key="idempotent-export",
        )
        first = ExportService().run_export(tenant, export.id, job_id)
        second = ExportService().run_export(tenant, export.id, uuid.uuid4())
        assert first.id == second.id and second.status == ExportStatus.COMPLETED
    elif run_once == "discovery":
        discovery = ProcessDiscoveryJob.objects.create(
            tenant_id=tenant,
            created_by=actor,
            process_name="order_to_cash",
            algorithm="inductive_miner",
            parameters={"noise_threshold": 0.0},
            async_job_id=job_id,
            idempotency_key="idempotent-discovery",
        )
        first = ProcessDiscoveryService().run_discovery(tenant, discovery.id, job_id)
        second = ProcessDiscoveryService().run_discovery(tenant, discovery.id, uuid.uuid4())
        assert first.id == second.id and second.status == AnalysisStatus.COMPLETED
    elif run_once == "conformance":
        model = ProcessModel.objects.create(
            tenant_id=tenant, created_by=actor, name="Reference", process_name="order_to_cash", source_kind="imported"
        )
        version = ProcessModelVersion.objects.create(
            tenant_id=tenant,
            created_by=actor,
            process_model=model,
            version=1,
            model_data=graph(),
            event_count=3,
            case_count=1,
            activity_count=3,
            published_at=timezone.now(),
        )
        check = ConformanceCheck.objects.create(
            tenant_id=tenant,
            created_by=actor,
            process_model_version=version,
            event_filter={},
            async_job_id=job_id,
            idempotency_key="idempotent-conformance",
        )
        first = ConformanceService().run_check(tenant, check.id, job_id)
        second = ConformanceService().run_check(tenant, check.id, uuid.uuid4())
        assert first.id == second.id and second.status == AnalysisStatus.COMPLETED
    else:
        rows = event_log(tenant, actor, cases=3)
        start = rows[0].occurred_at - timedelta(seconds=1)
        end = rows[-1].occurred_at + timedelta(seconds=1)
        analysis = BottleneckAnalysis.objects.create(
            tenant_id=tenant,
            created_by=actor,
            process_name="order_to_cash",
            time_range_start=start,
            time_range_end=end,
            async_job_id=job_id,
            idempotency_key="idempotent-bottleneck",
        )
        first = BottleneckService().run_analysis(tenant, analysis.id, job_id)
        second = BottleneckService().run_analysis(tenant, analysis.id, uuid.uuid4())
        assert first.id == second.id and second.status == AnalysisStatus.COMPLETED


def test_cancel_uses_default_reason_message_when_none_supplied() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    export = ExportFactory(tenant_id=tenant, created_by=actor, idempotency_key="default-reason-export")

    cancelled = ExportService().cancel_export(tenant, export.id, actor, "cancel-default-reason")

    assert cancelled.transition_history[-1]["metadata"]["reason"] == "Export cancel"


def test_process_overview_or_search_matches_process_name_alone() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    EventFactory(tenant_id=tenant, created_by=actor, process_name="unique_search_target")

    results = ProcessModelService().get_process_overview(tenant, {"search": "unique_search_target"})

    assert [row["process_name"] for row in results] == ["unique_search_target"]


def test_process_model_metadata_reference_overview_and_delete_guard() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    events = event_log(tenant, actor, cases=1)
    model = ProcessModelService().create_imported_model(tenant, actor, "Reference", "order_to_cash", "", graph())
    version = model.versions.get()
    referenced = ProcessModelService().set_reference_version(
        tenant,
        model.id,
        version.id,
        actor,
        "reference-model-v1",
        "validated by operator",
        correlation_id="corr-reference",
    )

    overview = ProcessModelService().get_process_overview(tenant, {"search": "order"})
    assert overview == [
        {
            "process_name": "order_to_cash",
            "event_count": len(events),
            "case_count": 1,
            "last_activity": events[-1].occurred_at,
            "has_reference": True,
            "model_id": model.id,
            "last_discovery": None,
        }
    ]
    assert referenced.id == version.id

    check = ConformanceFactory(process_model_version=version, status=AnalysisStatus.QUEUED)
    with pytest.raises(ValidationError):
        ProcessModelService().soft_delete_model(tenant, model.id, actor)

    ConformanceFactory._meta.model.objects.for_tenant(tenant).filter(id=check.id).update(
        status=AnalysisStatus.CANCELLED
    )
    ProcessModelService().update_model_metadata(tenant, model.id, actor, "Reference v2", "ready")
    ProcessModelService().soft_delete_model(tenant, model.id, actor)
    model.refresh_from_db()
    assert model.is_deleted is True
