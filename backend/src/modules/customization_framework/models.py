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


class PublicationEventType(models.TextChoices):
    """Append-only publication decisions for immutable snapshots."""

    PUBLISHED = "published", "Published"
    SUPERSEDED = "superseded", "Superseded"


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

    Publication state is recorded in :class:`PublicationRecord`; a snapshot
    row itself is never rewritten.
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
        raise ValidationError("Version snapshots cannot be deleted.", code="immutable_version")


class AppendOnlyTenantQuerySet(TenantQuerySet):
    """Block bulk mutation paths for tenant-owned immutable evidence."""

    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ValidationError("Evidence records are append-only.", code="append_only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Evidence records are append-only.", code="append_only")


class AppendOnlyTenantRecord(TenantScopedModel):
    """Defense-in-depth ORM guard shared by every immutable evidence table."""

    objects = AppendOnlyTenantQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Evidence records are append-only.", code="append_only")
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Evidence records are append-only.", code="append_only")


class MutableCustomizationModel(SoftDeleteOnlyMixin, TenantScopedModel, TimestampedModel):
    """Shared audit, lifecycle-history, and optimistic-lock columns."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.UUIDField(editable=False)
    updated_by = models.UUIDField(editable=False)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_by = models.UUIDField(null=True, blank=True, editable=False)
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


class CustomFieldDefinitionVersion(AppendOnlyTenantRecord):
    """Immutable snapshot supporting field rollback to any prior version."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    definition = models.ForeignKey(CustomFieldDefinition, models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField(editable=False)
    document = models.JSONField(editable=False)
    content_hash = models.CharField(max_length=64, editable=False)
    actor_id = models.UUIDField(editable=False)
    correlation_id = models.UUIDField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "customization_field_definition_versions"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "definition", "version"),
                name="cust_fdver_tenant_def_ver_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "definition", "version"),
                name="cust_fdver_def_ver_idx",
            ),
            models.Index(
                fields=("tenant_id", "correlation_id"),
                name="cust_fdver_corr_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "definition")


class CustomFieldValue(SoftDeleteOnlyMixin, TenantScopedModel, TimestampedModel):
    """One validated field value attached to a host record UUID."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    definition = models.ForeignKey(CustomFieldDefinition, models.PROTECT, related_name="values")
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
    published_version = models.PositiveIntegerField(null=True, blank=True, editable=False)
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
    form = models.ForeignKey(FormDefinition, models.PROTECT, related_name="layout_versions")
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

    objects = AppendOnlyTenantQuerySet.as_manager()

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
    published_version = models.PositiveIntegerField(null=True, blank=True, editable=False)
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

    objects = AppendOnlyTenantQuerySet.as_manager()

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


class RuleExecution(AppendOnlyTenantRecord):
    """Append-only, redacted evidence for one published rule evaluation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule = models.ForeignKey(BusinessRule, models.PROTECT, related_name="executions")
    rule_version = models.ForeignKey(BusinessRuleVersion, models.PROTECT, related_name="executions")
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
                    {"rule_version": "The rule version must belong to the execution rule."},
                    code="rule_version_mismatch",
                )

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)


class RuntimeConfiguration(TenantScopedModel, TimestampedModel):
    """Current validated configuration document for one tenant."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(unique=True, db_index=True)
    document = models.JSONField()
    version = models.PositiveIntegerField(editable=False)
    environment = models.CharField(max_length=32)
    updated_by = models.UUIDField(editable=False)

    class Meta:
        db_table = "customization_runtime_configurations"
        indexes = [
            models.Index(
                fields=("tenant_id", "environment"),
                name="cust_runtime_tenant_env_idx",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)


class RuntimeConfigurationVersion(AppendOnlyTenantRecord):
    """Immutable, actor-attributed runtime configuration snapshot."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration = models.ForeignKey(RuntimeConfiguration, models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField(editable=False)
    document = models.JSONField(editable=False)
    environment = models.CharField(max_length=32, editable=False)
    actor_id = models.UUIDField(editable=False)
    correlation_id = models.UUIDField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "customization_runtime_configuration_versions"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "configuration", "version"),
                name="cust_runtime_ver_tenant_cfg_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "configuration", "version"),
                name="cust_runtime_ver_cfg_idx",
            ),
            models.Index(
                fields=("tenant_id", "correlation_id"),
                name="cust_runtime_ver_corr_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "configuration")


class ConfigurationAuditRecord(AppendOnlyTenantRecord):
    """Immutable before/after evidence for a runtime configuration command."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration = models.ForeignKey(RuntimeConfiguration, models.PROTECT, related_name="audit_records")
    version = models.PositiveIntegerField(editable=False)
    action = models.CharField(max_length=32, editable=False)
    before = models.JSONField(null=True, blank=True, editable=False)
    after = models.JSONField(editable=False)
    actor_id = models.UUIDField(editable=False)
    correlation_id = models.UUIDField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "customization_configuration_audit_records"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "configuration", "version"),
                name="cust_cfg_audit_tenant_ver_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "configuration", "version"),
                name="cust_cfg_audit_cfg_ver_idx",
            ),
            models.Index(
                fields=("tenant_id", "correlation_id"),
                name="cust_cfg_audit_corr_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "configuration")


class IdempotentCommand(AppendOnlyTenantRecord):
    """Persisted mutation result used to replay safe tenant-scoped retries."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(max_length=128, editable=False)
    command_type = models.CharField(max_length=96, editable=False)
    request_fingerprint = models.CharField(max_length=64, editable=False)
    response_payload = models.JSONField(editable=False)
    response_status = models.PositiveSmallIntegerField(editable=False)
    resource_type = models.CharField(max_length=64, editable=False)
    resource_id = models.UUIDField(null=True, blank=True, editable=False)
    actor_id = models.UUIDField(editable=False)
    correlation_id = models.UUIDField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "customization_idempotent_commands"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"),
                name="cust_idem_tenant_key_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "command_type", "created_at"),
                name="cust_idem_command_time_idx",
            ),
            models.Index(
                fields=("tenant_id", "correlation_id"),
                name="cust_idem_corr_idx",
            ),
        ]


class LifecycleTransitionRecord(AppendOnlyTenantRecord):
    """Append-only replacement for mutable aggregate transition history."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    aggregate_type = models.CharField(max_length=64, editable=False)
    aggregate_id = models.UUIDField(editable=False)
    version = models.PositiveIntegerField(editable=False)
    transition_key = models.CharField(max_length=128, editable=False)
    command = models.CharField(max_length=64, editable=False)
    from_state = models.CharField(max_length=32, null=True, blank=True, editable=False)
    to_state = models.CharField(max_length=32, editable=False)
    metadata = models.JSONField(default=dict, blank=True, editable=False)
    actor_id = models.UUIDField(editable=False)
    correlation_id = models.UUIDField(editable=False)
    occurred_at = models.DateTimeField(editable=False)

    class Meta:
        db_table = "customization_lifecycle_transition_records"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "aggregate_type", "aggregate_id", "version"),
                name="cust_lifecycle_aggregate_ver_uniq",
            ),
            models.UniqueConstraint(
                fields=(
                    "tenant_id",
                    "aggregate_type",
                    "aggregate_id",
                    "transition_key",
                ),
                name="cust_lifecycle_transition_key_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "aggregate_type", "aggregate_id", "version"),
                name="cust_lifecycle_aggregate_idx",
            ),
            models.Index(
                fields=("tenant_id", "correlation_id"),
                name="cust_lifecycle_corr_idx",
            ),
        ]


class PublicationRecord(AppendOnlyTenantRecord):
    """Immutable publication/supersession decision for a snapshot."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    aggregate_type = models.CharField(max_length=64, editable=False)
    aggregate_id = models.UUIDField(editable=False)
    snapshot_id = models.UUIDField(editable=False)
    version = models.PositiveIntegerField(editable=False)
    event_type = models.CharField(max_length=16, choices=PublicationEventType.choices, editable=False)
    publication_key = models.CharField(max_length=128, editable=False)
    supersedes_snapshot_id = models.UUIDField(null=True, blank=True, editable=False)
    actor_id = models.UUIDField(editable=False)
    correlation_id = models.UUIDField(editable=False)
    occurred_at = models.DateTimeField(editable=False)

    class Meta:
        db_table = "customization_publication_records"
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "tenant_id",
                    "aggregate_type",
                    "aggregate_id",
                    "publication_key",
                    "event_type",
                ),
                name="cust_publication_key_event_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=(
                    "tenant_id",
                    "aggregate_type",
                    "aggregate_id",
                    "occurred_at",
                ),
                name="cust_publication_aggregate_idx",
            ),
            models.Index(
                fields=("tenant_id", "snapshot_id"),
                name="cust_publication_snapshot_idx",
            ),
            models.Index(
                fields=("tenant_id", "correlation_id"),
                name="cust_publication_corr_idx",
            ),
        ]


__all__ = [
    "AppendOnlyTenantQuerySet",
    "AppendOnlyTenantRecord",
    "BusinessRule",
    "BusinessRuleStatus",
    "BusinessRuleTrigger",
    "BusinessRuleVersion",
    "BusinessRuleVersionStatus",
    "ConfigurationAuditRecord",
    "CustomFieldDefinition",
    "CustomFieldDefinitionVersion",
    "CustomFieldValue",
    "FieldDataType",
    "FieldDefinitionStatus",
    "FieldValueSource",
    "FormDefinition",
    "FormDefinitionStatus",
    "FormLayoutVersion",
    "FormLayoutVersionStatus",
    "IdempotentCommand",
    "LifecycleTransitionRecord",
    "PublicationEventType",
    "PublicationRecord",
    "RuleExecution",
    "RuleExecutionStatus",
    "RuntimeConfiguration",
    "RuntimeConfigurationVersion",
    "generate_uuid",
]
