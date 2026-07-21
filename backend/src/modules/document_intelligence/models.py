"""Tenant-safe persistence for document intelligence.

Documents and their bytes remain owned by DMS.  This module deliberately stores
only UUID references that have been validated by the service layer.  The models
below enforce durable invariants as a second line of defence; provider and
cross-module behaviour belongs in :mod:`services` and :mod:`adapters`.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

from src.core.tenancy import TenantScopedModel, TimestampedModel


def generate_uuid() -> str:
    """Return the string UUID required by the immutable legacy migration.

    Migration ``0001_initial`` imports this callable, so it must remain stable
    even though all new domain primary keys use native ``UUIDField`` values.
    """

    return str(uuid.uuid4())


CONFIDENCE_MIN = Decimal("0.0000")
CONFIDENCE_MAX = Decimal("1.0000")


class ExtractionType(models.TextChoices):
    TEXT = "text", "Text"
    STRUCTURED = "structured", "Structured"
    TABLE = "table", "Table"
    ZONE = "zone", "Zone"


class ExtractionStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    NEEDS_REVIEW = "needs_review", "Needs review"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    TIMED_OUT = "timed_out", "Timed out"


class ClassificationStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    TIMED_OUT = "timed_out", "Timed out"


class ClassificationReviewStatus(models.TextChoices):
    NOT_REQUIRED = "not_required", "Not required"
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    CORRECTED = "corrected", "Corrected"


class TrainingStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    TRAINING = "training", "Training"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    TIMED_OUT = "timed_out", "Timed out"


class ModelVersionStatus(models.TextChoices):
    CANDIDATE = "candidate", "Candidate"
    ACTIVE = "active", "Active"
    RETIRED = "retired", "Retired"
    FAILED = "failed", "Failed"


class TemplateStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    RETIRED = "retired", "Retired"


class ZoneType(models.TextChoices):
    TEXT = "text", "Text"
    TABLE = "table", "Table"
    CHECKBOX = "checkbox", "Checkbox"
    BARCODE = "barcode", "Barcode"


class ExpectedDataType(models.TextChoices):
    STRING = "string", "String"
    INTEGER = "integer", "Integer"
    DECIMAL = "decimal", "Decimal"
    DATE = "date", "Date"
    BOOLEAN = "boolean", "Boolean"
    ARRAY = "array", "Array"


class TenantDomainModel(TenantScopedModel, TimestampedModel):
    """Common UUID ownership and audit columns for all eight entities."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.UUIDField(editable=False)

    class Meta:
        abstract = True


class SoftDeletableTenantModel(TenantDomainModel):
    """Archive columns for records whose evidence must be retained."""

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class AppendOnlyTenantModel(TenantDomainModel):
    """Reject application-level mutation of immutable evidence rows."""

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Append-only evidence rows cannot be updated.", code="append_only")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Append-only evidence rows cannot be deleted.", code="append_only")


def _confidence_check(field: str, *, nullable: bool = False) -> models.Q:
    bounded = models.Q(**{f"{field}__gte": CONFIDENCE_MIN, f"{field}__lte": CONFIDENCE_MAX})
    return models.Q(**{f"{field}__isnull": True}) | bounded if nullable else bounded


def _changed_fields(instance: models.Model, field_names: Iterable[str]) -> set[str]:
    """Return persisted fields whose value differs from ``instance``."""

    if instance._state.adding or instance.pk is None:
        return set()
    previous = (
        type(instance)._base_manager.filter(pk=instance.pk, tenant_id=instance.tenant_id).values(*field_names).first()
    )
    if previous is None:
        return set()
    return {name for name in field_names if previous[name] != getattr(instance, name)}


def _require_same_tenant(instance: TenantDomainModel, relation_name: str) -> None:
    relation_id = getattr(instance, f"{relation_name}_id", None)
    if relation_id is None or instance.tenant_id is None:
        return
    field = instance._meta.get_field(relation_name)
    related_model = field.remote_field.model
    if not related_model.objects.for_tenant(instance.tenant_id).filter(pk=relation_id).exists():
        raise ValidationError(
            {relation_name: "The referenced record does not belong to this tenant."},
            code="cross_tenant_reference",
        )


class ExtractionTemplate(SoftDeletableTenantModel):
    """Versioned, provider-neutral configuration for zone extraction."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    document_category = models.CharField(max_length=80, blank=True)
    engine = models.CharField(max_length=50)
    match_threshold = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0.7000"))
    status = models.CharField(max_length=20, choices=TemplateStatus.choices, default=TemplateStatus.DRAFT)
    version = models.PositiveIntegerField(default=1)
    activated_at = models.DateTimeField(null=True, blank=True)
    transition_history = models.JSONField(default=list, editable=False)

    IMMUTABLE_CONTENT_FIELDS = (
        "name",
        "description",
        "document_category",
        "engine",
        "match_threshold",
        "version",
    )

    class Meta:
        db_table = "document_intelligence_extraction_templates"
        constraints = [
            models.CheckConstraint(
                condition=_confidence_check("match_threshold"),
                name="docintel_template_threshold_range",
            ),
            models.CheckConstraint(condition=models.Q(version__gt=0), name="docintel_template_version_gt_zero"),
            models.UniqueConstraint(
                Lower("name"),
                models.F("tenant_id"),
                condition=models.Q(status=TemplateStatus.ACTIVE, is_deleted=False),
                name="docintel_template_active_name_ci_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "status", "name"], name="di_tpl_tenant_status_name"),
            models.Index(
                fields=["tenant_id", "document_category", "status"],
                name="di_tpl_tenant_cat_status",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            previous = type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).values("status").first()
            if previous and previous["status"] in {TemplateStatus.ACTIVE, TemplateStatus.RETIRED}:
                changed = _changed_fields(self, self.IMMUTABLE_CONTENT_FIELDS)
                if changed:
                    raise ValidationError(
                        f"Active or retired template content is immutable: {', '.join(sorted(changed))}.",
                        code="immutable_template",
                    )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} v{self.version}"


class DocumentExtraction(SoftDeletableTenantModel):
    """One durable OCR/extraction attempt against an immutable DMS version."""

    document_id = models.UUIDField()
    document_version_id = models.UUIDField()
    async_job_id = models.UUIDField(db_index=True)
    idempotency_key = models.CharField(max_length=255)
    engine = models.CharField(max_length=50)
    extraction_type = models.CharField(max_length=30, choices=ExtractionType.choices)
    template = models.ForeignKey(
        ExtractionTemplate,
        on_delete=models.PROTECT,
        related_name="extractions",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=24, choices=ExtractionStatus.choices, default=ExtractionStatus.QUEUED)
    raw_text = models.TextField(null=True, blank=True)
    structured_data = models.JSONField(null=True, blank=True)
    table_data = models.JSONField(null=True, blank=True)
    confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    processing_time_ms = models.PositiveIntegerField(null=True, blank=True)
    failure_code = models.CharField(max_length=40, blank=True)
    failure_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    transition_history = models.JSONField(default=list, editable=False)

    RESULT_FIELDS = (
        "status",
        "raw_text",
        "structured_data",
        "table_data",
        "confidence",
        "page_count",
        "processing_time_ms",
        "failure_code",
        "failure_message",
        "started_at",
        "completed_at",
        "document_id",
        "document_version_id",
        "engine",
        "extraction_type",
        "template_id",
    )

    class Meta:
        db_table = "document_intelligence_extractions"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "idempotency_key"], name="docintel_extraction_tenant_idem_uniq"
            ),
            models.CheckConstraint(
                condition=_confidence_check("confidence", nullable=True), name="docintel_extraction_confidence_range"
            ),
            models.CheckConstraint(
                condition=models.Q(page_count__isnull=True) | models.Q(page_count__gt=0),
                name="docintel_extraction_page_count_gt_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(processing_time_ms__isnull=True) | models.Q(processing_time_ms__gte=0),
                name="docintel_extraction_time_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status__in=[ExtractionStatus.COMPLETED, ExtractionStatus.NEEDS_REVIEW])
                    | (
                        models.Q(confidence__isnull=False, page_count__isnull=False, processing_time_ms__isnull=False)
                        & (
                            models.Q(extraction_type=ExtractionType.TEXT, raw_text__isnull=False)
                            | models.Q(
                                extraction_type__in=[ExtractionType.STRUCTURED, ExtractionType.ZONE],
                                structured_data__isnull=False,
                            )
                            | models.Q(extraction_type=ExtractionType.TABLE, table_data__isnull=False)
                        )
                    )
                ),
                name="docintel_extraction_terminal_evidence",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "document_id", "-created_at"], name="di_ext_tenant_doc_created"),
            models.Index(fields=["tenant_id", "status", "-created_at"], name="di_ext_tenant_status_created"),
            models.Index(
                fields=["tenant_id", "extraction_type", "-created_at"],
                name="di_ext_tenant_type_created",
            ),
            models.Index(fields=["tenant_id", "template", "-created_at"], name="di_ext_tenant_tpl_created"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "template")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        if not self._state.adding:
            previous = type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).values("status").first()
            if previous and previous["status"] in {ExtractionStatus.COMPLETED, ExtractionStatus.NEEDS_REVIEW}:
                changed = _changed_fields(self, self.RESULT_FIELDS)
                if changed:
                    raise ValidationError(
                        f"Completed extraction evidence is immutable: {', '.join(sorted(changed))}.",
                        code="immutable_extraction",
                    )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Extraction {self.id} ({self.status})"


class DocumentExtractionPage(AppendOnlyTenantModel):
    """Immutable per-page extraction evidence."""

    extraction = models.ForeignKey(DocumentExtraction, on_delete=models.PROTECT, related_name="pages")
    page_number = models.PositiveIntegerField()
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    raw_text = models.TextField(blank=True)
    # Empty containers are valid evidence for text-only and non-tabular pages.
    # ``blank=True`` keeps model validation aligned with the provider DTO while
    # preserving concrete (never-null) JSON shapes in the database.
    structured_data = models.JSONField(default=dict, blank=True)
    table_data = models.JSONField(default=list, blank=True)
    confidence = models.DecimalField(max_digits=5, decimal_places=4)
    provider_metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "document_intelligence_extraction_pages"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "extraction", "page_number"], name="docintel_page_tenant_ext_number_uniq"
            ),
            models.CheckConstraint(condition=models.Q(page_number__gt=0), name="docintel_page_number_gt_zero"),
            models.CheckConstraint(condition=models.Q(width__gt=0), name="docintel_page_width_gt_zero"),
            models.CheckConstraint(condition=models.Q(height__gt=0), name="docintel_page_height_gt_zero"),
            models.CheckConstraint(condition=_confidence_check("confidence"), name="docintel_page_confidence_range"),
        ]
        indexes = [models.Index(fields=["tenant_id", "extraction", "page_number"], name="di_page_tenant_ext_num")]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "extraction")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        super().save(*args, **kwargs)


class ClassifierTrainingJob(TenantDomainModel):
    """Permanent evidence for one tenant-specific classifier training run."""

    async_job_id = models.UUIDField(db_index=True)
    idempotency_key = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    training_items = models.JSONField()
    training_data_count = models.PositiveIntegerField()
    category_counts = models.JSONField()
    requested_version = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=TrainingStatus.choices, default=TrainingStatus.QUEUED)
    accuracy = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    failure_code = models.CharField(max_length=40, blank=True)
    failure_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    transition_history = models.JSONField(default=list, editable=False)

    class Meta:
        db_table = "document_intelligence_classifier_training_jobs"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "idempotency_key"], name="docintel_training_tenant_idem_uniq"),
            models.UniqueConstraint(
                fields=["tenant_id", "requested_version"], name="docintel_training_tenant_version_uniq"
            ),
            models.UniqueConstraint(
                fields=["tenant_id"],
                condition=models.Q(status__in=[TrainingStatus.QUEUED, TrainingStatus.TRAINING]),
                name="docintel_training_one_active_per_tenant",
            ),
            models.CheckConstraint(
                condition=models.Q(training_data_count__gte=50), name="docintel_training_minimum_count"
            ),
            models.CheckConstraint(
                condition=_confidence_check("accuracy", nullable=True), name="docintel_training_accuracy_range"
            ),
        ]
        indexes = [models.Index(fields=["tenant_id", "status", "-created_at"], name="di_train_tenant_status_created")]

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.training_items, list):
            raise ValidationError({"training_items": "Training items must be an array."})
        if not isinstance(self.category_counts, dict) or not self.category_counts:
            raise ValidationError({"category_counts": "Category counts must be a non-empty object."})
        invalid_counts = [
            category
            for category, count in self.category_counts.items()
            if not isinstance(category, str)
            or not category
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count < 5
        ]
        if invalid_counts:
            raise ValidationError({"category_counts": "Every represented category must contain at least five items."})
        if sum(self.category_counts.values()) != self.training_data_count:
            raise ValidationError({"category_counts": "Category counts must equal training_data_count."})
        if len(self.training_items) != self.training_data_count:
            raise ValidationError({"training_items": "Training item count must equal training_data_count."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Training evidence is retained permanently.", code="permanent_evidence")

    def __str__(self) -> str:
        return f"{self.name} ({self.requested_version})"


class ClassifierModelVersion(TenantDomainModel):
    """Immutable classifier artifact identity and activation lifecycle."""

    version = models.CharField(max_length=50)
    provider_key = models.CharField(max_length=80)
    artifact_ref = models.CharField(max_length=500)
    artifact_checksum = models.CharField(
        max_length=64,
        validators=[RegexValidator(r"^[0-9a-f]{64}$", "Checksum must be a lowercase SHA-256 digest.")],
    )
    training_job = models.ForeignKey(ClassifierTrainingJob, on_delete=models.PROTECT, related_name="model_versions")
    accuracy = models.DecimalField(max_digits=5, decimal_places=4)
    status = models.CharField(max_length=20, choices=ModelVersionStatus.choices, default=ModelVersionStatus.CANDIDATE)
    activated_by = models.UUIDField(null=True, blank=True, editable=False)
    activated_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)
    transition_history = models.JSONField(default=list, editable=False)

    IMMUTABLE_ARTIFACT_FIELDS = (
        "version",
        "provider_key",
        "artifact_ref",
        "artifact_checksum",
        "training_job_id",
        "accuracy",
    )

    class Meta:
        db_table = "document_intelligence_classifier_model_versions"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "version"], name="docintel_model_tenant_version_uniq"),
            models.UniqueConstraint(
                fields=["tenant_id"],
                condition=models.Q(status=ModelVersionStatus.ACTIVE),
                name="docintel_model_one_active_per_tenant",
            ),
            models.CheckConstraint(condition=_confidence_check("accuracy"), name="docintel_model_accuracy_range"),
        ]
        indexes = [models.Index(fields=["tenant_id", "status", "-created_at"], name="di_model_tenant_status_created")]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "training_job")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        changed = _changed_fields(self, self.IMMUTABLE_ARTIFACT_FIELDS)
        if changed:
            raise ValidationError(
                f"Classifier artifact evidence is immutable: {', '.join(sorted(changed))}.",
                code="immutable_model_artifact",
            )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Classifier model versions cannot be deleted.", code="permanent_evidence")

    def __str__(self) -> str:
        return f"Model {self.version} ({self.status})"


class DocumentClassification(SoftDeletableTenantModel):
    """Immutable classifier inference plus separately mutable review evidence."""

    document_id = models.UUIDField()
    document_version_id = models.UUIDField()
    async_job_id = models.UUIDField(db_index=True)
    idempotency_key = models.CharField(max_length=255)
    model_version = models.ForeignKey(ClassifierModelVersion, on_delete=models.PROTECT, related_name="classifications")
    status = models.CharField(max_length=24, choices=ClassificationStatus.choices, default=ClassificationStatus.QUEUED)
    category = models.CharField(max_length=80, null=True, blank=True)
    confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    secondary_category = models.CharField(max_length=80, blank=True)
    secondary_confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    needs_review = models.BooleanField(default=False)
    review_status = models.CharField(
        max_length=20,
        choices=ClassificationReviewStatus.choices,
        default=ClassificationReviewStatus.NOT_REQUIRED,
    )
    reviewed_category = models.CharField(max_length=80, blank=True)
    reviewed_by = models.UUIDField(null=True, blank=True, editable=False)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    processing_time_ms = models.PositiveIntegerField(null=True, blank=True)
    failure_code = models.CharField(max_length=40, blank=True)
    failure_message = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    transition_history = models.JSONField(default=list, editable=False)

    INFERENCE_FIELDS = (
        "status",
        "document_id",
        "document_version_id",
        "model_version_id",
        "category",
        "confidence",
        "secondary_category",
        "secondary_confidence",
        "processing_time_ms",
        "failure_code",
        "failure_message",
        "completed_at",
    )

    class Meta:
        db_table = "document_intelligence_classifications"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "idempotency_key"], name="docintel_classification_tenant_idem_uniq"
            ),
            models.CheckConstraint(
                condition=_confidence_check("confidence", nullable=True),
                name="docintel_classification_confidence_range",
            ),
            models.CheckConstraint(
                condition=_confidence_check("secondary_confidence", nullable=True),
                name="docintel_classification_secondary_range",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(secondary_category="", secondary_confidence__isnull=True)
                    | (models.Q(secondary_category__gt="") & models.Q(secondary_confidence__gt=Decimal("0.3000")))
                ),
                name="docintel_classification_secondary_pair",
            ),
            models.CheckConstraint(
                condition=models.Q(processing_time_ms__isnull=True) | models.Q(processing_time_ms__gte=0),
                name="docintel_classification_time_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=ClassificationStatus.COMPLETED)
                    | models.Q(category__isnull=False, confidence__isnull=False, processing_time_ms__isnull=False)
                ),
                name="docintel_classification_completed_evidence",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=ClassificationStatus.COMPLETED, confidence__lt=Decimal("0.5000"))
                    | models.Q(
                        needs_review=True,
                        review_status__in=[
                            ClassificationReviewStatus.PENDING,
                            ClassificationReviewStatus.CONFIRMED,
                            ClassificationReviewStatus.CORRECTED,
                        ],
                    )
                ),
                name="docintel_classification_low_conf_review",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "document_id", "-created_at"], name="di_cls_tenant_doc_created"),
            models.Index(fields=["tenant_id", "status", "-created_at"], name="di_cls_tenant_status_created"),
            models.Index(fields=["tenant_id", "category", "-created_at"], name="di_cls_tenant_cat_created"),
            models.Index(
                fields=["tenant_id", "needs_review", "review_status", "created_at"],
                name="di_cls_tenant_review_created",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "model_version")
        if (
            self.status == ClassificationStatus.COMPLETED
            and self.confidence is not None
            and self.confidence < Decimal("0.5000")
        ):
            previous = None
            if not self._state.adding:
                previous = (
                    type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).values("status").first()
                )
            if not self.needs_review or (
                (previous is None or previous["status"] != ClassificationStatus.COMPLETED)
                and self.review_status != ClassificationReviewStatus.PENDING
            ):
                raise ValidationError(
                    {"review_status": "New low-confidence classifications must enter pending review."}
                )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        if not self._state.adding:
            previous = type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).values("status").first()
            if previous and previous["status"] == ClassificationStatus.COMPLETED:
                changed = _changed_fields(self, self.INFERENCE_FIELDS)
                if changed:
                    raise ValidationError(
                        f"Completed classifier inference is immutable: {', '.join(sorted(changed))}.",
                        code="immutable_classification",
                    )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Classification {self.id} ({self.status})"


class DocumentClassificationScore(AppendOnlyTenantModel):
    """Immutable ordered category confidence for one classification."""

    classification = models.ForeignKey(DocumentClassification, on_delete=models.PROTECT, related_name="scores")
    category = models.CharField(max_length=80)
    confidence = models.DecimalField(max_digits=5, decimal_places=4)
    rank = models.PositiveIntegerField()

    class Meta:
        db_table = "document_intelligence_classification_scores"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "classification", "category"],
                name="docintel_score_tenant_cls_category_uniq",
            ),
            models.UniqueConstraint(
                fields=["tenant_id", "classification", "rank"], name="docintel_score_tenant_cls_rank_uniq"
            ),
            models.CheckConstraint(condition=models.Q(rank__gt=0), name="docintel_score_rank_gt_zero"),
            models.CheckConstraint(condition=_confidence_check("confidence"), name="docintel_score_confidence_range"),
        ]
        indexes = [models.Index(fields=["tenant_id", "classification", "rank"], name="di_score_tenant_cls_rank")]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "classification")
        if self.rank == 1 and self.classification_id:
            classification = (
                DocumentClassification.objects.for_tenant(self.tenant_id)
                .filter(pk=self.classification_id)
                .only("category", "confidence")
                .first()
            )
            if classification and (
                classification.category != self.category or classification.confidence != self.confidence
            ):
                raise ValidationError("Rank-one score must match the primary classification.", code="primary_mismatch")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        super().save(*args, **kwargs)


class ExtractionTemplateZone(SoftDeletableTenantModel):
    """Normalized rectangle and output mapping owned by a template revision."""

    template = models.ForeignKey(ExtractionTemplate, on_delete=models.PROTECT, related_name="zones")
    zone_name = models.CharField(max_length=100)
    extraction_key = models.CharField(max_length=100)
    zone_type = models.CharField(max_length=30, choices=ZoneType.choices)
    x = models.DecimalField(max_digits=8, decimal_places=4)
    y = models.DecimalField(max_digits=8, decimal_places=4)
    width = models.DecimalField(max_digits=8, decimal_places=4)
    height = models.DecimalField(max_digits=8, decimal_places=4)
    page_number = models.PositiveIntegerField(default=1)
    expected_data_type = models.CharField(max_length=30, choices=ExpectedDataType.choices)
    is_required = models.BooleanField(default=False)

    class Meta:
        db_table = "document_intelligence_extraction_template_zones"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "template", "zone_name"], name="docintel_zone_tenant_tpl_name_uniq"
            ),
            models.UniqueConstraint(
                fields=["tenant_id", "template", "extraction_key"], name="docintel_zone_tenant_tpl_key_uniq"
            ),
            models.CheckConstraint(condition=models.Q(x__gte=0), name="docintel_zone_x_nonnegative"),
            models.CheckConstraint(condition=models.Q(y__gte=0), name="docintel_zone_y_nonnegative"),
            models.CheckConstraint(condition=models.Q(width__gt=0), name="docintel_zone_width_positive"),
            models.CheckConstraint(condition=models.Q(height__gt=0), name="docintel_zone_height_positive"),
            models.CheckConstraint(condition=models.Q(x__lte=models.F("width") * -1 + 1), name="docintel_zone_x_bound"),
            models.CheckConstraint(
                condition=models.Q(y__lte=models.F("height") * -1 + 1), name="docintel_zone_y_bound"
            ),
            models.CheckConstraint(condition=models.Q(page_number__gt=0), name="docintel_zone_page_gt_zero"),
        ]
        indexes = [models.Index(fields=["tenant_id", "template", "page_number"], name="di_zone_tenant_tpl_page")]

    def clean(self) -> None:
        super().clean()
        _require_same_tenant(self, "template")
        if not self.template_id or self.tenant_id is None:
            return
        template = ExtractionTemplate.objects.for_tenant(self.tenant_id).filter(pk=self.template_id).first()
        if template is None:
            return
        if template.status not in {TemplateStatus.DRAFT, TemplateStatus.INACTIVE}:
            raise ValidationError({"template": "Zones can only be changed on draft or inactive templates."})
        if None not in (self.x, self.y, self.width, self.height):
            overlaps = (
                type(self)
                .objects.for_tenant(self.tenant_id)
                .filter(
                    template_id=self.template_id,
                    page_number=self.page_number,
                    is_deleted=False,
                    x__lt=self.x + self.width,
                    y__lt=self.y + self.height,
                    x__gt=self.x - models.F("width"),
                    y__gt=self.y - models.F("height"),
                )
            )
            if self.pk:
                overlaps = overlaps.exclude(pk=self.pk)
            if overlaps.exists():
                raise ValidationError("Template zones on the same page cannot overlap.", code="zone_overlap")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.template_id:
            template = ExtractionTemplate.objects.for_tenant(self.tenant_id).filter(pk=self.template_id).first()
            if template and template.status not in {TemplateStatus.DRAFT, TemplateStatus.INACTIVE}:
                raise ValidationError(
                    "Zones can only be changed on draft or inactive templates.", code="immutable_template"
                )
        return super().delete(*args, **kwargs)
