"""Strict operation-specific serializers for compliance API v2."""

from __future__ import annotations

from collections.abc import Mapping

from rest_framework import serializers

from .models import (
    ComplianceActivity,
    ComplianceAssessment,
    ComplianceConfigurationRevision,
    ComplianceEvidence,
    ComplianceFramework,
    CompliancePolicy,
    CompliancePolicyVersion,
    ComplianceRequirement,
    EvidenceRequirementLink,
    RequirementPolicyMapping,
)


class StrictSerializerMixin:
    """Reject undeclared fields; silently ignored input is unsafe input."""

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: ["Unknown field."] for key in sorted(unknown)})
        return super().to_internal_value(data)


class StrictModelSerializer(StrictSerializerMixin, serializers.ModelSerializer):
    pass


class StrictSerializer(StrictSerializerMixin, serializers.Serializer):
    pass


COMMON = ("id", "created_at", "updated_at", "created_by", "updated_by", "deleted_at", "deleted_by")


class FrameworkListSerializer(StrictModelSerializer):
    class Meta:
        model = ComplianceFramework
        fields = ("id", "code", "name", "version", "category", "source_kind", "status", "created_at", "updated_at")
        read_only_fields = fields


class FrameworkDetailSerializer(StrictModelSerializer):
    requirement_count = serializers.SerializerMethodField()

    class Meta:
        model = ComplianceFramework
        fields = COMMON + ("code", "name", "version", "category", "description", "source_kind", "source_package", "source_version", "status", "transition_history", "requirement_count")
        read_only_fields = fields

    def get_requirement_count(self, obj):
        return obj.requirements.filter(tenant_id=obj.tenant_id, deleted_at__isnull=True).count()


class FrameworkWriteSerializer(StrictSerializer):
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=255)
    version = serializers.CharField(max_length=50)
    category = serializers.CharField(max_length=50)
    description = serializers.CharField(required=False, allow_blank=True)
    source_kind = serializers.ChoiceField(choices=("custom", "imported", "extension"), default="custom")
    source_package = serializers.CharField(max_length=255, required=False, allow_blank=True)
    source_version = serializers.CharField(max_length=50, required=False, allow_blank=True)


class FrameworkImportSerializer(StrictSerializer):
    package = serializers.JSONField()


class RequirementListSerializer(StrictModelSerializer):
    framework_name = serializers.CharField(source="framework.name", read_only=True)

    class Meta:
        model = ComplianceRequirement
        fields = ("id", "framework", "framework_name", "code", "title", "section", "applicability", "status", "sort_order", "tags", "updated_at")
        read_only_fields = fields


class RequirementDetailSerializer(StrictModelSerializer):
    framework_name = serializers.CharField(source="framework.name", read_only=True)
    latest_assessment = serializers.SerializerMethodField()

    class Meta:
        model = ComplianceRequirement
        fields = COMMON + ("framework", "framework_name", "code", "title", "description", "section", "guidance", "applicability", "applicability_rationale", "status", "sort_order", "tags", "transition_history", "latest_assessment")
        read_only_fields = fields

    def get_latest_assessment(self, obj):
        assessment = obj.assessments.filter(tenant_id=obj.tenant_id).order_by("-assessed_at", "-created_at", "-id").first()
        return AssessmentSerializer(assessment).data if assessment else None


class RequirementWriteSerializer(StrictSerializer):
    framework_id = serializers.UUIDField()
    code = serializers.CharField(max_length=100)
    title = serializers.CharField(max_length=500)
    description = serializers.CharField()
    section = serializers.CharField(max_length=255, required=False, allow_blank=True)
    guidance = serializers.CharField(required=False, allow_blank=True)
    applicability = serializers.ChoiceField(choices=("applicable", "not_applicable"), required=False)
    applicability_rationale = serializers.CharField(required=False, allow_blank=True)
    sort_order = serializers.IntegerField(min_value=0, required=False)
    tags = serializers.ListField(child=serializers.CharField(max_length=100), max_length=50, required=False)


class RequirementBulkImportSerializer(StrictSerializer):
    framework_id = serializers.UUIDField()
    rows = serializers.ListField(child=serializers.DictField(), max_length=10000)


class PolicyListSerializer(StrictModelSerializer):
    owner_name = serializers.SerializerMethodField()

    class Meta:
        model = CompliancePolicy
        fields = ("id", "code", "title", "category", "owner", "owner_name", "review_frequency_days", "effective_date", "expiry_date", "next_review_date", "status", "current_version", "created_at", "updated_at")
        read_only_fields = fields

    def get_owner_name(self, obj):
        return obj.owner.get_full_name() or obj.owner.get_username() if obj.owner else None


class PolicyVersionSerializer(StrictModelSerializer):
    class Meta:
        model = CompliancePolicyVersion
        fields = ("id", "policy", "version", "content", "content_sha256", "change_summary", "created_by", "created_at", "approved_by", "approved_at", "published_by", "published_at")
        read_only_fields = fields


class PolicyDetailSerializer(StrictModelSerializer):
    versions = PolicyVersionSerializer(many=True, read_only=True)
    mapping_count = serializers.SerializerMethodField()

    class Meta:
        model = CompliancePolicy
        fields = COMMON + ("code", "title", "summary", "category", "owner", "review_frequency_days", "effective_date", "expiry_date", "next_review_date", "status", "current_version", "transition_history", "versions", "mapping_count")
        read_only_fields = fields

    def get_mapping_count(self, obj):
        return obj.requirement_mappings.filter(tenant_id=obj.tenant_id, deleted_at__isnull=True).count()


class PolicyWriteSerializer(StrictSerializer):
    code = serializers.CharField(max_length=100)
    title = serializers.CharField(max_length=500)
    summary = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(max_length=50)
    owner_id = serializers.CharField(required=False, allow_null=True)
    review_frequency_days = serializers.IntegerField(min_value=1, max_value=3650, required=False)
    effective_date = serializers.DateField(required=False, allow_null=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)


class PolicyVersionCreateSerializer(StrictSerializer):
    content = serializers.CharField(trim_whitespace=False)
    change_summary = serializers.CharField()


class PolicyTransitionSerializer(StrictSerializer):
    transition_key = serializers.CharField(max_length=255)
    reason = serializers.CharField(required=False, allow_blank=True)
    content = serializers.CharField(required=False, trim_whitespace=False)
    change_summary = serializers.CharField(required=False)


class MappingSerializer(StrictModelSerializer):
    requirement_code = serializers.CharField(source="requirement.code", read_only=True)
    policy_code = serializers.CharField(source="policy.code", read_only=True)

    class Meta:
        model = RequirementPolicyMapping
        fields = COMMON + ("requirement", "requirement_code", "policy", "policy_code", "policy_version", "coverage", "rationale", "mapped_at")
        read_only_fields = fields


class MappingWriteSerializer(StrictSerializer):
    requirement_id = serializers.UUIDField()
    policy_id = serializers.UUIDField()
    policy_version_id = serializers.UUIDField(required=False, allow_null=True)
    coverage = serializers.ChoiceField(choices=("none", "partial", "full", "not_applicable"))
    rationale = serializers.CharField(required=False, allow_blank=True)


class MappingBulkSerializer(StrictSerializer):
    rows = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=10000)


class AssessmentSerializer(StrictModelSerializer):
    requirement_code = serializers.CharField(source="requirement.code", read_only=True)

    class Meta:
        model = ComplianceAssessment
        fields = ("id", "requirement", "requirement_code", "mapping", "status", "assessor", "assessed_at", "due_date", "notes", "source", "created_at")
        read_only_fields = fields


class AssessmentCreateSerializer(StrictSerializer):
    requirement_id = serializers.UUIDField()
    mapping_id = serializers.UUIDField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=("not_assessed", "in_progress", "compliant", "partial", "non_compliant", "not_applicable"))
    assessed_at = serializers.DateTimeField(required=False)
    due_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    source = serializers.ChoiceField(choices=("manual", "import", "extension"), default="manual")


class EvidenceListSerializer(StrictModelSerializer):
    class Meta:
        model = ComplianceEvidence
        fields = ("id", "name", "evidence_type", "reference_kind", "classification", "collection_method", "valid_from", "valid_until", "collected_at", "created_at", "updated_at")
        read_only_fields = fields


class EvidenceLinkSerializer(StrictModelSerializer):
    requirement_code = serializers.CharField(source="requirement.code", read_only=True)

    class Meta:
        model = EvidenceRequirementLink
        fields = ("id", "evidence", "requirement", "requirement_code", "relevance", "notes", "created_by", "created_at")
        read_only_fields = fields


class EvidenceDetailSerializer(StrictModelSerializer):
    requirement_links = EvidenceLinkSerializer(many=True, read_only=True)

    class Meta:
        model = ComplianceEvidence
        fields = COMMON + ("name", "description", "evidence_type", "reference_kind", "document_id", "external_uri", "text_reference", "sha256", "classification", "collection_method", "valid_from", "valid_until", "collected_by", "collected_at", "requirement_links")
        read_only_fields = fields


class EvidenceWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=500)
    description = serializers.CharField(required=False, allow_blank=True)
    evidence_type = serializers.ChoiceField(choices=("document", "report", "screenshot", "log", "attestation", "external_reference"))
    reference_kind = serializers.ChoiceField(choices=("dms_document", "external_url", "text_reference"))
    document_id = serializers.UUIDField(required=False, allow_null=True)
    external_uri = serializers.URLField(required=False, allow_blank=True)
    text_reference = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    sha256 = serializers.RegexField(r"^[0-9a-f]{64}$", required=False, allow_blank=True)
    classification = serializers.ChoiceField(choices=("public", "internal", "confidential", "restricted"))
    collection_method = serializers.ChoiceField(choices=("manual", "import", "extension"), default="manual")
    valid_from = serializers.DateTimeField(required=False, allow_null=True)
    valid_until = serializers.DateTimeField(required=False, allow_null=True)
    collected_at = serializers.DateTimeField(required=False)


class EvidenceLinkWriteSerializer(StrictSerializer):
    requirement_id = serializers.UUIDField()
    relevance = serializers.ChoiceField(choices=("supporting", "primary", "contradicting"))
    notes = serializers.CharField(required=False, allow_blank=True)


class ConfigurationRevisionSerializer(StrictModelSerializer):
    class Meta:
        model = ComplianceConfigurationRevision
        fields = ("id", "environment", "version", "status", "policy_code_prefix", "default_review_frequency_days", "expiry_warning_days", "evidence_warning_days", "minimum_assessment_note_length", "allow_external_evidence_urls", "bulk_import_row_limit", "regulation_categories", "rollout", "created_by", "created_at", "activated_by", "activated_at", "transition_history")
        read_only_fields = fields


class ConfigurationWriteSerializer(StrictSerializer):
    environment = serializers.ChoiceField(choices=("development", "staging", "production"), required=False)
    policy_code_prefix = serializers.RegexField(r"^[A-Z0-9_-]{1,10}$", required=False)
    default_review_frequency_days = serializers.IntegerField(min_value=1, max_value=3650, required=False)
    expiry_warning_days = serializers.IntegerField(min_value=0, max_value=365, required=False)
    evidence_warning_days = serializers.IntegerField(min_value=0, max_value=365, required=False)
    minimum_assessment_note_length = serializers.IntegerField(min_value=0, max_value=2000, required=False)
    allow_external_evidence_urls = serializers.BooleanField(required=False)
    bulk_import_row_limit = serializers.IntegerField(min_value=1, max_value=10000, required=False)
    regulation_categories = serializers.ListField(child=serializers.CharField(max_length=50), min_length=1, max_length=100, required=False)
    rollout = serializers.DictField(required=False)


class ConfigurationImportSerializer(StrictSerializer):
    document = serializers.JSONField()


class ConfigurationPreviewSerializer(StrictSerializer):
    revision_id = serializers.UUIDField(read_only=True)
    environment = serializers.CharField(read_only=True)
    diff = serializers.ListField(read_only=True)
    affected = serializers.DictField(read_only=True)


class ActivitySerializer(StrictModelSerializer):
    class Meta:
        model = ComplianceActivity
        fields = ("id", "entity_type", "entity_id", "action", "actor", "correlation_id", "before", "after", "reason", "occurred_at")
        read_only_fields = fields


class DashboardSerializer(StrictSerializer):
    frameworks = serializers.IntegerField(read_only=True)
    requirements = serializers.IntegerField(read_only=True)
    unassessed_requirements = serializers.IntegerField(read_only=True)
    gaps = serializers.IntegerField(read_only=True)
    review_queue = serializers.IntegerField(read_only=True)
    expiring_evidence = serializers.IntegerField(read_only=True)


class ScorecardSerializer(StrictSerializer):
    framework_id = serializers.UUIDField(read_only=True)
    score = serializers.FloatField(read_only=True)
    earned_points = serializers.FloatField(read_only=True)
    possible_points = serializers.IntegerField(read_only=True)
    formula = serializers.CharField(read_only=True)
    requirements = serializers.ListField(read_only=True)


class GapSerializer(StrictSerializer):
    framework_id = serializers.UUIDField(read_only=True)
    total = serializers.IntegerField(read_only=True)
    gap_count = serializers.IntegerField(read_only=True)
    gaps = serializers.ListField(read_only=True)


class EvidenceValidationSerializer(StrictSerializer):
    evidence_id = serializers.UUIDField(read_only=True)
    reference_valid = serializers.BooleanField(read_only=True)
    hash_valid = serializers.BooleanField(read_only=True)
    fresh = serializers.BooleanField(read_only=True)
    checked_at = serializers.DateTimeField(read_only=True)


# Legacy read aliases remain import-compatible, but v2 controllers use the
# operation-specific serializers above.
CompliancePolicySerializer = PolicyDetailSerializer
ComplianceRequirementSerializer = RequirementDetailSerializer


__all__ = [name for name in globals() if name.endswith("Serializer")]
