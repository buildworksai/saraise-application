"""Tenant-safe persistence for the open-source compliance workspace.

The models deliberately contain persistence invariants only. Workflow commands,
authorization, audit creation, and related-object resolution belong to
``services.py``. PostgreSQL migrations add RLS and append-only triggers; the ORM
guards below provide the same immutability contract during SQLite test runs.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from src.core.tenancy import TenantQuerySet, TenantScopedModel, TimestampedModel


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_TAGS = 50
MAX_CATEGORIES = 100
KNOWN_ROLLOUT_CAPABILITIES = frozenset(
    {
        "frameworks",
        "requirements",
        "policies",
        "mappings",
        "assessments",
        "evidence",
        "dashboard",
        "configuration",
        "activity",
        "imports",
        "exports",
    }
)


def validate_sha256(value: str) -> None:
    """Reject non-canonical digests so hashes compare deterministically."""
    if not SHA256_RE.fullmatch(value):
        raise ValidationError("Must be a lowercase hexadecimal SHA-256 digest.", code="invalid_sha256")


def validate_optional_sha256(value: str) -> None:
    """Validate a digest only when one was supplied."""
    if value:
        validate_sha256(value)


def _validate_unique_nonblank_strings(value: Any, *, maximum: int, label: str) -> None:
    if not isinstance(value, list):
        raise ValidationError(f"{label} must be a list.", code="invalid_list")
    if len(value) > maximum:
        raise ValidationError(f"{label} may contain at most {maximum} items.", code="too_many_items")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValidationError(f"{label} must contain only nonblank strings.", code="invalid_item")
    normalised = [item.strip().casefold() for item in value]
    if len(normalised) != len(set(normalised)):
        raise ValidationError(f"{label} must not contain duplicates.", code="duplicate_item")


def validate_tags(value: Any) -> None:
    _validate_unique_nonblank_strings(value, maximum=MAX_TAGS, label="Tags")


def validate_regulation_categories(value: Any) -> None:
    _validate_unique_nonblank_strings(value, maximum=MAX_CATEGORIES, label="Regulation categories")
    if not value:
        raise ValidationError("At least one regulation category is required.", code="empty_categories")


def validate_rollout(value: Any) -> None:
    """Validate the deliberately small, portable feature-rollout document.

    Each capability maps to an object containing optional ``roles`` and
    ``cohorts`` arrays. Empty arrays mean no restriction. Unknown keys fail
    closed instead of becoming accidental feature flags.
    """
    if not isinstance(value, dict):
        raise ValidationError("Rollout must be an object.", code="invalid_rollout")
    unknown = set(value) - KNOWN_ROLLOUT_CAPABILITIES
    if unknown:
        raise ValidationError(
            f"Unknown rollout capabilities: {', '.join(sorted(unknown))}.",
            code="unknown_capability",
        )
    for capability, rule in value.items():
        if not isinstance(rule, dict):
            raise ValidationError(f"Rollout rule for {capability} must be an object.", code="invalid_rule")
        unknown_rule_keys = set(rule) - {"enabled", "roles", "cohorts"}
        if unknown_rule_keys:
            raise ValidationError(
                f"Unknown rollout fields for {capability}: {', '.join(sorted(unknown_rule_keys))}.",
                code="unknown_rollout_field",
            )
        if "enabled" in rule and not isinstance(rule["enabled"], bool):
            raise ValidationError(f"{capability}.enabled must be boolean.", code="invalid_enabled")
        for key in ("roles", "cohorts"):
            members = rule.get(key, [])
            _validate_unique_nonblank_strings(members, maximum=100, label=f"{capability}.{key}")


class MutableComplianceModel(TenantScopedModel, TimestampedModel):
    """Common ownership, actor, and soft-deletion fields for mutable records."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Make model validators real persistence guards, not form-only hints."""
        self.full_clean()
        super().save(*args, **kwargs)

    def soft_delete(self, *, actor: Any | None = None) -> None:
        """Archive the row without destroying compliance history."""
        self.deleted_at = timezone.now()
        self.deleted_by = actor
        self.updated_by = actor
        self.save(update_fields=("deleted_at", "deleted_by", "updated_by", "updated_at"))


class ImmutableQuerySet(TenantQuerySet):
    """Prevent bulk ORM operations bypassing append-only instance guards."""

    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ValidationError("Append-only compliance records cannot be updated.", code="append_only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Append-only compliance records cannot be deleted.", code="append_only")


class AppendOnlyComplianceModel(TenantScopedModel):
    """Base for immutable historical and audit records."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    objects = ImmutableQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Append-only compliance records cannot be updated.", code="append_only")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Append-only compliance records cannot be deleted.", code="append_only")


class FrameworkSourceKind(models.TextChoices):
    CUSTOM = "custom", "Custom"
    IMPORTED = "imported", "Imported"
    EXTENSION = "extension", "Extension"


class FrameworkStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class ComplianceFramework(MutableComplianceModel):
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    version = models.CharField(max_length=50)
    category = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    source_kind = models.CharField(max_length=20, choices=FrameworkSourceKind.choices)
    source_package = models.CharField(max_length=255, blank=True)
    source_version = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=FrameworkStatus.choices, default=FrameworkStatus.DRAFT)
    transition_history = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "compliance_frameworks"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "code", "version"),
                condition=Q(deleted_at__isnull=True),
                name="cmp_fw_tenant_code_ver_uq",
            ),
            models.CheckConstraint(
                condition=~Q(source_kind=FrameworkSourceKind.EXTENSION) | ~Q(source_package=""),
                name="cmp_fw_extension_package_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "name"), name="cmp_fw_tenant_status_name_ix"),
            models.Index(fields=("tenant_id", "category", "status"), name="cmp_fw_tenant_cat_status_ix"),
            models.Index(fields=("tenant_id", "deleted_at"), name="cmp_fw_tenant_deleted_ix"),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.version} - {self.name}"


class RequirementApplicability(models.TextChoices):
    APPLICABLE = "applicable", "Applicable"
    NOT_APPLICABLE = "not_applicable", "Not applicable"


class RequirementStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class ComplianceRequirement(MutableComplianceModel):
    framework = models.ForeignKey(ComplianceFramework, on_delete=models.PROTECT, related_name="requirements")
    code = models.CharField(max_length=100)
    title = models.CharField(max_length=500)
    description = models.TextField()
    section = models.CharField(max_length=255, blank=True)
    guidance = models.TextField(blank=True)
    applicability = models.CharField(
        max_length=20,
        choices=RequirementApplicability.choices,
        default=RequirementApplicability.APPLICABLE,
    )
    applicability_rationale = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=RequirementStatus.choices, default=RequirementStatus.ACTIVE)
    sort_order = models.PositiveIntegerField(default=0)
    tags = models.JSONField(default=list, blank=True, validators=(validate_tags,))
    transition_history = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "compliance_requirements"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "framework", "code"),
                condition=Q(deleted_at__isnull=True),
                name="cmp_req_tenant_fw_code_uq",
            ),
            models.CheckConstraint(
                condition=~Q(applicability=RequirementApplicability.NOT_APPLICABLE)
                | ~Q(applicability_rationale=""),
                name="cmp_req_na_rationale_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "framework", "status", "sort_order"),
                name="cmp_req_tenant_fw_status_ix",
            ),
            models.Index(
                fields=("tenant_id", "applicability", "status"),
                name="cmp_req_tenant_app_status_ix",
            ),
            models.Index(fields=("tenant_id", "deleted_at"), name="cmp_req_tenant_deleted_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.framework_id and self.tenant_id and self.framework.tenant_id != self.tenant_id:
            raise ValidationError({"framework": "Framework must belong to the same tenant."})

    def __str__(self) -> str:
        return f"{self.code} - {self.title}"


class PolicyStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    IN_REVIEW = "in_review", "In review"
    APPROVED = "approved", "Approved"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class CompliancePolicy(MutableComplianceModel):
    code = models.CharField(max_length=100)
    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True)
    category = models.CharField(max_length=50)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_compliance_policies",
    )
    review_frequency_days = models.PositiveSmallIntegerField()
    effective_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    next_review_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=PolicyStatus.choices, default=PolicyStatus.DRAFT)
    current_version = models.PositiveIntegerField(default=0)
    transition_history = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "compliance_policies"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "code"),
                condition=Q(deleted_at__isnull=True),
                name="cmp_policy_tenant_code_uq",
            ),
            models.CheckConstraint(
                condition=Q(expiry_date__isnull=True)
                | Q(effective_date__isnull=True)
                | Q(expiry_date__gt=models.F("effective_date")),
                name="cmp_policy_expiry_after_eff_ck",
            ),
            models.CheckConstraint(condition=Q(current_version__gte=0), name="cmp_policy_version_nonneg_ck"),
            models.CheckConstraint(
                condition=~Q(status=PolicyStatus.PUBLISHED)
                | (
                    Q(current_version__gt=0)
                    & Q(effective_date__isnull=False)
                ),
                name="cmp_policy_published_ready_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "title"), name="cmp_pol_tenant_status_title_ix"),
            models.Index(fields=("tenant_id", "owner", "status"), name="cmp_pol_tenant_owner_status_ix"),
            models.Index(
                fields=("tenant_id", "next_review_date", "status"),
                name="cmp_pol_tenant_review_ix",
            ),
            models.Index(fields=("tenant_id", "expiry_date", "status"), name="cmp_pol_tenant_exp_status_ix"),
            models.Index(fields=("tenant_id", "deleted_at"), name="cmp_pol_tenant_deleted_ix"),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.title}"

    def clean(self) -> None:
        super().clean()
        if self.status == PolicyStatus.PUBLISHED and self.owner_id is None:
            # Legacy rows had no owner column. The data migration can preserve
            # their published state, while every subsequent ORM write and the
            # publication service still fail closed until ownership is set.
            raise ValidationError({"owner": "Published policies require an owner."})


class CompliancePolicyVersion(AppendOnlyComplianceModel):
    policy = models.ForeignKey(CompliancePolicy, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    content = models.TextField()
    content_sha256 = models.CharField(max_length=64, validators=(validate_sha256,))
    change_summary = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "compliance_policy_versions"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "policy", "version"), name="cmp_pol_ver_number_uq"),
            models.UniqueConstraint(
                fields=("tenant_id", "policy", "content_sha256"),
                name="cmp_pol_ver_content_uq",
            ),
            models.CheckConstraint(
                condition=Q(content_sha256__regex=r"^[0-9a-f]{64}$"),
                name="cmp_pol_ver_sha256_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "policy", "-version"), name="cmp_pol_ver_tenant_pol_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.policy_id and self.tenant_id and self.policy.tenant_id != self.tenant_id:
            raise ValidationError({"policy": "Policy must belong to the same tenant."})

    def __str__(self) -> str:
        return f"{self.policy.code} v{self.version}"


class MappingCoverage(models.TextChoices):
    NONE = "none", "None"
    PARTIAL = "partial", "Partial"
    FULL = "full", "Full"
    NOT_APPLICABLE = "not_applicable", "Not applicable"


class RequirementPolicyMapping(MutableComplianceModel):
    requirement = models.ForeignKey(
        ComplianceRequirement,
        on_delete=models.PROTECT,
        related_name="policy_mappings",
    )
    policy = models.ForeignKey(CompliancePolicy, on_delete=models.PROTECT, related_name="requirement_mappings")
    policy_version = models.ForeignKey(
        CompliancePolicyVersion,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="requirement_mappings",
    )
    coverage = models.CharField(max_length=20, choices=MappingCoverage.choices)
    rationale = models.TextField(blank=True)
    mapped_at = models.DateTimeField()

    class Meta:
        db_table = "compliance_requirement_policy_mappings"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "requirement", "policy"),
                condition=Q(deleted_at__isnull=True),
                name="cmp_map_tenant_req_pol_uq",
            ),
            models.CheckConstraint(
                condition=Q(coverage=MappingCoverage.FULL) | ~Q(rationale=""),
                name="cmp_map_rationale_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "requirement", "coverage"),
                name="cmp_map_tenant_req_cov_ix",
            ),
            models.Index(fields=("tenant_id", "policy", "coverage"), name="cmp_map_tenant_pol_cov_ix"),
            models.Index(fields=("tenant_id", "deleted_at"), name="cmp_map_tenant_deleted_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.requirement_id and self.tenant_id and self.requirement.tenant_id != self.tenant_id:
            errors["requirement"] = "Requirement must belong to the same tenant."
        if self.policy_id and self.tenant_id and self.policy.tenant_id != self.tenant_id:
            errors["policy"] = "Policy must belong to the same tenant."
        if self.policy_version_id:
            if self.policy_version.tenant_id != self.tenant_id:
                errors["policy_version"] = "Policy version must belong to the same tenant."
            elif self.policy_id and self.policy_version.policy_id != self.policy_id:
                errors["policy_version"] = "Policy version must belong to the mapped policy."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.requirement.code} -> {self.policy.code} ({self.coverage})"


class AssessmentStatus(models.TextChoices):
    NOT_ASSESSED = "not_assessed", "Not assessed"
    IN_PROGRESS = "in_progress", "In progress"
    COMPLIANT = "compliant", "Compliant"
    PARTIAL = "partial", "Partial"
    NON_COMPLIANT = "non_compliant", "Non-compliant"
    NOT_APPLICABLE = "not_applicable", "Not applicable"


class AssessmentSource(models.TextChoices):
    MANUAL = "manual", "Manual"
    IMPORT = "import", "Import"
    EXTENSION = "extension", "Extension"


class ComplianceAssessment(AppendOnlyComplianceModel):
    requirement = models.ForeignKey(ComplianceRequirement, on_delete=models.PROTECT, related_name="assessments")
    mapping = models.ForeignKey(
        RequirementPolicyMapping,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assessments",
    )
    status = models.CharField(max_length=20, choices=AssessmentStatus.choices)
    assessor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="compliance_assessments",
    )
    assessed_at = models.DateTimeField()
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    source = models.CharField(max_length=20, choices=AssessmentSource.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "compliance_assessments"
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=(AssessmentStatus.NOT_ASSESSED, AssessmentStatus.IN_PROGRESS, AssessmentStatus.COMPLIANT))
                | ~Q(notes=""),
                name="cmp_assessment_notes_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "requirement", "-assessed_at"),
                name="cmp_assess_tenant_req_ix",
            ),
            models.Index(fields=("tenant_id", "status", "due_date"), name="cmp_assess_tenant_due_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.requirement_id and self.tenant_id and self.requirement.tenant_id != self.tenant_id:
            errors["requirement"] = "Requirement must belong to the same tenant."
        if self.mapping_id:
            if self.mapping.tenant_id != self.tenant_id:
                errors["mapping"] = "Mapping must belong to the same tenant."
            elif self.requirement_id and self.mapping.requirement_id != self.requirement_id:
                errors["mapping"] = "Mapping must reference the assessed requirement."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.requirement.code} - {self.status} at {self.assessed_at.isoformat()}"


class EvidenceType(models.TextChoices):
    DOCUMENT = "document", "Document"
    REPORT = "report", "Report"
    SCREENSHOT = "screenshot", "Screenshot"
    LOG = "log", "Log"
    ATTESTATION = "attestation", "Attestation"
    EXTERNAL_REFERENCE = "external_reference", "External reference"


class EvidenceReferenceKind(models.TextChoices):
    DMS_DOCUMENT = "dms_document", "DMS document"
    EXTERNAL_URL = "external_url", "External URL"
    TEXT_REFERENCE = "text_reference", "Text reference"


class EvidenceClassification(models.TextChoices):
    PUBLIC = "public", "Public"
    INTERNAL = "internal", "Internal"
    CONFIDENTIAL = "confidential", "Confidential"
    RESTRICTED = "restricted", "Restricted"


class EvidenceCollectionMethod(models.TextChoices):
    MANUAL = "manual", "Manual"
    IMPORT = "import", "Import"
    EXTENSION = "extension", "Extension"


class ComplianceEvidence(MutableComplianceModel):
    name = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    evidence_type = models.CharField(max_length=30, choices=EvidenceType.choices)
    reference_kind = models.CharField(max_length=20, choices=EvidenceReferenceKind.choices)
    document_id = models.UUIDField(null=True, blank=True)
    external_uri = models.URLField(blank=True)
    text_reference = models.CharField(max_length=1000, blank=True)
    sha256 = models.CharField(max_length=64, blank=True, validators=(validate_optional_sha256,))
    classification = models.CharField(max_length=20, choices=EvidenceClassification.choices)
    collection_method = models.CharField(max_length=20, choices=EvidenceCollectionMethod.choices)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="collected_compliance_evidence",
    )
    collected_at = models.DateTimeField()

    class Meta:
        db_table = "compliance_evidence"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(reference_kind=EvidenceReferenceKind.DMS_DOCUMENT)
                    & Q(document_id__isnull=False)
                    & Q(external_uri="")
                    & Q(text_reference="")
                )
                | (
                    Q(reference_kind=EvidenceReferenceKind.EXTERNAL_URL)
                    & Q(document_id__isnull=True)
                    & ~Q(external_uri="")
                    & Q(text_reference="")
                )
                | (
                    Q(reference_kind=EvidenceReferenceKind.TEXT_REFERENCE)
                    & Q(document_id__isnull=True)
                    & Q(external_uri="")
                    & ~Q(text_reference="")
                ),
                name="cmp_evidence_reference_ck",
            ),
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True)
                | (Q(valid_from__isnull=False) & Q(valid_until__gt=models.F("valid_from"))),
                name="cmp_evidence_validity_ck",
            ),
            models.CheckConstraint(
                condition=Q(sha256="") | Q(sha256__regex=r"^[0-9a-f]{64}$"),
                name="cmp_evidence_sha256_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "classification", "collected_at"),
                name="cmp_evid_tenant_class_ix",
            ),
            models.Index(fields=("tenant_id", "valid_until", "deleted_at"), name="cmp_evid_tenant_valid_ix"),
            models.Index(fields=("tenant_id", "document_id"), name="cmp_evid_tenant_doc_ix"),
            models.Index(fields=("tenant_id", "deleted_at"), name="cmp_evid_tenant_deleted_ix"),
        ]

    def __str__(self) -> str:
        return self.name


class EvidenceRelevance(models.TextChoices):
    SUPPORTING = "supporting", "Supporting"
    PRIMARY = "primary", "Primary"
    CONTRADICTING = "contradicting", "Contradicting"


class EvidenceRequirementLink(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evidence = models.ForeignKey(
        ComplianceEvidence,
        on_delete=models.PROTECT,
        related_name="requirement_links",
    )
    requirement = models.ForeignKey(
        ComplianceRequirement,
        on_delete=models.PROTECT,
        related_name="evidence_links",
    )
    relevance = models.CharField(max_length=20, choices=EvidenceRelevance.choices)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "compliance_evidence_requirement_links"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "evidence", "requirement"),
                name="cmp_evid_link_tenant_uq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "requirement", "relevance"),
                name="cmp_evid_link_req_rel_ix",
            ),
            models.Index(fields=("tenant_id", "evidence"), name="cmp_evid_link_evidence_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.evidence_id and self.tenant_id and self.evidence.tenant_id != self.tenant_id:
            errors["evidence"] = "Evidence must belong to the same tenant."
        if self.requirement_id and self.tenant_id and self.requirement.tenant_id != self.tenant_id:
            errors["requirement"] = "Requirement must belong to the same tenant."
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.evidence.name} -> {self.requirement.code}"


class ConfigurationEnvironment(models.TextChoices):
    DEVELOPMENT = "development", "Development"
    STAGING = "staging", "Staging"
    PRODUCTION = "production", "Production"


class ConfigurationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    SUPERSEDED = "superseded", "Superseded"


class ComplianceConfigurationRevision(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.CharField(max_length=20, choices=ConfigurationEnvironment.choices)
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=ConfigurationStatus.choices, default=ConfigurationStatus.DRAFT)
    policy_code_prefix = models.CharField(max_length=10)
    default_review_frequency_days = models.PositiveSmallIntegerField(
        validators=(MinValueValidator(1), MaxValueValidator(3650))
    )
    expiry_warning_days = models.PositiveSmallIntegerField(
        validators=(MinValueValidator(0), MaxValueValidator(365))
    )
    evidence_warning_days = models.PositiveSmallIntegerField(
        validators=(MinValueValidator(0), MaxValueValidator(365))
    )
    minimum_assessment_note_length = models.PositiveSmallIntegerField(
        validators=(MinValueValidator(0), MaxValueValidator(2000))
    )
    allow_external_evidence_urls = models.BooleanField()
    bulk_import_row_limit = models.PositiveIntegerField(
        validators=(MinValueValidator(1), MaxValueValidator(10_000))
    )
    regulation_categories = models.JSONField(default=list, validators=(validate_regulation_categories,))
    rollout = models.JSONField(default=dict, blank=True, validators=(validate_rollout,))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    transition_history = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "compliance_configuration_revisions"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "environment", "version"),
                name="cmp_cfg_tenant_env_version_uq",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "environment"),
                condition=Q(status=ConfigurationStatus.ACTIVE),
                name="cmp_cfg_one_active_uq",
            ),
            models.CheckConstraint(
                condition=Q(default_review_frequency_days__range=(1, 3650)),
                name="cmp_cfg_review_range_ck",
            ),
            models.CheckConstraint(
                condition=Q(expiry_warning_days__range=(0, 365)),
                name="cmp_cfg_expiry_range_ck",
            ),
            models.CheckConstraint(
                condition=Q(evidence_warning_days__range=(0, 365)),
                name="cmp_cfg_evidence_range_ck",
            ),
            models.CheckConstraint(
                condition=Q(minimum_assessment_note_length__range=(0, 2000)),
                name="cmp_cfg_note_range_ck",
            ),
            models.CheckConstraint(
                condition=Q(bulk_import_row_limit__range=(1, 10_000)),
                name="cmp_cfg_import_range_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "environment", "status", "-version"),
                name="cmp_cfg_tenant_env_status_ix",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.environment} configuration v{self.version} ({self.status})"


class ActivityEntityType(models.TextChoices):
    FRAMEWORK = "framework", "Framework"
    REQUIREMENT = "requirement", "Requirement"
    POLICY = "policy", "Policy"
    POLICY_VERSION = "policy_version", "Policy version"
    MAPPING = "mapping", "Mapping"
    ASSESSMENT = "assessment", "Assessment"
    EVIDENCE = "evidence", "Evidence"
    EVIDENCE_LINK = "evidence_link", "Evidence link"
    CONFIGURATION = "configuration", "Configuration"


class ComplianceActivity(AppendOnlyComplianceModel):
    entity_type = models.CharField(max_length=30, choices=ActivityEntityType.choices)
    entity_id = models.UUIDField()
    action = models.CharField(max_length=100)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="compliance_activity",
    )
    correlation_id = models.UUIDField()
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "compliance_activity"
        indexes = [
            models.Index(fields=("tenant_id", "-occurred_at"), name="cmp_act_tenant_time_ix"),
            models.Index(
                fields=("tenant_id", "entity_type", "entity_id", "-occurred_at"),
                name="cmp_act_tenant_entity_ix",
            ),
            models.Index(fields=("tenant_id", "correlation_id"), name="cmp_act_tenant_corr_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        for field_name in ("before", "after"):
            value = getattr(self, field_name)
            if not isinstance(value, Mapping):
                raise ValidationError({field_name: "Audit snapshots must be JSON objects."})

    def __str__(self) -> str:
        return f"{self.entity_type}:{self.entity_id} {self.action}"


__all__ = [
    "ActivityEntityType",
    "AssessmentSource",
    "AssessmentStatus",
    "ComplianceActivity",
    "ComplianceAssessment",
    "ComplianceConfigurationRevision",
    "ComplianceEvidence",
    "ComplianceFramework",
    "CompliancePolicy",
    "CompliancePolicyVersion",
    "ComplianceRequirement",
    "ConfigurationEnvironment",
    "ConfigurationStatus",
    "EvidenceClassification",
    "EvidenceCollectionMethod",
    "EvidenceReferenceKind",
    "EvidenceRelevance",
    "EvidenceRequirementLink",
    "EvidenceType",
    "FrameworkSourceKind",
    "FrameworkStatus",
    "MappingCoverage",
    "PolicyStatus",
    "RequirementApplicability",
    "RequirementPolicyMapping",
    "RequirementStatus",
]
