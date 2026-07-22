"""Operation-specific serializers for the governed BI v2 contract."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from rest_framework import serializers

from .models import Dashboard, DashboardShare, DashboardWidget, QueryDefinition, QueryExecution, Report

CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
SUPPORTED_OPERATORS = {"eq", "ne", "neq", "in", "not_in", "gt", "gte", "lt", "lte", "contains", "is_null"}
SCALAR_TYPES = {"string", "integer", "number", "boolean", "date", "datetime", "uuid"}


class RejectUnknownFieldsMixin:
    """Reject typos instead of silently accepting an unstable request contract."""

    def to_internal_value(self, data: Any) -> Any:
        if hasattr(data, "keys"):
            unknown = set(data.keys()) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: ["Unknown field."] for key in sorted(unknown)})
        return super().to_internal_value(data)


class CodeField(serializers.CharField):
    def to_internal_value(self, data: Any) -> str:
        value = super().to_internal_value(data).strip().upper()
        if not CODE_RE.fullmatch(value):
            raise serializers.ValidationError(
                "Use 1-64 uppercase letters, digits, or underscores; start with a letter."
            )
        return value


class FilterListField(serializers.ListField):
    child = serializers.DictField()

    def to_internal_value(self, data: Any) -> list[dict[str, Any]]:
        values = super().to_internal_value(data)
        for index, item in enumerate(values):
            if set(item) - {"field", "operator", "value", "parameter"}:
                raise serializers.ValidationError(f"Filter {index} contains unsupported keys.")
            if not isinstance(item.get("field"), str) or not item["field"].strip():
                raise serializers.ValidationError(f"Filter {index} requires a field.")
            if item.get("operator") not in SUPPORTED_OPERATORS:
                raise serializers.ValidationError(f"Filter {index} has an unsupported operator.")
            if "value" in item and "parameter" in item:
                raise serializers.ValidationError(f"Filter {index} cannot bind both value and parameter.")
        return values


class DatasetListSerializer(serializers.Serializer):
    key = serializers.CharField()
    module = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()
    version = serializers.CharField()
    locked = serializers.BooleanField(default=False)
    required_entitlement = serializers.CharField(required=False, allow_blank=True)
    freshness = serializers.CharField(source="data_freshness", required=False)
    data_freshness = serializers.CharField(required=False)
    upgrade_url = serializers.URLField(required=False, allow_null=True)
    entitlement = serializers.SerializerMethodField()
    dimension_count = serializers.SerializerMethodField()
    measure_count = serializers.SerializerMethodField()

    def get_entitlement(self, obj: Any) -> dict[str, Any]:
        def read(name: str, default: Any = None) -> Any:
            return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)

        locked = bool(read("locked", False))
        return {
            "state": "locked" if locked else "free",
            "required_entitlement": read("required_entitlement", ""),
            "upgrade_url": read("upgrade_url"),
        }

    def get_dimension_count(self, obj: Any) -> int:
        dimensions = obj.get("dimensions", ()) if isinstance(obj, dict) else getattr(obj, "dimensions", ())
        return len(dimensions)

    def get_measure_count(self, obj: Any) -> int:
        measures = obj.get("measures", ()) if isinstance(obj, dict) else getattr(obj, "measures", ())
        return len(measures)


class DatasetDetailSerializer(DatasetListSerializer):
    dimensions = serializers.SerializerMethodField()
    measures = serializers.SerializerMethodField()
    supported_grouping = serializers.ListField(child=serializers.CharField(), required=False)
    supported_ordering = serializers.ListField(child=serializers.CharField(), required=False)
    maximum_row_limit = serializers.IntegerField(source="max_row_limit", required=False)

    def get_dimensions(self, obj: Any) -> list[dict[str, Any]]:
        raw = obj.get("dimensions", ()) if isinstance(obj, dict) else getattr(obj, "dimensions", ())
        result = []
        for item in raw:
            value = dict(item) if isinstance(item, dict) else asdict(item)
            value["type"] = value.pop("scalar_type", value.get("type", "string"))
            result.append(value)
        return result

    def get_measures(self, obj: Any) -> list[dict[str, Any]]:
        raw = obj.get("measures", ()) if isinstance(obj, dict) else getattr(obj, "measures", ())
        return [dict(item) if isinstance(item, dict) else asdict(item) for item in raw]


class QueryListSerializer(serializers.ModelSerializer):
    class Meta:
        model = QueryDefinition
        fields = ("id", "query_code", "name", "dataset_key", "state", "version", "created_by_id", "updated_at")


class QueryDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = QueryDefinition
        exclude = ("tenant_id", "deleted_at")
        read_only_fields = (
            "id",
            "state",
            "transition_history",
            "version",
            "created_by_id",
            "updated_by_id",
            "created_at",
            "updated_at",
        )


class QueryCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    query_code = CodeField(max_length=64)
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    dataset_key = serializers.CharField(max_length=160)
    dimensions = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    measures = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    filters = FilterListField(required=False, default=list)
    grouping = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    ordering = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    parameters_schema = serializers.DictField(required=False, default=dict)
    row_limit = serializers.IntegerField(min_value=1, max_value=10000, required=False, default=500)
    cache_ttl_seconds = serializers.IntegerField(min_value=0, max_value=86400, required=False, default=300)

    def validate_parameters_schema(self, value: dict[str, Any]) -> dict[str, Any]:
        for name, definition in value.items():
            if not isinstance(name, str) or not isinstance(definition, dict):
                raise serializers.ValidationError("Parameter definitions must be objects keyed by name.")
            if definition.get("type") not in SCALAR_TYPES:
                raise serializers.ValidationError(f"Parameter {name!r} has an unsupported type.")
        return value


class QueryUpdateSerializer(QueryCreateSerializer):
    version = serializers.IntegerField(min_value=1)
    query_code = CodeField(max_length=64, required=False)
    name = serializers.CharField(max_length=255, required=False)
    dataset_key = serializers.CharField(max_length=160, required=False)
    row_limit = serializers.IntegerField(min_value=1, max_value=10000, required=False)
    cache_ttl_seconds = serializers.IntegerField(min_value=0, max_value=86400, required=False)


class QueryTransitionSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class QueryValidateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    parameters = serializers.DictField(required=False, default=dict)


class ExecutionRequestSerializer(QueryValidateSerializer):
    pass


class ReportListSerializer(serializers.ModelSerializer):
    dataset_key = serializers.CharField(source="query_definition.dataset_key", read_only=True)

    class Meta:
        model = Report
        fields = ("id", "report_code", "report_name", "report_type", "dataset_key", "state", "version", "updated_at")


class ReportDetailSerializer(serializers.ModelSerializer):
    query = QueryListSerializer(source="query_definition", read_only=True)

    class Meta:
        model = Report
        exclude = ("tenant_id", "deleted_at", "legacy_query")
        read_only_fields = (
            "id",
            "state",
            "transition_history",
            "version",
            "created_by_id",
            "updated_by_id",
            "created_at",
            "updated_at",
        )


class ReportCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    report_code = CodeField(max_length=64)
    report_name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    report_type = serializers.ChoiceField(choices=("table", "pivot", "chart", "kpi"))
    query_definition_id = serializers.UUIDField()
    visualization = serializers.DictField(required=False, default=dict)
    default_parameters = serializers.DictField(required=False, default=dict)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        visualization = attrs.get("visualization", {})
        report_type = attrs.get("report_type")
        declared = visualization.get("type") if isinstance(visualization, dict) else None
        compatible = {
            "table": {None, "table"},
            "pivot": {None, "pivot"},
            "kpi": {None, "kpi"},
            "chart": {None, "bar", "line", "area", "pie", "funnel"},
        }
        if report_type in compatible and declared not in compatible[report_type]:
            raise serializers.ValidationError({"visualization": "Visualization type is incompatible with report_type."})
        return attrs


class ReportUpdateSerializer(ReportCreateSerializer):
    version = serializers.IntegerField(min_value=1)
    report_code = CodeField(max_length=64, required=False)
    report_name = serializers.CharField(max_length=255, required=False)
    report_type = serializers.ChoiceField(choices=("table", "pivot", "chart", "kpi"), required=False)
    query_definition_id = serializers.UUIDField(required=False)


class ReportTransitionSerializer(QueryTransitionSerializer):
    pass


class DashboardListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dashboard
        fields = (
            "id",
            "dashboard_code",
            "dashboard_name",
            "state",
            "version",
            "refresh_interval_seconds",
            "updated_at",
        )


class DashboardDetailSerializer(serializers.ModelSerializer):
    widgets = serializers.SerializerMethodField()

    class Meta:
        model = Dashboard
        exclude = ("tenant_id", "deleted_at", "legacy_layout")
        read_only_fields = (
            "id",
            "state",
            "transition_history",
            "version",
            "created_by_id",
            "updated_by_id",
            "created_at",
            "updated_at",
        )

    def get_widgets(self, obj: Dashboard) -> list[dict[str, Any]]:
        rows = (
            DashboardWidget.objects.for_tenant(obj.tenant_id)
            .filter(dashboard=obj, deleted_at__isnull=True)
            .order_by("display_order", "id")
        )
        return WidgetListSerializer(rows, many=True).data


class DashboardCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    dashboard_code = CodeField(max_length=64)
    dashboard_name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    global_filters = FilterListField(required=False, default=list)
    refresh_interval_seconds = serializers.IntegerField(min_value=30, max_value=86400, required=False, allow_null=True)


class DashboardUpdateSerializer(DashboardCreateSerializer):
    version = serializers.IntegerField(min_value=1)
    dashboard_code = CodeField(max_length=64, required=False)
    dashboard_name = serializers.CharField(max_length=255, required=False)


class WidgetListSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardWidget
        fields = (
            "id",
            "dashboard_id",
            "query_definition_id",
            "report_id",
            "widget_type",
            "title",
            "x",
            "y",
            "width",
            "height",
            "display_order",
            "version",
        )


class WidgetDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardWidget
        exclude = ("tenant_id", "deleted_at")


class WidgetCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    query_definition_id = serializers.UUIDField(required=False, allow_null=True)
    report_id = serializers.UUIDField(required=False, allow_null=True)
    widget_type = serializers.ChoiceField(choices=("kpi", "table", "bar", "line", "area", "pie", "funnel"))
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    x = serializers.IntegerField(min_value=0)
    y = serializers.IntegerField(min_value=0)
    width = serializers.IntegerField(min_value=1, max_value=12)
    height = serializers.IntegerField(min_value=1, max_value=24)
    visualization = serializers.DictField(required=False, default=dict)
    filters = FilterListField(required=False, default=list)
    refresh_interval_seconds = serializers.IntegerField(min_value=30, max_value=86400, required=False, allow_null=True)
    display_order = serializers.IntegerField(min_value=0)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if bool(attrs.get("query_definition_id")) == bool(attrs.get("report_id")):
            raise serializers.ValidationError("Exactly one query_definition_id or report_id is required.")
        return attrs


class WidgetUpdateSerializer(WidgetCreateSerializer):
    version = serializers.IntegerField(min_value=1)
    widget_type = serializers.ChoiceField(
        choices=("kpi", "table", "bar", "line", "area", "pie", "funnel"), required=False
    )
    title = serializers.CharField(max_length=255, required=False)
    x = serializers.IntegerField(min_value=0, required=False)
    y = serializers.IntegerField(min_value=0, required=False)
    width = serializers.IntegerField(min_value=1, max_value=12, required=False)
    height = serializers.IntegerField(min_value=1, max_value=24, required=False)
    display_order = serializers.IntegerField(min_value=0, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return attrs


class WidgetReorderSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    widgets = serializers.ListField(child=serializers.DictField())


class ShareListSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardShare
        exclude = ("tenant_id",)


class ShareCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    subject_type = serializers.ChoiceField(choices=("user", "role"))
    subject_id = serializers.CharField(max_length=255)
    access_level = serializers.ChoiceField(choices=("view", "edit"))
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class ShareUpdateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    access_level = serializers.ChoiceField(choices=("view", "edit"), required=False)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class ExecutionListSerializer(serializers.ModelSerializer):
    job_id = serializers.UUIDField(source="async_job_id", read_only=True)

    class Meta:
        model = QueryExecution
        fields = (
            "id",
            "job_id",
            "query_definition_id",
            "report_id",
            "dashboard_id",
            "actor_id",
            "definition_version",
            "dataset_key",
            "dataset_version",
            "dataset_schema_fingerprint",
            "status",
            "row_count",
            "truncated",
            "cache_hit",
            "duration_ms",
            "created_at",
            "started_at",
            "completed_at",
        )


class ExecutionDetailSerializer(serializers.ModelSerializer):
    job_id = serializers.UUIDField(source="async_job_id", read_only=True)

    class Meta:
        model = QueryExecution
        exclude = ("tenant_id", "result_rows")


class ExecutionResultSerializer(serializers.ModelSerializer):
    execution_id = serializers.UUIDField(source="id", read_only=True)
    columns = serializers.JSONField(source="result_columns", read_only=True)

    class Meta:
        model = QueryExecution
        fields = (
            "execution_id",
            "columns",
            "row_count",
            "truncated",
            "cache_hit",
            "definition_version",
            "dataset_key",
            "dataset_version",
            "dataset_schema_fingerprint",
            "effective_query_fingerprint",
            "freshness_token",
            "data_as_of",
            "result_purged_at",
            "completed_at",
        )


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("healthy", "degraded", "unavailable"))
    ready = serializers.BooleanField()
    dependencies = serializers.DictField(child=serializers.DictField())


__all__ = [name for name in globals() if name.endswith("Serializer")]
