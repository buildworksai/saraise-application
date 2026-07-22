"""Tenant-safe persistence model for the metadata kernel.

The schema and record version tables are evidence, not mutable working rows.
Services create new snapshots and use narrowly-scoped queryset lifecycle
updates where publication requires an atomic state transition.
"""

from __future__ import annotations

import math
import re
import uuid
from datetime import date
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from src.core.tenancy import TenantQuerySet, TenantScopedModel, TimestampedModel

UNKNOWN_ACTOR_ID = uuid.UUID(int=0)
BUILT_IN_FIELD_TYPES = frozenset({"text", "number", "date", "boolean", "select", "reference", "json"})


def _same_tenant(instance: models.Model, relation_name: str) -> None:
    """Validate ownership without ever resolving an unscoped relation."""
    relation_id = getattr(instance, f"{relation_name}_id", None)
    tenant_id = getattr(instance, "tenant_id", None)
    if relation_id is None or tenant_id is None:
        return
    relation = instance._meta.get_field(relation_name)
    related_model = relation.remote_field.model
    if not related_model._base_manager.filter(pk=relation_id, tenant_id=tenant_id).exists():
        raise ValidationError(
            {relation_name: "The referenced object was not found in this tenant."},
            code="cross_tenant_reference",
        )


class ImmutableEvidenceError(ValidationError):
    """Raised when code attempts to rewrite retained evidence."""


class AppendOnlyQuerySet(TenantQuerySet):
    """Block bulk mutation paths around append-only evidence."""

    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ImmutableEvidenceError("Append-only evidence cannot be updated.", code="append_only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableEvidenceError("Append-only evidence cannot be deleted.", code="append_only")


class SchemaVersionQuerySet(TenantQuerySet):
    """Permit only lifecycle metadata updates required by publication."""

    _LIFECYCLE_FIELDS = frozenset({"status", "compatibility", "validation_report", "published_at", "published_by"})

    def update(self, **kwargs: Any) -> int:
        forbidden = set(kwargs) - self._LIFECYCLE_FIELDS
        if forbidden:
            raise ImmutableEvidenceError(
                f"Schema snapshot content is immutable: {', '.join(sorted(forbidden))}.",
                code="immutable_schema_content",
            )
        return super().update(**kwargs)

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableEvidenceError("Schema version snapshots cannot be deleted.", code="immutable_schema_version")


class ActiveResourceManager(models.Manager.from_queryset(TenantQuerySet)):  # type: ignore[misc]
    """Default record manager that hides soft-deleted rows."""

    def get_queryset(self) -> TenantQuerySet:
        return super().get_queryset().filter(deleted_at__isnull=True)

    def create(self, **kwargs: Any) -> "DynamicResource":
        """Translate applied-v1 constructor arguments into the versioned shape.

        This is intentionally a persistence compatibility shim, not an API
        mutation path. Governed views always use ``DynamicResourceService``.
        """
        entity = kwargs.get("entity_definition")
        if entity is not None and kwargs.get("schema_version") is None:
            kwargs["schema_version"] = _legacy_schema_version(entity)
        actor = kwargs.get("created_by")
        if actor is not None and not isinstance(actor, uuid.UUID):
            actor_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:legacy-user:{getattr(actor, 'pk', actor)}")
            kwargs["created_by"] = actor_uuid
            kwargs.setdefault("updated_by", actor_uuid)
        kwargs.setdefault("record_key", str(uuid.uuid4()))
        kwargs.setdefault("display_name", kwargs["record_key"])
        return super().create(**kwargs)


class FieldDefinitionManager(models.Manager.from_queryset(AppendOnlyQuerySet)):  # type: ignore[misc]
    """Read-only-version compatible manager for applied v1 field creation."""

    def create(self, **kwargs: Any) -> "FieldDefinition":
        entity = kwargs.pop("entity_definition", None)
        if entity is not None and kwargs.get("schema_version") is None:
            kwargs["schema_version"] = _legacy_schema_version(entity)
        schema_version = kwargs.get("schema_version")
        if schema_version is None:
            raise ValidationError({"schema_version": "Schema version is required."})
        kwargs.setdefault(
            "order",
            self.filter(tenant_id=kwargs.get("tenant_id"), schema_version=schema_version).count(),
        )
        return super().create(**kwargs)


def _legacy_schema_version(entity: "EntityDefinition") -> "EntitySchemaVersion":
    """Return/create a real candidate snapshot for legacy direct constructors."""
    version = EntitySchemaVersion.objects.filter(entity_definition=entity).order_by("-version").first()
    if version is not None:
        return version
    canonical = '{"fields":[]}'
    return EntitySchemaVersion.objects.create(
        tenant_id=entity.tenant_id,
        entity_definition=entity,
        version=1,
        status=EntitySchemaVersion.Status.CANDIDATE,
        schema={"fields": []},
        schema_hash=__import__("hashlib").sha256(canonical.encode("utf-8")).hexdigest(),
        created_by=entity.created_by,
    )


class EntityDefinition(TenantScopedModel, TimestampedModel):
    """Stable identity and current lifecycle pointer for a modeled entity."""

    class Origin(models.TextChoices):
        CUSTOM = "custom", "Custom"
        SYSTEM = "system", "System"
        EXTENSION = "extension", "Extension"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    class NamingStrategy(models.TextChoices):
        UUID = "uuid", "UUID"
        SEQUENCE = "sequence", "Sequence"
        FIELD = "field", "Field"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    plural_name = models.CharField(max_length=160)
    code = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    owner_module = models.SlugField(max_length=100, default="metadata_modeling")
    icon = models.CharField(max_length=100, blank=True)
    origin = models.CharField(max_length=16, choices=Origin.choices, default=Origin.CUSTOM)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    is_submittable = models.BooleanField(default=False)
    track_changes = models.BooleanField(default=True)
    naming_strategy = models.CharField(max_length=16, choices=NamingStrategy.choices, default=NamingStrategy.UUID)
    naming_config = models.JSONField(default=dict, blank=True)
    active_version = models.ForeignKey(
        "EntitySchemaVersion", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    lock_version = models.PositiveIntegerField(default=1)
    created_by = models.UUIDField(default=UNKNOWN_ACTOR_ID, editable=False)
    updated_by = models.UUIDField(default=UNKNOWN_ACTOR_ID, editable=False)
    archived_at = models.DateTimeField(null=True, blank=True, editable=False)
    archived_by = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["name", "code"]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "code"], name="meta_entity_tenant_code_uq"),
            models.CheckConstraint(condition=Q(lock_version__gte=1), name="meta_entity_lock_gte_1_ck"),
            models.CheckConstraint(
                condition=(
                    Q(status="archived", archived_at__isnull=False, archived_by__isnull=False)
                    | (~Q(status="archived") & Q(archived_at__isnull=True, archived_by__isnull=True))
                ),
                name="meta_entity_archive_audit_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status="published") | Q(active_version__isnull=False),
                name="meta_entity_published_ver_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "status", "name"], name="meta_entity_status_name_ix"),
            models.Index(fields=["tenant_id", "owner_module", "status"], name="meta_entity_owner_status_ix"),
            models.Index(fields=["tenant_id", "-updated_at"], name="meta_entity_updated_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.active_version_id:
            _same_tenant(self, "active_version")
            active_entity_id = (
                EntitySchemaVersion._base_manager.filter(pk=self.active_version_id, tenant_id=self.tenant_id)
                .values_list("entity_definition_id", flat=True)
                .first()
            )
            if active_entity_id is not None and active_entity_id != self.pk:
                raise ValidationError(
                    {"active_version": "The active version must belong to this entity."},
                    code="invalid_active_version",
                )
        if self.naming_strategy == self.NamingStrategy.UUID and self.naming_config:
            raise ValidationError({"naming_config": "UUID naming does not accept configuration."})
        if self.naming_strategy == self.NamingStrategy.FIELD:
            if (
                not isinstance(self.naming_config, dict)
                or set(self.naming_config) != {"field_key"}
                or not isinstance(self.naming_config.get("field_key"), str)
                or not self.naming_config["field_key"]
            ):
                raise ValidationError({"naming_config": "Field naming requires only a non-empty field_key."})
        if self.naming_strategy == self.NamingStrategy.SEQUENCE:
            allowed = {"sequence_key", "prefix_template", "padding", "reset_period"}
            if not isinstance(self.naming_config, dict) or set(self.naming_config) - allowed:
                raise ValidationError({"naming_config": "Sequence naming contains unsupported options."})
            template = self.naming_config.get("prefix_template")
            numeric_tokens = re.findall(r"\{#+\}", template) if isinstance(template, str) else []
            placeholders = re.findall(r"\{[^{}]+\}", template) if isinstance(template, str) else []
            if (
                not template
                or len(numeric_tokens) != 1
                or any(token not in {"{YYYY}", "{MM}", numeric_tokens[0]} for token in placeholders)
            ):
                raise ValidationError(
                    {"naming_config": "Sequence naming requires one numeric token and only {YYYY}/{MM} placeholders."}
                )
        if self.pk and not self._state.adding:
            prior = type(self).objects.filter(pk=self.pk).values("code").first()
            if prior and prior["code"] != self.code:
                published = EntitySchemaVersion.objects.filter(
                    entity_definition_id=self.pk,
                    status__in=[EntitySchemaVersion.Status.PUBLISHED, EntitySchemaVersion.Status.SUPERSEDED],
                ).exists()
                if published:
                    raise ValidationError({"code": "Code is immutable after first publication."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.plural_name:
            self.plural_name = self.name
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    @property
    def fields(self) -> TenantQuerySet:
        """Compatibility accessor over immutable version-owned fields."""
        return FieldDefinition.objects.filter(schema_version__entity_definition=self)


class EntitySchemaVersion(TenantScopedModel):
    """Immutable canonical snapshot of one complete entity schema."""

    class Status(models.TextChoices):
        CANDIDATE = "candidate", "Candidate"
        PUBLISHED = "published", "Published"
        SUPERSEDED = "superseded", "Superseded"
        REJECTED = "rejected", "Rejected"

    class Compatibility(models.TextChoices):
        COMPATIBLE = "compatible", "Compatible"
        REQUIRES_BACKFILL = "requires_backfill", "Requires backfill"
        BREAKING = "breaking", "Breaking"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity_definition = models.ForeignKey(EntityDefinition, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CANDIDATE)
    schema = models.JSONField()
    schema_hash = models.CharField(max_length=64)
    change_summary = models.TextField(blank=True)
    compatibility = models.CharField(max_length=24, choices=Compatibility.choices, default=Compatibility.COMPATIBLE)
    validation_report = models.JSONField(default=dict, blank=True)
    based_on_version = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="derived_versions"
    )
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    published_by = models.UUIDField(null=True, blank=True, editable=False)
    created_by = models.UUIDField(default=UNKNOWN_ACTOR_ID, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = SchemaVersionQuerySet.as_manager()

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "entity_definition", "version"], name="meta_schema_entity_ver_uq"
            ),
            models.UniqueConstraint(
                fields=["tenant_id", "entity_definition", "schema_hash"], name="meta_schema_entity_hash_uq"
            ),
            models.UniqueConstraint(
                fields=["tenant_id", "entity_definition"],
                condition=Q(status="published"),
                name="meta_schema_one_published_uq",
            ),
            models.CheckConstraint(condition=Q(version__gte=1), name="meta_schema_ver_gte_1_ck"),
            models.CheckConstraint(
                condition=(
                    Q(status="published", published_at__isnull=False, published_by__isnull=False)
                    | (~Q(status="published") & Q(published_at__isnull=True, published_by__isnull=True))
                ),
                name="meta_schema_publish_audit_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "entity_definition", "-version"], name="meta_schema_entity_ver_ix"),
            models.Index(fields=["tenant_id", "status", "created_at"], name="meta_schema_status_created_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        _same_tenant(self, "entity_definition")
        if self.based_on_version_id:
            _same_tenant(self, "based_on_version")
            base_entity_id = (
                type(self)
                ._base_manager.filter(pk=self.based_on_version_id, tenant_id=self.tenant_id)
                .values_list("entity_definition_id", flat=True)
                .first()
            )
            if base_entity_id is not None and base_entity_id != self.entity_definition_id:
                raise ValidationError({"based_on_version": "The base version must belong to the same entity."})
        if not re.fullmatch(r"[0-9a-f]{64}", self.schema_hash):
            raise ValidationError({"schema_hash": "Schema hash must be a lowercase SHA-256 digest."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableEvidenceError(
                "Schema snapshots are immutable; create a new version.", code="immutable_schema"
            )
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ImmutableEvidenceError("Schema version snapshots cannot be deleted.", code="immutable_schema")

    def __str__(self) -> str:
        return f"{self.entity_definition.code} v{self.version}"


class FieldDefinition(TenantScopedModel):
    """Immutable normalized field belonging to a schema snapshot."""

    class FieldType(models.TextChoices):
        TEXT = "text", "Text"
        NUMBER = "number", "Number"
        DATE = "date", "Date"
        BOOLEAN = "boolean", "Boolean"
        SELECT = "select", "Select"
        REFERENCE = "reference", "Reference"
        JSON = "json", "JSON"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    schema_version = models.ForeignKey(EntitySchemaVersion, on_delete=models.CASCADE, related_name="fields")
    name = models.CharField(max_length=160)
    key = models.SlugField(max_length=100)
    field_type = models.CharField(max_length=32, choices=FieldType.choices)
    is_required = models.BooleanField(default=False)
    is_read_only = models.BooleanField(default=False)
    is_searchable = models.BooleanField(default=False)
    default_value = models.JSONField(null=True, blank=True)
    validation_rules = models.JSONField(default=dict, blank=True)
    options = models.JSONField(default=list, blank=True)
    reference_entity_code = models.SlugField(max_length=100, null=True, blank=True)
    help_text = models.TextField(blank=True)
    placeholder = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = FieldDefinitionManager()

    class Meta:
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "schema_version", "key"], name="meta_field_schema_key_uq"),
            models.UniqueConstraint(fields=["tenant_id", "schema_version", "order"], name="meta_field_schema_order_uq"),
            models.CheckConstraint(
                condition=~Q(field_type="select") | ~Q(options=[]), name="meta_field_select_opts_ck"
            ),
            models.CheckConstraint(
                condition=(
                    (Q(field_type="reference") & Q(reference_entity_code__isnull=False) & ~Q(reference_entity_code=""))
                    | (
                        ~Q(field_type="reference")
                        & (Q(reference_entity_code__isnull=True) | Q(reference_entity_code=""))
                    )
                ),
                name="meta_field_reference_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "schema_version", "order"], name="meta_field_schema_order_ix"),
            models.Index(fields=["tenant_id", "reference_entity_code"], name="meta_field_reference_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        _same_tenant(self, "schema_version")
        if not isinstance(self.validation_rules, dict):
            raise ValidationError({"validation_rules": "Validation rules must be an object."})
        if not isinstance(self.options, list):
            raise ValidationError({"options": "Options must be an array."})
        allowed_rules = {
            self.FieldType.TEXT: {"min_length", "max_length", "regex"},
            self.FieldType.NUMBER: {"minimum", "maximum", "integer_only", "decimal_places"},
            self.FieldType.DATE: {"minimum", "maximum"},
            self.FieldType.SELECT: {"allow_blank"},
            self.FieldType.REFERENCE: {"target_status"},
            self.FieldType.JSON: {"type", "required", "properties", "items", "enum"},
            self.FieldType.BOOLEAN: set(),
        }.get(self.field_type)
        if allowed_rules is None:
            return
        unknown = set(self.validation_rules) - allowed_rules
        if unknown:
            raise ValidationError({"validation_rules": f"Unsupported rules: {', '.join(sorted(unknown))}."})
        if self.field_type == self.FieldType.SELECT:
            if not self.options or any(not isinstance(value, str) for value in self.options):
                raise ValidationError({"options": "Select options must be a non-empty array of strings."})
            if len(set(self.options)) != len(self.options):
                raise ValidationError({"options": "Select options must be unique."})
        elif self.options:
            raise ValidationError({"options": "Options are supported only for select fields."})
        if self.field_type == self.FieldType.REFERENCE:
            if self.validation_rules.get("target_status", "published") != "published":
                raise ValidationError({"validation_rules": "References may target only published entities."})
        if "regex" in self.validation_rules:
            expression = self.validation_rules["regex"]
            if not isinstance(expression, str) or len(expression) > 4096:
                raise ValidationError({"validation_rules": "Regex must be a string of at most 4096 characters."})
            try:
                re.compile(expression)
            except re.error as exc:
                raise ValidationError({"validation_rules": "Regex is invalid."}) from exc
        if self.default_value is not None:
            self._validate_default()

    def _validate_default(self) -> None:
        value = self.default_value
        if self.field_type == self.FieldType.TEXT and not isinstance(value, str):
            raise ValidationError({"default_value": "Text defaults must be strings."})
        if self.field_type == self.FieldType.NUMBER:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValidationError({"default_value": "Number defaults must be finite numbers."})
        if self.field_type == self.FieldType.DATE:
            if not isinstance(value, str):
                raise ValidationError({"default_value": "Date defaults must use YYYY-MM-DD."})
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValidationError({"default_value": "Date defaults must use YYYY-MM-DD."}) from exc
        if self.field_type == self.FieldType.BOOLEAN and not isinstance(value, bool):
            raise ValidationError({"default_value": "Boolean defaults must be booleans."})
        if self.field_type == self.FieldType.SELECT and value not in self.options:
            raise ValidationError({"default_value": "Select defaults must be one of the configured options."})
        if self.field_type == self.FieldType.REFERENCE:
            try:
                uuid.UUID(str(value))
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValidationError({"default_value": "Reference defaults must be resource UUIDs."}) from exc

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableEvidenceError("Published field snapshots are immutable.", code="immutable_field")
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ImmutableEvidenceError("Field snapshots cannot be deleted.", code="immutable_field")

    def __str__(self) -> str:
        return f"{self.name} ({self.key})"


class DynamicResource(TenantScopedModel, TimestampedModel):
    """A soft-deletable dynamic record pinned to its validating schema."""

    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity_definition = models.ForeignKey(EntityDefinition, on_delete=models.PROTECT, related_name="resources")
    schema_version = models.ForeignKey(EntitySchemaVersion, on_delete=models.PROTECT, related_name="resources")
    record_key = models.CharField(max_length=160)
    display_name = models.CharField(max_length=255)
    state = models.CharField(max_length=16, choices=State.choices, default=State.DRAFT)
    data = models.JSONField(default=dict, blank=True)
    lock_version = models.PositiveIntegerField(default=1)
    created_by = models.UUIDField(default=UNKNOWN_ACTOR_ID, editable=False)
    updated_by = models.UUIDField(default=UNKNOWN_ACTOR_ID, editable=False)
    submitted_at = models.DateTimeField(null=True, blank=True, editable=False)
    submitted_by = models.UUIDField(null=True, blank=True, editable=False)
    cancelled_at = models.DateTimeField(null=True, blank=True, editable=False)
    cancelled_by = models.UUIDField(null=True, blank=True, editable=False)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True, editable=False)
    deleted_by = models.UUIDField(null=True, blank=True, editable=False)

    objects = ActiveResourceManager()
    all_objects = TenantQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "entity_definition", "record_key"], name="meta_resource_entity_key_uq"
            ),
            models.CheckConstraint(condition=Q(lock_version__gte=1), name="meta_resource_lock_gte_1_ck"),
            models.CheckConstraint(
                condition=(
                    Q(
                        state="draft",
                        submitted_at__isnull=True,
                        submitted_by__isnull=True,
                        cancelled_at__isnull=True,
                        cancelled_by__isnull=True,
                    )
                    | Q(
                        state="submitted",
                        submitted_at__isnull=False,
                        submitted_by__isnull=False,
                        cancelled_at__isnull=True,
                        cancelled_by__isnull=True,
                    )
                    | Q(
                        state="cancelled",
                        submitted_at__isnull=False,
                        submitted_by__isnull=False,
                        cancelled_at__isnull=False,
                        cancelled_by__isnull=False,
                    )
                ),
                name="meta_resource_state_audit_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(deleted_at__isnull=True, deleted_by__isnull=True)
                    | Q(deleted_at__isnull=False, deleted_by__isnull=False)
                ),
                name="meta_resource_delete_audit_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "entity_definition", "state", "-created_at"],
                name="meta_resource_state_created_ix",
            ),
            models.Index(fields=["tenant_id", "entity_definition", "display_name"], name="meta_resource_display_ix"),
            models.Index(fields=["tenant_id", "-updated_at"], name="meta_resource_updated_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        _same_tenant(self, "entity_definition")
        _same_tenant(self, "schema_version")
        schema_entity_id = (
            EntitySchemaVersion._base_manager.filter(pk=self.schema_version_id, tenant_id=self.tenant_id)
            .values_list("entity_definition_id", flat=True)
            .first()
        )
        if schema_entity_id is not None and schema_entity_id != self.entity_definition_id:
            raise ValidationError({"schema_version": "The schema version must belong to the selected entity."})
        is_submittable = (
            EntityDefinition._base_manager.filter(pk=self.entity_definition_id, tenant_id=self.tenant_id)
            .values_list("is_submittable", flat=True)
            .first()
        )
        if is_submittable is False and self.state != self.State.DRAFT:
            raise ValidationError({"state": "Records for a non-submittable entity must remain draft."})
        if not isinstance(self.data, dict):
            raise ValidationError({"data": "Record data must be an object."})

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Hard deletion is forbidden; use the soft-delete service.", code="hard_delete_forbidden")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.entity_definition.code} · {self.record_key}"


class DynamicResourceVersion(TenantScopedModel):
    """Append-only evidence for each successful dynamic-record mutation."""

    class Operation(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        SUBMIT = "submit", "Submit"
        CANCEL = "cancel", "Cancel"
        DELETE = "delete", "Delete"
        RESTORE = "restore", "Restore"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource = models.ForeignKey(DynamicResource, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    schema_version = models.ForeignKey(EntitySchemaVersion, on_delete=models.PROTECT)
    state = models.CharField(max_length=16, choices=DynamicResource.State.choices)
    record_key = models.CharField(max_length=160)
    display_name = models.CharField(max_length=255)
    data = models.JSONField(blank=True)
    changed_fields = models.JSONField(default=list, blank=True)
    operation = models.CharField(max_length=16, choices=Operation.choices)
    changed_by = models.UUIDField()
    correlation_id = models.CharField(max_length=64, db_index=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "resource", "version"], name="meta_resver_resource_ver_uq"),
            models.CheckConstraint(condition=Q(version__gte=1), name="meta_resver_ver_gte_1_ck"),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "resource", "-version"], name="meta_resver_resource_ver_ix"),
            models.Index(fields=["tenant_id", "operation", "-changed_at"], name="meta_resver_operation_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        _same_tenant(self, "resource")
        _same_tenant(self, "schema_version")
        resource_schema_id = (
            DynamicResource._base_manager.filter(pk=self.resource_id, tenant_id=self.tenant_id)
            .values_list("schema_version_id", flat=True)
            .first()
        )
        if resource_schema_id is not None and resource_schema_id != self.schema_version_id:
            raise ValidationError({"schema_version": "History must use the resource's pinned schema version."})
        if not isinstance(self.changed_fields, list) or any(
            not isinstance(value, str) for value in self.changed_fields
        ):
            raise ValidationError({"changed_fields": "Changed fields must be an array of field keys."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableEvidenceError("Resource history is append-only.", code="append_only")
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ImmutableEvidenceError("Resource history is append-only.", code="append_only")

    def __str__(self) -> str:
        return f"{self.record_key} v{self.version} ({self.operation})"


class NamingSequence(TenantScopedModel, TimestampedModel):
    """Concurrency-safe counter backing configured sequence naming."""

    class ResetPeriod(models.TextChoices):
        NEVER = "never", "Never"
        YEARLY = "yearly", "Yearly"
        MONTHLY = "monthly", "Monthly"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity_definition = models.ForeignKey(EntityDefinition, on_delete=models.PROTECT, related_name="naming_sequences")
    sequence_key = models.SlugField(max_length=100, default="default")
    prefix_template = models.CharField(max_length=120)
    next_value = models.PositiveBigIntegerField(default=1)
    padding = models.PositiveSmallIntegerField(default=5)
    reset_period = models.CharField(max_length=12, choices=ResetPeriod.choices, default=ResetPeriod.NEVER)
    period_key = models.CharField(max_length=10, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["entity_definition", "sequence_key", "period_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "entity_definition", "sequence_key", "period_key"],
                name="meta_sequence_period_uq",
            ),
            models.CheckConstraint(condition=Q(next_value__gte=1), name="meta_sequence_next_gte_1_ck"),
            models.CheckConstraint(condition=Q(padding__gte=1, padding__lte=12), name="meta_sequence_padding_ck"),
        ]

    def clean(self) -> None:
        super().clean()
        _same_tenant(self, "entity_definition")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.entity_definition.code}:{self.sequence_key}:{self.period_key or 'all'}"


def _default_allowed_field_types() -> list[str]:
    return sorted(BUILT_IN_FIELD_TYPES)


def _default_feature_flags() -> dict[str, bool]:
    return {"async_validation": True, "schema_import_export": True, "extension_catalog": True}


def _default_rollout() -> dict[str, dict[str, object]]:
    return {
        "metadata_modeling": {
            "enabled": True,
            "tenant_percentage": 100,
            "roles": [],
            "cohorts": [],
        }
    }


class MetadataModelingConfiguration(TenantScopedModel, TimestampedModel):
    """Versioned, environment-specific runtime policy for the metadata kernel."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.SlugField(max_length=32, default="production")
    version = models.PositiveIntegerField(default=1)
    synchronous_validation_limit = models.PositiveIntegerField(default=100)
    max_fields_per_schema = models.PositiveIntegerField(default=250)
    max_schema_bytes = models.PositiveIntegerField(default=1_048_576)
    max_record_data_bytes = models.PositiveIntegerField(default=1_048_576)
    max_regex_length = models.PositiveIntegerField(default=4096)
    default_page_size = models.PositiveSmallIntegerField(default=25)
    max_page_size = models.PositiveSmallIntegerField(default=100)
    allowed_field_types = models.JSONField(default=_default_allowed_field_types)
    feature_flags = models.JSONField(default=_default_feature_flags)
    rollout = models.JSONField(default=_default_rollout)
    created_by = models.UUIDField(default=UNKNOWN_ACTOR_ID, editable=False)
    updated_by = models.UUIDField(default=UNKNOWN_ACTOR_ID, editable=False)

    class Meta:
        ordering = ["environment"]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "environment"], name="meta_config_tenant_env_uq"),
            models.CheckConstraint(condition=Q(version__gte=1), name="meta_config_ver_gte_1_ck"),
            models.CheckConstraint(
                condition=Q(synchronous_validation_limit__gte=1, synchronous_validation_limit__lte=10000),
                name="meta_config_sync_limit_ck",
            ),
            models.CheckConstraint(
                condition=Q(max_fields_per_schema__gte=1, max_fields_per_schema__lte=1000),
                name="meta_config_fields_limit_ck",
            ),
            models.CheckConstraint(
                condition=Q(max_schema_bytes__gte=1024, max_schema_bytes__lte=10_485_760),
                name="meta_config_schema_bytes_ck",
            ),
            models.CheckConstraint(
                condition=Q(max_record_data_bytes__gte=128, max_record_data_bytes__lte=10_485_760),
                name="meta_config_record_bytes_ck",
            ),
            models.CheckConstraint(
                condition=Q(max_regex_length__gte=1, max_regex_length__lte=4096),
                name="meta_config_regex_limit_ck",
            ),
            models.CheckConstraint(
                condition=Q(default_page_size__gte=1) & Q(default_page_size__lte=models.F("max_page_size")),
                name="meta_config_default_page_ck",
            ),
            models.CheckConstraint(
                condition=Q(max_page_size__gte=1, max_page_size__lte=1000), name="meta_config_max_page_ck"
            ),
        ]
        indexes = [models.Index(fields=["tenant_id", "environment", "-version"], name="meta_config_env_ver_ix")]

    def clean(self) -> None:
        super().clean()
        if (
            not isinstance(self.allowed_field_types, list)
            or not self.allowed_field_types
            or any(not isinstance(value, str) for value in self.allowed_field_types)
            or len(set(self.allowed_field_types)) != len(self.allowed_field_types)
            or not set(self.allowed_field_types).issubset(BUILT_IN_FIELD_TYPES)
        ):
            raise ValidationError({"allowed_field_types": "Allowed field types must be a unique built-in allow-list."})
        if not isinstance(self.feature_flags, dict) or any(
            not isinstance(key, str) or not isinstance(value, bool) for key, value in self.feature_flags.items()
        ):
            raise ValidationError({"feature_flags": "Feature flags must map stable keys to booleans."})
        if not isinstance(self.rollout, dict):
            raise ValidationError({"rollout": "Rollout policy must be an object."})
        if set(self.rollout) == {"percentage"}:
            percentage = self.rollout["percentage"]
            if isinstance(percentage, bool) or not isinstance(percentage, int) or not 0 <= percentage <= 100:
                raise ValidationError({"rollout": "Rollout percentage must be an integer from 0 through 100."})
            self.rollout = {
                "metadata_modeling": {
                    "enabled": True,
                    "tenant_percentage": percentage,
                    "roles": [],
                    "cohorts": [],
                }
            }
        for capability, policy in self.rollout.items():
            if not isinstance(capability, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]*", capability):
                raise ValidationError({"rollout": "Rollout capability keys must be stable slugs."})
            if not isinstance(policy, dict) or set(policy) != {"enabled", "tenant_percentage", "roles", "cohorts"}:
                raise ValidationError({"rollout": "Each rollout requires enabled, tenant_percentage, roles and cohorts."})
            percentage = policy["tenant_percentage"]
            if isinstance(percentage, bool) or not isinstance(percentage, int) or not 0 <= percentage <= 100:
                raise ValidationError({"rollout": "Rollout percentage must be an integer from 0 through 100."})
            if not isinstance(policy["enabled"], bool):
                raise ValidationError({"rollout": "Rollout enabled must be boolean."})
            if any(
                not isinstance(policy[key], list)
                or any(not isinstance(item, str) for item in policy[key])
                for key in ("roles", "cohorts")
            ):
                raise ValidationError({"rollout": "Rollout roles and cohorts must be string arrays."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Metadata modeling configuration ({self.environment}) v{self.version}"


class MetadataConfigurationAudit(TenantScopedModel):
    """Immutable before/after evidence enabling configuration rollback."""

    class Operation(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        ROLLBACK = "rollback", "Rollback"
        IMPORT = "import", "Import"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration = models.ForeignKey(
        MetadataModelingConfiguration, on_delete=models.PROTECT, related_name="audit_history"
    )
    version = models.PositiveIntegerField()
    operation = models.CharField(max_length=16, choices=Operation.choices)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField()
    changed_by = models.UUIDField()
    correlation_id = models.CharField(max_length=64, db_index=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "configuration", "version"], name="meta_cfgaudit_config_ver_uq"
            ),
            models.CheckConstraint(condition=Q(version__gte=1), name="meta_cfgaudit_ver_gte_1_ck"),
        ]
        indexes = [models.Index(fields=["tenant_id", "configuration", "-version"], name="meta_cfgaudit_config_ix")]

    def clean(self) -> None:
        super().clean()
        _same_tenant(self, "configuration")
        if not isinstance(self.before, dict) or not isinstance(self.after, dict):
            raise ValidationError("Configuration audit snapshots must be JSON objects.")

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableEvidenceError("Configuration audit records are immutable.", code="append_only")
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ImmutableEvidenceError("Configuration audit records are immutable.", code="append_only")

    def __str__(self) -> str:
        return f"{self.configuration.environment} configuration v{self.version} ({self.operation})"


__all__ = [
    "BUILT_IN_FIELD_TYPES",
    "DynamicResource",
    "DynamicResourceVersion",
    "EntityDefinition",
    "EntitySchemaVersion",
    "FieldDefinition",
    "ImmutableEvidenceError",
    "MetadataConfigurationAudit",
    "MetadataModelingConfiguration",
    "NamingSequence",
]
