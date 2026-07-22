"""Operation-specific API serializers for compliance risk management.

Serializers validate the wire contract only. Persistence is deliberately owned
by ``services.py`` so API, jobs, and future paid extensions share one set of
tenant and lifecycle guarantees.
"""

from __future__ import annotations

from rest_framework import serializers

from .models import (
    ComplianceCalendarEntry,
    ComplianceRequirement,
    Control,
    ControlTest,
    RemediationAction,
    RiskAssessment,
    RiskConfiguration,
    RiskConfigurationVersion,
)


class StrictSerializer(serializers.Serializer):
    """Reject unknown inputs instead of silently ignoring client mistakes."""

    def to_internal_value(self, data: object) -> dict[str, object]:
        if isinstance(data, dict):
            unknown = sorted(set(data) - set(self.fields))
            if unknown:
                raise serializers.ValidationError({name: "Unknown field." for name in unknown})
        return super().to_internal_value(data)


class StrictModelSerializer(serializers.ModelSerializer):
    def to_internal_value(self, data: object) -> dict[str, object]:
        if isinstance(data, dict):
            unknown = sorted(set(data) - set(self.fields))
            if unknown:
                raise serializers.ValidationError({name: "Unknown field." for name in unknown})
        return super().to_internal_value(data)


AUDIT_READ_ONLY = (
    "id",
    "tenant_id",
    "created_at",
    "updated_at",
    "created_by_id",
    "updated_by_id",
    "is_deleted",
    "deleted_at",
    "deleted_by_id",
    "transition_history",
)

RISK_DETAIL_FIELDS = (
    *AUDIT_READ_ONLY,
    "risk_code",
    "name",
    "category",
    "description",
    "likelihood",
    "impact",
    "inherent_score",
    "residual_likelihood",
    "residual_impact",
    "residual_score",
    "risk_level",
    "qualitative_rationale",
    "mitigation_strategy",
    "owner_id",
    "review_date",
    "status",
    "accepted_until",
    "closed_at",
)


class RiskAssessmentListSerializer(StrictModelSerializer):
    class Meta:
        model = RiskAssessment
        fields = (
            "id",
            "risk_code",
            "name",
            "category",
            "likelihood",
            "impact",
            "inherent_score",
            "residual_score",
            "risk_level",
            "owner_id",
            "review_date",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class RiskAssessmentDetailSerializer(StrictModelSerializer):
    class Meta:
        model = RiskAssessment
        fields = RISK_DETAIL_FIELDS
        read_only_fields = fields


class RiskAssessmentCreateSerializer(StrictModelSerializer):
    idempotency_key = serializers.CharField(max_length=255, required=False, write_only=True)

    class Meta:
        model = RiskAssessment
        fields = (
            "risk_code",
            "name",
            "category",
            "description",
            "likelihood",
            "impact",
            "residual_likelihood",
            "residual_impact",
            "qualitative_rationale",
            "mitigation_strategy",
            "owner_id",
            "review_date",
            "idempotency_key",
        )
        extra_kwargs = {
            name: {"required": True}
            for name in (
                "risk_code",
                "name",
                "category",
                "description",
                "likelihood",
                "impact",
                "owner_id",
                "review_date",
            )
        }

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        left, right = attrs.get("residual_likelihood"), attrs.get("residual_impact")
        if (left is None) != (right is None):
            raise serializers.ValidationError(
                {"residual_likelihood": "Residual likelihood and impact must be supplied together."}
            )
        return attrs


class RiskAssessmentUpdateSerializer(RiskAssessmentCreateSerializer):
    class Meta(RiskAssessmentCreateSerializer.Meta):
        fields = tuple(name for name in RiskAssessmentCreateSerializer.Meta.fields if name != "idempotency_key")
        extra_kwargs: dict[str, dict[str, bool]] = {}


class RiskTransitionSerializer(StrictSerializer):
    command = serializers.ChoiceField(choices=("assess", "start_mitigation", "accept", "close", "reopen"))
    transition_key = serializers.CharField(max_length=255)
    context = serializers.JSONField(default=dict)


class RiskScorePreviewSerializer(StrictSerializer):
    likelihood = serializers.IntegerField(min_value=1, max_value=10)
    impact = serializers.IntegerField(min_value=1, max_value=10)
    residual_likelihood = serializers.IntegerField(min_value=1, max_value=10, required=False, allow_null=True)
    residual_impact = serializers.IntegerField(min_value=1, max_value=10, required=False, allow_null=True)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if (attrs.get("residual_likelihood") is None) != (attrs.get("residual_impact") is None):
            raise serializers.ValidationError("Residual likelihood and impact must be supplied together.")
        return attrs


class RiskScoreResultSerializer(serializers.Serializer):
    """Render calculated scores with the same fixed-scale contract as models."""

    inherent_score = serializers.DecimalField(max_digits=7, decimal_places=2, read_only=True)
    residual_score = serializers.DecimalField(
        max_digits=7,
        decimal_places=2,
        allow_null=True,
        read_only=True,
    )
    risk_level = serializers.CharField(read_only=True)
    likelihood_scale_max = serializers.IntegerField(read_only=True)
    impact_scale_max = serializers.IntegerField(read_only=True)
    explanation = serializers.JSONField(read_only=True)


CONTROL_FIELDS = (
    *AUDIT_READ_ONLY,
    "risk",
    "control_code",
    "name",
    "description",
    "test_procedure",
    "frequency",
    "frequency_days",
    "owner_id",
    "default_tester_id",
    "next_test_due",
    "status",
)


class ControlListSerializer(StrictModelSerializer):
    risk_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Control
        fields = (
            "id",
            "risk_id",
            "control_code",
            "name",
            "frequency",
            "owner_id",
            "next_test_due",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ControlDetailSerializer(StrictModelSerializer):
    risk_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Control
        fields = tuple("risk_id" if name == "risk" else name for name in CONTROL_FIELDS)
        read_only_fields = fields


class ControlCreateSerializer(StrictModelSerializer):
    class Meta:
        model = Control
        fields = (
            "control_code",
            "name",
            "description",
            "test_procedure",
            "frequency",
            "frequency_days",
            "owner_id",
            "default_tester_id",
            "next_test_due",
        )


class ControlUpdateSerializer(ControlCreateSerializer):
    pass


class ControlTransitionSerializer(StrictSerializer):
    command = serializers.ChoiceField(choices=("activate", "retire", "reactivate"))
    transition_key = serializers.CharField(max_length=255)


class EvidenceItemSerializer(StrictSerializer):
    document_id = serializers.UUIDField()
    version_id = serializers.UUIDField()
    label = serializers.CharField(max_length=255)
    checksum = serializers.RegexField(r"^[A-Fa-f0-9]{32,128}$")


TEST_FIELDS = (
    *AUDIT_READ_ONLY,
    "control",
    "scheduled_for",
    "started_at",
    "completed_at",
    "tester_id",
    "result",
    "findings",
    "evidence",
    "status",
    "cancellation_reason",
)


class ControlTestListSerializer(StrictModelSerializer):
    control_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ControlTest
        fields = ("id", "control_id", "scheduled_for", "tester_id", "result", "status", "started_at", "completed_at")
        read_only_fields = fields


class ControlTestDetailSerializer(StrictModelSerializer):
    control_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ControlTest
        fields = tuple("control_id" if name == "control" else name for name in TEST_FIELDS)
        read_only_fields = fields


class ControlTestCreateSerializer(StrictModelSerializer):
    idempotency_key = serializers.CharField(max_length=255, write_only=True)

    class Meta:
        model = ControlTest
        fields = ("scheduled_for", "tester_id", "idempotency_key")


class ControlTestUpdateSerializer(StrictModelSerializer):
    class Meta:
        model = ControlTest
        fields = ("scheduled_for", "tester_id")


class ControlTestTransitionSerializer(StrictSerializer):
    transition_key = serializers.CharField(max_length=255)


class ControlTestResultSerializer(ControlTestTransitionSerializer):
    result = serializers.ChoiceField(choices=("passed", "failed", "partially_passed"))
    findings = serializers.CharField(required=False, allow_blank=True)
    evidence = EvidenceItemSerializer(many=True, required=False, default=list)
    remediation = serializers.JSONField(required=False)


class ControlTestCancelSerializer(ControlTestTransitionSerializer):
    reason = serializers.CharField(allow_blank=False)


REQUIREMENT_FIELDS = (
    *AUDIT_READ_ONLY,
    "regulation_code",
    "requirement_code",
    "regulation_name",
    "title",
    "description",
    "applicability",
    "applicability_rationale",
    "status",
    "owner_id",
    "effective_date",
    "due_date",
    "last_assessed_at",
    "source_url",
    "cross_references",
)


class RequirementListSerializer(StrictModelSerializer):
    class Meta:
        model = ComplianceRequirement
        fields = (
            "id",
            "regulation_code",
            "requirement_code",
            "regulation_name",
            "title",
            "applicability",
            "status",
            "owner_id",
            "effective_date",
            "due_date",
            "last_assessed_at",
        )
        read_only_fields = fields


class RequirementDetailSerializer(StrictModelSerializer):
    class Meta:
        model = ComplianceRequirement
        fields = REQUIREMENT_FIELDS
        read_only_fields = fields


class RequirementCreateSerializer(StrictModelSerializer):
    class Meta:
        model = ComplianceRequirement
        fields = (
            "regulation_code",
            "requirement_code",
            "regulation_name",
            "title",
            "description",
            "applicability",
            "applicability_rationale",
            "owner_id",
            "effective_date",
            "due_date",
            "source_url",
            "cross_references",
        )


class RequirementUpdateSerializer(RequirementCreateSerializer):
    pass


class RequirementTransitionSerializer(StrictSerializer):
    command = serializers.ChoiceField(
        choices=("assess_compliant", "assess_partial", "assess_non_compliant", "remediate")
    )
    rationale = serializers.CharField(allow_blank=False)
    evidence = EvidenceItemSerializer(many=True, required=False, default=list)
    transition_key = serializers.CharField(max_length=255)


CALENDAR_FIELDS = (
    *AUDIT_READ_ONLY,
    "requirement",
    "title",
    "event_type",
    "scheduled_date",
    "reminder_days",
    "assigned_to_id",
    "status",
    "completed_date",
    "completion_notes",
)


class CalendarEntryListSerializer(StrictModelSerializer):
    requirement_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ComplianceCalendarEntry
        fields = (
            "id",
            "requirement_id",
            "title",
            "event_type",
            "scheduled_date",
            "reminder_days",
            "assigned_to_id",
            "status",
            "completed_date",
        )
        read_only_fields = fields


class CalendarEntryDetailSerializer(StrictModelSerializer):
    requirement_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ComplianceCalendarEntry
        fields = tuple("requirement_id" if name == "requirement" else name for name in CALENDAR_FIELDS)
        read_only_fields = fields


class CalendarEntryCreateSerializer(StrictModelSerializer):
    requirement_id = serializers.UUIDField()

    class Meta:
        model = ComplianceCalendarEntry
        fields = ("requirement_id", "title", "event_type", "scheduled_date", "reminder_days", "assigned_to_id")


class CalendarEntryUpdateSerializer(CalendarEntryCreateSerializer):
    pass


class CalendarEntryTransitionSerializer(StrictSerializer):
    command = serializers.ChoiceField(choices=("complete", "cancel"))
    transition_key = serializers.CharField(max_length=255)
    context = serializers.JSONField(default=dict)


REMEDIATION_FIELDS = (
    *AUDIT_READ_ONLY,
    "risk",
    "control_test",
    "action_code",
    "description",
    "assigned_to_id",
    "due_date",
    "priority",
    "status",
    "completion_date",
    "completion_evidence",
    "cancellation_reason",
)


class RemediationListSerializer(StrictModelSerializer):
    risk_id = serializers.UUIDField(read_only=True)
    control_test_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = RemediationAction
        fields = (
            "id",
            "risk_id",
            "control_test_id",
            "action_code",
            "assigned_to_id",
            "due_date",
            "priority",
            "status",
            "completion_date",
        )
        read_only_fields = fields


class RemediationDetailSerializer(StrictModelSerializer):
    risk_id = serializers.UUIDField(read_only=True)
    control_test_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = RemediationAction
        fields = tuple(
            "risk_id" if name == "risk" else "control_test_id" if name == "control_test" else name
            for name in REMEDIATION_FIELDS
        )
        read_only_fields = fields


class RemediationCreateSerializer(StrictModelSerializer):
    control_test_id = serializers.UUIDField(required=False, allow_null=True)

    class Meta:
        model = RemediationAction
        fields = ("control_test_id", "action_code", "description", "assigned_to_id", "due_date", "priority")


class RemediationUpdateSerializer(RemediationCreateSerializer):
    pass


class RemediationTransitionSerializer(StrictSerializer):
    command = serializers.ChoiceField(choices=("start", "complete", "cancel"))
    transition_key = serializers.CharField(max_length=255)
    context = serializers.JSONField(default=dict)


class DashboardSummarySerializer(StrictSerializer):
    total_risks = serializers.IntegerField(min_value=0)
    critical_risks = serializers.IntegerField(min_value=0)
    risks_by_level = serializers.DictField(child=serializers.IntegerField(min_value=0))
    risks_by_status = serializers.DictField(child=serializers.IntegerField(min_value=0))
    overdue_reviews = serializers.IntegerField(min_value=0)
    overdue_controls = serializers.IntegerField(min_value=0)
    overdue_calendar = serializers.IntegerField(min_value=0)
    overdue_remediations = serializers.IntegerField(min_value=0)
    upcoming_events = serializers.IntegerField(min_value=0)
    upcoming_compliance_events = CalendarEntryListSerializer(many=True)
    overdue_work = serializers.ListField(child=serializers.DictField())


class HeatmapCellSerializer(StrictSerializer):
    likelihood = serializers.IntegerField()
    impact = serializers.IntegerField()
    count = serializers.IntegerField(min_value=0)
    level = serializers.ChoiceField(choices=("negligible", "low", "medium", "high", "critical"))
    risk_ids = serializers.ListField(child=serializers.UUIDField())


CONFIG_FIELDS = (
    "id",
    "tenant_id",
    "environment",
    "version",
    "likelihood_scale_max",
    "impact_scale_max",
    "level_thresholds",
    "default_review_days",
    "default_reminder_days",
    "acceptance_max_days",
    "overdue_job_enabled",
    "feature_flags",
    "extension_config",
    "published_at",
    "published_by_id",
    "created_at",
    "updated_at",
)


class RiskConfigurationSerializer(StrictModelSerializer):
    class Meta:
        model = RiskConfiguration
        fields = CONFIG_FIELDS
        read_only_fields = fields


class RiskConfigurationPublishSerializer(StrictSerializer):
    environment = serializers.ChoiceField(choices=("development", "staging", "production"))
    expected_version = serializers.IntegerField(min_value=0)
    change_summary = serializers.CharField(max_length=500)
    candidate = serializers.JSONField()


class RiskConfigurationPreviewSerializer(RiskConfigurationPublishSerializer):
    expected_version = serializers.IntegerField(min_value=0, required=False)
    change_summary = serializers.CharField(required=False, allow_blank=True)


class RiskConfigurationVersionSerializer(StrictModelSerializer):
    class Meta:
        model = RiskConfigurationVersion
        fields = (
            "id",
            "tenant_id",
            "environment",
            "version",
            "configuration",
            "change_summary",
            "actor_id",
            "correlation_id",
            "created_at",
            "restored_from_version",
        )
        read_only_fields = fields


class ConfigurationRollbackSerializer(StrictSerializer):
    environment = serializers.ChoiceField(choices=("development", "staging", "production"))
    version = serializers.IntegerField(min_value=1)
    expected_version = serializers.IntegerField(min_value=1)
    change_summary = serializers.CharField(required=False, allow_blank=True, max_length=500)


class ConfigurationImportSerializer(StrictSerializer):
    environment = serializers.ChoiceField(choices=("development", "staging", "production"))
    dry_run = serializers.BooleanField(required=True)
    document = serializers.JSONField()
    expected_version = serializers.IntegerField(required=False, min_value=0)
    change_summary = serializers.CharField(required=False, allow_blank=True, max_length=500)


# Backward-compatible read alias; new code must use operation-specific classes.
ComplianceRiskSerializer = RiskAssessmentDetailSerializer
