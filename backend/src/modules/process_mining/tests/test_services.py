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
