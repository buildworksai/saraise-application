"""Tenant-safe process-mining persistence and evidence invariants."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models

from src.core.tenancy import TenantQuerySet, TenantScopedModel, TimestampedModel


def generate_uuid() -> str:
    """Keep the callable imported by the immutable legacy migration."""

    return str(uuid.uuid4())


class AnalysisStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    TIMED_OUT = "timed_out", "Timed out"
    CANCELLED = "cancelled", "Cancelled"


class ExportStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    TIMED_OUT = "timed_out", "Timed out"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"


class MiningAlgorithmName(models.TextChoices):
    ALPHA = "alpha_miner", "Alpha miner"
    HEURISTIC = "heuristic_miner", "Heuristic miner"
    INDUCTIVE = "inductive_miner", "Inductive miner"


class ExportFormat(models.TextChoices):
    XES = "xes", "XES"
    CSV = "csv", "CSV"
    JSON = "json", "JSON"


class ModelSourceKind(models.TextChoices):
    DISCOVERED = "discovered", "Discovered"
    IMPORTED = "imported", "Imported"


class DeviationType(models.TextChoices):
    MISSING_ACTIVITY = "missing_activity", "Missing activity"
    UNEXPECTED_ACTIVITY = "unexpected_activity", "Unexpected activity"
    WRONG_ORDER = "wrong_order", "Wrong order"
    SKIPPED_PATH = "skipped_path", "Skipped path"


class BottleneckSeverity(models.TextChoices):
    CRITICAL = "critical", "Critical"
    HIGH = "high", "High"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"


class MutableDomainModel(TenantScopedModel, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.UUIDField(db_index=True, editable=False)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class AppendOnlyQuerySet(TenantQuerySet):
    def update(self, **kwargs: object) -> int:
        del kwargs
        raise ValidationError("Append-only evidence cannot be updated.", code="append_only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Append-only evidence cannot be deleted.", code="append_only")


class AppendOnlyDomainModel(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.UUIDField(db_index=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Completed analytical evidence is immutable.", code="append_only")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Append-only evidence cannot be deleted.", code="append_only")


class StatefulDomainModel(MutableDomainModel):
    """Reject status changes unless transition history changes in the same write."""

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding and self.pk:
            prior = type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).values(
                "status", "transition_history"
            ).first()
            if prior and prior["status"] != self.status and prior["transition_history"] == self.transition_history:
                raise ValidationError("Status changes must use the registered state machine.", code="state_machine")
        super().save(*args, **kwargs)


def _same_tenant(instance: models.Model, relation: str) -> None:
    relation_id = getattr(instance, f"{relation}_id", None)
    if relation_id is None or not getattr(instance, "tenant_id", None):
        return
    related_model = instance._meta.get_field(relation).remote_field.model
    if not related_model.objects.for_tenant(instance.tenant_id).filter(pk=relation_id).exists():
        raise ValidationError({relation: "Referenced evidence was not found."}, code="cross_tenant_reference")


def _changed(instance: models.Model, names: Iterable[str]) -> set[str]:
    if instance._state.adding or not instance.pk:
        return set()
    prior = type(instance)._base_manager.filter(pk=instance.pk, tenant_id=instance.tenant_id).values(*names).first()
    return set() if prior is None else {name for name in names if prior[name] != getattr(instance, name)}


def validate_graph(model_data: object) -> None:
    """Validate the versioned canonical graph ABI used by all adapters."""

    if not isinstance(model_data, dict):
        raise ValidationError("model_data must be an object.", code="invalid_graph")
    if model_data.get("schema_version") != "1.0":
        raise ValidationError("model_data.schema_version must be '1.0'.", code="invalid_graph")
    nodes = model_data.get("nodes")
    edges = model_data.get("edges")
    if not isinstance(nodes, list) or not nodes:
        raise ValidationError("A graph requires at least one node.", code="invalid_graph")
    if not isinstance(edges, list):
        raise ValidationError("Graph edges must be a list.", code="invalid_graph")
    node_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]:
            raise ValidationError("Every graph node requires a stable string id.", code="invalid_graph")
        if node.get("type") not in {"start", "activity", "end", "gateway"}:
            raise ValidationError("Graph node type is invalid.", code="invalid_graph")
        if node["id"] in node_ids:
            raise ValidationError("Graph node ids must be unique.", code="invalid_graph")
        if int(node.get("frequency", 0)) < 0:
            raise ValidationError("Node frequency cannot be negative.", code="invalid_graph")
        node_ids.add(node["id"])
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("source") not in node_ids or edge.get("target") not in node_ids:
            raise ValidationError("Every graph edge must connect existing nodes.", code="invalid_graph")
        if int(edge.get("frequency", 0)) < 0 or Decimal(str(edge.get("duration_seconds", 0))) < 0:
            raise ValidationError("Edge evidence cannot be negative.", code="invalid_graph")


class ProcessEvent(AppendOnlyDomainModel):
    process_name = models.CharField(max_length=255)
    source_module = models.CharField(max_length=100)
    source_event_id = models.CharField(max_length=255, null=True, blank=True)
    case_id = models.CharField(max_length=255)
    activity = models.CharField(max_length=255)
    occurred_at = models.DateTimeField()
    resource = models.CharField(max_length=255, null=True, blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    ingested_at = models.DateTimeField(auto_now_add=True)
    event_hash = models.CharField(max_length=64)

    class Meta:
        db_table = "process_mining_events"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "event_hash"], name="pm_event_tenant_hash_uniq"),
            models.UniqueConstraint(
                fields=["tenant_id", "source_module", "source_event_id"],
                condition=models.Q(source_event_id__isnull=False) & ~models.Q(source_event_id=""),
                name="pm_event_source_id_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "process_name", "occurred_at"], name="pm_evt_process_time"),
            models.Index(fields=["tenant_id", "process_name", "case_id", "occurred_at"], name="pm_evt_case_time"),
            models.Index(fields=["tenant_id", "activity", "occurred_at"], name="pm_evt_activity_time"),
            models.Index(fields=["tenant_id", "resource", "occurred_at"], name="pm_evt_resource_time"),
        ]


class EventExportJob(StatefulDomainModel):
    process_name = models.CharField(max_length=255)
    format = models.CharField(max_length=32, choices=ExportFormat.choices)
    event_filter = models.JSONField(default=dict)
    status = models.CharField(max_length=24, choices=ExportStatus.choices, default=ExportStatus.QUEUED)
    transition_history = models.JSONField(default=list, editable=False)
    async_job_id = models.UUIDField(null=True, unique=True, db_index=True)
    idempotency_key = models.CharField(max_length=255)
    artifact_key = models.CharField(max_length=1024, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    row_count = models.PositiveBigIntegerField(null=True)
    byte_size = models.PositiveBigIntegerField(null=True)
    sha256 = models.CharField(max_length=64, blank=True)
    expires_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "process_mining_export_jobs"
        constraints = [models.UniqueConstraint(fields=["tenant_id", "idempotency_key"], name="pm_export_idem_uniq")]
        indexes = [
            models.Index(fields=["tenant_id", "status", "created_at"], name="pm_export_status_time"),
            models.Index(fields=["tenant_id", "process_name", "created_at"], name="pm_export_process_time"),
        ]


class ProcessDiscoveryJob(StatefulDomainModel):
    process_name = models.CharField(max_length=255)
    algorithm = models.CharField(max_length=160, choices=MiningAlgorithmName.choices)
    parameters = models.JSONField(default=dict)
    status = models.CharField(max_length=24, choices=AnalysisStatus.choices, default=AnalysisStatus.QUEUED)
    transition_history = models.JSONField(default=list, editable=False)
    async_job_id = models.UUIDField(null=True, unique=True, db_index=True)
    idempotency_key = models.CharField(max_length=255)
    event_count = models.PositiveBigIntegerField(default=0)
    case_count = models.PositiveBigIntegerField(default=0)
    activity_count = models.PositiveBigIntegerField(default=0)
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "process_mining_discovery_jobs"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "idempotency_key"], name="pm_discovery_idem_uniq"),
            models.UniqueConstraint(
                fields=["tenant_id", "process_name", "algorithm"],
                condition=models.Q(status__in=[AnalysisStatus.QUEUED, AnalysisStatus.RUNNING]),
                name="pm_discovery_active_uniq",
            ),
            models.CheckConstraint(condition=models.Q(event_count__gte=0), name="pm_disc_event_nonneg"),
            models.CheckConstraint(condition=models.Q(case_count__gte=0), name="pm_disc_case_nonneg"),
            models.CheckConstraint(condition=models.Q(activity_count__gte=0), name="pm_disc_activity_nonneg"),
        ]
        indexes = [models.Index(fields=["tenant_id", "process_name", "status", "created_at"], name="pm_disc_status_time")]


class ProcessModel(MutableDomainModel):
    name = models.CharField(max_length=255)
    process_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    source_kind = models.CharField(max_length=24, choices=ModelSourceKind.choices)
    current_version_number = models.PositiveIntegerField(default=1)
    reference_version_number = models.PositiveIntegerField(null=True)

    class Meta:
        db_table = "process_mining_models"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "name"], condition=models.Q(is_deleted=False), name="pm_model_active_name_uniq"
            ),
            models.CheckConstraint(
                condition=models.Q(reference_version_number__isnull=True) | models.Q(reference_version_number__gt=0),
                name="pm_model_ref_positive",
            ),
        ]
        indexes = [models.Index(fields=["tenant_id", "process_name", "created_at"], name="pm_model_process_time")]


class ProcessModelVersion(AppendOnlyDomainModel):
    process_model = models.ForeignKey(ProcessModel, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    discovery_job = models.ForeignKey(
        ProcessDiscoveryJob, on_delete=models.PROTECT, related_name="model_versions", null=True, blank=True
    )
    algorithm = models.CharField(max_length=160, choices=MiningAlgorithmName.choices, null=True, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    model_data = models.JSONField()
    event_count = models.PositiveBigIntegerField(default=0)
    case_count = models.PositiveBigIntegerField(default=0)
    activity_count = models.PositiveBigIntegerField(default=0)
    avg_case_duration_seconds = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    is_reference = models.BooleanField(default=False)
    published_at = models.DateTimeField()

    class Meta:
        db_table = "process_mining_model_versions"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "process_model", "version"], name="pm_model_version_uniq"),
            models.UniqueConstraint(
                fields=["tenant_id", "process_model"], condition=models.Q(is_reference=True), name="pm_model_reference_uniq"
            ),
            models.CheckConstraint(condition=models.Q(event_count__gte=0), name="pm_ver_event_nonneg"),
            models.CheckConstraint(condition=models.Q(case_count__gte=0), name="pm_ver_case_nonneg"),
            models.CheckConstraint(condition=models.Q(activity_count__gte=0), name="pm_ver_activity_nonneg"),
            models.CheckConstraint(
                condition=models.Q(avg_case_duration_seconds__isnull=True) | models.Q(avg_case_duration_seconds__gte=0),
                name="pm_ver_duration_nonneg",
            ),
        ]
        indexes = [models.Index(fields=["tenant_id", "process_model", "published_at"], name="pm_version_model_time")]

    def clean(self) -> None:
        _same_tenant(self, "process_model")
        if self.discovery_job_id:
            _same_tenant(self, "discovery_job")
        validate_graph(self.model_data)


class ProcessModelReferenceAssignment(AppendOnlyDomainModel):
    """Immutable evidence selecting a reference version; latest assignment wins."""

    process_model = models.ForeignKey(ProcessModel, on_delete=models.PROTECT, related_name="reference_assignments")
    process_model_version = models.ForeignKey(
        ProcessModelVersion, on_delete=models.PROTECT, related_name="reference_assignments"
    )
    transition_key = models.CharField(max_length=255)
    reason = models.TextField(blank=True)
    correlation_id = models.CharField(max_length=128, db_index=True)

    class Meta:
        db_table = "process_mining_model_reference_assignments"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "process_model", "transition_key"], name="pm_ref_assignment_key_uniq"
            )
        ]
        indexes = [models.Index(fields=["tenant_id", "process_model", "created_at"], name="pm_ref_current")]

    def clean(self) -> None:
        _same_tenant(self, "process_model")
        _same_tenant(self, "process_model_version")
        if self.process_model_version_id and self.process_model_id:
            if self.process_model_version.process_model_id != self.process_model_id:
                raise ValidationError(
                    {"process_model_version": "Reference version does not belong to this model."},
                    code="invalid_reference",
                )


class ProcessMiningConfiguration(TenantScopedModel, TimestampedModel):
    """The single current, tenant-bound process-mining configuration document."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.JSONField()
    version = models.PositiveIntegerField(default=1)
    updated_by = models.UUIDField(db_index=True)

    class Meta:
        db_table = "process_mining_configurations"
        constraints = [models.UniqueConstraint(fields=["tenant_id"], name="pm_config_one_per_tenant")]


class ProcessMiningConfigurationVersion(AppendOnlyDomainModel):
    """Immutable snapshot used for history, export, and rollback."""

    configuration = models.ForeignKey(
        ProcessMiningConfiguration, on_delete=models.PROTECT, related_name="versions"
    )
    version = models.PositiveIntegerField()
    document = models.JSONField()
    correlation_id = models.CharField(max_length=128, db_index=True)
    source = models.CharField(max_length=32)

    class Meta:
        db_table = "process_mining_configuration_versions"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "configuration", "version"], name="pm_config_version_uniq")
        ]
        indexes = [models.Index(fields=["tenant_id", "configuration", "version"], name="pm_config_history")]

    def clean(self) -> None:
        _same_tenant(self, "configuration")


class ProcessMiningConfigurationAudit(AppendOnlyDomainModel):
    """Immutable who/what/when evidence for every configuration mutation."""

    configuration = models.ForeignKey(ProcessMiningConfiguration, on_delete=models.PROTECT, related_name="audits")
    version = models.PositiveIntegerField()
    action = models.CharField(max_length=32)
    previous_document = models.JSONField(blank=True)
    current_document = models.JSONField()
    correlation_id = models.CharField(max_length=128, db_index=True)

    class Meta:
        db_table = "process_mining_configuration_audits"
        indexes = [models.Index(fields=["tenant_id", "configuration", "created_at"], name="pm_config_audit_time")]

    def clean(self) -> None:
        _same_tenant(self, "configuration")


class ProcessEventRetentionTombstone(AppendOnlyDomainModel):
    """Governed immutable authorization evidence; source events remain intact."""

    cutoff = models.DateTimeField()
    event_count = models.PositiveBigIntegerField()
    reason = models.TextField()
    correlation_id = models.CharField(max_length=128, db_index=True)

    class Meta:
        db_table = "process_mining_event_retention_tombstones"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "cutoff"], name="pm_retention_cutoff_uniq")
        ]


class ExportArtifactDeletion(AppendOnlyDomainModel):
    """Durable idempotent deletion request committed before artifact removal."""

    export_job = models.ForeignKey(EventExportJob, on_delete=models.PROTECT, related_name="artifact_deletions")
    artifact_key = models.CharField(max_length=1024)
    correlation_id = models.CharField(max_length=128, db_index=True)

    class Meta:
        db_table = "process_mining_export_artifact_deletions"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "export_job"], name="pm_export_delete_once")
        ]

    def clean(self) -> None:
        _same_tenant(self, "export_job")


class ConformanceCheck(StatefulDomainModel):
    process_model_version = models.ForeignKey(ProcessModelVersion, on_delete=models.PROTECT, related_name="checks")
    event_filter = models.JSONField(default=dict)
    status = models.CharField(max_length=24, choices=AnalysisStatus.choices, default=AnalysisStatus.QUEUED)
    transition_history = models.JSONField(default=list, editable=False)
    async_job_id = models.UUIDField(null=True, unique=True, db_index=True)
    idempotency_key = models.CharField(max_length=255)
    fitness = models.DecimalField(max_digits=5, decimal_places=4, null=True)
    precision = models.DecimalField(max_digits=5, decimal_places=4, null=True)
    generalization = models.DecimalField(max_digits=5, decimal_places=4, null=True)
    total_cases = models.PositiveBigIntegerField(null=True)
    conformant_cases = models.PositiveBigIntegerField(null=True)
    deviating_cases = models.PositiveBigIntegerField(null=True)
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "process_mining_conformance_checks"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "idempotency_key"], name="pm_conf_idem_uniq"),
            models.UniqueConstraint(
                fields=["tenant_id", "process_model_version"],
                condition=models.Q(status__in=[AnalysisStatus.QUEUED, AnalysisStatus.RUNNING]),
                name="pm_conf_active_uniq",
            ),
            *[
                models.CheckConstraint(
                    condition=models.Q(**{f"{field}__isnull": True})
                    | (models.Q(**{f"{field}__gte": Decimal("0")}) & models.Q(**{f"{field}__lte": Decimal("1")})),
                    name=f"pm_conf_{field}_range",
                )
                for field in ("fitness", "precision", "generalization")
            ],
            models.CheckConstraint(
                condition=~models.Q(status=AnalysisStatus.COMPLETED)
                | models.Q(total_cases=models.F("conformant_cases") + models.F("deviating_cases")),
                name="pm_conf_case_totals",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "process_model_version", "status", "created_at"], name="pm_conf_status_time"
            )
        ]

    def clean(self) -> None:
        _same_tenant(self, "process_model_version")


class ConformanceDeviation(AppendOnlyDomainModel):
    conformance_check = models.ForeignKey(ConformanceCheck, on_delete=models.PROTECT, related_name="deviations")
    case_id = models.CharField(max_length=255)
    deviation_type = models.CharField(max_length=32, choices=DeviationType.choices)
    expected = models.CharField(max_length=255, blank=True)
    actual = models.CharField(max_length=255, blank=True)
    position = models.PositiveIntegerField(null=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "process_mining_conformance_deviations"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "conformance_check", "case_id", "position", "deviation_type"],
                name="pm_deviation_evidence_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["tenant_id", "conformance_check", "deviation_type"], name="pm_dev_check_type"),
            models.Index(fields=["tenant_id", "case_id"], name="pm_dev_case"),
        ]

    def clean(self) -> None:
        _same_tenant(self, "conformance_check")


class ConformanceCaseMetric(AppendOnlyDomainModel):
    conformance_check = models.ForeignKey(ConformanceCheck, on_delete=models.PROTECT, related_name="case_metrics")
    case_id = models.CharField(max_length=255)
    fitness = models.DecimalField(max_digits=5, decimal_places=4)
    is_conformant = models.BooleanField()
    deviation_count = models.PositiveIntegerField()
    trace_length = models.PositiveIntegerField()

    class Meta:
        db_table = "process_mining_conformance_case_metrics"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "conformance_check", "case_id"], name="pm_case_metric_uniq"),
            models.CheckConstraint(
                condition=models.Q(fitness__gte=Decimal("0")) & models.Q(fitness__lte=Decimal("1")),
                name="pm_case_fitness_range",
            ),
        ]
        indexes = [models.Index(fields=["tenant_id", "conformance_check", "fitness"], name="pm_case_fit_check")]

    def clean(self) -> None:
        _same_tenant(self, "conformance_check")


class BottleneckAnalysis(StatefulDomainModel):
    process_name = models.CharField(max_length=255)
    time_range_start = models.DateTimeField()
    time_range_end = models.DateTimeField()
    status = models.CharField(max_length=24, choices=AnalysisStatus.choices, default=AnalysisStatus.QUEUED)
    transition_history = models.JSONField(default=list, editable=False)
    async_job_id = models.UUIDField(null=True, unique=True, db_index=True)
    idempotency_key = models.CharField(max_length=255)
    total_cases = models.PositiveBigIntegerField(default=0)
    total_variants = models.PositiveBigIntegerField(default=0)
    avg_case_duration_seconds = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "process_mining_bottleneck_analyses"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "idempotency_key"], name="pm_bneck_idem_uniq"),
            models.CheckConstraint(condition=models.Q(time_range_end__gt=models.F("time_range_start")), name="pm_bneck_time_order"),
        ]
        indexes = [models.Index(fields=["tenant_id", "process_name", "status", "created_at"], name="pm_bneck_status_time")]


class BottleneckFinding(AppendOnlyDomainModel):
    analysis = models.ForeignKey(BottleneckAnalysis, on_delete=models.PROTECT, related_name="findings")
    from_activity = models.CharField(max_length=255)
    to_activity = models.CharField(max_length=255)
    avg_duration_seconds = models.DecimalField(max_digits=14, decimal_places=2)
    median_duration_seconds = models.DecimalField(max_digits=14, decimal_places=2)
    p95_duration_seconds = models.DecimalField(max_digits=14, decimal_places=2)
    case_count = models.PositiveBigIntegerField()
    severity = models.CharField(max_length=16, choices=BottleneckSeverity.choices)
    resource_bottleneck = models.CharField(max_length=255, blank=True)
    rank = models.PositiveIntegerField()

    class Meta:
        db_table = "process_mining_bottleneck_findings"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "analysis", "from_activity", "to_activity"], name="pm_find_transition_uniq"),
            models.UniqueConstraint(fields=["tenant_id", "analysis", "rank"], name="pm_find_rank_uniq"),
            *[
                models.CheckConstraint(condition=models.Q(**{f"{field}__gte": 0}), name=f"pm_find_{label}_nonneg")
                for field, label in (
                    ("avg_duration_seconds", "avg"),
                    ("median_duration_seconds", "median"),
                    ("p95_duration_seconds", "p95"),
                )
            ],
        ]
        indexes = [models.Index(fields=["tenant_id", "analysis", "severity", "rank"], name="pm_find_severity_rank")]

    def clean(self) -> None:
        _same_tenant(self, "analysis")


class ProcessVariant(AppendOnlyDomainModel):
    analysis = models.ForeignKey(BottleneckAnalysis, on_delete=models.PROTECT, related_name="variants")
    variant_key = models.CharField(max_length=64)
    activities = models.JSONField()
    case_count = models.PositiveBigIntegerField()
    percentage = models.DecimalField(max_digits=7, decimal_places=4)
    avg_duration_seconds = models.DecimalField(max_digits=14, decimal_places=2)
    is_happy_path = models.BooleanField(default=False)
    is_grouped_other = models.BooleanField(default=False)

    class Meta:
        db_table = "process_mining_variants"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "analysis", "variant_key"], name="pm_variant_key_uniq"),
            models.UniqueConstraint(
                fields=["tenant_id", "analysis"], condition=models.Q(is_happy_path=True), name="pm_variant_happy_uniq"
            ),
            models.CheckConstraint(
                condition=models.Q(percentage__gte=0) & models.Q(percentage__lte=100), name="pm_variant_pct_range"
            ),
            models.CheckConstraint(condition=models.Q(avg_duration_seconds__gte=0), name="pm_variant_duration_nonneg"),
        ]
        indexes = [models.Index(fields=["tenant_id", "analysis", "case_count"], name="pm_variant_case_count")]

    def clean(self) -> None:
        _same_tenant(self, "analysis")
        if not isinstance(self.activities, list) or not self.activities or not all(
            isinstance(value, str) and value.strip() for value in self.activities
        ):
            raise ValidationError({"activities": "Activities must be a nonempty ordered string list."})


__all__ = [
    "AnalysisStatus",
    "BottleneckAnalysis",
    "BottleneckFinding",
    "BottleneckSeverity",
    "ConformanceCaseMetric",
    "ConformanceCheck",
    "ConformanceDeviation",
    "DeviationType",
    "EventExportJob",
    "ExportFormat",
    "ExportStatus",
    "MiningAlgorithmName",
    "ModelSourceKind",
    "ProcessDiscoveryJob",
    "ProcessEvent",
    "ProcessModel",
    "ProcessModelVersion",
    "ProcessModelReferenceAssignment",
    "ProcessMiningConfiguration",
    "ProcessMiningConfigurationVersion",
    "ProcessMiningConfigurationAudit",
    "ProcessEventRetentionTombstone",
    "ExportArtifactDeletion",
    "ProcessVariant",
    "generate_uuid",
    "validate_graph",
]
