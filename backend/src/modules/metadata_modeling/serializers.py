from rest_framework import serializers
from .models import EntityDefinition, FieldDefinition, DynamicResource


class FieldDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FieldDefinition
        fields = [
            "id",
            "name",
            "key",
            "field_type",
            "is_required",
            "default_value",
            "validation_rules",
            "options",
            "order",
        ]


class EntityDefinitionSerializer(serializers.ModelSerializer):
    fields = FieldDefinitionSerializer(many=True, read_only=True)

    class Meta:
        model = EntityDefinition
        fields = ["id", "name", "code", "description", "is_system", "fields", "created_at"]


class DynamicResourceSerializer(serializers.ModelSerializer):
    data = serializers.JSONField()

    class Meta:
        model = DynamicResource
        fields = ["id", "entity_definition", "data", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
