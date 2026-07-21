"""Tenant-safe declarative customization persistence.

This module contains data invariants only. Contract resolution, schema
validation, lifecycle commands, publication, and rule evaluation belong to the
service layer. The legacy UUID-string generator is intentionally retained
because the immutable ``0001_initial`` migration imports it.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models

from src.core.tenancy import TenantQuerySet, TenantScopedModel, TimestampedModel


def generate_uuid() -> str:
    """Return a UUID string for the preserved legacy migration callable."""

    return str(uuid.uuid4())


class FieldDataType(models.TextChoices):
    """Supported, declarative custom-field storage contracts."""

    TEXT = "text", "Text"
    LONG_TEXT = "long_text", "Long text"
    INTEGER = "integer", "Integer"
    DECIMAL = "decimal", "Decimal"
    BOOLEAN = "boolean", "Boolean"
    DATE = "date", "Date"
    DATETIME = "datetime", "Datetime"
    UUID = "uuid", "UUID"
    CHOICE = "choice", "Choice"
    MULTI_CHOICE = "multi_choice", "Multiple choice"
    JSON = "json", "JSON"


class FieldDefinitionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    DEPRECATED = "deprecated", "Deprecated"
    RETIRED = "retired", "Retired"


class FieldValueSource(models.TextChoices):
    UI = "ui", "UI"
    API = "api", "API"
    IMPORT = "import", "Import"
    RULE = "rule", "Rule"


class FormDefinitionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class FormLayoutVersionStatus(models.TextChoices):
    CANDIDATE = "candidate", "Candidate"
    PUBLISHED = "published", "Published"
    SUPERSEDED = "superseded", "Superseded"
    REJECTED = "rejected", "Rejected"


class BusinessRuleTrigger(models.TextChoices):
    VALIDATE = "validate", "Validate"
    BEFORE_CREATE = "before_create", "Before create"
    BEFORE_UPDATE = "before_update", "Before update"
    FORM_CHANGE = "form_change", "Form change"


class BusinessRuleStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    PAUSED = "paused", "Paused"
    RETIRED = "retired", "Retired"


class BusinessRuleVersionStatus(models.TextChoices):
    CANDIDATE = "candidate", "Candidate"
    PUBLISHED = "published", "Published"
    SUPERSEDED = "superseded", "Superseded"
    REJECTED = "rejected", "Rejected"


class RuleExecutionStatus(models.TextChoices):
    MATCHED = "matched", "Matched"
    NOT_MATCHED = "not_matched", "Not matched"
    REJECTED = "rejected", "Rejected"
    FAILED = "failed", "Failed"


class SoftDeleteOnlyMixin:
    """Prevent application code from bypassing service-level soft deletion."""

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError(
            "Hard deletion is forbidden; use the tenant-scoped soft-delete service.",
            code="hard_delete_forbidden",
        )


class ImmutableVersionMixin:
    """Reject direct mutation/deletion of immutable version snapshots.

    Publication services may atomically update lifecycle metadata with a
    tenant-filtered queryset; persisted content is never rewritten.
    """

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError(
                "Version snapshots are immutable; create a new version.",
                code="immutable_version",
            )
        # Field and relationship validation runs before persistence. Database
        # constraints remain authoritative under concurrency and therefore are
        # intentionally left for the database to enforce.
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError(
            "Version snapshots cannot be deleted.", code="immutable_version"
        )


class AppendOnlyExecutionQuerySet(TenantQuerySet):
    """Block bulk mutation paths for execution evidence."""

    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ValidationError("Rule executions are append-only.", code="append_only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Rule executions are append-only.", code="append_only")


class MutableCustomizationModel(
    SoftDeleteOnlyMixin, TenantScopedModel, TimestampedModel
):
    """Shared audit, lifecycle-history, and optimistic-lock columns."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.UUIDField(editable=False)
    updated_by = models.UUIDField(editable=False)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_by = models.UUIDField(null=True, blank=True, editable=False)
    transition_history = models.JSONField(default=list, blank=True, editable=False)
    lock_version = models.PositiveIntegerField(default=1, editable=False)

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)


def _require_same_tenant(instance: TenantScopedModel, relation_name: str) -> None:
    """Validate the ORM relationship against the instance ownership boundary."""

    relation_id = getattr(instance, f"{relation_name}_id", None)
    tenant_id = getattr(instance, "tenant_id", None)
    if relation_id is None or tenant_id is None:
        return
    field = instance._meta.get_field(relation_name)
    related_model = field.remote_field.model
    if not related_model.objects.for_tenant(tenant_id).filter(pk=relation_id).exists():
        raise ValidationError(
            {relation_name: "The referenced record must belong to the same tenant."},
            code="cross_tenant_reference",
        )


class CustomFieldDefinition(MutableCustomizationModel):
    """Tenant-owned declarative field contract for a registered resource."""

    key = models.SlugField(max_length=100)
    label = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    owner_module = models.SlugField(max_length=100)
    target_resource = models.SlugField(max_length=120)
    target_contract_version = models.CharField(max_length=32)
    data_type = models.CharField(max_length=20, choices=FieldDataType.choices)
    required = models.BooleanField(default=False)
    searchable = models.BooleanField(default=False)
    default_value = models.JSONField(null=True, blank=True)
    validation_schema = models.JSONField(default=dict, blank=True)
    presentation_schema = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16,
        choices=FieldDefinitionStatus.choices,
        default=FieldDefinitionStatus.DRAFT,
        editable=False,
    )
    activated_at = models.DateTimeField(null=True, blank=True, editable=False)
    deprecated_at = models.DateTimeField(null=True, blank=True, editable=False)
    retired_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "customization_field_definitions"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "owner_module", "target_resource", "key"),
                condition=models.Q(deleted_at__isnull=True),
                name="cust_fd_live_target_key_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(key__regex=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"),
                name="cust_fd_key_lower_slug_ck",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status=FieldDefinitionStatus.DRAFT,
                        activated_at__isnull=True,
                        deprecated_at__isnull=True,
                        retired_at__isnull=True,
                    )
                    | models.Q(
                        status=FieldDefinitionStatus.ACTIVE,
                        activated_at__isnull=False,
                        deprecated_at__isnull=True,
                        retired_at__isnull=True,
                    )
                    | models.Q(
                        status=FieldDefinitionStatus.DEPRECATED,
                        activated_at__isnull=False,
                        deprecated_at__isnull=False,
                        retired_at__isnull=True,
                    )
                    | models.Q(
                        status=FieldDefinitionStatus.RETIRED,
                        activated_at__isnull=False,
                        deprecated_at__isnull=False,
                        retired_at__isnull=False,
                    )
                ),
                name="cust_fd_lifecycle_timestamps_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "owner_module", "target_resource", "status"),
                name="cust_fd_tgt_status_idx",
            ),
            models.Index(
                fields=("tenant_id", "status", "updated_at"),
                name="cust_fd_status_upd_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.owner_module}.{self.target_resource}.{self.key}"


class CustomFieldValue(SoftDeleteOnlyMixin, TenantScopedModel, TimestampedModel):
    """One validated field value attached to a host record UUID."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    definition = models.ForeignKey(
        CustomFieldDefinition, models.PROTECT, related_name="values"
    )
    target_record_id = models.UUIDField()
    value = models.JSONField()
    definition_revision = models.PositiveIntegerField(editable=False)
    source = models.CharField(max_length=12, choices=FieldValueSource.choices)
    created_by = models.UUIDField(editable=False)
    updated_by = models.UUIDField(editable=False)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_by = models.UUIDField(null=True, blank=True, editable=False)
    lock_version = models.PositiveIntegerField(default=1, editable=False)

    class Meta:
        db_table = "customization_field_values"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "definition", "target_record_id"),
                condition=models.Q(deleted_at__isnull=True),
                name="cust_fv_live_target_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "target_record_id"),
                name="cust_fv_tenant_record_idx",
            ),
            models.Index(
                fields=("tenant_id", "definition", "updated_at"),
                name="cust_fv_tenant_def_updated_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "definition")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)


class FormDefinition(MutableCustomizationModel):
    """Tenant-owned form identity whose layouts are immutable versions."""

    key = models.SlugField(max_length=100)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    owner_module = models.SlugField(max_length=100)
    target_resource = models.SlugField(max_length=120)
    target_contract_version = models.CharField(max_length=32)
    status = models.CharField(
        max_length=12,
        choices=FormDefinitionStatus.choices,
        default=FormDefinitionStatus.DRAFT,
        editable=False,
    )
    published_version = models.PositiveIntegerField(
        null=True, blank=True, editable=False
    )
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    published_by = models.UUIDField(null=True, blank=True, editable=False)
    archived_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "customization_form_definitions"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "owner_module", "target_resource", "key"),
                condition=models.Q(deleted_at__isnull=True),
                name="cust_form_live_target_key_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=FormDefinitionStatus.PUBLISHED)
                    | models.Q(
                        published_version__isnull=False,
                        published_at__isnull=False,
                        published_by__isnull=False,
                    )
                ),
                name="cust_form_published_fields_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "owner_module", "target_resource", "status"),
                name="cust_form_tgt_status_idx",
            ),
            models.Index(
                fields=("tenant_id", "status", "updated_at"),
                name="cust_form_status_upd_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.owner_module}.{self.target_resource}.{self.key}"


class FormLayoutVersion(ImmutableVersionMixin, TenantScopedModel):
    """Immutable, content-addressed form layout snapshot."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    form = models.ForeignKey(
        FormDefinition, models.PROTECT, related_name="layout_versions"
    )
    version = models.PositiveIntegerField(editable=False)
    schema_version = models.PositiveSmallIntegerField(default=1, editable=False)
    layout = models.JSONField()
    content_hash = models.CharField(max_length=64, editable=False)
    change_summary = models.CharField(max_length=500)
    status = models.CharField(
        max_length=12,
        choices=FormLayoutVersionStatus.choices,
        default=FormLayoutVersionStatus.CANDIDATE,
        editable=False,
    )
    validation_errors = models.JSONField(default=list, blank=True, editable=False)
    created_by = models.UUIDField(editable=False)
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    published_by = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "customization_form_layout_versions"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "form", "version"),
                name="cust_layout_tenant_form_ver_uniq",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "form", "content_hash"),
                name="cust_layout_tenant_form_hash_uniq",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "form"),
                condition=models.Q(status=FormLayoutVersionStatus.PUBLISHED),
                name="cust_layout_one_published_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "form", "status", "version"),
                name="cust_layout_form_stat_ver_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "form")


class BusinessRule(MutableCustomizationModel):
    """Tenant-owned rule identity evaluated through immutable AST versions."""

    key = models.SlugField(max_length=100)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    owner_module = models.SlugField(max_length=100)
    target_resource = models.SlugField(max_length=120)
    target_contract_version = models.CharField(max_length=32)
    trigger = models.CharField(max_length=20, choices=BusinessRuleTrigger.choices)
    priority = models.PositiveSmallIntegerField(default=100)
    stop_on_match = models.BooleanField(default=False)
    status = models.CharField(
        max_length=12,
        choices=BusinessRuleStatus.choices,
        default=BusinessRuleStatus.DRAFT,
        editable=False,
    )
    published_version = models.PositiveIntegerField(
        null=True, blank=True, editable=False
    )
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    published_by = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "customization_business_rules"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "owner_module", "target_resource", "key"),
                condition=models.Q(deleted_at__isnull=True),
                name="cust_rule_live_target_key_uniq",
            ),
            models.UniqueConstraint(
                fields=(
                    "tenant_id",
                    "owner_module",
                    "target_resource",
                    "trigger",
                    "priority",
                    "key",
                ),
                condition=models.Q(deleted_at__isnull=True),
                name="cust_rule_live_trigger_priority_key_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(priority__gte=1, priority__lte=1000),
                name="cust_rule_priority_range_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=(
                    "tenant_id",
                    "owner_module",
                    "target_resource",
                    "trigger",
                    "status",
                    "priority",
                ),
                name="cust_rule_tgt_trig_stat_idx",
            ),
            models.Index(
                fields=("tenant_id", "status", "updated_at"),
                name="cust_rule_status_upd_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.owner_module}.{self.target_resource}.{self.key}"


class BusinessRuleVersion(ImmutableVersionMixin, TenantScopedModel):
    """Immutable, validated declarative rule program snapshot."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    rule = models.ForeignKey(BusinessRule, models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField(editable=False)
    language_version = models.PositiveSmallIntegerField(default=1, editable=False)
    condition_ast = models.JSONField()
    action_ast = models.JSONField()
    dependencies = models.JSONField(default=list, blank=True)
    content_hash = models.CharField(max_length=64, editable=False)
    status = models.CharField(
        max_length=12,
        choices=BusinessRuleVersionStatus.choices,
        default=BusinessRuleVersionStatus.CANDIDATE,
        editable=False,
    )
    validation_errors = models.JSONField(default=list, blank=True, editable=False)
    change_summary = models.CharField(max_length=500)
    created_by = models.UUIDField(editable=False)
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    published_by = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "customization_business_rule_versions"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "rule", "version"),
                name="cust_rulever_tenant_rule_ver_uniq",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "rule", "content_hash"),
                name="cust_rulever_tenant_rule_hash_uniq",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "rule"),
                condition=models.Q(status=BusinessRuleVersionStatus.PUBLISHED),
                name="cust_rulever_one_published_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "rule", "status", "version"),
                name="cust_rulever_rule_stat_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "rule")


class RuleExecution(TenantScopedModel):
    """Append-only, redacted evidence for one published rule evaluation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule = models.ForeignKey(BusinessRule, models.PROTECT, related_name="executions")
    rule_version = models.ForeignKey(
        BusinessRuleVersion, models.PROTECT, related_name="executions"
    )
    target_record_id = models.UUIDField(null=True, blank=True)
    trigger = models.CharField(max_length=20, choices=BusinessRuleTrigger.choices)
    idempotency_key = models.CharField(max_length=128)
    status = models.CharField(max_length=12, choices=RuleExecutionStatus.choices)
    input_fingerprint = models.CharField(max_length=64)
    result = models.JSONField(default=dict, blank=True)
    diagnostics = models.JSONField(default=list, blank=True)
    duration_ms = models.PositiveIntegerField()
    correlation_id = models.UUIDField()
    executed_by = models.UUIDField()
    executed_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyExecutionQuerySet.as_manager()

    class Meta:
        db_table = "customization_rule_executions"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "rule", "idempotency_key"),
                name="cust_exec_tenant_rule_idem_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "rule", "executed_at"),
                name="cust_exec_tenant_rule_time_idx",
            ),
            models.Index(
                fields=("tenant_id", "target_record_id", "executed_at"),
                name="cust_exec_record_time_idx",
            ),
            models.Index(
                fields=("tenant_id", "status", "executed_at"),
                name="cust_exec_status_time_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "rule")
        _require_same_tenant(self, "rule_version")
        if self.rule_id and self.rule_version_id:
            version_rule_id = (
                BusinessRuleVersion.objects.for_tenant(self.tenant_id)
                .filter(pk=self.rule_version_id)
                .values_list("rule_id", flat=True)
                .first()
            )
            if version_rule_id is not None and version_rule_id != self.rule_id:
                raise ValidationError(
                    {
                        "rule_version": "The rule version must belong to the execution rule."
                    },
                    code="rule_version_mismatch",
                )

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError(
                "Rule executions are append-only.", code="append_only"
            )
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Rule executions are append-only.", code="append_only")


__all__ = [
    "BusinessRule",
    "BusinessRuleStatus",
    "BusinessRuleTrigger",
    "BusinessRuleVersion",
    "BusinessRuleVersionStatus",
    "CustomFieldDefinition",
    "CustomFieldValue",
    "FieldDataType",
    "FieldDefinitionStatus",
    "FieldValueSource",
    "FormDefinition",
    "FormDefinitionStatus",
    "FormLayoutVersion",
    "FormLayoutVersionStatus",
    "RuleExecution",
    "RuleExecutionStatus",
    "generate_uuid",
]
