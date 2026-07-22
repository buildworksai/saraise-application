"""Strict read/write serializers for the governed MDM API v2."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal

from rest_framework import serializers

from src.core.async_jobs.models import AsyncJob

from .models import (
    DataQualityIssue,
    DataQualityRule,
    MasterDataEntity,
    MasterDataVersion,
    MasterEntityType,
    MatchCandidate,
    MatchingRule,
    MergeHistory,
    MergeParticipant,
)
from .services import MatchResult, MergePreview, QualityReport, ValidationFinding, ValidationReport


class StrictSerializerMixin:
    """Reject unknown request keys instead of silently ignoring them."""

    def to_internal_value(self, data: object) -> object:
        if isinstance(data, Mapping):
            unknown = set(data) - set(self.fields)  # type: ignore[attr-defined]
            if unknown:
                raise serializers.ValidationError({key: ["Unknown field."] for key in sorted(unknown)})
        return super().to_internal_value(data)  # type: ignore[misc]


class StrictSerializer(StrictSerializerMixin, serializers.Serializer):
    pass


class StrictModelSerializer(StrictSerializerMixin, serializers.ModelSerializer):
    pass


def _mask_path(data: dict[str, object], path: str) -> None:
    current: object = data
    parts = path.split(".")
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        current = current[part]
    if isinstance(current, dict) and parts[-1] in current:
        current[parts[-1]] = "••••••"


def _masked_data(entity: MasterDataEntity, context: Mapping[str, object]) -> dict[str, object]:
    result = deepcopy(entity.data)
    request = context.get("request")
    allowed = set(getattr(request, "allowed_sensitive_fields", ())) if request is not None else set()
    for path in entity.entity_type.sensitive_fields:
        if path not in allowed:
            _mask_path(result, path)
    return result


def _masked_snapshot(snapshot: Mapping[str, object], entity: MasterDataEntity, context: Mapping[str, object]) -> dict[str, object]:
    result = deepcopy(dict(snapshot))
    request = context.get("request")
    allowed = set(getattr(request, "allowed_sensitive_fields", ())) if request is not None else set()
    nested = result.get("data")
    target = nested if isinstance(nested, dict) else result
    for path in entity.entity_type.sensitive_fields:
        if path not in allowed:
            _mask_path(target, path)
    return result


TYPE_LIST_FIELDS = (
    "id",
    "tenant_id",
    "key",
    "display_name",
    "description",
    "schema_version",
    "owner_module",
    "is_system",
    "is_active",
    "is_deleted",
    "deleted_at",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
)
TYPE_DETAIL_FIELDS = TYPE_LIST_FIELDS + (
    "json_schema",
    "required_fields",
    "sensitive_fields",
    "searchable_fields",
    "metadata",
)


class MasterEntityTypeListSerializer(StrictModelSerializer):
    class Meta:
        model = MasterEntityType
        fields = TYPE_LIST_FIELDS
        read_only_fields = fields


class MasterEntityTypeDetailSerializer(StrictModelSerializer):
    class Meta:
        model = MasterEntityType
        fields = TYPE_DETAIL_FIELDS
        read_only_fields = fields


class MasterEntityTypeCreateSerializer(StrictSerializer):
    key = serializers.RegexField(r"^[a-z][a-z0-9_]{1,63}$", max_length=64)
    display_name = serializers.CharField(max_length=120)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    json_schema = serializers.JSONField()
    required_fields = serializers.ListField(child=serializers.CharField(max_length=255), required=False, default=list)
    sensitive_fields = serializers.ListField(child=serializers.CharField(max_length=255), required=False, default=list)
    searchable_fields = serializers.ListField(child=serializers.CharField(max_length=255), required=False, default=list)
    owner_module = serializers.CharField(max_length=100, required=False, default="master_data_management")
    metadata = serializers.JSONField(required=False, default=dict)
    idempotency_key = serializers.CharField(max_length=255)


class MasterEntityTypeChangesSerializer(StrictSerializer):
    display_name = serializers.CharField(max_length=120, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    json_schema = serializers.JSONField(required=False)
    required_fields = serializers.ListField(child=serializers.CharField(max_length=255), required=False)
    sensitive_fields = serializers.ListField(child=serializers.CharField(max_length=255), required=False)
    searchable_fields = serializers.ListField(child=serializers.CharField(max_length=255), required=False)
    metadata = serializers.JSONField(required=False)
    is_active = serializers.BooleanField(required=False)


class FlatOrNestedChangesMixin:
    """Accept one validated change set in either flat or nested wire form."""

    change_fields: frozenset[str] = frozenset()

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        values = dict(attrs)
        nested = dict(values.pop("changes", {}))
        flat = {field: values.pop(field) for field in self.change_fields if field in values}
        duplicates = set(flat).intersection(nested)
        if duplicates:
            raise serializers.ValidationError(
                {field: ["Field cannot be supplied both flat and under changes."] for field in sorted(duplicates)}
            )
        changes = {**nested, **flat}
        if not changes:
            raise serializers.ValidationError({"changes": ["At least one change is required."]})
        values["changes"] = changes
        return values


class MasterEntityTypeUpdateSerializer(FlatOrNestedChangesMixin, MasterEntityTypeChangesSerializer):
    change_fields = frozenset(
        {
            "display_name",
            "description",
            "json_schema",
            "required_fields",
            "sensitive_fields",
            "searchable_fields",
            "metadata",
            "is_active",
        }
    )
    expected_schema_version = serializers.IntegerField(min_value=1)
    changes = MasterEntityTypeChangesSerializer(required=False)
    idempotency_key = serializers.CharField(max_length=255)


class DeactivateSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=255)
    idempotency_key = serializers.CharField(max_length=255)


ENTITY_LIST_FIELDS = (
    "id",
    "tenant_id",
    "entity_type",
    "entity_code",
    "entity_name",
    "source_system",
    "source_record_id",
    "status",
    "quality_score",
    "quality_evaluated_at",
    "golden_record",
    "is_golden",
    "version",
    "is_deleted",
    "deleted_at",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
)


class MasterDataEntityListSerializer(StrictModelSerializer):
    entity_type_key = serializers.CharField(source="entity_type.key", read_only=True)
    entity_type_display_name = serializers.CharField(source="entity_type.display_name", read_only=True)

    class Meta:
        model = MasterDataEntity
        fields = ENTITY_LIST_FIELDS + ("entity_type_key", "entity_type_display_name")
        read_only_fields = fields


class MasterDataEntityDetailSerializer(StrictModelSerializer):
    entity_type_key = serializers.CharField(source="entity_type.key", read_only=True)
    entity_type_display_name = serializers.CharField(source="entity_type.display_name", read_only=True)
    data = serializers.SerializerMethodField()
    open_issue_count = serializers.SerializerMethodField()

    class Meta:
        model = MasterDataEntity
        fields = ENTITY_LIST_FIELDS + (
            "entity_type_key",
            "entity_type_display_name",
            "data",
            "transition_history",
            "open_issue_count",
        )
        read_only_fields = fields

    def get_data(self, obj: MasterDataEntity) -> dict[str, object]:
        return _masked_data(obj, self.context)

    def get_open_issue_count(self, obj: MasterDataEntity) -> int:
        annotated = getattr(obj, "open_issue_count", None)
        if annotated is not None:
            return int(annotated)
        return obj.quality_issues.filter(tenant_id=obj.tenant_id, status__in=("open", "in_review")).count()


class MasterDataEntityCreateSerializer(StrictSerializer):
    entity_type_id = serializers.UUIDField()
    entity_code = serializers.CharField(max_length=100)
    entity_name = serializers.CharField(max_length=255)
    data = serializers.JSONField()
    source_system = serializers.CharField(max_length=100, required=False, default="manual")
    source_record_id = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(max_length=255)


class MasterDataEntityChangesSerializer(StrictSerializer):
    entity_code = serializers.CharField(max_length=100, required=False)
    entity_name = serializers.CharField(max_length=255, required=False)
    data = serializers.JSONField(required=False)
    source_system = serializers.CharField(max_length=100, required=False)
    source_record_id = serializers.CharField(max_length=255, required=False, allow_blank=True)


class MasterDataEntityUpdateSerializer(FlatOrNestedChangesMixin, MasterDataEntityChangesSerializer):
    change_fields = frozenset(
        {"entity_code", "entity_name", "data", "source_system", "source_record_id"}
    )
    expected_version = serializers.IntegerField(min_value=1)
    changes = MasterDataEntityChangesSerializer(required=False)
    reason = serializers.CharField(max_length=255)
    idempotency_key = serializers.CharField(max_length=255)


class LifecycleSerializer(StrictSerializer):
    expected_version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=255)
    idempotency_key = serializers.CharField(max_length=255)


class RollbackSerializer(LifecycleSerializer):
    version_number = serializers.IntegerField(min_value=1)


class ValidateRequestSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=255, required=False)
    idempotency_key = serializers.CharField(max_length=255)


class MasterDataVersionSerializer(StrictModelSerializer):
    data_snapshot = serializers.SerializerMethodField()

    class Meta:
        model = MasterDataVersion
        fields = (
            "id",
            "tenant_id",
            "entity",
            "version_number",
            "entity_type_key",
            "entity_code",
            "entity_name",
            "data_snapshot",
            "status_snapshot",
            "quality_score_snapshot",
            "changed_fields",
            "change_reason",
            "changed_by",
            "correlation_id",
            "created_at",
        )
        read_only_fields = fields

    def get_data_snapshot(self, obj: MasterDataVersion) -> dict[str, object]:
        snapshot = deepcopy(obj.data_snapshot)
        request = self.context.get("request")
        allowed = set(getattr(request, "allowed_sensitive_fields", ())) if request is not None else set()
        for path in obj.entity.entity_type.sensitive_fields:
            if path not in allowed:
                _mask_path(snapshot, path)
        return snapshot


RULE_LIST_FIELDS = (
    "id",
    "tenant_id",
    "entity_type",
    "name",
    "field_path",
    "rule_type",
    "dimension",
    "severity",
    "weight",
    "is_active",
    "is_deleted",
    "deleted_at",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
)


class DataQualityRuleListSerializer(StrictModelSerializer):
    entity_type_key = serializers.CharField(source="entity_type.key", read_only=True)

    class Meta:
        model = DataQualityRule
        fields = RULE_LIST_FIELDS + ("entity_type_key",)
        read_only_fields = fields


class DataQualityRuleDetailSerializer(StrictModelSerializer):
    entity_type_key = serializers.CharField(source="entity_type.key", read_only=True)

    class Meta:
        model = DataQualityRule
        fields = RULE_LIST_FIELDS + ("entity_type_key", "configuration")
        read_only_fields = fields


class DataQualityRuleWriteSerializer(StrictSerializer):
    entity_type_id = serializers.UUIDField(required=False)
    name = serializers.CharField(max_length=120, required=False)
    field_path = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    rule_type = serializers.ChoiceField(choices=("required", "format", "range", "uniqueness", "referential", "timeliness"), required=False)
    configuration = serializers.JSONField(required=False)
    dimension = serializers.ChoiceField(choices=("completeness", "accuracy", "consistency", "timeliness", "uniqueness", "conformity"), required=False)
    severity = serializers.ChoiceField(choices=("info", "warning", "error", "critical"), required=False)
    weight = serializers.DecimalField(max_digits=7, decimal_places=4, min_value=Decimal("0.0001"), required=False)
    is_active = serializers.BooleanField(required=False)
    idempotency_key = serializers.CharField(max_length=255)


class DataQualityRuleChangesSerializer(StrictSerializer):
    name = serializers.CharField(max_length=120, required=False)
    field_path = serializers.CharField(max_length=255, required=False, allow_blank=True)
    rule_type = serializers.ChoiceField(choices=("required", "format", "range", "uniqueness", "referential", "timeliness"), required=False)
    configuration = serializers.JSONField(required=False)
    dimension = serializers.ChoiceField(choices=("completeness", "accuracy", "consistency", "timeliness", "uniqueness", "conformity"), required=False)
    severity = serializers.ChoiceField(choices=("info", "warning", "error", "critical"), required=False)
    weight = serializers.DecimalField(max_digits=7, decimal_places=4, min_value=Decimal("0.0001"), required=False)
    is_active = serializers.BooleanField(required=False)


class DataQualityRuleUpdateSerializer(FlatOrNestedChangesMixin, DataQualityRuleChangesSerializer):
    change_fields = frozenset(
        {
            "name",
            "field_path",
            "rule_type",
            "configuration",
            "dimension",
            "severity",
            "weight",
            "is_active",
        }
    )
    changes = DataQualityRuleChangesSerializer(required=False)
    idempotency_key = serializers.CharField(max_length=255)


class DataQualityIssueListSerializer(StrictModelSerializer):
    entity_name = serializers.CharField(source="entity.entity_name", read_only=True)
    entity_type_key = serializers.CharField(source="entity.entity_type.key", read_only=True)
    rule_name = serializers.CharField(source="rule.name", allow_null=True, read_only=True)

    class Meta:
        model = DataQualityIssue
        fields = (
            "id", "tenant_id", "entity", "entity_name", "entity_type_key", "rule", "rule_name", "field_path",
            "dimension", "severity", "message", "status", "assigned_to", "created_by", "updated_by",
            "created_at", "updated_at",
        )
        read_only_fields = fields


class DataQualityIssueDetailSerializer(DataQualityIssueListSerializer):
    class Meta(DataQualityIssueListSerializer.Meta):
        fields = DataQualityIssueListSerializer.Meta.fields + (
            "evidence", "resolution", "resolved_by", "resolved_at", "transition_history",
        )
        read_only_fields = fields


class QualityIssueResolutionSerializer(StrictSerializer):
    resolution = serializers.CharField(required=False, allow_blank=False)
    assignee_id = serializers.UUIDField(required=False)
    transition_key = serializers.CharField(max_length=255)


class MatchingRuleListSerializer(StrictModelSerializer):
    entity_type_key = serializers.CharField(source="entity_type.key", read_only=True)

    class Meta:
        model = MatchingRule
        fields = (
            "id", "tenant_id", "entity_type", "entity_type_key", "name", "algorithm", "review_threshold",
            "auto_confirm_threshold", "is_active", "is_deleted", "deleted_at", "created_by", "updated_by",
            "created_at", "updated_at",
        )
        read_only_fields = fields


class MatchingRuleDetailSerializer(MatchingRuleListSerializer):
    class Meta(MatchingRuleListSerializer.Meta):
        fields = MatchingRuleListSerializer.Meta.fields + (
            "field_weights", "blocking_fields",
        )
        read_only_fields = fields


class MatchingRuleWriteSerializer(StrictSerializer):
    entity_type_id = serializers.UUIDField(required=False)
    name = serializers.CharField(max_length=120, required=False)
    algorithm = serializers.ChoiceField(choices=("exact", "normalized", "fuzzy", "phonetic"), required=False)
    field_weights = serializers.DictField(child=serializers.DecimalField(max_digits=5, decimal_places=4), required=False)
    blocking_fields = serializers.ListField(child=serializers.CharField(max_length=255), required=False)
    review_threshold = serializers.DecimalField(max_digits=5, decimal_places=4, min_value=0, max_value=1, required=False)
    auto_confirm_threshold = serializers.DecimalField(max_digits=5, decimal_places=4, min_value=0, max_value=1, required=False)
    is_active = serializers.BooleanField(required=False)
    idempotency_key = serializers.CharField(max_length=255)


class MatchingRuleChangesSerializer(StrictSerializer):
    name = serializers.CharField(max_length=120, required=False)
    algorithm = serializers.ChoiceField(choices=("exact", "normalized", "fuzzy", "phonetic"), required=False)
    field_weights = serializers.DictField(child=serializers.DecimalField(max_digits=5, decimal_places=4), required=False)
    blocking_fields = serializers.ListField(child=serializers.CharField(max_length=255), required=False)
    review_threshold = serializers.DecimalField(max_digits=5, decimal_places=4, min_value=0, max_value=1, required=False)
    auto_confirm_threshold = serializers.DecimalField(max_digits=5, decimal_places=4, min_value=0, max_value=1, required=False)
    is_active = serializers.BooleanField(required=False)


class MatchingRuleUpdateSerializer(FlatOrNestedChangesMixin, MatchingRuleChangesSerializer):
    change_fields = frozenset(
        {
            "name",
            "algorithm",
            "field_weights",
            "blocking_fields",
            "review_threshold",
            "auto_confirm_threshold",
            "is_active",
        }
    )
    changes = MatchingRuleChangesSerializer(required=False)
    idempotency_key = serializers.CharField(max_length=255)


class DeactivateRuleSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=255, required=False)
    idempotency_key = serializers.CharField(max_length=255)


class MatchCandidateListSerializer(StrictModelSerializer):
    left_entity = MasterDataEntityDetailSerializer(read_only=True)
    right_entity = MasterDataEntityDetailSerializer(read_only=True)
    matching_rule_name = serializers.CharField(source="matching_rule.name", read_only=True)

    class Meta:
        model = MatchCandidate
        fields = (
            "id", "tenant_id", "matching_rule", "matching_rule_name", "left_entity", "right_entity",
            "confidence", "status", "reviewed_by", "reviewed_at", "created_by", "updated_by",
            "created_at", "updated_at",
        )
        read_only_fields = fields


class MatchCandidateDetailSerializer(MatchCandidateListSerializer):
    class Meta(MatchCandidateListSerializer.Meta):
        fields = MatchCandidateListSerializer.Meta.fields + (
            "field_scores", "evidence", "review_note", "merge_history", "transition_history",
        )
        read_only_fields = fields


class MatchReviewSerializer(StrictSerializer):
    decision = serializers.ChoiceField(choices=("confirm", "reject"))
    note = serializers.CharField(required=False, allow_blank=True, default="")
    transition_key = serializers.CharField(max_length=255)


class MatchPreviewRequestSerializer(StrictSerializer):
    left_entity_id = serializers.UUIDField()
    right_entity_id = serializers.UUIDField()
    rule_id = serializers.UUIDField()


class MatchResultSerializer(StrictSerializer):
    rule_id = serializers.UUIDField(read_only=True)
    left_entity_id = serializers.UUIDField(read_only=True)
    right_entity_id = serializers.UUIDField(read_only=True)
    confidence = serializers.DecimalField(max_digits=5, decimal_places=4, read_only=True)
    field_scores = serializers.DictField(read_only=True)
    evidence = serializers.DictField(read_only=True)
    outcome = serializers.CharField(read_only=True)


class ScanRequestSerializer(StrictSerializer):
    entity_type_id = serializers.UUIDField()
    rule_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    idempotency_key = serializers.CharField(max_length=255)


class MergePreviewSerializer(StrictSerializer):
    entity_ids = serializers.ListField(child=serializers.UUIDField())
    survivor_id = serializers.UUIDField(read_only=True)
    golden_values = serializers.DictField(read_only=True)
    golden_record = serializers.DictField(source="golden_values", read_only=True)
    provenance = serializers.DictField(read_only=True)
    source_versions = serializers.DictField(read_only=True)
    fields = serializers.SerializerMethodField(method_name="get_survivorship_fields")
    conflicts = serializers.SerializerMethodField()
    survivorship_overrides = serializers.DictField(child=serializers.UUIDField(), write_only=True, required=False, default=dict)

    def get_survivorship_fields(self, obj: MergePreview) -> list[dict[str, object]]:
        values = dict(obj.golden_values)
        flattened: list[tuple[str, object]] = []

        def visit(current: Mapping[str, object], prefix: str = "") -> None:
            for key, value in sorted(current.items()):
                path = f"{prefix}.{key}" if prefix else key
                if isinstance(value, Mapping):
                    visit(value, path)
                else:
                    flattened.append((path, value))

        visit(values)
        return [
            {
                "field_path": path,
                "value": value,
                "source_entity_id": obj.provenance.get(path),
                "rationale": "Deterministic survivorship policy",
                "alternatives": [],
            }
            for path, value in flattened
        ]

    def get_conflicts(self, obj: MergePreview) -> list[dict[str, str]]:
        return [
            {"code": "MERGE_PREVIEW_CONFLICT", "message": conflict}
            for conflict in obj.conflicts
        ]


class MergeRequestSerializer(StrictSerializer):
    entity_ids = serializers.ListField(child=serializers.UUIDField(), min_length=2)
    survivorship_overrides = serializers.DictField(child=serializers.UUIDField(), required=False, default=dict)
    reason = serializers.CharField()
    idempotency_key = serializers.CharField(max_length=255)


class MergeParticipantSerializer(StrictModelSerializer):
    source_snapshot = serializers.SerializerMethodField()

    class Meta:
        model = MergeParticipant
        fields = ("id", "tenant_id", "source_entity", "source_version", "source_snapshot", "role", "created_at")
        read_only_fields = fields

    def get_source_snapshot(self, obj: MergeParticipant) -> dict[str, object]:
        return _masked_snapshot(obj.source_snapshot, obj.source_entity, self.context)


class MergeHistoryListSerializer(StrictModelSerializer):
    golden_record_name = serializers.CharField(source="golden_record.entity_name", read_only=True)
    participant_count = serializers.IntegerField(source="participants.count", read_only=True)

    class Meta:
        model = MergeHistory
        fields = (
            "id", "tenant_id", "golden_record", "golden_record_name", "status", "reason", "merged_by",
            "reversed_by", "reversed_at", "participant_count", "correlation_id", "created_at",
        )
        read_only_fields = fields


class MergeHistoryDetailSerializer(MergeHistoryListSerializer):
    participants = MergeParticipantSerializer(many=True, read_only=True)
    golden_snapshot_before = serializers.SerializerMethodField()
    golden_snapshot_after = serializers.SerializerMethodField()

    class Meta(MergeHistoryListSerializer.Meta):
        fields = MergeHistoryListSerializer.Meta.fields + (
            "survivorship_policy", "golden_snapshot_before", "golden_snapshot_after", "reversal_reason",
            "transition_history", "participants",
        )
        read_only_fields = fields

    def get_golden_snapshot_before(self, obj: MergeHistory) -> dict[str, object]:
        return _masked_snapshot(obj.golden_snapshot_before, obj.golden_record, self.context)

    def get_golden_snapshot_after(self, obj: MergeHistory) -> dict[str, object]:
        return _masked_snapshot(obj.golden_snapshot_after, obj.golden_record, self.context)


class MergeReverseSerializer(StrictSerializer):
    reason = serializers.CharField()
    transition_key = serializers.CharField(max_length=255)


class AsyncJobSerializer(StrictModelSerializer):
    class Meta:
        model = AsyncJob
        fields = (
            "id", "command", "status", "result", "error_message", "attempts", "correlation_id",
            "started_at", "completed_at", "created_at", "updated_at",
        )
        read_only_fields = fields


class ValidationFindingSerializer(StrictSerializer):
    field_path = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)
    dimension = serializers.CharField(read_only=True)
    severity = serializers.CharField(read_only=True)
    rule_id = serializers.UUIDField(read_only=True, allow_null=True)


class ValidationReportSerializer(StrictSerializer):
    valid = serializers.BooleanField(read_only=True)
    evaluated = serializers.BooleanField(read_only=True)
    findings = ValidationFindingSerializer(many=True, read_only=True)


class QualityReportSerializer(StrictSerializer):
    entity_id = serializers.UUIDField(read_only=True)
    evaluated = serializers.BooleanField(read_only=True)
    score = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True, allow_null=True)
    dimension_scores = serializers.DictField(read_only=True)
    issue_count = serializers.IntegerField(read_only=True)
    findings = ValidationFindingSerializer(many=True, read_only=True)


class MDMSummarySerializer(StrictSerializer):
    entity_count = serializers.IntegerField(read_only=True)
    entity_status_counts = serializers.DictField(read_only=True)
    quality_distribution = serializers.DictField(read_only=True)
    total_entities = serializers.IntegerField(read_only=True)
    active_entities = serializers.IntegerField(read_only=True)
    pending_review_entities = serializers.IntegerField(read_only=True)
    merged_entities = serializers.IntegerField(read_only=True)
    archived_entities = serializers.IntegerField(read_only=True)
    quality_evaluated_entities = serializers.IntegerField(read_only=True)
    average_quality_score = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True, allow_null=True)
    score_distribution = serializers.ListField(read_only=True)
    quality_trend = serializers.ListField(read_only=True)
    open_issues = serializers.IntegerField(read_only=True)
    critical_issues = serializers.IntegerField(read_only=True)
    pending_matches = serializers.IntegerField(read_only=True)
    recent_activity = serializers.ListField(read_only=True)


# Legacy symbol is a read serializer only; v1 routing has been removed.
MasterDataEntitySerializer = MasterDataEntityDetailSerializer

__all__ = [name for name in globals() if name.endswith("Serializer")]
