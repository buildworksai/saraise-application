"""Tenant-safe persistence contracts for Master Data Management.

The models enforce structural invariants and ownership boundaries.  Commands,
validation policy, scoring, matching, and survivorship remain service-layer
concerns; direct lifecycle mutation and physical deletion are intentionally
blocked here as a second line of defence.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q

from src.core.tenancy import TenantQuerySet, TenantScopedModel, TimestampedModel


ENTITY_TYPE_KEY_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"
FIELD_PATH_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


class EntityStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PENDING_REVIEW = "pending_review", "Pending review"
    MERGED = "merged", "Merged"
    ARCHIVED = "archived", "Archived"


class QualityRuleType(models.TextChoices):
    REQUIRED = "required", "Required"
    FORMAT = "format", "Format"
    RANGE = "range", "Range"
    UNIQUENESS = "uniqueness", "Uniqueness"
    REFERENTIAL = "referential", "Referential"
    TIMELINESS = "timeliness", "Timeliness"


class QualityDimension(models.TextChoices):
    COMPLETENESS = "completeness", "Completeness"
    ACCURACY = "accuracy", "Accuracy"
    CONSISTENCY = "consistency", "Consistency"
    TIMELINESS = "timeliness", "Timeliness"
    UNIQUENESS = "uniqueness", "Uniqueness"
    CONFORMITY = "conformity", "Conformity"


class IssueSeverity(models.TextChoices):
    INFO = "info", "Info"
    WARNING = "warning", "Warning"
    ERROR = "error", "Error"
    CRITICAL = "critical", "Critical"


class IssueStatus(models.TextChoices):
    OPEN = "open", "Open"
    IN_REVIEW = "in_review", "In review"
    RESOLVED = "resolved", "Resolved"
    WAIVED = "waived", "Waived"


class MatchingAlgorithm(models.TextChoices):
    EXACT = "exact", "Exact"
    NORMALIZED = "normalized", "Normalized"
    FUZZY = "fuzzy", "Fuzzy"
    PHONETIC = "phonetic", "Phonetic"


class MatchStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    REJECTED = "rejected", "Rejected"
    MERGED = "merged", "Merged"


class MergeStatus(models.TextChoices):
    APPLIED = "applied", "Applied"
    REVERSED = "reversed", "Reversed"


class ParticipantRole(models.TextChoices):
    SURVIVOR = "survivor", "Survivor"
    MERGED_SOURCE = "merged_source", "Merged source"


class HardDeleteForbiddenMixin:
    """Make archive/deactivation the only supported removal semantics."""

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError(
            "Physical deletion is forbidden; use the tenant-scoped lifecycle service.",
            code="hard_delete_forbidden",
        )


class MutableMDMModel(HardDeleteForbiddenMixin, TenantScopedModel, TimestampedModel):
    """Shared identity and actor audit columns for mutable aggregates."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.UUIDField(editable=False)
    updated_by = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)


class SoftDeleteMixin(models.Model):
    is_deleted = models.BooleanField(default=False, editable=False)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        abstract = True

    def clean(self) -> None:
        super().clean()
        if self.is_deleted != (self.deleted_at is not None):
            raise ValidationError(
                {"deleted_at": "is_deleted and deleted_at must be set or cleared together."},
                code="invalid_soft_delete_state",
            )


class StatefulMixin(models.Model):
    """Reject direct state assignment without a matching transition record."""

    ALLOWED_TRANSITIONS: dict[tuple[str, str], frozenset[str]] = {}

    class Meta:
        abstract = True

    def clean(self) -> None:
        super().clean()
        if self._state.adding or not self.pk:
            return
        prior = type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).values(
            "status", "transition_history"
        ).first()
        if prior is None:
            return
        old_history = prior["transition_history"]
        new_history = self.transition_history
        if prior["status"] == self.status:
            if old_history != new_history:
                raise ValidationError(
                    {"transition_history": "Transition history may change only with status."},
                    code="state_machine_required",
                )
            return
        valid_record = (
            isinstance(old_history, list)
            and isinstance(new_history, list)
            and len(new_history) == len(old_history) + 1
            and new_history[:-1] == old_history
            and isinstance(new_history[-1], dict)
            and new_history[-1].get("from_state") == prior["status"]
            and new_history[-1].get("to_state") == self.status
            and new_history[-1].get("command")
            in self.ALLOWED_TRANSITIONS.get((str(prior["status"]), str(self.status)), frozenset())
        )
        if not valid_record:
            raise ValidationError(
                {"status": "Status changes must use the registered state machine."},
                code="state_machine_required",
            )


class AppendOnlyQuerySet(TenantQuerySet):
    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ValidationError("Append-only records cannot be updated.", code="append_only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Append-only records cannot be deleted.", code="append_only")


class AppendOnlyMDMModel(TenantScopedModel):
    """Shared immutable identity for version and participant evidence."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Append-only records cannot be updated.", code="append_only")
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Append-only records cannot be deleted.", code="append_only")


def _require_json_object(instance: models.Model, field_name: str) -> None:
    if not isinstance(getattr(instance, field_name), dict):
        raise ValidationError({field_name: "Must be a JSON object."}, code="invalid_json_object")


def _require_json_array(instance: models.Model, field_name: str) -> None:
    if not isinstance(getattr(instance, field_name), list):
        raise ValidationError({field_name: "Must be a JSON array."}, code="invalid_json_array")


def _require_field_paths(instance: models.Model, field_name: str) -> None:
    value = getattr(instance, field_name)
    if not isinstance(value, list) or any(
        not isinstance(path, str) or not FIELD_PATH_PATTERN.fullmatch(path) for path in value
    ):
        raise ValidationError(
            {field_name: "Must contain only dotted field paths."},
            code="invalid_field_paths",
        )
    if len(value) != len(set(value)):
        raise ValidationError({field_name: "Field paths must be unique."}, code="duplicate_field_path")


def _require_same_tenant(instance: TenantScopedModel, relation_name: str) -> None:
    relation_id = getattr(instance, f"{relation_name}_id", None)
    if relation_id is None or not getattr(instance, "tenant_id", None):
        return
    field = instance._meta.get_field(relation_name)
    related_model = field.remote_field.model
    if not related_model.objects.for_tenant(instance.tenant_id).filter(pk=relation_id).exists():
        raise ValidationError(
            {relation_name: "The referenced record must belong to the same tenant."},
            code="cross_tenant_reference",
        )


class MasterEntityType(SoftDeleteMixin, MutableMDMModel):
    """Tenant-owned declarative entity schema and paid-module extension key."""

    key = models.CharField(
        max_length=64,
        validators=[RegexValidator(ENTITY_TYPE_KEY_PATTERN, "Use a lowercase snake-case key.")],
    )
    display_name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    json_schema = models.JSONField(default=dict)
    schema_version = models.PositiveIntegerField(default=1, editable=False)
    required_fields = models.JSONField(default=list, blank=True)
    sensitive_fields = models.JSONField(default=list, blank=True)
    searchable_fields = models.JSONField(default=list, blank=True)
    owner_module = models.CharField(max_length=100, default="master_data_management")
    is_system = models.BooleanField(default=False, editable=False)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "mdm_entity_types"
        ordering = ("key",)
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "key"), name="mdm_type_tenant_key_uniq"),
            models.CheckConstraint(condition=Q(key__regex=ENTITY_TYPE_KEY_PATTERN), name="mdm_type_key_format_ck"),
            models.CheckConstraint(condition=Q(schema_version__gte=1), name="mdm_type_schema_ver_gte_1_ck"),
            models.CheckConstraint(
                condition=Q(is_system=False) | Q(is_deleted=False),
                name="mdm_type_system_not_deleted_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "is_active", "key"), name="mdm_type_active_key_idx"),
            models.Index(fields=("tenant_id", "owner_module"), name="mdm_type_owner_idx"),
            models.Index(fields=("tenant_id", "updated_at"), name="mdm_type_updated_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_json_object(self, "json_schema")
        _require_json_object(self, "metadata")
        for field_name in ("required_fields", "sensitive_fields", "searchable_fields"):
            _require_field_paths(self, field_name)
        if self.is_system and self.is_deleted:
            raise ValidationError(
                {"is_system": "System entity types cannot be deleted; deactivate them instead."},
                code="system_type_lifecycle",
            )
        if not self._state.adding and self.is_deleted:
            is_referenced = (
                self.entities.exists()
                or self.quality_rules.filter(is_deleted=False).exists()
                or self.matching_rules.filter(is_deleted=False).exists()
            )
            if is_referenced:
                raise ValidationError(
                    {"is_deleted": "Referenced entity types cannot be deleted; deactivate them instead."},
                    code="entity_type_referenced",
                )

    def __str__(self) -> str:
        return f"{self.key} ({self.display_name})"


class MasterDataEntity(SoftDeleteMixin, StatefulMixin, MutableMDMModel):
    """One governed master record described by a tenant entity type."""

    entity_type = models.ForeignKey(MasterEntityType, models.PROTECT, related_name="entities")
    entity_code = models.CharField(max_length=100)
    entity_name = models.CharField(max_length=255)
    data = models.JSONField(default=dict)
    source_system = models.CharField(max_length=100, default="manual")
    source_record_id = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=24, choices=EntityStatus.choices, default=EntityStatus.ACTIVE, editable=False)
    quality_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), editable=False)
    quality_evaluated_at = models.DateTimeField(null=True, blank=True, editable=False)
    golden_record = models.ForeignKey(
        "self",
        models.PROTECT,
        null=True,
        blank=True,
        related_name="golden_members",
        editable=False,
    )
    is_golden = models.BooleanField(default=False, editable=False)
    version = models.PositiveIntegerField(default=1, editable=False)
    transition_history = models.JSONField(default=list, blank=True, editable=False)

    ALLOWED_TRANSITIONS = {
        (EntityStatus.ACTIVE, EntityStatus.PENDING_REVIEW): frozenset({"request_review"}),
        (EntityStatus.PENDING_REVIEW, EntityStatus.ACTIVE): frozenset({"approve"}),
        (EntityStatus.ACTIVE, EntityStatus.MERGED): frozenset({"merge"}),
        (EntityStatus.PENDING_REVIEW, EntityStatus.MERGED): frozenset({"merge"}),
        (EntityStatus.ACTIVE, EntityStatus.ARCHIVED): frozenset({"archive"}),
        (EntityStatus.PENDING_REVIEW, EntityStatus.ARCHIVED): frozenset({"archive"}),
        (EntityStatus.ARCHIVED, EntityStatus.ACTIVE): frozenset({"restore"}),
        (EntityStatus.MERGED, EntityStatus.ACTIVE): frozenset({"reverse_merge"}),
    }

    class Meta:
        db_table = "mdm_entities"
        ordering = ("entity_code",)
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "entity_type", "entity_code"),
                condition=Q(is_deleted=False),
                name="mdm_entity_live_business_key_uniq",
            ),
            models.CheckConstraint(
                condition=Q(quality_score__gte=Decimal("0.00"), quality_score__lte=Decimal("100.00")),
                name="mdm_entity_quality_0_100_ck",
            ),
            models.CheckConstraint(condition=Q(version__gte=1), name="mdm_entity_version_gte_1_ck"),
            models.CheckConstraint(
                condition=~Q(id=F("golden_record_id")),
                name="mdm_entity_golden_not_self_ck",
            ),
            models.CheckConstraint(
                condition=Q(is_golden=False) | Q(golden_record__isnull=True),
                name="mdm_entity_golden_has_no_parent_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=EntityStatus.MERGED, golden_record__isnull=False)
                    | ~Q(status=EntityStatus.MERGED, golden_record__isnull=True)
                ),
                name="mdm_entity_merged_has_golden_ck",
            ),
            models.CheckConstraint(
                condition=Q(status=EntityStatus.MERGED) | Q(golden_record__isnull=True),
                name="mdm_entity_nonmerged_no_golden_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "entity_type", "status", "entity_code"),
                name="mdm_entity_type_stat_code_idx",
            ),
            models.Index(fields=("tenant_id", "entity_type", "quality_score"), name="mdm_entity_type_quality_idx"),
            models.Index(fields=("tenant_id", "golden_record"), name="mdm_entity_golden_idx"),
            models.Index(
                fields=("tenant_id", "source_system", "source_record_id"),
                name="mdm_entity_source_idx",
            ),
            models.Index(fields=("tenant_id", "is_deleted", "updated_at"), name="mdm_entity_deleted_upd_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_json_object(self, "data")
        _require_json_array(self, "transition_history")
        _require_same_tenant(self, "entity_type")
        _require_same_tenant(self, "golden_record")
        if self.is_deleted != (self.status == EntityStatus.ARCHIVED):
            raise ValidationError(
                {"is_deleted": "Only archived entities are soft-deleted."},
                code="entity_archive_state",
            )
        if self.golden_record_id:
            golden = MasterDataEntity.objects.for_tenant(self.tenant_id).filter(pk=self.golden_record_id).first()
            if golden is not None and golden.entity_type_id != self.entity_type_id:
                raise ValidationError(
                    {"golden_record": "Golden record and source must use the same entity type."},
                    code="golden_type_mismatch",
                )

    def __str__(self) -> str:
        return f"{self.entity_type.key if self.entity_type_id else 'untyped'} - {self.entity_code}"


class MasterDataVersion(AppendOnlyMDMModel):
    """Immutable entity snapshot written for each optimistic version."""

    entity = models.ForeignKey(MasterDataEntity, models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField()
    entity_type_key = models.CharField(max_length=64)
    entity_code = models.CharField(max_length=100)
    entity_name = models.CharField(max_length=255)
    data_snapshot = models.JSONField()
    status_snapshot = models.CharField(max_length=24, choices=EntityStatus.choices)
    quality_score_snapshot = models.DecimalField(max_digits=5, decimal_places=2)
    changed_fields = models.JSONField(default=list, blank=True)
    change_reason = models.CharField(max_length=255)
    changed_by = models.UUIDField()
    correlation_id = models.CharField(max_length=64)

    class Meta:
        db_table = "mdm_entity_versions"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "entity", "version_number"),
                name="mdm_version_entity_number_uniq",
            ),
            models.CheckConstraint(condition=Q(version_number__gte=1), name="mdm_version_number_gte_1_ck"),
            models.CheckConstraint(
                condition=Q(quality_score_snapshot__gte=Decimal("0.00"), quality_score_snapshot__lte=Decimal("100.00")),
                name="mdm_version_quality_0_100_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "entity", "-version_number"), name="mdm_version_entity_desc_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "entity")
        _require_json_object(self, "data_snapshot")
        _require_field_paths(self, "changed_fields")


class DataQualityRule(SoftDeleteMixin, MutableMDMModel):
    entity_type = models.ForeignKey(MasterEntityType, models.CASCADE, related_name="quality_rules")
    name = models.CharField(max_length=120)
    field_path = models.CharField(max_length=255, blank=True, default="")
    rule_type = models.CharField(max_length=20, choices=QualityRuleType.choices)
    configuration = models.JSONField(default=dict, blank=True)
    dimension = models.CharField(max_length=20, choices=QualityDimension.choices)
    severity = models.CharField(max_length=12, choices=IssueSeverity.choices)
    weight = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("1.0000"))
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "mdm_quality_rules"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "entity_type", "name"),
                condition=Q(is_deleted=False),
                name="mdm_quality_rule_live_name_uniq",
            ),
            models.CheckConstraint(condition=Q(weight__gt=0), name="mdm_quality_rule_weight_gt_0_ck"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "entity_type", "is_active"), name="mdm_quality_rule_active_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "entity_type")
        _require_json_object(self, "configuration")
        if self.field_path and not FIELD_PATH_PATTERN.fullmatch(self.field_path):
            raise ValidationError({"field_path": "Must be a dotted field path."}, code="invalid_field_path")


class DataQualityIssue(StatefulMixin, MutableMDMModel):
    entity = models.ForeignKey(MasterDataEntity, models.CASCADE, related_name="quality_issues")
    rule = models.ForeignKey(DataQualityRule, models.PROTECT, null=True, blank=True, related_name="issues")
    field_path = models.CharField(max_length=255, blank=True, default="")
    dimension = models.CharField(max_length=20, choices=QualityDimension.choices)
    severity = models.CharField(max_length=12, choices=IssueSeverity.choices)
    message = models.CharField(max_length=500)
    evidence = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=IssueStatus.choices, default=IssueStatus.OPEN, editable=False)
    assigned_to = models.UUIDField(null=True, blank=True)
    resolution = models.TextField(blank=True, default="", editable=False)
    resolved_by = models.UUIDField(null=True, blank=True, editable=False)
    resolved_at = models.DateTimeField(null=True, blank=True, editable=False)
    transition_history = models.JSONField(default=list, blank=True, editable=False)

    ALLOWED_TRANSITIONS = {
        (IssueStatus.OPEN, IssueStatus.IN_REVIEW): frozenset({"assign"}),
        (IssueStatus.OPEN, IssueStatus.RESOLVED): frozenset({"resolve"}),
        (IssueStatus.IN_REVIEW, IssueStatus.RESOLVED): frozenset({"resolve"}),
        (IssueStatus.OPEN, IssueStatus.WAIVED): frozenset({"waive"}),
        (IssueStatus.IN_REVIEW, IssueStatus.WAIVED): frozenset({"waive"}),
    }

    class Meta:
        db_table = "mdm_quality_issues"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "entity", "rule", "field_path"),
                condition=Q(status=IssueStatus.OPEN, rule__isnull=False),
                name="mdm_issue_open_rule_field_uniq",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "entity", "field_path"),
                condition=Q(status=IssueStatus.OPEN, rule__isnull=True),
                name="mdm_issue_open_null_rule_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status__in=(IssueStatus.OPEN, IssueStatus.IN_REVIEW),
                        resolved_by__isnull=True,
                        resolved_at__isnull=True,
                        resolution="",
                    )
                    | (
                        Q(
                            status__in=(IssueStatus.RESOLVED, IssueStatus.WAIVED),
                            resolved_by__isnull=False,
                            resolved_at__isnull=False,
                        )
                        & ~Q(resolution="")
                    )
                ),
                name="mdm_issue_resolution_state_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "status", "severity", "created_at"),
                name="mdm_issue_status_severity_idx",
            ),
            models.Index(fields=("tenant_id", "entity", "status"), name="mdm_issue_entity_status_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "entity")
        _require_same_tenant(self, "rule")
        _require_json_object(self, "evidence")
        _require_json_array(self, "transition_history")
        if self.rule_id and self.entity_id:
            entity = MasterDataEntity.objects.for_tenant(self.tenant_id).filter(pk=self.entity_id).first()
            rule = DataQualityRule.objects.for_tenant(self.tenant_id).filter(pk=self.rule_id).first()
            if entity is not None and rule is not None and entity.entity_type_id != rule.entity_type_id:
                raise ValidationError(
                    {"rule": "Rule and entity must use the same entity type."},
                    code="rule_type_mismatch",
                )


class MatchingRule(SoftDeleteMixin, MutableMDMModel):
    entity_type = models.ForeignKey(MasterEntityType, models.CASCADE, related_name="matching_rules")
    name = models.CharField(max_length=120)
    algorithm = models.CharField(max_length=16, choices=MatchingAlgorithm.choices)
    field_weights = models.JSONField(default=dict)
    blocking_fields = models.JSONField(default=list, blank=True)
    review_threshold = models.DecimalField(max_digits=5, decimal_places=4)
    auto_confirm_threshold = models.DecimalField(max_digits=5, decimal_places=4)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "mdm_matching_rules"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "entity_type", "name"),
                condition=Q(is_deleted=False),
                name="mdm_matching_rule_live_name_uniq",
            ),
            models.CheckConstraint(
                condition=Q(review_threshold__gte=0, review_threshold__lte=1),
                name="mdm_match_review_threshold_ck",
            ),
            models.CheckConstraint(
                condition=Q(auto_confirm_threshold__gte=0, auto_confirm_threshold__lte=1),
                name="mdm_match_confirm_threshold_ck",
            ),
            models.CheckConstraint(
                condition=Q(review_threshold__lte=F("auto_confirm_threshold")),
                name="mdm_match_threshold_order_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "entity_type", "is_active"), name="mdm_matching_rule_active_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "entity_type")
        _require_field_paths(self, "blocking_fields")
        _require_json_object(self, "field_weights")
        weights: list[Decimal] = []
        for path, value in self.field_weights.items():
            if not isinstance(path, str) or not FIELD_PATH_PATTERN.fullmatch(path):
                raise ValidationError({"field_weights": "Every key must be a dotted field path."})
            try:
                weight = Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValidationError({"field_weights": "Every field weight must be decimal."}) from exc
            if weight <= 0:
                raise ValidationError({"field_weights": "Every field weight must be positive."})
            weights.append(weight)
        if not weights or abs(sum(weights) - Decimal("1.0000")) > Decimal("0.0001"):
            raise ValidationError({"field_weights": "Positive field weights must sum to 1.0000."})


class MatchCandidate(StatefulMixin, MutableMDMModel):
    matching_rule = models.ForeignKey(MatchingRule, models.PROTECT, related_name="candidates")
    left_entity = models.ForeignKey(MasterDataEntity, models.CASCADE, related_name="matches_as_left")
    right_entity = models.ForeignKey(MasterDataEntity, models.CASCADE, related_name="matches_as_right")
    confidence = models.DecimalField(max_digits=5, decimal_places=4)
    field_scores = models.JSONField(default=dict)
    evidence = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=MatchStatus.choices, default=MatchStatus.PENDING, editable=False)
    reviewed_by = models.UUIDField(null=True, blank=True, editable=False)
    reviewed_at = models.DateTimeField(null=True, blank=True, editable=False)
    review_note = models.TextField(blank=True, default="", editable=False)
    merge_history = models.ForeignKey(
        "MergeHistory",
        models.SET_NULL,
        null=True,
        blank=True,
        related_name="candidates",
        editable=False,
    )
    transition_history = models.JSONField(default=list, blank=True, editable=False)

    ALLOWED_TRANSITIONS = {
        (MatchStatus.PENDING, MatchStatus.CONFIRMED): frozenset({"confirm"}),
        (MatchStatus.PENDING, MatchStatus.REJECTED): frozenset({"reject"}),
        (MatchStatus.CONFIRMED, MatchStatus.MERGED): frozenset({"merge"}),
    }

    class Meta:
        db_table = "mdm_match_candidates"
        constraints = [
            models.CheckConstraint(
                condition=Q(left_entity_id__lt=F("right_entity_id")),
                name="mdm_candidate_canonical_order_ck",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "matching_rule", "left_entity", "right_entity"),
                name="mdm_candidate_pair_uniq",
            ),
            models.CheckConstraint(
                condition=Q(confidence__gte=0, confidence__lte=1),
                name="mdm_candidate_confidence_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=MatchStatus.PENDING, reviewed_by__isnull=True, reviewed_at__isnull=True)
                    | Q(
                        status__in=(MatchStatus.CONFIRMED, MatchStatus.REJECTED, MatchStatus.MERGED),
                        reviewed_by__isnull=False,
                        reviewed_at__isnull=False,
                    )
                ),
                name="mdm_candidate_review_state_ck",
            ),
            models.CheckConstraint(
                condition=Q(status=MatchStatus.MERGED, merge_history__isnull=False) | ~Q(status=MatchStatus.MERGED),
                name="mdm_candidate_merged_history_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "-confidence"), name="mdm_candidate_status_score_idx"),
            models.Index(fields=("tenant_id", "left_entity", "right_entity"), name="mdm_candidate_pair_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        for relation in ("matching_rule", "left_entity", "right_entity", "merge_history"):
            _require_same_tenant(self, relation)
        _require_json_object(self, "field_scores")
        _require_json_object(self, "evidence")
        _require_json_array(self, "transition_history")
        if self.left_entity_id and self.right_entity_id and self.left_entity_id >= self.right_entity_id:
            raise ValidationError(
                {"right_entity": "Entity pairs must use ascending UUID order."},
                code="noncanonical_pair",
            )
        rule = (
            MatchingRule.objects.for_tenant(self.tenant_id).filter(pk=self.matching_rule_id).first()
            if self.matching_rule_id
            else None
        )
        left = (
            MasterDataEntity.objects.for_tenant(self.tenant_id).filter(pk=self.left_entity_id).first()
            if self.left_entity_id
            else None
        )
        right = (
            MasterDataEntity.objects.for_tenant(self.tenant_id).filter(pk=self.right_entity_id).first()
            if self.right_entity_id
            else None
        )
        if rule and left and right and (
            left.entity_type_id != right.entity_type_id or left.entity_type_id != rule.entity_type_id
        ):
            raise ValidationError(
                "Both entities and the matching rule must use the same entity type.",
                code="matching_type_mismatch",
            )


class MergeHistoryQuerySet(TenantQuerySet):
    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ValidationError("Merge history changes require the reversal state machine.", code="append_only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Merge history cannot be deleted.", code="append_only")


class MergeHistory(StatefulMixin, TenantScopedModel):
    """Durable merge evidence; only its one governed reversal is mutable."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    golden_record = models.ForeignKey(MasterDataEntity, models.PROTECT, related_name="merge_histories")
    status = models.CharField(max_length=12, choices=MergeStatus.choices, default=MergeStatus.APPLIED, editable=False)
    survivorship_policy = models.JSONField(default=dict)
    golden_snapshot_before = models.JSONField(default=dict)
    golden_snapshot_after = models.JSONField(default=dict)
    reason = models.TextField()
    merged_by = models.UUIDField()
    reversed_by = models.UUIDField(null=True, blank=True, editable=False)
    reversed_at = models.DateTimeField(null=True, blank=True, editable=False)
    reversal_reason = models.TextField(blank=True, default="", editable=False)
    idempotency_key = models.CharField(max_length=255)
    correlation_id = models.CharField(max_length=64)
    transition_history = models.JSONField(default=list, blank=True, editable=False)

    objects = MergeHistoryQuerySet.as_manager()

    ALLOWED_TRANSITIONS = {
        (MergeStatus.APPLIED, MergeStatus.REVERSED): frozenset({"reverse"}),
    }

    class Meta:
        db_table = "mdm_merge_history"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="mdm_merge_idempotency_uniq"),
            models.CheckConstraint(
                condition=(
                    Q(
                        status=MergeStatus.APPLIED,
                        reversed_by__isnull=True,
                        reversed_at__isnull=True,
                        reversal_reason="",
                    )
                    | (
                        Q(
                            status=MergeStatus.REVERSED,
                            reversed_by__isnull=False,
                            reversed_at__isnull=False,
                        )
                        & ~Q(reversal_reason="")
                    )
                ),
                name="mdm_merge_reversal_state_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "golden_record", "-created_at"), name="mdm_merge_golden_created_idx"),
            models.Index(fields=("tenant_id", "status", "-created_at"), name="mdm_merge_status_created_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "golden_record")
        for field_name in ("survivorship_policy", "golden_snapshot_before", "golden_snapshot_after"):
            _require_json_object(self, field_name)
        _require_json_array(self, "transition_history")
        if self._state.adding or not self.pk:
            return
        prior = type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).values().first()
        if prior is None:
            return
        mutable = {"status", "reversed_by", "reversed_at", "reversal_reason", "transition_history"}
        changed = {
            field.attname
            for field in self._meta.concrete_fields
            if field.attname not in {"id"} and prior.get(field.attname) != getattr(self, field.attname)
        }
        if changed - mutable or prior["status"] != MergeStatus.APPLIED or self.status != MergeStatus.REVERSED:
            raise ValidationError("Merge history is append-only except for governed reversal.", code="append_only")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean(validate_constraints=False)
        update_fields = kwargs.get("update_fields")
        if update_fields and self.status == MergeStatus.REVERSED:
            kwargs["update_fields"] = sorted(
                set(update_fields) | {"reversed_by", "reversed_at", "reversal_reason"}
            )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Merge history cannot be deleted.", code="append_only")


class MergeParticipant(AppendOnlyMDMModel):
    merge_history = models.ForeignKey(MergeHistory, models.CASCADE, related_name="participants")
    source_entity = models.ForeignKey(MasterDataEntity, models.PROTECT, related_name="merge_participations")
    source_version = models.PositiveIntegerField()
    source_snapshot = models.JSONField()
    role = models.CharField(max_length=16, choices=ParticipantRole.choices)

    class Meta:
        db_table = "mdm_merge_participants"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "merge_history", "source_entity"),
                name="mdm_participant_source_uniq",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "merge_history"),
                condition=Q(role=ParticipantRole.SURVIVOR),
                name="mdm_participant_one_survivor_uniq",
            ),
            models.CheckConstraint(condition=Q(source_version__gte=1), name="mdm_participant_version_gte_1_ck"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "source_entity", "-created_at"), name="mdm_participant_source_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "merge_history")
        _require_same_tenant(self, "source_entity")
        _require_json_object(self, "source_snapshot")
        merge = (
            MergeHistory.objects.for_tenant(self.tenant_id).filter(pk=self.merge_history_id).first()
            if self.merge_history_id
            else None
        )
        source = (
            MasterDataEntity.objects.for_tenant(self.tenant_id).filter(pk=self.source_entity_id).first()
            if self.source_entity_id
            else None
        )
        if merge and source and merge.golden_record.entity_type_id != source.entity_type_id:
            raise ValidationError(
                {"source_entity": "Merge participants must use the golden record entity type."},
                code="merge_type_mismatch",
            )


__all__ = [
    "DataQualityIssue",
    "DataQualityRule",
    "EntityStatus",
    "IssueSeverity",
    "IssueStatus",
    "MasterDataEntity",
    "MasterDataVersion",
    "MasterEntityType",
    "MatchCandidate",
    "MatchingAlgorithm",
    "MatchingRule",
    "MatchStatus",
    "MergeHistory",
    "MergeParticipant",
    "MergeStatus",
    "ParticipantRole",
    "QualityDimension",
    "QualityRuleType",
]
