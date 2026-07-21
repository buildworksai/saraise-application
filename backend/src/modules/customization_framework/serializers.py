"""Operation-specific serializers for the governed customization API."""

from __future__ import annotations

import json
from collections.abc import Mapping

from rest_framework import serializers
from src.core.api import CapabilityUnavailable

from .models import (
    BusinessRule,
    BusinessRuleVersion,
    CustomFieldDefinition,
    CustomFieldValue,
    FormDefinition,
    FormLayoutVersion,
    RuleExecution,
)
from .services import (
    MAX_JSON_BYTES,
    CustomFieldService,
    CustomizationRegistry,
    FormService,
    ResourceContract,
)


class StrictSerializerMixin:
    """Reject undeclared request keys instead of silently discarding them."""

    def to_internal_value(self, data: object) -> object:
        if isinstance(data, Mapping):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: ["Unknown field."] for key in sorted(unknown)})
        return super().to_internal_value(data)  # type: ignore[misc]


def _bounded_json(value: object, label: str) -> object:
    try:
        size = len(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode())
    except (TypeError, ValueError) as exc:
        raise serializers.ValidationError(f"{label} must be valid JSON.") from exc
    if size > MAX_JSON_BYTES:
        raise serializers.ValidationError(f"{label} exceeds the {MAX_JSON_BYTES}-byte limit.")
    return value


def _capability_state(obj: object) -> str:
    try:
        CustomizationRegistry.resolve_resource_contract(
            getattr(obj, "tenant_id"),
            getattr(obj, "owner_module"),
            getattr(obj, "target_resource"),
            getattr(obj, "target_contract_version"),
        )
    except CapabilityUnavailable:
        return "capability_unavailable"
    return "available"


class StrictModelSerializer(StrictSerializerMixin, serializers.ModelSerializer):
    def to_representation(self, instance: object) -> dict[str, object]:
        data = super().to_representation(instance)
        history = data.get("transition_history")
        if isinstance(history, list):
            data["transition_history"] = [
                {
                    "command": item.get("command"),
                    "from": item.get("from_state"),
                    "to": item.get("to_state"),
                    "actor_id": (item.get("metadata") or {}).get("actor_id"),
                    "occurred_at": item.get("occurred_at"),
                    "correlation_id": (item.get("metadata") or {}).get("correlation_id"),
                }
                for item in history
            ]
        return data


class ResourceContractSerializer(StrictSerializerMixin, serializers.Serializer):
    """Safe discovery metadata for free and paid module target selectors."""

    module = serializers.CharField(read_only=True)
    resource = serializers.CharField(read_only=True)
    version = serializers.CharField(read_only=True)
    fields = serializers.DictField(read_only=True)
    custom_field_types = serializers.ListField(child=serializers.CharField(), read_only=True)
    form_surfaces = serializers.ListField(child=serializers.CharField(), read_only=True)
    rule_triggers = serializers.ListField(child=serializers.CharField(), read_only=True)
    entitlement_keys = serializers.ListField(child=serializers.CharField(), read_only=True)
    available = serializers.BooleanField(read_only=True)
    discovery = serializers.DictField(read_only=True)

    def to_representation(self, instance: ResourceContract) -> dict[str, object]:
        return {
            "module": instance.module,
            "resource": instance.resource,
            "version": instance.version,
            "fields": {key: dict(value) for key, value in instance.fields.items()},
            "custom_field_types": sorted(instance.custom_field_types),
            "form_surfaces": sorted(instance.form_surfaces),
            "rule_triggers": sorted(instance.rule_triggers),
            "entitlement_keys": sorted(instance.entitlement_keys),
            "available": instance.available,
            "discovery": dict(instance.discovery or {}),
        }


FIELD_READ = (
    "id",
    "tenant_id",
    "key",
    "label",
    "description",
    "owner_module",
    "target_resource",
    "target_contract_version",
    "data_type",
    "required",
    "searchable",
    "default_value",
    "validation_schema",
    "presentation_schema",
    "status",
    "activated_at",
    "deprecated_at",
    "retired_at",
    "transition_history",
    "lock_version",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
    "deleted_at",
    "deleted_by",
)


class FieldDefinitionListSerializer(StrictModelSerializer):
    dependency_count = serializers.SerializerMethodField()
    value_count = serializers.SerializerMethodField()
    capability_state = serializers.SerializerMethodField()

    class Meta:
        model = CustomFieldDefinition
        fields = (
            "id",
            "tenant_id",
            "key",
            "label",
            "owner_module",
            "target_resource",
            "data_type",
            "required",
            "searchable",
            "status",
            "lock_version",
            "created_at",
            "updated_at",
            "dependency_count",
            "value_count",
            "capability_state",
        )
        read_only_fields = fields

    def get_value_count(self, obj: CustomFieldDefinition) -> int:
        return obj.values.filter(tenant_id=obj.tenant_id, deleted_at__isnull=True).count()

    def get_dependency_count(self, obj: CustomFieldDefinition) -> int:
        if obj.deleted_at is not None:
            return 0
        return int(CustomFieldService().get_definition_impact(obj.tenant_id, definition_id=obj.id)["dependency_count"])

    def get_capability_state(self, obj: CustomFieldDefinition) -> str:
        return _capability_state(obj)


class FieldDefinitionDetailSerializer(StrictModelSerializer):
    dependency_count = serializers.SerializerMethodField()
    value_count = serializers.SerializerMethodField()
    capability_state = serializers.SerializerMethodField()

    class Meta:
        model = CustomFieldDefinition
        fields = FIELD_READ + ("dependency_count", "value_count", "capability_state")
        read_only_fields = fields

    def get_value_count(self, obj: CustomFieldDefinition) -> int:
        return obj.values.filter(tenant_id=obj.tenant_id, deleted_at__isnull=True).count()

    def get_dependency_count(self, obj: CustomFieldDefinition) -> int:
        if obj.deleted_at is not None:
            return 0
        return int(CustomFieldService().get_definition_impact(obj.tenant_id, definition_id=obj.id)["dependency_count"])

    def get_capability_state(self, obj: CustomFieldDefinition) -> str:
        return _capability_state(obj)


class FieldDefinitionCreateSerializer(StrictModelSerializer):
    class Meta:
        model = CustomFieldDefinition
        fields = (
            "key",
            "label",
            "description",
            "owner_module",
            "target_resource",
            "target_contract_version",
            "data_type",
            "required",
            "searchable",
            "default_value",
            "validation_schema",
            "presentation_schema",
        )

    def validate_key(self, value: str) -> str:
        return value.strip().lower()

    def validate_owner_module(self, value: str) -> str:
        return value.strip().lower()

    def validate_target_resource(self, value: str) -> str:
        return value.strip().lower()

    def validate_validation_schema(self, value: object) -> object:
        return _bounded_json(value, "validation_schema")

    def validate_presentation_schema(self, value: object) -> object:
        return _bounded_json(value, "presentation_schema")

    def validate_default_value(self, value: object) -> object:
        return _bounded_json(value, "default_value")


class FieldDefinitionUpdateSerializer(FieldDefinitionCreateSerializer):
    expected_lock_version = serializers.IntegerField(min_value=1, write_only=True)

    class Meta(FieldDefinitionCreateSerializer.Meta):
        fields = FieldDefinitionCreateSerializer.Meta.fields + ("expected_lock_version",)
        extra_kwargs = {key: {"required": False} for key in FieldDefinitionCreateSerializer.Meta.fields}


class FieldTransitionSerializer(StrictSerializerMixin, serializers.Serializer):
    transition_key = serializers.CharField(min_length=1, max_length=128, trim_whitespace=True)


class ValueValidationSerializer(StrictSerializerMixin, serializers.Serializer):
    value = serializers.JSONField()
    target_record_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_value(self, value: object) -> object:
        return _bounded_json(value, "value")


VALUE_READ = (
    "id",
    "tenant_id",
    "definition_id",
    "definition_key",
    "target_record_id",
    "value",
    "definition_revision",
    "source",
    "lock_version",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
    "deleted_at",
    "deleted_by",
)


class FieldValueListSerializer(StrictModelSerializer):
    definition_id = serializers.UUIDField(read_only=True)
    definition_key = serializers.CharField(source="definition.key", read_only=True)

    class Meta:
        model = CustomFieldValue
        fields = (
            "id",
            "tenant_id",
            "definition_id",
            "definition_key",
            "target_record_id",
            "value",
            "definition_revision",
            "source",
            "lock_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class FieldValueDetailSerializer(StrictModelSerializer):
    definition_id = serializers.UUIDField(read_only=True)
    definition_key = serializers.CharField(source="definition.key", read_only=True)

    class Meta:
        model = CustomFieldValue
        fields = VALUE_READ
        read_only_fields = fields


class FieldValueCreateSerializer(StrictSerializerMixin, serializers.Serializer):
    definition_id = serializers.UUIDField()
    target_record_id = serializers.UUIDField()
    value = serializers.JSONField()
    source = serializers.ChoiceField(choices=("ui", "api", "import"), default="api")

    def validate_value(self, value: object) -> object:
        return _bounded_json(value, "value")


class FieldValueUpdateSerializer(StrictSerializerMixin, serializers.Serializer):
    value = serializers.JSONField()
    source = serializers.ChoiceField(choices=("ui", "api", "import"), default="api")
    expected_lock_version = serializers.IntegerField(min_value=1)

    def validate_value(self, value: object) -> object:
        return _bounded_json(value, "value")


FORM_READ = (
    "id",
    "tenant_id",
    "key",
    "name",
    "description",
    "owner_module",
    "target_resource",
    "target_contract_version",
    "status",
    "published_version",
    "published_at",
    "published_by",
    "archived_at",
    "transition_history",
    "lock_version",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
    "deleted_at",
    "deleted_by",
)


class FormListSerializer(StrictModelSerializer):
    dependency_count = serializers.SerializerMethodField()
    capability_state = serializers.SerializerMethodField()

    class Meta:
        model = FormDefinition
        fields = (
            "id",
            "tenant_id",
            "key",
            "name",
            "owner_module",
            "target_resource",
            "status",
            "published_version",
            "lock_version",
            "created_at",
            "updated_at",
            "dependency_count",
            "capability_state",
        )
        read_only_fields = fields

    def get_dependency_count(self, obj: FormDefinition) -> int:
        if obj.deleted_at is not None:
            return 0
        return int(FormService().get_form_impact(obj.tenant_id, form_id=obj.id)["dependency_count"])

    def get_capability_state(self, obj: FormDefinition) -> str:
        return _capability_state(obj)


class FormDetailSerializer(StrictModelSerializer):
    dependency_count = serializers.SerializerMethodField()
    capability_state = serializers.SerializerMethodField()

    class Meta:
        model = FormDefinition
        fields = FORM_READ + ("dependency_count", "capability_state")
        read_only_fields = fields

    def get_dependency_count(self, obj: FormDefinition) -> int:
        if obj.deleted_at is not None:
            return 0
        return int(FormService().get_form_impact(obj.tenant_id, form_id=obj.id)["dependency_count"])

    def get_capability_state(self, obj: FormDefinition) -> str:
        return _capability_state(obj)


class FormCreateSerializer(StrictModelSerializer):
    class Meta:
        model = FormDefinition
        fields = ("key", "name", "description", "owner_module", "target_resource", "target_contract_version")

    def validate_key(self, value: str) -> str:
        return value.strip().lower()

    def validate_owner_module(self, value: str) -> str:
        return value.strip().lower()

    def validate_target_resource(self, value: str) -> str:
        return value.strip().lower()


class FormUpdateSerializer(FormCreateSerializer):
    expected_lock_version = serializers.IntegerField(min_value=1, write_only=True)

    class Meta(FormCreateSerializer.Meta):
        fields = FormCreateSerializer.Meta.fields + ("expected_lock_version",)
        extra_kwargs = {key: {"required": False} for key in FormCreateSerializer.Meta.fields}


class LayoutVersionCreateSerializer(StrictSerializerMixin, serializers.Serializer):
    layout = serializers.JSONField()
    change_summary = serializers.CharField(min_length=1, max_length=500, trim_whitespace=True)

    def validate_layout(self, value: object) -> object:
        return _bounded_json(value, "layout")


class LayoutValidationSerializer(StrictSerializerMixin, serializers.Serializer):
    layout = serializers.JSONField()

    def validate_layout(self, value: object) -> object:
        return _bounded_json(value, "layout")


class LayoutVersionDetailSerializer(StrictModelSerializer):
    form_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = FormLayoutVersion
        fields = (
            "id",
            "tenant_id",
            "form",
            "form_id",
            "version",
            "schema_version",
            "layout",
            "content_hash",
            "change_summary",
            "status",
            "validation_errors",
            "created_by",
            "created_at",
            "published_at",
            "published_by",
        )
        read_only_fields = fields


class FormPublishSerializer(FieldTransitionSerializer):
    layout_version_id = serializers.UUIDField()


RULE_READ = (
    "id",
    "tenant_id",
    "key",
    "name",
    "description",
    "owner_module",
    "target_resource",
    "target_contract_version",
    "trigger",
    "priority",
    "stop_on_match",
    "status",
    "published_version",
    "published_at",
    "published_by",
    "transition_history",
    "lock_version",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
    "deleted_at",
    "deleted_by",
)


class RuleListSerializer(StrictModelSerializer):
    execution_count = serializers.SerializerMethodField()
    diagnostic_count = serializers.SerializerMethodField()
    capability_state = serializers.SerializerMethodField()

    class Meta:
        model = BusinessRule
        fields = (
            "id",
            "tenant_id",
            "key",
            "name",
            "owner_module",
            "target_resource",
            "trigger",
            "priority",
            "stop_on_match",
            "status",
            "published_version",
            "lock_version",
            "created_at",
            "updated_at",
            "execution_count",
            "diagnostic_count",
            "capability_state",
        )
        read_only_fields = fields

    def get_execution_count(self, obj: BusinessRule) -> int:
        return obj.executions.filter(tenant_id=obj.tenant_id).count()

    def get_diagnostic_count(self, obj: BusinessRule) -> int:
        return sum(
            len(item)
            for item in obj.versions.filter(tenant_id=obj.tenant_id).values_list("validation_errors", flat=True)
        )

    def get_capability_state(self, obj: BusinessRule) -> str:
        return _capability_state(obj)


class RuleDetailSerializer(StrictModelSerializer):
    execution_count = serializers.SerializerMethodField()
    diagnostic_count = serializers.SerializerMethodField()
    capability_state = serializers.SerializerMethodField()

    class Meta:
        model = BusinessRule
        fields = RULE_READ + ("execution_count", "diagnostic_count", "capability_state")
        read_only_fields = fields

    def get_execution_count(self, obj: BusinessRule) -> int:
        return obj.executions.filter(tenant_id=obj.tenant_id).count()

    def get_diagnostic_count(self, obj: BusinessRule) -> int:
        return sum(
            len(item)
            for item in obj.versions.filter(tenant_id=obj.tenant_id).values_list("validation_errors", flat=True)
        )

    def get_capability_state(self, obj: BusinessRule) -> str:
        return _capability_state(obj)


class RuleCreateSerializer(StrictModelSerializer):
    class Meta:
        model = BusinessRule
        fields = (
            "key",
            "name",
            "description",
            "owner_module",
            "target_resource",
            "target_contract_version",
            "trigger",
            "priority",
            "stop_on_match",
        )

    def validate_key(self, value: str) -> str:
        return value.strip().lower()

    def validate_owner_module(self, value: str) -> str:
        return value.strip().lower()

    def validate_target_resource(self, value: str) -> str:
        return value.strip().lower()


class RuleUpdateSerializer(RuleCreateSerializer):
    expected_lock_version = serializers.IntegerField(min_value=1, write_only=True)

    class Meta(RuleCreateSerializer.Meta):
        fields = RuleCreateSerializer.Meta.fields + ("expected_lock_version",)
        extra_kwargs = {key: {"required": False} for key in RuleCreateSerializer.Meta.fields}


class RuleVersionCreateSerializer(StrictSerializerMixin, serializers.Serializer):
    condition_ast = serializers.JSONField()
    action_ast = serializers.JSONField()
    change_summary = serializers.CharField(min_length=1, max_length=500, trim_whitespace=True)

    def validate_condition_ast(self, value: object) -> object:
        return _bounded_json(value, "condition_ast")

    def validate_action_ast(self, value: object) -> object:
        return _bounded_json(value, "action_ast")


class RuleVersionValidationSerializer(StrictSerializerMixin, serializers.Serializer):
    condition_ast = serializers.JSONField()
    action_ast = serializers.JSONField()

    def validate_condition_ast(self, value: object) -> object:
        return _bounded_json(value, "condition_ast")

    def validate_action_ast(self, value: object) -> object:
        return _bounded_json(value, "action_ast")


class RuleVersionDetailSerializer(StrictModelSerializer):
    rule_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = BusinessRuleVersion
        fields = (
            "id",
            "tenant_id",
            "rule",
            "rule_id",
            "version",
            "language_version",
            "condition_ast",
            "action_ast",
            "dependencies",
            "content_hash",
            "status",
            "validation_errors",
            "change_summary",
            "created_by",
            "created_at",
            "published_at",
            "published_by",
        )
        read_only_fields = fields


class RulePublishSerializer(FieldTransitionSerializer):
    version_id = serializers.UUIDField()


class RuleEvaluateSerializer(StrictSerializerMixin, serializers.Serializer):
    record = serializers.JSONField()
    changed_fields = serializers.ListField(child=serializers.SlugField(max_length=100), default=list)
    target_record_id = serializers.UUIDField(required=False, allow_null=True)
    idempotency_key = serializers.CharField(min_length=1, max_length=128, trim_whitespace=True)

    def validate_record(self, value: object) -> object:
        if not isinstance(value, Mapping):
            raise serializers.ValidationError("record must be an object.")
        return _bounded_json(value, "record")


class RuleExecutionListSerializer(StrictModelSerializer):
    rule_id = serializers.UUIDField(read_only=True)
    rule_version_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = RuleExecution
        fields = (
            "id",
            "tenant_id",
            "rule",
            "rule_id",
            "rule_version",
            "rule_version_id",
            "target_record_id",
            "trigger",
            "status",
            "duration_ms",
            "correlation_id",
            "executed_by",
            "executed_at",
        )
        read_only_fields = fields


class RuleExecutionDetailSerializer(StrictModelSerializer):
    rule_id = serializers.UUIDField(read_only=True)
    rule_version_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = RuleExecution
        fields = (
            "id",
            "tenant_id",
            "rule",
            "rule_id",
            "rule_version",
            "rule_version_id",
            "target_record_id",
            "trigger",
            "idempotency_key",
            "status",
            "input_fingerprint",
            "result",
            "diagnostics",
            "duration_ms",
            "correlation_id",
            "executed_by",
            "executed_at",
        )
        read_only_fields = fields


class ImpactReportSerializer(StrictSerializerMixin, serializers.Serializer):
    entity_type = serializers.CharField(read_only=True)
    entity_id = serializers.UUIDField(read_only=True)
    dependency_count = serializers.IntegerField(read_only=True)
    blocking = serializers.BooleanField(read_only=True)
    capability_unavailable = serializers.BooleanField(read_only=True)
    value_count = serializers.IntegerField(read_only=True, required=False)
    version_count = serializers.IntegerField(read_only=True, required=False)
    layout_version_count = serializers.IntegerField(read_only=True, required=False)
    execution_count = serializers.IntegerField(read_only=True, required=False)
    field_references = serializers.ListField(child=serializers.CharField(), read_only=True, required=False)
    forms = serializers.ListField(child=serializers.DictField(), read_only=True, required=False)
    rules = serializers.ListField(child=serializers.DictField(), read_only=True, required=False)


class HealthSerializer(StrictSerializerMixin, serializers.Serializer):
    status = serializers.ChoiceField(choices=("healthy", "degraded", "unavailable"), read_only=True)
    live = serializers.BooleanField(read_only=True)
    ready = serializers.BooleanField(read_only=True)
    checked_at = serializers.DateTimeField(read_only=True)
    checks = serializers.DictField(read_only=True)


__all__ = [name for name in globals() if name.endswith("Serializer")]
