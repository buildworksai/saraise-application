"""Strict read/write DTO boundaries for metadata-modeling API v2."""

from __future__ import annotations

from rest_framework import serializers

from .models import (
    DynamicResource, DynamicResourceVersion, EntityDefinition, EntitySchemaVersion,
    FieldDefinition, MetadataConfigurationAudit, MetadataModelingConfiguration, NamingSequence,
)


class FieldDefinitionReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = FieldDefinition
        fields = (
            "id", "name", "key", "field_type", "is_required", "is_read_only", "is_searchable",
            "default_value", "validation_rules", "options", "reference_entity_code", "help_text",
            "placeholder", "order", "created_at",
        )
        read_only_fields = fields


class FieldDefinitionWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    key = serializers.RegexField(r"^[a-z][a-z0-9_]*$", max_length=100)
    field_type = serializers.ChoiceField(choices=FieldDefinition.FieldType.choices)
    is_required = serializers.BooleanField(default=False)
    is_read_only = serializers.BooleanField(default=False)
    is_searchable = serializers.BooleanField(default=False)
    default_value = serializers.JSONField(required=False, allow_null=True, default=None)
    validation_rules = serializers.DictField(required=False, default=dict)
    options = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    reference_entity_code = serializers.SlugField(max_length=100, required=False, allow_blank=True, allow_null=True)
    help_text = serializers.CharField(required=False, allow_blank=True, default="")
    placeholder = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    order = serializers.IntegerField(min_value=0)


class EntityDefinitionListSerializer(serializers.ModelSerializer):
    active_version_number = serializers.IntegerField(source="active_version.version", read_only=True, allow_null=True)
    record_count = serializers.SerializerMethodField()

    class Meta:
        model = EntityDefinition
        fields = (
            "id", "name", "plural_name", "code", "description", "owner_module", "origin", "status", "icon",
            "active_version",
            "active_version_number", "record_count", "lock_version", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_record_count(self, obj: EntityDefinition) -> int:
        annotated = getattr(obj, "record_count", None)
        return int(annotated if annotated is not None else obj.resources.filter(deleted_at__isnull=True).count())


class EntitySchemaVersionListSerializer(serializers.ModelSerializer):
    validation_report = serializers.SerializerMethodField()

    class Meta:
        model = EntitySchemaVersion
        fields = (
            "id", "version", "status", "schema_hash", "change_summary", "compatibility",
            "validation_report", "based_on_version", "published_at", "published_by", "created_by", "created_at",
        )
        read_only_fields = fields

    def get_validation_report(self, obj: EntitySchemaVersion):
        report = dict(obj.validation_report or {})
        return {
            "valid": bool(report.get("valid", False)),
            "compatibility": report.get("compatibility", obj.compatibility),
            "resource_count": int(report.get("resource_count", report.get("resources_scanned", 0))),
            "incompatible_resource_count": int(
                report.get("incompatible_resource_count", report.get("incompatible_resources", 0))
            ),
            "errors": report.get("errors", []),
            "warnings": report.get("warnings", []),
        }


class EntitySchemaVersionDetailSerializer(EntitySchemaVersionListSerializer):
    fields = FieldDefinitionReadSerializer(many=True, read_only=True)

    class Meta(EntitySchemaVersionListSerializer.Meta):
        fields = EntitySchemaVersionListSerializer.Meta.fields + ("entity_definition", "schema", "fields")


class EntityDefinitionDetailSerializer(EntityDefinitionListSerializer):
    current_version = EntitySchemaVersionListSerializer(source="active_version", read_only=True)
    active_fields = serializers.SerializerMethodField()

    class Meta(EntityDefinitionListSerializer.Meta):
        fields = EntityDefinitionListSerializer.Meta.fields + (
            "description", "is_submittable", "track_changes", "naming_strategy", "naming_config",
            "current_version", "active_fields", "created_by", "updated_by", "archived_at", "archived_by",
        )

    def get_active_fields(self, obj: EntityDefinition):
        if obj.active_version_id is None:
            return []
        return FieldDefinitionReadSerializer(obj.active_version.fields.order_by("order"), many=True).data


class EntityDefinitionCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    plural_name = serializers.CharField(max_length=160, required=False)
    code = serializers.SlugField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    owner_module = serializers.SlugField(max_length=100, required=False, default="metadata_modeling")
    icon = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    origin = serializers.ChoiceField(choices=EntityDefinition.Origin.choices, default=EntityDefinition.Origin.CUSTOM)
    is_submittable = serializers.BooleanField(default=False)
    track_changes = serializers.BooleanField(default=True)
    naming_strategy = serializers.ChoiceField(choices=EntityDefinition.NamingStrategy.choices, default="uuid")
    naming_config = serializers.DictField(required=False, default=dict)


class EntityDefinitionUpdateSerializer(EntityDefinitionCreateSerializer):
    code = serializers.SlugField(max_length=100, required=False)
    name = serializers.CharField(max_length=160, required=False)
    plural_name = serializers.CharField(max_length=160, required=False)
    owner_module = serializers.HiddenField(default="metadata_modeling")
    origin = serializers.HiddenField(default="custom")
    lock_version = serializers.IntegerField(min_value=1, write_only=True, required=False)


class EntityDefinitionImportSerializer(serializers.Serializer):
    document = serializers.JSONField()
    mode = serializers.ChoiceField(choices=("create", "new_version", "validate_only"))


class EntityDefinitionPreviewSerializer(serializers.Serializer):
    schema = serializers.DictField(required=False)
    candidate_schema = serializers.JSONField(required=False)
    entity = serializers.DictField(required=False)
    sample_data = serializers.DictField(required=False, allow_null=True)

    def validate(self, attrs):
        schema = attrs.get("schema")
        if schema is None:
            candidate = attrs.get("candidate_schema")
            schema = candidate if isinstance(candidate, dict) else {"fields": candidate}
        if not isinstance(schema, dict) or not isinstance(schema.get("fields"), list):
            raise serializers.ValidationError({"candidate_schema": "A fields array is required."})
        attrs["schema"] = schema
        return attrs


class SchemaCandidateCreateSerializer(serializers.Serializer):
    fields = FieldDefinitionWriteSerializer(many=True)
    based_on_version_id = serializers.UUIDField(required=False, allow_null=True)
    change_summary = serializers.CharField(required=False, allow_blank=True, default="")


class SchemaPublishSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=255, required=False, write_only=True)


class SchemaRollbackSerializer(SchemaPublishSerializer):
    pass


class DynamicResourceListSerializer(serializers.ModelSerializer):
    entity_code = serializers.CharField(source="entity_definition.code", read_only=True)
    entity_name = serializers.CharField(source="entity_definition.name", read_only=True)
    schema_version_number = serializers.IntegerField(source="schema_version.version", read_only=True)
    searchable_data = serializers.SerializerMethodField()

    class Meta:
        model = DynamicResource
        fields = (
            "id", "entity_definition", "entity_code", "entity_name", "schema_version", "schema_version_number",
            "record_key", "display_name", "state", "lock_version", "searchable_data", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_searchable_data(self, obj: DynamicResource):
        keys = [field.key for field in obj.schema_version.fields.all() if field.is_searchable]
        return {key: obj.data.get(key) for key in keys if key in obj.data}


class DynamicResourceDetailSerializer(DynamicResourceListSerializer):
    fields = FieldDefinitionReadSerializer(source="schema_version.fields", many=True, read_only=True)

    class Meta(DynamicResourceListSerializer.Meta):
        fields = DynamicResourceListSerializer.Meta.fields + (
            "data", "fields", "created_by", "updated_by", "submitted_at", "submitted_by", "cancelled_at", "cancelled_by",
        )


class DynamicResourceCreateSerializer(serializers.Serializer):
    entity_id = serializers.UUIDField(required=False)
    entity_definition = serializers.UUIDField(required=False, write_only=True)
    data = serializers.DictField()
    display_name = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, attrs):
        entity_id = attrs.pop("entity_definition", None) or attrs.get("entity_id")
        if entity_id is None:
            raise serializers.ValidationError({"entity_id": [{"code": "REQUIRED", "message": "Entity is required."}]})
        attrs["entity_id"] = entity_id
        return attrs


class DynamicResourceReplaceSerializer(serializers.Serializer):
    data = serializers.DictField()
    display_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    lock_version = serializers.IntegerField(min_value=1, required=False, write_only=True)


class DynamicResourcePatchSerializer(serializers.Serializer):
    data = serializers.DictField(required=False)
    changes = serializers.DictField(required=False)
    display_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    lock_version = serializers.IntegerField(min_value=1, required=False, write_only=True)

    def validate(self, attrs):
        if "data" in attrs and "changes" in attrs:
            raise serializers.ValidationError({"changes": "Supply changes only once."})
        attrs["data"] = attrs.pop("changes", attrs.get("data", {}))
        return attrs


class ResourceTransitionSerializer(serializers.Serializer):
    lock_version = serializers.IntegerField(min_value=1, required=False)
    reason = serializers.CharField(max_length=2000, required=False, allow_blank=False)


class DynamicResourceVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DynamicResourceVersion
        fields = (
            "id", "version", "schema_version", "state", "record_key", "display_name", "data",
            "changed_fields", "operation", "changed_by", "correlation_id", "changed_at",
        )
        read_only_fields = fields


class NamingSequenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NamingSequence
        fields = (
            "id", "entity_definition", "sequence_key", "prefix_template", "next_value", "padding",
            "reset_period", "period_key", "is_active", "created_at", "updated_at",
        )
        read_only_fields = fields


class SequenceResetSerializer(serializers.Serializer):
    next_value = serializers.IntegerField(min_value=1, max_value=9_999_999_999_999)


class MetadataConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetadataModelingConfiguration
        fields = (
            "id", "environment", "version", "synchronous_validation_limit", "max_fields_per_schema",
            "max_schema_bytes", "max_record_data_bytes", "max_regex_length", "default_page_size",
            "max_page_size", "allowed_field_types", "feature_flags", "rollout", "created_by", "updated_by",
            "created_at", "updated_at",
        )
        read_only_fields = fields


class MetadataConfigurationWriteSerializer(serializers.Serializer):
    synchronous_validation_limit = serializers.IntegerField(min_value=1, max_value=10_000, required=False)
    max_fields_per_schema = serializers.IntegerField(min_value=1, max_value=1_000, required=False)
    max_schema_bytes = serializers.IntegerField(min_value=1_024, max_value=10_485_760, required=False)
    max_record_data_bytes = serializers.IntegerField(min_value=128, max_value=10_485_760, required=False)
    max_regex_length = serializers.IntegerField(min_value=1, max_value=4_096, required=False)
    default_page_size = serializers.IntegerField(min_value=1, max_value=1_000, required=False)
    max_page_size = serializers.IntegerField(min_value=1, max_value=1_000, required=False)
    allowed_field_types = serializers.ListField(child=serializers.ChoiceField(choices=FieldDefinition.FieldType.choices), required=False)
    feature_flags = serializers.DictField(child=serializers.BooleanField(), required=False)
    rollout = serializers.DictField(required=False)


class MetadataConfigurationAuditSerializer(serializers.ModelSerializer):
    before = serializers.SerializerMethodField()
    after = serializers.SerializerMethodField()
    changes = serializers.SerializerMethodField()

    class Meta:
        model = MetadataConfigurationAudit
        fields = (
            "id", "version", "operation", "before", "after", "changes",
            "changed_by", "correlation_id", "changed_at",
        )
        read_only_fields = fields

    def get_before(self, obj: MetadataConfigurationAudit):
        values = self._values(obj.before)
        return values or None

    def get_after(self, obj: MetadataConfigurationAudit):
        return self._values(obj.after)

    @staticmethod
    def _values(document):
        excluded = {"format_version", "environment", "version"}
        return {key: value for key, value in document.items() if key not in excluded}

    def get_changes(self, obj: MetadataConfigurationAudit):
        before = self._values(obj.before)
        after = self._values(obj.after)
        keys = sorted(set(before) | set(after))
        return [
            {"path": key, "before": before.get(key), "after": after.get(key)}
            for key in keys
            if before.get(key) != after.get(key)
        ]


# Compatibility aliases are read-only; all v2 mutations use dedicated DTOs.
FieldDefinitionSerializer = FieldDefinitionReadSerializer
EntityDefinitionSerializer = EntityDefinitionDetailSerializer
DynamicResourceSerializer = DynamicResourceDetailSerializer
