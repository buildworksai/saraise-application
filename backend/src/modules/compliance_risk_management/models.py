"""Tenant-safe persistence for compliance risk management.

Business workflows and configured scoring rules live in :mod:`services`.  This
module is the database-facing last line of defence: ownership, lifecycle enum,
relationship, conditional-field, uniqueness, soft-deletion, and immutable
history invariants are enforced here as well as in migrations.
"""

from __future__ import annotations

import uuid
import datetime as dt
from numbers import Real
from typing import Any

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import F, Q

from src.core.tenancy import TenantQuerySet, TenantScopedModel, TimestampedModel


def generate_uuid() -> str:
    """Compatibility callable retained for the immutable legacy migration."""

    return str(uuid.uuid4())


def default_level_thresholds() -> dict[str, int]:
    """Return inclusive upper bounds for the default five-by-five matrix."""

    return {"negligible": 1, "low": 4, "medium": 9, "high": 16, "critical": 25}


def default_reminder_days() -> list[int]:
    """Return an independent default reminder schedule for each row."""

    return [30, 14, 7, 1]


class RiskCategory(models.TextChoices):
    OPERATIONAL = "operational", "Operational"
    FINANCIAL = "financial", "Financial"
    COMPLIANCE = "compliance", "Compliance"
    STRATEGIC = "strategic", "Strategic"
    TECHNOLOGY = "technology", "Technology"
    REPUTATIONAL = "reputational", "Reputational"


class RiskLevel(models.TextChoices):
    NEGLIGIBLE = "negligible", "Negligible"
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class RiskStatus(models.TextChoices):
    IDENTIFIED = "identified", "Identified"
    ASSESSED = "assessed", "Assessed"
    MITIGATING = "mitigating", "Mitigating"
    ACCEPTED = "accepted", "Accepted"
    CLOSED = "closed", "Closed"


class ControlFrequency(models.TextChoices):
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    MONTHLY = "monthly", "Monthly"
    QUARTERLY = "quarterly", "Quarterly"
    ANNUALLY = "annually", "Annually"
    CUSTOM = "custom", "Custom"


class ControlStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    RETIRED = "retired", "Retired"


class ControlTestResult(models.TextChoices):
    NOT_TESTED = "not_tested", "Not tested"
    PASSED = "passed", "Passed"
    FAILED = "failed", "Failed"
    PARTIALLY_PASSED = "partially_passed", "Partially passed"


class ControlTestStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    IN_PROGRESS = "in_progress", "In progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class RequirementApplicability(models.TextChoices):
    MANDATORY = "mandatory", "Mandatory"
    CONDITIONAL = "conditional", "Conditional"
    RECOMMENDED = "recommended", "Recommended"


class RequirementStatus(models.TextChoices):
    NOT_ASSESSED = "not_assessed", "Not assessed"
    COMPLIANT = "compliant", "Compliant"
    PARTIALLY_COMPLIANT = "partially_compliant", "Partially compliant"
    NON_COMPLIANT = "non_compliant", "Non-compliant"


class CalendarEventType(models.TextChoices):
    DEADLINE = "deadline", "Deadline"
    REVIEW = "review", "Review"
    SUBMISSION = "submission", "Submission"
    AUDIT = "audit", "Audit"
    RENEWAL = "renewal", "Renewal"


class CalendarEntryStatus(models.TextChoices):
    UPCOMING = "upcoming", "Upcoming"
    OVERDUE = "overdue", "Overdue"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class RemediationPriority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class RemediationStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    IN_PROGRESS = "in_progress", "In progress"
    OVERDUE = "overdue", "Overdue"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class ConfigurationEnvironment(models.TextChoices):
    DEVELOPMENT = "development", "Development"
    STAGING = "staging", "Staging"
    PRODUCTION = "production", "Production"


class HardDeleteForbidden(ValidationError):
    """Raised when application code attempts to bypass soft deletion."""


class AppendOnlyViolation(ValidationError):
    """Raised when immutable compliance evidence is changed or removed."""


class MutableDomainQuerySet(TenantQuerySet):
    """Keep bulk callers from bypassing service-owned soft deletion."""

    def delete(self) -> tuple[int, dict[str, int]]:
        raise HardDeleteForbidden(
            "Hard deletion is forbidden; use the tenant-scoped soft-delete service.",
            code="hard_delete_forbidden",
        )


class MutableDomainModel(TenantScopedModel, TimestampedModel):
    """Shared audit and lifecycle columns for mutable tenant aggregates."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by_id = models.UUIDField(db_index=True, editable=False)
    updated_by_id = models.UUIDField(null=True, blank=True, db_index=True, editable=False)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_by_id = models.UUIDField(null=True, blank=True, editable=False)
    transition_history = models.JSONField(default=list, blank=True, editable=False)

    objects = MutableDomainQuerySet.as_manager()

    class Meta:
        abstract = True

    def clean(self) -> None:
        super().clean()
        deletion_metadata_complete = self.deleted_at is not None and self.deleted_by_id is not None
        deletion_metadata_absent = self.deleted_at is None and self.deleted_by_id is None
        if (self.is_deleted and not deletion_metadata_complete) or (
            not self.is_deleted and not deletion_metadata_absent
        ):
            raise ValidationError(
                {"is_deleted": "Deletion time and actor must be set together."},
                code="invalid_soft_delete",
            )
        if not isinstance(self.transition_history, list):
            raise ValidationError(
                {"transition_history": "Transition history must be an array."},
                code="invalid_transition_history",
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise HardDeleteForbidden(
            "Hard deletion is forbidden; use the tenant-scoped soft-delete service.",
            code="hard_delete_forbidden",
        )


def _validate_same_tenant(instance: TenantScopedModel, relation_name: str) -> None:
    relation_id = getattr(instance, f"{relation_name}_id", None)
    if relation_id is None or not instance.tenant_id:
        return
    related_model = instance._meta.get_field(relation_name).remote_field.model
    if not related_model.objects.for_tenant(instance.tenant_id).filter(pk=relation_id).exists():
        raise ValidationError(
            {relation_name: "The referenced record must belong to the same tenant."},
            code="cross_tenant_reference",
        )


def _validate_evidence_shape(evidence: Any, field_name: str) -> None:
    if not isinstance(evidence, list):
        raise ValidationError({field_name: "Evidence must be an array."}, code="invalid_evidence")
    required = {"document_id", "version_id", "label", "checksum"}
    for index, item in enumerate(evidence):
        if not isinstance(item, dict) or set(item) != required:
            raise ValidationError(
                {field_name: f"Evidence item {index} must contain exactly {sorted(required)}."},
                code="invalid_evidence",
            )
        identifiers_valid = all(
            isinstance(item[key], uuid.UUID) or (isinstance(item[key], str) and bool(item[key].strip()))
            for key in ("document_id", "version_id")
        )
        text_valid = all(isinstance(item[key], str) and bool(item[key].strip()) for key in ("label", "checksum"))
        if not identifiers_valid or not text_valid:
            raise ValidationError(
                {field_name: f"Evidence item {index} contains an invalid identifier or text value."},
                code="invalid_evidence",
            )
        item["document_id"] = str(item["document_id"])
        item["version_id"] = str(item["version_id"])


class RiskAssessment(MutableDomainModel):
    """A tenant-owned, scored compliance risk aggregate."""

    risk_code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=32, choices=RiskCategory.choices)
    description = models.TextField()
    likelihood = models.PositiveSmallIntegerField()
    impact = models.PositiveSmallIntegerField()
    inherent_score = models.DecimalField(max_digits=7, decimal_places=2, editable=False)
    residual_likelihood = models.PositiveSmallIntegerField(null=True, blank=True)
    residual_impact = models.PositiveSmallIntegerField(null=True, blank=True)
    residual_score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True, editable=False)
    risk_level = models.CharField(max_length=20, choices=RiskLevel.choices, editable=False)
    qualitative_rationale = models.TextField(blank=True)
    mitigation_strategy = models.TextField(blank=True)
    owner_id = models.UUIDField(db_index=True)
    review_date = models.DateField()
    status = models.CharField(max_length=20, choices=RiskStatus.choices, default=RiskStatus.IDENTIFIED, editable=False)
    accepted_until = models.DateField(null=True, blank=True, editable=False)
    closed_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "compliance_risks"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "risk_code"), condition=Q(is_deleted=False), name="crm_risk_live_code_uniq"
            ),
            models.CheckConstraint(condition=Q(category__in=RiskCategory.values), name="crm_risk_category_ck"),
            models.CheckConstraint(condition=Q(risk_level__in=RiskLevel.values), name="crm_risk_level_ck"),
            models.CheckConstraint(condition=Q(status__in=RiskStatus.values), name="crm_risk_status_ck"),
            models.CheckConstraint(condition=Q(likelihood__gte=1, impact__gte=1), name="crm_risk_scores_positive_ck"),
            models.CheckConstraint(
                condition=(
                    Q(residual_likelihood__isnull=True, residual_impact__isnull=True, residual_score__isnull=True)
                    | Q(residual_likelihood__isnull=False, residual_impact__isnull=False, residual_score__isnull=False)
                ),
                name="crm_risk_residual_pair_ck",
            ),
            models.CheckConstraint(
                condition=Q(residual_score__isnull=True)
                | Q(residual_score__lte=F("inherent_score"))
                | ~Q(qualitative_rationale=""),
                name="crm_risk_residual_override_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=RiskStatus.ACCEPTED, accepted_until__isnull=False, closed_at__isnull=True)
                    | Q(status=RiskStatus.CLOSED, accepted_until__isnull=True, closed_at__isnull=False)
                    | Q(
                        status__in=[RiskStatus.IDENTIFIED, RiskStatus.ASSESSED, RiskStatus.MITIGATING],
                        accepted_until__isnull=True,
                        closed_at__isnull=True,
                    )
                ),
                name="crm_risk_lifecycle_fields_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_deleted=False, deleted_at__isnull=True, deleted_by_id__isnull=True)
                    | Q(is_deleted=True, deleted_at__isnull=False, deleted_by_id__isnull=False)
                ),
                name="crm_risk_soft_delete_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "review_date"), name="crm_risk_status_review_idx"),
            models.Index(fields=("tenant_id", "risk_level", "status"), name="crm_risk_level_status_idx"),
            models.Index(fields=("tenant_id", "category", "status"), name="crm_risk_category_status_idx"),
            models.Index(fields=("tenant_id", "owner_id", "status"), name="crm_risk_owner_status_idx"),
            models.Index(fields=("tenant_id", "created_at"), name="crm_risk_created_idx"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.risk_code = self.risk_code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.risk_code} - {self.name}"


class Control(MutableDomainModel):
    risk = models.ForeignKey(RiskAssessment, on_delete=models.PROTECT, related_name="controls")
    control_code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    description = models.TextField()
    test_procedure = models.TextField()
    frequency = models.CharField(max_length=20, choices=ControlFrequency.choices)
    frequency_days = models.PositiveIntegerField(null=True, blank=True)
    owner_id = models.UUIDField(db_index=True)
    default_tester_id = models.UUIDField(null=True, blank=True, db_index=True)
    next_test_due = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=ControlStatus.choices, default=ControlStatus.DRAFT, editable=False)

    class Meta:
        db_table = "compliance_risk_controls"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "control_code"), condition=Q(is_deleted=False), name="crm_control_live_code_uniq"
            ),
            models.CheckConstraint(condition=Q(frequency__in=ControlFrequency.values), name="crm_control_frequency_ck"),
            models.CheckConstraint(condition=Q(status__in=ControlStatus.values), name="crm_control_status_ck"),
            models.CheckConstraint(
                condition=(
                    Q(frequency=ControlFrequency.CUSTOM, frequency_days__gte=1, frequency_days__lte=3660)
                    | (~Q(frequency=ControlFrequency.CUSTOM) & Q(frequency_days__isnull=True))
                ),
                name="crm_control_frequency_days_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status=ControlStatus.ACTIVE) | Q(next_test_due__isnull=False),
                name="crm_control_active_due_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_deleted=False, deleted_at__isnull=True, deleted_by_id__isnull=True)
                    | Q(is_deleted=True, deleted_at__isnull=False, deleted_by_id__isnull=False)
                ),
                name="crm_control_soft_delete_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "risk", "status"), name="crm_control_risk_status_idx"),
            models.Index(fields=("tenant_id", "status", "next_test_due"), name="crm_control_status_due_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_same_tenant(self, "risk")
        if self.frequency == ControlFrequency.CUSTOM:
            if self.frequency_days is None or not 1 <= self.frequency_days <= 3660:
                raise ValidationError(
                    {"frequency_days": "Custom frequency requires a value from 1 through 3660."},
                    code="invalid_custom_frequency",
                )
        elif self.frequency_days is not None:
            raise ValidationError(
                {"frequency_days": "Frequency days must be empty unless frequency is custom."},
                code="unexpected_frequency_days",
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.control_code = self.control_code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.control_code} - {self.name}"


class ControlTestQuerySet(TenantQuerySet):
    """Prevent bulk paths from rewriting terminal execution evidence."""

    def update(self, **kwargs: Any) -> int:
        if self.filter(status__in=[ControlTestStatus.COMPLETED, ControlTestStatus.CANCELLED]).exists():
            raise AppendOnlyViolation("Terminal control tests are immutable.", code="terminal_test")
        return super().update(**kwargs)

    def delete(self) -> tuple[int, dict[str, int]]:
        raise AppendOnlyViolation("Control tests cannot be deleted.", code="immutable_test")


class ControlTest(MutableDomainModel):
    control = models.ForeignKey(Control, on_delete=models.PROTECT, related_name="tests")
    scheduled_for = models.DateField()
    started_at = models.DateTimeField(null=True, blank=True, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)
    tester_id = models.UUIDField(db_index=True)
    result = models.CharField(
        max_length=24, choices=ControlTestResult.choices, default=ControlTestResult.NOT_TESTED, editable=False
    )
    findings = models.TextField(blank=True)
    evidence = models.JSONField(default=list, blank=True, encoder=DjangoJSONEncoder)
    status = models.CharField(
        max_length=20, choices=ControlTestStatus.choices, default=ControlTestStatus.SCHEDULED, editable=False
    )
    cancellation_reason = models.TextField(blank=True)

    objects = ControlTestQuerySet.as_manager()

    class Meta:
        db_table = "compliance_risk_control_tests"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "control", "scheduled_for"), name="crm_test_control_schedule_uniq"
            ),
            models.CheckConstraint(condition=Q(result__in=ControlTestResult.values), name="crm_test_result_ck"),
            models.CheckConstraint(condition=Q(status__in=ControlTestStatus.values), name="crm_test_status_ck"),
            models.CheckConstraint(
                condition=(
                    Q(
                        status=ControlTestStatus.SCHEDULED,
                        started_at__isnull=True,
                        completed_at__isnull=True,
                        result=ControlTestResult.NOT_TESTED,
                        cancellation_reason="",
                    )
                    | Q(
                        status=ControlTestStatus.IN_PROGRESS,
                        started_at__isnull=False,
                        completed_at__isnull=True,
                        result=ControlTestResult.NOT_TESTED,
                        cancellation_reason="",
                    )
                    | (
                        Q(
                            status=ControlTestStatus.COMPLETED,
                            started_at__isnull=False,
                            completed_at__isnull=False,
                            cancellation_reason="",
                        )
                        & ~Q(result=ControlTestResult.NOT_TESTED)
                    )
                    | (
                        Q(
                            status=ControlTestStatus.CANCELLED,
                            completed_at__isnull=False,
                            result=ControlTestResult.NOT_TESTED,
                        )
                        & ~Q(cancellation_reason="")
                    )
                ),
                name="crm_test_lifecycle_ck",
            ),
            models.CheckConstraint(
                condition=~Q(result__in=[ControlTestResult.FAILED, ControlTestResult.PARTIALLY_PASSED])
                | ~Q(findings=""),
                name="crm_test_findings_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_deleted=False, deleted_at__isnull=True, deleted_by_id__isnull=True)
                    | Q(is_deleted=True, deleted_at__isnull=False, deleted_by_id__isnull=False)
                ),
                name="crm_test_soft_delete_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "scheduled_for"), name="crm_test_status_schedule_idx"),
            models.Index(fields=("tenant_id", "control", "completed_at"), name="crm_test_control_done_idx"),
            models.Index(fields=("tenant_id", "tester_id", "status"), name="crm_test_tester_status_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_same_tenant(self, "control")
        _validate_evidence_shape(self.evidence, "evidence")

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding and self.pk:
            previous = type(self).objects.filter(pk=self.pk).values("status").first()
            if previous and previous["status"] in {ControlTestStatus.COMPLETED, ControlTestStatus.CANCELLED}:
                raise AppendOnlyViolation("Terminal control tests are immutable.", code="terminal_test")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise AppendOnlyViolation("Control tests cannot be deleted.", code="immutable_test")

    def __str__(self) -> str:
        return f"{self.control_id} @ {self.scheduled_for}"


class ComplianceRequirement(MutableDomainModel):
    regulation_code = models.CharField(max_length=50)
    requirement_code = models.CharField(max_length=80)
    regulation_name = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    description = models.TextField()
    applicability = models.CharField(max_length=20, choices=RequirementApplicability.choices)
    applicability_rationale = models.TextField(blank=True)
    status = models.CharField(
        max_length=24, choices=RequirementStatus.choices, default=RequirementStatus.NOT_ASSESSED, editable=False
    )
    owner_id = models.UUIDField(db_index=True)
    effective_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    last_assessed_at = models.DateTimeField(null=True, blank=True, editable=False)
    source_url = models.URLField(max_length=2048, blank=True)
    cross_references = models.JSONField(default=list, blank=True, encoder=DjangoJSONEncoder)

    class Meta:
        db_table = "compliance_risk_requirements"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "regulation_code", "requirement_code"),
                condition=Q(is_deleted=False),
                name="crm_req_live_code_uniq",
            ),
            models.CheckConstraint(
                condition=Q(applicability__in=RequirementApplicability.values), name="crm_req_applicability_ck"
            ),
            models.CheckConstraint(condition=Q(status__in=RequirementStatus.values), name="crm_req_status_ck"),
            models.CheckConstraint(
                condition=~Q(applicability=RequirementApplicability.CONDITIONAL) | ~Q(applicability_rationale=""),
                name="crm_req_conditional_reason_ck",
            ),
            models.CheckConstraint(
                condition=Q(effective_date__isnull=True)
                | Q(due_date__isnull=True)
                | Q(due_date__gte=F("effective_date")),
                name="crm_req_date_order_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_deleted=False, deleted_at__isnull=True, deleted_by_id__isnull=True)
                    | Q(is_deleted=True, deleted_at__isnull=False, deleted_by_id__isnull=False)
                ),
                name="crm_req_soft_delete_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "due_date"), name="crm_req_status_due_idx"),
            models.Index(fields=("tenant_id", "regulation_code", "applicability"), name="crm_req_reg_app_idx"),
            models.Index(fields=("tenant_id", "owner_id", "status"), name="crm_req_owner_status_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if (
            self.applicability == RequirementApplicability.CONDITIONAL
            and not self.applicability_rationale.strip()
        ):
            raise ValidationError(
                {"applicability_rationale": "Conditional applicability requires a rationale."},
                code="conditional_rationale_required",
            )
        if self.effective_date and self.due_date and self.due_date < self.effective_date:
            raise ValidationError(
                {"due_date": "Due date must be on or after the effective date."},
                code="invalid_date_order",
            )
        if not isinstance(self.cross_references, list):
            raise ValidationError(
                {"cross_references": "Cross-references must be an array."}, code="invalid_cross_references"
            )
        normalized: list[str] = []
        for value in self.cross_references:
            try:
                reference_id = uuid.UUID(str(value))
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValidationError(
                    {"cross_references": "Every cross-reference must be a UUID."}, code="invalid_cross_references"
                ) from exc
            if self.pk and reference_id == self.pk:
                raise ValidationError(
                    {"cross_references": "A requirement cannot reference itself."}, code="self_reference"
                )
            normalized.append(str(reference_id))
        if len(normalized) != len(set(normalized)):
            raise ValidationError(
                {"cross_references": "Cross-references must be unique."}, code="duplicate_cross_reference"
            )
        if normalized:
            found = set(
                type(self).objects.for_tenant(self.tenant_id).filter(pk__in=normalized).values_list("id", flat=True)
            )
            if found != {uuid.UUID(value) for value in normalized}:
                raise ValidationError(
                    {"cross_references": "Every referenced requirement must belong to the same tenant."},
                    code="cross_tenant_reference",
                )
        self.cross_references = normalized

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.regulation_code = self.regulation_code.strip().upper()
        self.requirement_code = self.requirement_code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.regulation_code}/{self.requirement_code} - {self.title}"


class ComplianceCalendarEntry(MutableDomainModel):
    requirement = models.ForeignKey(ComplianceRequirement, on_delete=models.PROTECT, related_name="calendar_entries")
    title = models.CharField(max_length=255)
    event_type = models.CharField(max_length=20, choices=CalendarEventType.choices)
    scheduled_date = models.DateField()
    reminder_days = models.JSONField(default=list, blank=True)
    assigned_to_id = models.UUIDField(db_index=True)
    status = models.CharField(
        max_length=20, choices=CalendarEntryStatus.choices, default=CalendarEntryStatus.UPCOMING, editable=False
    )
    completed_date = models.DateField(null=True, blank=True, editable=False)
    completion_notes = models.TextField(blank=True)

    class Meta:
        db_table = "compliance_risk_calendar_entries"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "requirement", "event_type", "scheduled_date", "title"),
                name="crm_calendar_event_uniq",
            ),
            models.CheckConstraint(condition=Q(event_type__in=CalendarEventType.values), name="crm_calendar_type_ck"),
            models.CheckConstraint(condition=Q(status__in=CalendarEntryStatus.values), name="crm_calendar_status_ck"),
            models.CheckConstraint(
                condition=(
                    Q(status=CalendarEntryStatus.COMPLETED, completed_date__isnull=False)
                    | Q(
                        status__in=[
                            CalendarEntryStatus.UPCOMING,
                            CalendarEntryStatus.OVERDUE,
                            CalendarEntryStatus.CANCELLED,
                        ],
                        completed_date__isnull=True,
                    )
                ),
                name="crm_calendar_completion_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_deleted=False, deleted_at__isnull=True, deleted_by_id__isnull=True)
                    | Q(is_deleted=True, deleted_at__isnull=False, deleted_by_id__isnull=False)
                ),
                name="crm_calendar_soft_delete_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "scheduled_date"), name="crm_calendar_status_date_idx"),
            models.Index(fields=("tenant_id", "assigned_to_id", "status"), name="crm_calendar_assignee_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_same_tenant(self, "requirement")
        if not isinstance(self.reminder_days, list) or any(
            type(day) is not int or not 0 <= day <= 365 for day in self.reminder_days
        ):
            raise ValidationError(
                {"reminder_days": "Reminder days must be integers from 0 through 365."}, code="invalid_reminders"
            )
        if self.reminder_days != sorted(set(self.reminder_days), reverse=True):
            raise ValidationError(
                {"reminder_days": "Reminder days must be unique and sorted descending."}, code="invalid_reminders"
            )

    def __str__(self) -> str:
        return f"{self.title} ({self.scheduled_date})"


class RemediationAction(MutableDomainModel):
    risk = models.ForeignKey(RiskAssessment, on_delete=models.PROTECT, related_name="remediation_actions")
    control_test = models.ForeignKey(
        ControlTest, on_delete=models.PROTECT, related_name="remediation_actions", null=True, blank=True
    )
    action_code = models.CharField(max_length=50)
    description = models.TextField()
    assigned_to_id = models.UUIDField(db_index=True)
    due_date = models.DateField()
    priority = models.CharField(max_length=12, choices=RemediationPriority.choices)
    status = models.CharField(
        max_length=20, choices=RemediationStatus.choices, default=RemediationStatus.PLANNED, editable=False
    )
    completion_date = models.DateField(null=True, blank=True, editable=False)
    completion_evidence = models.JSONField(default=list, blank=True, encoder=DjangoJSONEncoder)
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        db_table = "compliance_risk_remediation_actions"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "action_code"), condition=Q(is_deleted=False), name="crm_action_live_code_uniq"
            ),
            models.CheckConstraint(condition=Q(priority__in=RemediationPriority.values), name="crm_action_priority_ck"),
            models.CheckConstraint(condition=Q(status__in=RemediationStatus.values), name="crm_action_status_ck"),
            models.CheckConstraint(
                condition=(
                    Q(status=RemediationStatus.COMPLETED, completion_date__isnull=False)
                    | Q(
                        status__in=[
                            RemediationStatus.PLANNED,
                            RemediationStatus.IN_PROGRESS,
                            RemediationStatus.OVERDUE,
                            RemediationStatus.CANCELLED,
                        ],
                        completion_date__isnull=True,
                    )
                ),
                name="crm_action_completion_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status=RemediationStatus.CANCELLED) | ~Q(cancellation_reason=""),
                name="crm_action_cancel_reason_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_deleted=False, deleted_at__isnull=True, deleted_by_id__isnull=True)
                    | Q(is_deleted=True, deleted_at__isnull=False, deleted_by_id__isnull=False)
                ),
                name="crm_action_soft_delete_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "risk", "status"), name="crm_action_risk_status_idx"),
            models.Index(
                fields=("tenant_id", "assigned_to_id", "status", "due_date"), name="crm_action_assignee_due_idx"
            ),
            models.Index(fields=("tenant_id", "priority", "status"), name="crm_action_priority_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_same_tenant(self, "risk")
        _validate_same_tenant(self, "control_test")
        _validate_evidence_shape(self.completion_evidence, "completion_evidence")
        if self.control_test_id and self.risk_id and self.control_test.control.risk_id != self.risk_id:
            raise ValidationError(
                {"control_test": "The control test must belong to a control for this risk."}, code="risk_test_mismatch"
            )
        if self.status == RemediationStatus.COMPLETED:
            if not self.completion_evidence:
                raise ValidationError(
                    {"completion_evidence": "Completion evidence is required."}, code="evidence_required"
                )
            if self.completion_date and self.created_at and self.completion_date < self.created_at.date():
                raise ValidationError(
                    {"completion_date": "Completion cannot predate creation."}, code="invalid_completion_date"
                )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.action_code = self.action_code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.action_code} - {self.status}"


class RiskConfiguration(MutableDomainModel):
    environment = models.CharField(max_length=20, choices=ConfigurationEnvironment.choices)
    version = models.PositiveIntegerField()
    likelihood_scale_max = models.PositiveSmallIntegerField(default=5)
    impact_scale_max = models.PositiveSmallIntegerField(default=5)
    level_thresholds = models.JSONField(default=default_level_thresholds)
    default_review_days = models.PositiveIntegerField(default=365)
    default_reminder_days = models.JSONField(default=default_reminder_days)
    acceptance_max_days = models.PositiveIntegerField(default=365)
    overdue_job_enabled = models.BooleanField(default=True)
    feature_flags = models.JSONField(default=dict, blank=True)
    extension_config = models.JSONField(default=dict, blank=True)
    published_at = models.DateTimeField()
    published_by_id = models.UUIDField(db_index=True)

    class Meta:
        db_table = "compliance_risk_configurations"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "environment"), name="crm_config_tenant_env_uniq"),
            models.CheckConstraint(
                condition=Q(environment__in=ConfigurationEnvironment.values), name="crm_config_environment_ck"
            ),
            models.CheckConstraint(
                condition=Q(likelihood_scale_max__gte=3, likelihood_scale_max__lte=10),
                name="crm_config_likelihood_scale_ck",
            ),
            models.CheckConstraint(
                condition=Q(impact_scale_max__gte=3, impact_scale_max__lte=10), name="crm_config_impact_scale_ck"
            ),
            models.CheckConstraint(
                condition=Q(default_review_days__gte=1, default_review_days__lte=3650), name="crm_config_review_days_ck"
            ),
            models.CheckConstraint(
                condition=Q(acceptance_max_days__gte=1, acceptance_max_days__lte=1095), name="crm_config_accept_days_ck"
            ),
            models.CheckConstraint(condition=Q(version__gte=1), name="crm_config_version_ck"),
            models.CheckConstraint(
                condition=(
                    Q(is_deleted=False, deleted_at__isnull=True, deleted_by_id__isnull=True)
                    | Q(is_deleted=True, deleted_at__isnull=False, deleted_by_id__isnull=False)
                ),
                name="crm_config_soft_delete_ck",
            ),
        ]
        indexes = [models.Index(fields=("tenant_id", "environment", "version"), name="crm_config_env_version_idx")]

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.default_reminder_days, list) or any(
            type(day) is not int or not 0 <= day <= 365 for day in self.default_reminder_days
        ):
            raise ValidationError(
                {"default_reminder_days": "Reminder days must be integers from 0 through 365."},
                code="invalid_reminders",
            )
        if self.default_reminder_days != sorted(set(self.default_reminder_days), reverse=True):
            raise ValidationError(
                {"default_reminder_days": "Reminder days must be unique and sorted descending."},
                code="invalid_reminders",
            )
        if not isinstance(self.level_thresholds, dict):
            raise ValidationError(
                {"level_thresholds": "Level thresholds must be an object."}, code="invalid_thresholds"
            )
        expected_levels = list(RiskLevel.values)
        if list(self.level_thresholds) != expected_levels:
            raise ValidationError(
                {"level_thresholds": f"Thresholds must contain the ordered levels {expected_levels}."},
                code="invalid_thresholds",
            )
        bounds = list(self.level_thresholds.values())
        if any(isinstance(bound, bool) or not isinstance(bound, Real) or bound < 1 for bound in bounds) or any(
            current >= following for current, following in zip(bounds, bounds[1:])
        ):
            raise ValidationError(
                {"level_thresholds": "Threshold upper bounds must be positive and strictly increasing."},
                code="invalid_thresholds",
            )
        if bounds[-1] < self.likelihood_scale_max * self.impact_scale_max:
            raise ValidationError(
                {"level_thresholds": "The critical upper bound must cover the entire configured score matrix."},
                code="invalid_thresholds",
            )
        if not isinstance(self.feature_flags, dict):
            raise ValidationError({"feature_flags": "Feature flags must be an object."}, code="invalid_feature_flags")
        if not isinstance(self.extension_config, dict):
            raise ValidationError({"extension_config": "Extension configuration must be an object."})
        if self.extension_config:
            from .extensions import registry

            for key, document in self.extension_config.items():
                try:
                    registry.validate_fragment(key, document)
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValidationError(
                        {"extension_config": f"Invalid or unavailable schema fragment {key}."}
                    ) from exc

    def __str__(self) -> str:
        return f"{self.environment} v{self.version}"


class AppendOnlyConfigurationQuerySet(TenantQuerySet):
    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise AppendOnlyViolation("Configuration history is append-only.", code="append_only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise AppendOnlyViolation("Configuration history is append-only.", code="append_only")


class RiskConfigurationVersion(TenantScopedModel):
    """Immutable versioned configuration snapshot and audit record."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.CharField(max_length=20, choices=ConfigurationEnvironment.choices)
    version = models.PositiveIntegerField()
    configuration = models.JSONField()
    change_summary = models.TextField()
    actor_id = models.UUIDField(db_index=True)
    correlation_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    restored_from_version = models.PositiveIntegerField(null=True, blank=True)

    objects = AppendOnlyConfigurationQuerySet.as_manager()

    class Meta:
        db_table = "compliance_risk_configuration_versions"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "environment", "version"), name="crm_config_version_uniq"),
            models.CheckConstraint(
                condition=Q(environment__in=ConfigurationEnvironment.values), name="crm_config_ver_environment_ck"
            ),
            models.CheckConstraint(condition=Q(version__gte=1), name="crm_config_ver_number_ck"),
            models.CheckConstraint(
                condition=Q(restored_from_version__isnull=True) | Q(restored_from_version__gte=1),
                name="crm_config_ver_restore_ck",
            ),
        ]
        indexes = [models.Index(fields=("tenant_id", "environment", "created_at"), name="crm_config_history_idx")]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise AppendOnlyViolation("Configuration history is append-only.", code="append_only")
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise AppendOnlyViolation("Configuration history is append-only.", code="append_only")

    def __str__(self) -> str:
        return f"{self.environment} configuration v{self.version}"


class ComplianceRisk(RiskAssessment):
    """Table-free compatibility proxy for callers of the former v1 model."""

    class Meta:
        proxy = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if "risk_name" in kwargs:
            kwargs["name"] = kwargs.pop("risk_name")
        if "mitigation_plan" in kwargs:
            kwargs["mitigation_strategy"] = kwargs.pop("mitigation_plan")
        if "name" in kwargs and "likelihood" not in kwargs:
            level = str(kwargs.get("risk_level", RiskLevel.MEDIUM))
            scores = {
                RiskLevel.NEGLIGIBLE: (1, 1, "1.00"),
                RiskLevel.LOW: (1, 1, "1.00"),
                RiskLevel.MEDIUM: (2, 2, "4.00"),
                RiskLevel.HIGH: (4, 4, "16.00"),
                RiskLevel.CRITICAL: (5, 5, "25.00"),
            }
            likelihood, impact, score = scores.get(level, scores[RiskLevel.MEDIUM])
            principal = uuid.UUID("00000000-0000-0000-0000-00000000c0de")
            kwargs.setdefault("category", RiskCategory.COMPLIANCE)
            kwargs.setdefault("description", "Legacy risk record")
            kwargs.setdefault("likelihood", likelihood)
            kwargs.setdefault("impact", impact)
            kwargs.setdefault("inherent_score", score)
            kwargs.setdefault("risk_level", level)
            kwargs.setdefault("owner_id", principal)
            kwargs.setdefault("created_by_id", principal)
            kwargs.setdefault("review_date", dt.date.today() + dt.timedelta(days=365))
        super().__init__(*args, **kwargs)

    @property
    def risk_name(self) -> str:
        return self.name

    @property
    def mitigation_plan(self) -> str:
        return self.mitigation_strategy

    def __getattribute__(self, name: str) -> Any:
        value = super().__getattribute__(name)
        if name == "status" and not super().__getattribute__("_state").adding:
            return {"identified": "open", "mitigating": "mitigated"}.get(value, value)
        return value
