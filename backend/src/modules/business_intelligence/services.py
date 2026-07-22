"""Transactional business services for governed, tenant-isolated analytics."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any, Iterable, Mapping

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Model, Q
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

from src.core.api import OperationFailed
from src.core.async_jobs import services as async_jobs

from .datasets import dataset_registry
from .models import Dashboard, DashboardShare, DashboardWidget, QueryDefinition, QueryExecution, Report

logger = logging.getLogger(__name__)

TERMINAL_EXECUTION_STATES = frozenset({"succeeded", "failed", "cancelled", "timed_out"})
STATE_TRANSITIONS = {
    "publish": {"draft": "published"},
    "archive": {"draft": "archived", "published": "archived"},
    "restore": {"archived": "draft"},
}


class BIConflict(OperationFailed):
    """Stable governed 409 response for lifecycle, version, and idempotency conflicts."""

    def __init__(self, detail: str | None = None, code: str = "CONFLICT") -> None:
        super().__init__(
            error_code=code,
            message=detail or "The resource changed or cannot perform this operation in its current state.",
            http_status=409,
        )


class CapabilityUnavailable(OperationFailed):
    """Stable failure-honest response when no authoritative provider can run."""

    def __init__(self) -> None:
        super().__init__(
            error_code="CAPABILITY_UNAVAILABLE",
            message="The requested analytics capability is unavailable.",
            http_status=503,
        )


def _tenant_uuid(value: uuid.UUID | str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({"tenant_id": "A valid tenant UUID is required."}) from exc


def _required_text(value: object, name: str, maximum: int = 255) -> str:
    normalized = str(value).strip() if value is not None else ""
    if not normalized or len(normalized) > maximum:
        raise ValidationError({name: f"A non-empty value up to {maximum} characters is required."})
    return normalized


def _validate_visualization(resource_type: str, visualization: object) -> None:
    if not isinstance(visualization, Mapping):
        raise ValidationError({"visualization": "Visualization configuration must be an object."})
    declared = visualization.get("type")
    compatible = {
        "table": {None, "table"},
        "pivot": {None, "pivot"},
        "kpi": {None, "kpi"},
        "chart": {None, "bar", "line", "area", "pie", "funnel"},
        "bar": {None, "bar"},
        "line": {None, "line"},
        "area": {None, "area"},
        "pie": {None, "pie"},
        "funnel": {None, "funnel"},
    }
    if resource_type not in compatible or declared not in compatible[resource_type]:
        raise ValidationError({"visualization": "Visualization type is incompatible with the resource type."})


def _validate_filter_fields(query: QueryDefinition, filters: object) -> None:
    if not isinstance(filters, list):
        raise ValidationError({"filters": "Filters must be a list."})
    descriptor = _registry_get(query.dataset_key).describe()
    dimensions = {item.key for item in getattr(descriptor, "dimensions", ())}
    invalid = [
        item.get("field") for item in filters if not isinstance(item, Mapping) or item.get("field") not in dimensions
    ]
    if invalid:
        raise ValidationError({"filters": "A filter references a field unavailable from the dataset."})


def _record(
    command: str,
    actor_id: str,
    correlation_id: str,
    reason: str = "",
    idempotency_key: str = "",
) -> dict[str, str]:
    target_states = {
        "create": "draft",
        "update": "draft",
        "publish": "published",
        "archive": "archived",
        "restore": "draft",
        "delete": "archived",
        "enqueue": "queued",
        "start": "running",
        "succeed": "succeeded",
        "fail": "failed",
        "cancel": "cancelled",
    }
    return {
        "command": command,
        "to_state": target_states.get(command, command),
        "actor_id": actor_id,
        "correlation_id": correlation_id,
        "reason": reason,
        "timestamp": timezone.now().isoformat(),
        "idempotency_key": idempotency_key,
    }


def _descriptor_dict(value: object) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    fields = getattr(value, "__dict__", None)
    if isinstance(fields, dict):
        return {key: item for key, item in fields.items() if not key.startswith("_")}
    raise CapabilityUnavailable()


def _dataset_provenance(provider: object) -> tuple[str, str]:
    descriptor = provider.describe()
    data = _descriptor_dict(descriptor)
    fingerprint = getattr(descriptor, "schema_fingerprint", "")
    if not fingerprint:
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return str(data.get("version", "")), str(fingerprint)


def _registry_get(key: str) -> object:
    try:
        getter = getattr(dataset_registry, "get", None) or getattr(dataset_registry, "get_provider", None)
        provider = getter(key) if getter else None
    except Exception as exc:
        logger.warning("bi.dataset.unavailable", extra={"dataset_key": key, "status": "unavailable"})
        raise CapabilityUnavailable() from exc
    if provider is None:
        raise CapabilityUnavailable()
    return provider


def _model_payload(model: type[Model], payload: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {field.name for field in model._meta.concrete_fields}
    server_owned = {
        "id",
        "tenant_id",
        "created_at",
        "updated_at",
        "created_by_id",
        "updated_by_id",
        "state",
        "transition_history",
        "version",
        "deleted_at",
        "legacy_query",
        "legacy_layout",
        "async_job",
        "actor_id",
        "idempotency_key",
        "status",
        "result_columns",
        "result_rows",
        "row_count",
        "truncated",
        "cache_hit",
        "duration_ms",
        "error_code",
        "error_message",
        "started_at",
        "completed_at",
        "dataset_version",
        "dataset_schema_fingerprint",
        "effective_query_fingerprint",
        "freshness_token",
        "data_as_of",
        "result_purged_at",
    }
    return {key: value for key, value in payload.items() if key in allowed and key not in server_owned}


def _get(model: type[Model], tenant_id: uuid.UUID | str, object_id: object, *, include_deleted: bool = False) -> Any:
    queryset = model.objects.for_tenant(_tenant_uuid(tenant_id))
    if not include_deleted and any(field.name == "deleted_at" for field in model._meta.fields):
        queryset = queryset.filter(deleted_at__isnull=True)
    try:
        return queryset.get(pk=object_id)
    except (model.DoesNotExist, ValueError, TypeError) as exc:
        raise NotFound() from exc


class DatasetCatalogService:
    @staticmethod
    def list_datasets(tenant_id: uuid.UUID | str, actor: object, include_locked: bool = False) -> list[dict[str, Any]]:
        _tenant_uuid(tenant_id)
        descriptor_lister = getattr(dataset_registry, "descriptors", None)
        if callable(descriptor_lister):
            values = descriptor_lister()
        else:
            provider_lister = getattr(dataset_registry, "providers", None)
            providers = provider_lister() if callable(provider_lister) else {}
            values = providers.values() if isinstance(providers, Mapping) else providers
        result: list[dict[str, Any]] = []
        for entry in values:
            provider = entry[1] if isinstance(entry, tuple) and len(entry) == 2 else entry
            descriptor = provider.describe() if hasattr(provider, "describe") else provider
            data = _descriptor_dict(descriptor)
            data.setdefault("owning_module", data.get("module"))
            locked = bool(data.get("locked", False))
            if locked and not include_locked:
                continue
            if locked:
                data = {
                    key: data.get(key)
                    for key in (
                        "key",
                        "module",
                        "owning_module",
                        "label",
                        "description",
                        "version",
                        "required_entitlement",
                        "upgrade_url",
                    )
                }
                data["locked"] = True
            result.append(data)
        return result

    @staticmethod
    def get_dataset(tenant_id: uuid.UUID | str, actor: object, dataset_key: str) -> dict[str, Any]:
        _tenant_uuid(tenant_id)
        provider = _registry_get(dataset_key)
        descriptor = _descriptor_dict(provider.describe())
        descriptor.setdefault("owning_module", descriptor.get("module"))
        if descriptor.get("locked"):
            raise OperationFailed(
                error_code="ENTITLEMENT_REQUIRED",
                message="Dataset entitlement is required.",
                http_status=403,
            )
        return descriptor


class _DefinitionService:
    model: type[Model]

    @classmethod
    def _transition(
        cls,
        tenant_id: uuid.UUID | str,
        object_id: object,
        actor_id: str,
        expected_version: int,
        command: str,
        correlation_id: str,
        idempotency_key: str,
        reason: str = "",
    ) -> Any:
        _required_text(idempotency_key, "idempotency_key")
        with transaction.atomic():
            obj = (
                cls.model.objects.for_tenant(_tenant_uuid(tenant_id))
                .select_for_update()
                .filter(pk=object_id, deleted_at__isnull=True)
                .first()
            )
            if obj is None:
                raise NotFound()
            replay = next(
                (item for item in obj.transition_history if item.get("idempotency_key") == idempotency_key),
                None,
            )
            if replay is not None:
                if replay.get("command") != command:
                    raise BIConflict("Idempotency key was used for another command.", code="IDEMPOTENCY_CONFLICT")
                return obj
            if obj.version != expected_version:
                raise BIConflict("The supplied version is stale.", code="VERSION_CONFLICT")
            target = STATE_TRANSITIONS.get(command, {}).get(obj.state)
            if target is None:
                raise BIConflict(f"Cannot {command} a {obj.state} resource.", code="ILLEGAL_TRANSITION")
            cls._publish_guard(tenant_id, obj, command)
            obj.state = target
            obj.version += 1
            obj.updated_by_id = actor_id
            obj.transition_history = [
                *obj.transition_history,
                _record(command, actor_id, correlation_id, reason, idempotency_key),
            ]
            update_fields = ["state", "version", "updated_by_id", "transition_history", "updated_at"]
            if isinstance(obj, QueryDefinition):
                update_fields.extend(("dataset_version", "dataset_schema_fingerprint"))
            obj.save(update_fields=update_fields)
            return obj

    @classmethod
    def _publish_guard(cls, tenant_id: uuid.UUID | str, obj: Any, command: str) -> None:
        return None

    @classmethod
    def _soft_delete(
        cls,
        tenant_id: uuid.UUID | str,
        object_id: object,
        actor_id: str,
        expected_version: int,
        correlation_id: str,
        idempotency_key: str,
    ) -> Any:
        _required_text(idempotency_key, "idempotency_key")
        with transaction.atomic():
            obj = cls.model.objects.for_tenant(_tenant_uuid(tenant_id)).select_for_update().filter(pk=object_id).first()
            if obj is None:
                raise NotFound()
            replay = next(
                (item for item in obj.transition_history if item.get("idempotency_key") == idempotency_key), None
            )
            if replay is not None:
                if replay.get("command") != "delete":
                    raise BIConflict("Idempotency key was used for another command.", code="IDEMPOTENCY_CONFLICT")
                return obj
            if obj.deleted_at is not None:
                raise NotFound()
            if obj.version != expected_version:
                raise BIConflict("The supplied version is stale.", code="VERSION_CONFLICT")
            obj.state = "archived"
            obj.deleted_at = timezone.now()
            obj.version += 1
            obj.updated_by_id = actor_id
            obj.transition_history = [
                *obj.transition_history,
                _record("delete", actor_id, correlation_id, idempotency_key=idempotency_key),
            ]
            obj.save(
                update_fields=("state", "deleted_at", "version", "updated_by_id", "transition_history", "updated_at")
            )
            return obj


class QueryService(_DefinitionService):
    model = QueryDefinition

    @staticmethod
    def _validate_spec(
        tenant_id: uuid.UUID | str, payload: Mapping[str, Any], parameters: Mapping[str, Any] | None = None
    ) -> object:
        forbidden = {"sql", "query", "expression", "python", "script"} & set(payload)
        if forbidden:
            raise ValidationError({key: "Executable expressions are not accepted." for key in forbidden})
        provider = _registry_get(str(payload.get("dataset_key", "")))
        descriptor = _descriptor_dict(provider.describe())
        maximum = int(descriptor.get("maximum_row_limit", descriptor.get("max_row_limit", 10000)))
        if int(payload.get("row_limit", 500)) > maximum:
            raise ValidationError({"row_limit": f"This dataset permits at most {maximum} rows."})
        schema = payload.get("parameters_schema", {})
        if not isinstance(schema, Mapping):
            raise ValidationError({"parameters_schema": "Parameter schema must be an object."})
        parameter_filters = {
            item.get("parameter")
            for item in payload.get("filters", [])
            if isinstance(item, Mapping) and item.get("parameter")
        }
        unknown_bindings = parameter_filters - set(schema)
        if unknown_bindings:
            raise ValidationError({"filters": "Every parameter binding must exist in parameters_schema."})
        if parameters is not None:
            if not isinstance(parameters, Mapping):
                raise ValidationError({"parameters": "Parameters must match the declared schema."})
            unknown = set(parameters) - set(schema)
            missing = {
                name
                for name, definition in schema.items()
                if isinstance(definition, Mapping) and definition.get("required") and name not in parameters
            }
            if unknown or missing:
                detail: dict[str, str] = {}
                detail.update({name: "Unknown parameter." for name in unknown})
                detail.update({name: "This parameter is required." for name in missing})
                raise ValidationError({"parameters": detail})
            expected_types = {"string": str, "integer": int, "number": (int, float), "boolean": bool}
            invalid = {}
            for name, value in parameters.items():
                definition = schema.get(name, {})
                declared_type = definition.get("type") if isinstance(definition, Mapping) else None
                expected = expected_types.get(declared_type)
                if expected is not None and (
                    not isinstance(value, expected)
                    or declared_type in {"integer", "number"}
                    and isinstance(value, bool)
                ):
                    invalid[name] = f"Expected {declared_type}."
                elif declared_type == "date":
                    try:
                        date.fromisoformat(str(value))
                    except (TypeError, ValueError):
                        invalid[name] = "Expected date."
                elif declared_type == "datetime":
                    try:
                        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                    except (TypeError, ValueError):
                        invalid[name] = "Expected datetime."
                elif declared_type == "uuid":
                    try:
                        uuid.UUID(str(value))
                    except (TypeError, ValueError, AttributeError):
                        invalid[name] = "Expected uuid."
            if invalid:
                raise ValidationError({"parameters": invalid})
        try:
            return provider.validate(_tenant_uuid(tenant_id), dict(payload))
        except (ValidationError, APIException):
            raise
        except Exception as exc:
            raise ValidationError({"query": "The dataset rejected this query definition."}) from exc

    @classmethod
    def create(
        cls,
        tenant_id: uuid.UUID | str,
        actor_id: str,
        payload: Mapping[str, Any],
        correlation_id: str,
        idempotency_key: str,
    ) -> QueryDefinition:
        tenant = _tenant_uuid(tenant_id)
        actor = _required_text(actor_id, "actor_id")
        _required_text(idempotency_key, "idempotency_key")
        normalized = dict(payload)
        normalized["query_code"] = _required_text(normalized.get("query_code"), "query_code", 64).upper()
        cls._validate_spec(tenant, normalized)
        provider = _registry_get(str(normalized["dataset_key"]))
        dataset_version, schema_fingerprint = _dataset_provenance(provider)
        with transaction.atomic():
            existing = (
                QueryDefinition.objects.for_tenant(tenant)
                .filter(query_code=normalized["query_code"], deleted_at__isnull=True)
                .first()
            )
            if existing is not None:
                if any(item.get("idempotency_key") == idempotency_key for item in existing.transition_history):
                    return existing
                raise BIConflict("An active query already uses this code.", code="DUPLICATE_CODE")
            try:
                obj = QueryDefinition.objects.create(
                    tenant_id=tenant,
                    created_by_id=actor,
                    updated_by_id=actor,
                    dataset_version=dataset_version,
                    dataset_schema_fingerprint=schema_fingerprint,
                    transition_history=[_record("create", actor, correlation_id, idempotency_key=idempotency_key)],
                    **_model_payload(QueryDefinition, normalized),
                )
            except IntegrityError as exc:
                raise BIConflict("An active query already uses this code.", code="DUPLICATE_CODE") from exc
        logger.info(
            "bi.query.created",
            extra={
                "tenant_id": str(tenant),
                "actor_id": actor,
                "resource_id": str(obj.id),
                "dataset_key": obj.dataset_key,
                "correlation_id": correlation_id,
            },
        )
        return obj

    @classmethod
    def update(
        cls,
        tenant_id: uuid.UUID | str,
        query_id: object,
        actor_id: str,
        expected_version: int,
        payload: Mapping[str, Any],
        correlation_id: str,
        idempotency_key: str,
    ) -> QueryDefinition:
        _required_text(idempotency_key, "idempotency_key")
        tenant = _tenant_uuid(tenant_id)
        with transaction.atomic():
            obj = (
                QueryDefinition.objects.for_tenant(tenant)
                .select_for_update()
                .filter(pk=query_id, deleted_at__isnull=True)
                .first()
            )
            if obj is None:
                raise NotFound()
            replay = next(
                (item for item in obj.transition_history if item.get("idempotency_key") == idempotency_key), None
            )
            if replay is not None:
                if replay.get("command") != "update":
                    raise BIConflict("Idempotency key was used for another command.", code="IDEMPOTENCY_CONFLICT")
                return obj
            if obj.version != expected_version:
                raise BIConflict("The supplied version is stale.", code="VERSION_CONFLICT")
            candidate = {field.name: getattr(obj, field.name) for field in QueryDefinition._meta.concrete_fields}
            candidate.update(payload)
            cls._validate_spec(tenant, candidate)
            provider = _registry_get(str(candidate["dataset_key"]))
            dataset_version, schema_fingerprint = _dataset_provenance(provider)
            for key, value in _model_payload(QueryDefinition, payload).items():
                if key not in {
                    "id",
                    "tenant_id",
                    "state",
                    "transition_history",
                    "version",
                    "created_by_id",
                    "updated_by_id",
                    "created_at",
                    "updated_at",
                    "deleted_at",
                }:
                    setattr(obj, key, value.upper() if key == "query_code" else value)
            if obj.state == "published":
                obj.state = "draft"
            obj.dataset_version = dataset_version
            obj.dataset_schema_fingerprint = schema_fingerprint
            obj.version += 1
            obj.updated_by_id = actor_id
            obj.transition_history = [
                *obj.transition_history,
                _record("update", actor_id, correlation_id, idempotency_key=idempotency_key),
            ]
            obj.save()
            return obj

    @classmethod
    def _publish_guard(cls, tenant_id: uuid.UUID | str, obj: QueryDefinition, command: str) -> None:
        if command == "publish":
            cls._validate_spec(
                tenant_id, {field.name: getattr(obj, field.name) for field in QueryDefinition._meta.concrete_fields}
            )
            provider = _registry_get(obj.dataset_key)
            obj.dataset_version, obj.dataset_schema_fingerprint = _dataset_provenance(provider)

    @classmethod
    def publish(
        cls,
        tenant_id: uuid.UUID | str,
        query_id: object,
        actor_id: str,
        expected_version: int,
        correlation_id: str,
        idempotency_key: str,
        reason: str = "",
    ) -> QueryDefinition:
        return cls._transition(
            tenant_id, query_id, actor_id, expected_version, "publish", correlation_id, idempotency_key, reason
        )

    @classmethod
    def archive(
        cls,
        tenant_id: uuid.UUID | str,
        query_id: object,
        actor_id: str,
        expected_version: int,
        correlation_id: str,
        idempotency_key: str,
        reason: str = "",
    ) -> QueryDefinition:
        return cls._transition(
            tenant_id, query_id, actor_id, expected_version, "archive", correlation_id, idempotency_key, reason
        )

    @classmethod
    def restore(
        cls,
        tenant_id: uuid.UUID | str,
        query_id: object,
        actor_id: str,
        expected_version: int,
        correlation_id: str,
        idempotency_key: str,
        reason: str = "",
    ) -> QueryDefinition:
        return cls._transition(
            tenant_id, query_id, actor_id, expected_version, "restore", correlation_id, idempotency_key, reason
        )

    @classmethod
    def soft_delete(
        cls,
        tenant_id: uuid.UUID | str,
        query_id: object,
        actor_id: str,
        expected_version: int,
        correlation_id: str,
        idempotency_key: str,
    ) -> QueryDefinition:
        return cls._soft_delete(tenant_id, query_id, actor_id, expected_version, correlation_id, idempotency_key)

    @classmethod
    def validate(cls, tenant_id: uuid.UUID | str, query_id: object, parameters: Mapping[str, Any]) -> object:
        obj = _get(QueryDefinition, tenant_id, query_id)
        spec = {field.name: getattr(obj, field.name) for field in QueryDefinition._meta.concrete_fields}
        return cls._validate_spec(tenant_id, spec, cls._effective_parameters(obj, parameters))

    @staticmethod
    def _effective_parameters(query: QueryDefinition, parameters: Mapping[str, Any]) -> dict[str, Any]:
        effective = {
            name: definition["default"]
            for name, definition in query.parameters_schema.items()
            if isinstance(definition, Mapping) and "default" in definition
        }
        effective.update(parameters)
        return effective

    @classmethod
    def enqueue_execution(
        cls,
        tenant_id: uuid.UUID | str,
        query_id: object,
        actor_id: str,
        parameters: Mapping[str, Any],
        correlation_id: str,
        idempotency_key: str,
    ) -> QueryExecution:
        query = _get(QueryDefinition, tenant_id, query_id)
        if query.state != "published":
            raise BIConflict("Only published queries can execute.", code="NOT_PUBLISHED")
        effective = cls._effective_parameters(query, parameters)
        cls.validate(tenant_id, query_id, effective)
        return ExecutionService.enqueue(tenant_id, query, actor_id, effective, correlation_id, idempotency_key)


class ReportService(_DefinitionService):
    model = Report

    @classmethod
    def create(
        cls,
        tenant_id: uuid.UUID | str,
        actor_id: str,
        payload: Mapping[str, Any],
        correlation_id: str,
        idempotency_key: str,
    ) -> Report:
        tenant = _tenant_uuid(tenant_id)
        _required_text(idempotency_key, "idempotency_key")
        data = dict(payload)
        query_id = data.pop("query_definition_id", None)
        if query_id is None:
            raise ValidationError({"query_definition_id": "A governed query definition is required."})
        query = _get(QueryDefinition, tenant, query_id)
        _validate_visualization(str(data.get("report_type", "")), data.get("visualization", {}))
        QueryService._validate_spec(
            tenant,
            {field.name: getattr(query, field.name) for field in QueryDefinition._meta.concrete_fields},
            data.get("default_parameters", {}),
        )
        with transaction.atomic():
            existing = (
                Report.objects.for_tenant(tenant)
                .filter(report_code=str(data.get("report_code", "")).upper(), deleted_at__isnull=True)
                .first()
            )
            if existing is not None:
                if any(item.get("idempotency_key") == idempotency_key for item in existing.transition_history):
                    return existing
                raise BIConflict("An active report already uses this code.", code="DUPLICATE_CODE")
            try:
                obj = Report.objects.create(
                    tenant_id=tenant,
                    query_definition=query,
                    created_by_id=actor_id,
                    updated_by_id=actor_id,
                    transition_history=[_record("create", actor_id, correlation_id, idempotency_key=idempotency_key)],
                    **_model_payload(Report, data),
                )
            except IntegrityError as exc:
                raise BIConflict("An active report already uses this code.", code="DUPLICATE_CODE") from exc
        logger.info(
            "bi.report.created",
            extra={
                "tenant_id": str(tenant),
                "actor_id": actor_id,
                "resource_id": str(obj.id),
                "dataset_key": query.dataset_key,
                "correlation_id": correlation_id,
            },
        )
        return obj

    @classmethod
    def update(
        cls,
        tenant_id: uuid.UUID | str,
        report_id: object,
        actor_id: str,
        expected_version: int,
        payload: Mapping[str, Any],
        correlation_id: str,
        idempotency_key: str,
    ) -> Report:
        tenant = _tenant_uuid(tenant_id)
        _required_text(idempotency_key, "idempotency_key")
        with transaction.atomic():
            obj = (
                Report.objects.for_tenant(tenant)
                .select_for_update()
                .filter(pk=report_id, deleted_at__isnull=True)
                .first()
            )
            if obj is None:
                raise NotFound()
            replay = next(
                (item for item in obj.transition_history if item.get("idempotency_key") == idempotency_key), None
            )
            if replay is not None:
                if replay.get("command") != "update":
                    raise BIConflict("Idempotency key was used for another command.", code="IDEMPOTENCY_CONFLICT")
                return obj
            if obj.version != expected_version:
                raise BIConflict("The supplied version is stale.", code="VERSION_CONFLICT")
            data = dict(payload)
            if "query_definition_id" in data:
                obj.query_definition = _get(QueryDefinition, tenant, data.pop("query_definition_id"))
            report_type = str(data.get("report_type", obj.report_type))
            visualization = data.get("visualization", obj.visualization)
            _validate_visualization(report_type, visualization)
            QueryService._validate_spec(
                tenant,
                {
                    field.name: getattr(obj.query_definition, field.name)
                    for field in QueryDefinition._meta.concrete_fields
                },
                data.get("default_parameters", obj.default_parameters),
            )
            for key, value in _model_payload(Report, data).items():
                if key not in {"id", "tenant_id", "version", "state", "deleted_at", "legacy_query"}:
                    setattr(obj, key, value)
            if obj.state == "published":
                obj.state = "draft"
            obj.version += 1
            obj.updated_by_id = actor_id
            obj.transition_history = [
                *obj.transition_history,
                _record("update", actor_id, correlation_id, idempotency_key=idempotency_key),
            ]
            obj.save()
            return obj

    @classmethod
    def _publish_guard(cls, tenant_id: uuid.UUID | str, obj: Report, command: str) -> None:
        if command == "publish" and (
            obj.legacy_query or not obj.query_definition_id or obj.query_definition.state != "published"
        ):
            raise BIConflict("A published query definition is required.", code="PUBLISH_GUARD_FAILED")

    @classmethod
    def publish(
        cls,
        tenant_id: uuid.UUID | str,
        report_id: object,
        actor_id: str,
        expected_version: int,
        correlation_id: str,
        idempotency_key: str,
        reason: str = "",
    ) -> Report:
        return cls._transition(
            tenant_id, report_id, actor_id, expected_version, "publish", correlation_id, idempotency_key, reason
        )

    @classmethod
    def archive(
        cls,
        tenant_id: uuid.UUID | str,
        report_id: object,
        actor_id: str,
        expected_version: int,
        correlation_id: str,
        idempotency_key: str,
        reason: str = "",
    ) -> Report:
        return cls._transition(
            tenant_id, report_id, actor_id, expected_version, "archive", correlation_id, idempotency_key, reason
        )

    @classmethod
    def restore(
        cls,
        tenant_id: uuid.UUID | str,
        report_id: object,
        actor_id: str,
        expected_version: int,
        correlation_id: str,
        idempotency_key: str,
        reason: str = "",
    ) -> Report:
        return cls._transition(
            tenant_id, report_id, actor_id, expected_version, "restore", correlation_id, idempotency_key, reason
        )

    @classmethod
    def soft_delete(
        cls,
        tenant_id: uuid.UUID | str,
        report_id: object,
        actor_id: str,
        expected_version: int,
        correlation_id: str,
        idempotency_key: str,
    ) -> Report:
        return cls._soft_delete(tenant_id, report_id, actor_id, expected_version, correlation_id, idempotency_key)

    @classmethod
    def enqueue_execution(
        cls,
        tenant_id: uuid.UUID | str,
        report_id: object,
        actor_id: str,
        parameters: Mapping[str, Any],
        correlation_id: str,
        idempotency_key: str,
    ) -> QueryExecution:
        report = _get(Report, tenant_id, report_id)
        if report.state != "published":
            raise BIConflict("Only published reports can execute.", code="NOT_PUBLISHED")
        merged = dict(report.default_parameters)
        merged.update(parameters)
        merged = QueryService._effective_parameters(report.query_definition, merged)
        QueryService.validate(tenant_id, report.query_definition_id, merged)
        return ExecutionService.enqueue(
            tenant_id, report.query_definition, actor_id, merged, correlation_id, idempotency_key, report=report
        )


class DashboardService(_DefinitionService):
    model = Dashboard

    @staticmethod
    def _authorize(dashboard: Dashboard, actor_id: str, access: str) -> None:
        """Enforce owner/share semantics independently of route permissions."""
        if dashboard.created_by_id == str(actor_id):
            return
        if access == "owner":
            raise NotFound()
        shares = (
            DashboardShare.objects.for_tenant(dashboard.tenant_id)
            .filter(
                dashboard=dashboard,
                subject_type="user",
                subject_id=str(actor_id),
                revoked_at__isnull=True,
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
        )
        if access == "edit":
            shares = shares.filter(access_level="edit")
        if not shares.exists():
            raise NotFound()

    @classmethod
    def create(
        cls,
        tenant_id: uuid.UUID | str,
        actor_id: str,
        payload: Mapping[str, Any],
        correlation_id: str,
        idempotency_key: str,
    ) -> Dashboard:
        tenant = _tenant_uuid(tenant_id)
        _required_text(idempotency_key, "idempotency_key")
        existing = (
            Dashboard.objects.for_tenant(tenant)
            .filter(dashboard_code=str(payload.get("dashboard_code", "")).upper(), deleted_at__isnull=True)
            .first()
        )
        if existing is not None:
            if any(item.get("idempotency_key") == idempotency_key for item in existing.transition_history):
                return existing
            raise BIConflict("An active dashboard already uses this code.", code="DUPLICATE_CODE")
        try:
            return Dashboard.objects.create(
                tenant_id=tenant,
                created_by_id=actor_id,
                updated_by_id=actor_id,
                transition_history=[_record("create", actor_id, correlation_id, idempotency_key=idempotency_key)],
                **_model_payload(Dashboard, payload),
            )
        except IntegrityError as exc:
            raise BIConflict("An active dashboard already uses this code.", code="DUPLICATE_CODE") from exc

    @classmethod
    def update(
        cls,
        tenant_id: uuid.UUID | str,
        dashboard_id: object,
        actor_id: str,
        expected_version: int,
        payload: Mapping[str, Any],
        correlation_id: str,
        idempotency_key: str,
    ) -> Dashboard:
        tenant = _tenant_uuid(tenant_id)
        _required_text(idempotency_key, "idempotency_key")
        with transaction.atomic():
            obj = (
                Dashboard.objects.for_tenant(tenant)
                .select_for_update()
                .filter(pk=dashboard_id, deleted_at__isnull=True)
                .first()
            )
            if obj is None:
                raise NotFound()
            cls._authorize(obj, actor_id, "edit")
            replay = next(
                (item for item in obj.transition_history if item.get("idempotency_key") == idempotency_key), None
            )
            if replay is not None:
                if replay.get("command") != "update":
                    raise BIConflict("Idempotency key was used for another command.", code="IDEMPOTENCY_CONFLICT")
                return obj
            if obj.version != expected_version:
                raise BIConflict("The supplied version is stale.", code="VERSION_CONFLICT")
            for key, value in _model_payload(Dashboard, payload).items():
                if key not in {"id", "tenant_id", "version", "state", "deleted_at", "legacy_layout"}:
                    setattr(obj, key, value)
            if obj.state == "published":
                obj.state = "draft"
            obj.version += 1
            obj.updated_by_id = actor_id
            obj.transition_history = [
                *obj.transition_history,
                _record("update", actor_id, correlation_id, idempotency_key=idempotency_key),
            ]
            obj.save()
            return obj

    @classmethod
    def _publish_guard(cls, tenant_id: uuid.UUID | str, obj: Dashboard, command: str) -> None:
        if command != "publish":
            return
        widgets = (
            DashboardWidget.objects.for_tenant(_tenant_uuid(tenant_id))
            .filter(dashboard=obj, deleted_at__isnull=True)
            .select_related("query_definition", "report__query_definition")
        )
        if not widgets.exists():
            raise BIConflict("A dashboard needs at least one widget before publication.", code="PUBLISH_GUARD_FAILED")
        for widget in widgets:
            query = widget.query_definition or (widget.report.query_definition if widget.report_id else None)
            if query is None or query.state != "published" or (widget.report_id and widget.report.state != "published"):
                raise BIConflict("Every dashboard widget must use a published definition.", code="PUBLISH_GUARD_FAILED")
            _validate_filter_fields(query, obj.global_filters)

    @classmethod
    def publish(
        cls,
        tenant_id: uuid.UUID | str,
        dashboard_id: object,
        actor_id: str,
        expected_version: int,
        correlation_id: str,
        idempotency_key: str,
        reason: str = "",
    ) -> Dashboard:
        cls._authorize(_get(Dashboard, tenant_id, dashboard_id), actor_id, "owner")
        return cls._transition(
            tenant_id, dashboard_id, actor_id, expected_version, "publish", correlation_id, idempotency_key, reason
        )

    @classmethod
    def archive(
        cls,
        tenant_id: uuid.UUID | str,
        dashboard_id: object,
        actor_id: str,
        expected_version: int,
        correlation_id: str,
        idempotency_key: str,
        reason: str = "",
    ) -> Dashboard:
        cls._authorize(_get(Dashboard, tenant_id, dashboard_id), actor_id, "owner")
        return cls._transition(
            tenant_id, dashboard_id, actor_id, expected_version, "archive", correlation_id, idempotency_key, reason
        )

    @classmethod
    def restore(
        cls,
        tenant_id: uuid.UUID | str,
        dashboard_id: object,
        actor_id: str,
        expected_version: int,
        correlation_id: str,
        idempotency_key: str,
        reason: str = "",
    ) -> Dashboard:
        cls._authorize(_get(Dashboard, tenant_id, dashboard_id), actor_id, "owner")
        return cls._transition(
            tenant_id, dashboard_id, actor_id, expected_version, "restore", correlation_id, idempotency_key, reason
        )

    @classmethod
    def soft_delete(
        cls,
        tenant_id: uuid.UUID | str,
        dashboard_id: object,
        actor_id: str,
        expected_version: int,
        correlation_id: str,
        idempotency_key: str,
    ) -> Dashboard:
        cls._authorize(_get(Dashboard, tenant_id, dashboard_id), actor_id, "owner")
        return cls._soft_delete(tenant_id, dashboard_id, actor_id, expected_version, correlation_id, idempotency_key)

    @staticmethod
    def _assert_layout(dashboard: Dashboard, candidate: Mapping[str, Any], exclude_id: object | None = None) -> None:
        try:
            left, top = int(candidate["x"]), int(candidate["y"])
            width, height = int(candidate["width"]), int(candidate["height"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError({"layout": "x, y, width, and height must be integers."}) from exc
        right, bottom = left + width, top + height
        if left < 0 or top < 0 or not 1 <= width <= 12 or not 1 <= height <= 24 or right > 12:
            raise ValidationError({"layout": "Widget layout is outside the supported grid bounds."})
        for widget in (
            DashboardWidget.objects.for_tenant(dashboard.tenant_id)
            .filter(dashboard=dashboard, deleted_at__isnull=True)
            .exclude(pk=exclude_id)
        ):
            if (
                left < widget.x + widget.width
                and right > widget.x
                and top < widget.y + widget.height
                and bottom > widget.y
            ):
                raise BIConflict("Widget layout overlaps an existing widget.", code="LAYOUT_COLLISION")

    @classmethod
    def add_widget(
        cls,
        tenant_id: uuid.UUID | str,
        dashboard_id: object,
        actor_id: str,
        payload: Mapping[str, Any],
        correlation_id: str,
        idempotency_key: str,
    ) -> DashboardWidget:
        tenant = _tenant_uuid(tenant_id)
        _required_text(idempotency_key, "idempotency_key")
        dashboard = _get(Dashboard, tenant, dashboard_id)
        cls._authorize(dashboard, actor_id, "edit")
        data = dict(payload)
        if data.get("query_definition_id"):
            data["query_definition"] = _get(QueryDefinition, tenant, data.pop("query_definition_id"))
        if data.get("report_id"):
            data["report"] = _get(Report, tenant, data.pop("report_id"))
        if bool(data.get("query_definition")) == bool(data.get("report")):
            raise ValidationError({"source": "Exactly one governed query or report is required."})
        source_query = data.get("query_definition") or data["report"].query_definition
        if source_query is None:
            raise ValidationError({"source": "The selected report has no executable query definition."})
        _validate_visualization(str(data.get("widget_type", "")), data.get("visualization", {}))
        _validate_filter_fields(source_query, data.get("filters", []))
        cls._assert_layout(dashboard, data)
        with transaction.atomic():
            widget = DashboardWidget.objects.create(
                tenant_id=tenant, dashboard=dashboard, **_model_payload(DashboardWidget, data)
            )
            dashboard.version += 1
            dashboard.updated_by_id = actor_id
            dashboard.save(update_fields=("version", "updated_by_id", "updated_at"))
        return widget

    @classmethod
    def update_widget(
        cls,
        tenant_id: uuid.UUID | str,
        dashboard_id: object,
        widget_id: object,
        actor_id: str,
        expected_version: int,
        payload: Mapping[str, Any],
        correlation_id: str,
        idempotency_key: str,
    ) -> DashboardWidget:
        tenant = _tenant_uuid(tenant_id)
        _required_text(idempotency_key, "idempotency_key")
        dashboard = _get(Dashboard, tenant, dashboard_id)
        cls._authorize(dashboard, actor_id, "edit")
        with transaction.atomic():
            widget = (
                DashboardWidget.objects.for_tenant(tenant)
                .select_for_update()
                .filter(pk=widget_id, dashboard=dashboard, deleted_at__isnull=True)
                .first()
            )
            if widget is None:
                raise NotFound()
            if widget.version != expected_version:
                raise BIConflict("The supplied version is stale.", code="VERSION_CONFLICT")
            data = dict(payload)
            if "query_definition_id" in data:
                data["query_definition"] = _get(QueryDefinition, tenant, data.pop("query_definition_id"))
                data["report"] = None
            if "report_id" in data:
                data["report"] = _get(Report, tenant, data.pop("report_id"))
                data["query_definition"] = None
            source_query = data.get("query_definition", widget.query_definition)
            source_report = data.get("report", widget.report)
            if bool(source_query) == bool(source_report):
                raise ValidationError({"source": "Exactly one governed query or report is required."})
            resolved_query = source_query or source_report.query_definition
            if resolved_query is None:
                raise ValidationError({"source": "The selected report has no executable query definition."})
            _validate_visualization(
                str(data.get("widget_type", widget.widget_type)), data.get("visualization", widget.visualization)
            )
            _validate_filter_fields(resolved_query, data.get("filters", widget.filters))
            candidate = {key: data.get(key, getattr(widget, key)) for key in ("x", "y", "width", "height")}
            cls._assert_layout(dashboard, candidate, widget.id)
            for key, value in _model_payload(DashboardWidget, data).items():
                if key not in {"id", "tenant_id", "dashboard", "version", "deleted_at"}:
                    setattr(widget, key, value)
            widget.version += 1
            widget.save()
            dashboard.version += 1
            dashboard.updated_by_id = actor_id
            dashboard.save(update_fields=("version", "updated_by_id", "updated_at"))
            return widget

    @classmethod
    def remove_widget(
        cls,
        tenant_id: uuid.UUID | str,
        dashboard_id: object,
        widget_id: object,
        actor_id: str,
        correlation_id: str,
        idempotency_key: str,
    ) -> DashboardWidget:
        tenant = _tenant_uuid(tenant_id)
        _required_text(idempotency_key, "idempotency_key")
        dashboard = _get(Dashboard, tenant, dashboard_id)
        cls._authorize(dashboard, actor_id, "edit")
        with transaction.atomic():
            widget = (
                DashboardWidget.objects.for_tenant(tenant)
                .select_for_update()
                .filter(pk=widget_id, dashboard=dashboard, deleted_at__isnull=True)
                .first()
            )
            if widget is None:
                raise NotFound()
            widget.deleted_at = timezone.now()
            widget.version += 1
            widget.save(update_fields=("deleted_at", "version", "updated_at"))
            dashboard.version += 1
            dashboard.updated_by_id = actor_id
            dashboard.save(update_fields=("version", "updated_by_id", "updated_at"))
            return widget

    @classmethod
    def reorder_widgets(
        cls,
        tenant_id: uuid.UUID | str,
        dashboard_id: object,
        actor_id: str,
        expected_version: int,
        widgets: Iterable[Mapping[str, Any]],
        correlation_id: str,
        idempotency_key: str,
    ) -> Dashboard:
        tenant = _tenant_uuid(tenant_id)
        _required_text(idempotency_key, "idempotency_key")
        items = list(widgets)
        with transaction.atomic():
            dashboard = (
                Dashboard.objects.for_tenant(tenant)
                .select_for_update()
                .filter(pk=dashboard_id, deleted_at__isnull=True)
                .first()
            )
            if dashboard is None:
                raise NotFound()
            cls._authorize(dashboard, actor_id, "edit")
            if dashboard.version != expected_version:
                raise BIConflict("The supplied version is stale.", code="VERSION_CONFLICT")
            current = {
                str(item.id): item
                for item in DashboardWidget.objects.for_tenant(tenant)
                .select_for_update()
                .filter(dashboard=dashboard, deleted_at__isnull=True)
            }
            if {str(item.get("id")) for item in items} != set(current):
                raise ValidationError({"widgets": "The complete active widget layout is required."})
            rectangles: list[tuple[int, int, int, int]] = []
            for order, data in enumerate(items):
                x, y, width, height = (int(data[key]) for key in ("x", "y", "width", "height"))
                if x < 0 or y < 0 or not 1 <= width <= 12 or not 1 <= height <= 24 or x + width > 12:
                    raise ValidationError({"widgets": "A widget is outside layout bounds."})
                rect = (x, y, x + width, y + height)
                if any(
                    rect[0] < old[2] and rect[2] > old[0] and rect[1] < old[3] and rect[3] > old[1]
                    for old in rectangles
                ):
                    raise BIConflict("Widget layout contains a collision.", code="LAYOUT_COLLISION")
                rectangles.append(rect)
                widget = current[str(data["id"])]
                widget.x, widget.y, widget.width, widget.height, widget.display_order = x, y, width, height, order
                widget.version += 1
                widget.save()
            dashboard.version += 1
            dashboard.updated_by_id = actor_id
            dashboard.save(update_fields=("version", "updated_by_id", "updated_at"))
            return dashboard

    @classmethod
    def share(
        cls,
        tenant_id: uuid.UUID | str,
        dashboard_id: object,
        actor_id: str,
        payload: Mapping[str, Any],
        correlation_id: str,
        idempotency_key: str,
    ) -> DashboardShare:
        tenant = _tenant_uuid(tenant_id)
        _required_text(idempotency_key, "idempotency_key")
        dashboard = _get(Dashboard, tenant, dashboard_id)
        cls._authorize(dashboard, actor_id, "owner")
        if payload.get("subject_type") not in {"user", "role"}:
            raise ValidationError({"subject_type": "Use user or role."})
        _required_text(payload.get("subject_id"), "subject_id")
        if payload.get("access_level") not in {"view", "edit"}:
            raise ValidationError({"access_level": "Use view or edit."})
        expires_at = payload.get("expires_at")
        if expires_at is not None and expires_at <= timezone.now():
            raise ValidationError({"expires_at": "Expiry must be in the future."})
        with transaction.atomic():
            share = (
                DashboardShare.objects.for_tenant(tenant)
                .select_for_update()
                .filter(
                    dashboard=dashboard,
                    subject_type=payload["subject_type"],
                    subject_id=payload["subject_id"],
                    revoked_at__isnull=True,
                )
                .first()
            )
            if share is None:
                share = DashboardShare.objects.create(
                    tenant_id=tenant,
                    dashboard=dashboard,
                    shared_by_id=actor_id,
                    **_model_payload(DashboardShare, payload),
                )
            else:
                share.access_level = payload["access_level"]
                share.expires_at = expires_at
                share.save(update_fields=("access_level", "expires_at", "updated_at"))
        logger.info(
            "bi.dashboard.shared",
            extra={
                "tenant_id": str(tenant),
                "actor_id": actor_id,
                "resource_id": str(dashboard.id),
                "correlation_id": correlation_id,
            },
        )
        return share

    @classmethod
    def update_share(
        cls,
        tenant_id: uuid.UUID | str,
        dashboard_id: object,
        share_id: object,
        actor_id: str,
        payload: Mapping[str, Any],
        correlation_id: str,
        idempotency_key: str,
    ) -> DashboardShare:
        tenant = _tenant_uuid(tenant_id)
        _required_text(idempotency_key, "idempotency_key")
        cls._authorize(_get(Dashboard, tenant, dashboard_id), actor_id, "owner")
        share = (
            DashboardShare.objects.for_tenant(tenant)
            .filter(pk=share_id, dashboard_id=dashboard_id, revoked_at__isnull=True)
            .first()
        )
        if share is None:
            raise NotFound()
        if "access_level" in payload and payload["access_level"] not in {"view", "edit"}:
            raise ValidationError({"access_level": "Use view or edit."})
        if payload.get("expires_at") is not None and payload["expires_at"] <= timezone.now():
            raise ValidationError({"expires_at": "Expiry must be in the future."})
        for key in ("access_level", "expires_at"):
            if key in payload:
                setattr(share, key, payload[key])
        share.save()
        return share

    @classmethod
    def revoke_share(
        cls,
        tenant_id: uuid.UUID | str,
        dashboard_id: object,
        share_id: object,
        actor_id: str,
        correlation_id: str,
        idempotency_key: str,
    ) -> DashboardShare:
        tenant = _tenant_uuid(tenant_id)
        _required_text(idempotency_key, "idempotency_key")
        cls._authorize(_get(Dashboard, tenant, dashboard_id), actor_id, "owner")
        with transaction.atomic():
            share = (
                DashboardShare.objects.for_tenant(tenant)
                .select_for_update()
                .filter(pk=share_id, dashboard_id=dashboard_id)
                .first()
            )
            if share is None:
                raise NotFound()
            if share.revoked_at is None:
                share.revoked_at = timezone.now()
                share.save(update_fields=("revoked_at", "updated_at"))
        logger.info(
            "bi.dashboard.share_revoked",
            extra={
                "tenant_id": str(tenant),
                "actor_id": actor_id,
                "resource_id": str(dashboard_id),
                "correlation_id": correlation_id,
            },
        )
        return share

    @classmethod
    def enqueue_execution(
        cls,
        tenant_id: uuid.UUID | str,
        dashboard_id: object,
        actor_id: str,
        parameters: Mapping[str, Any],
        correlation_id: str,
        idempotency_key: str,
    ) -> list[QueryExecution]:
        dashboard = _get(Dashboard, tenant_id, dashboard_id)
        cls._authorize(dashboard, actor_id, "view")
        if dashboard.state != "published":
            raise BIConflict("Only published dashboards can execute.", code="NOT_PUBLISHED")
        executions: list[QueryExecution] = []
        fingerprints: dict[str, QueryExecution] = {}
        widgets = (
            DashboardWidget.objects.for_tenant(_tenant_uuid(tenant_id))
            .filter(dashboard=dashboard, deleted_at__isnull=True)
            .select_related("query_definition", "report__query_definition")
        )
        for index, widget in enumerate(widgets):
            query = widget.query_definition or widget.report.query_definition
            effective = QueryService._effective_parameters(query, parameters)
            QueryService.validate(tenant_id, query.id, effective)
            effective["__bi_filters"] = [*dashboard.global_filters, *widget.filters]
            fingerprint = hashlib.sha256(
                json.dumps({"query": str(query.id), "parameters": effective}, sort_keys=True, default=str).encode()
            ).hexdigest()
            if fingerprint not in fingerprints:
                fingerprints[fingerprint] = ExecutionService.enqueue(
                    tenant_id,
                    query,
                    actor_id,
                    effective,
                    correlation_id,
                    f"{idempotency_key}:{index}",
                    report=widget.report,
                    dashboard=dashboard,
                )
                executions.append(fingerprints[fingerprint])
        return executions


class ExecutionService:
    @classmethod
    def enqueue(
        cls,
        tenant_id: uuid.UUID | str,
        query: QueryDefinition,
        actor_id: str,
        parameters: Mapping[str, Any],
        correlation_id: str,
        idempotency_key: str,
        *,
        report: Report | None = None,
        dashboard: Dashboard | None = None,
    ) -> QueryExecution:
        tenant = _tenant_uuid(tenant_id)
        key = _required_text(idempotency_key, "idempotency_key")
        existing = QueryExecution.objects.for_tenant(tenant).filter(idempotency_key=key).first()
        if existing is not None:
            same_request = (
                existing.query_definition_id == query.id
                and existing.report_id == (report.id if report else None)
                and existing.dashboard_id == (dashboard.id if dashboard else None)
                and existing.parameters == dict(parameters)
            )
            if not same_request:
                raise BIConflict("Idempotency key was used for another execution.", code="IDEMPOTENCY_CONFLICT")
            return existing
        with transaction.atomic():
            job = async_jobs.enqueue(
                tenant, actor_id, "business_intelligence.execute_query", {"tenant_id": str(tenant)}, key
            )
            existing = QueryExecution.objects.for_tenant(tenant).filter(idempotency_key=key).first()
            if existing is not None:
                return existing
            execution = QueryExecution.objects.create(
                tenant_id=tenant,
                query_definition=query,
                report=report,
                dashboard=dashboard,
                async_job=job,
                actor_id=actor_id,
                idempotency_key=key,
                definition_version=query.version,
                dataset_key=query.dataset_key,
                dataset_version=query.dataset_version,
                dataset_schema_fingerprint=query.dataset_schema_fingerprint,
                parameters=dict(parameters),
                status="queued",
                transition_history=[_record("enqueue", actor_id, correlation_id)],
            )
            job.payload = {"tenant_id": str(tenant), "execution_id": str(execution.id)}
            job.correlation_id = correlation_id
            job.save(update_fields=("payload", "correlation_id", "updated_at"))
        logger.info(
            "bi.execution.enqueued",
            extra={
                "tenant_id": str(tenant),
                "actor_id": actor_id,
                "resource_id": str(execution.id),
                "dataset_key": query.dataset_key,
                "status": "queued",
                "correlation_id": correlation_id,
            },
        )
        return execution

    @classmethod
    def execute_job(cls, tenant_id: uuid.UUID | str, execution_id: object) -> QueryExecution:
        tenant = _tenant_uuid(tenant_id)
        with transaction.atomic():
            execution = (
                QueryExecution.objects.for_tenant(tenant)
                .select_for_update()
                .select_related("query_definition")
                .filter(pk=execution_id)
                .first()
            )
            if execution is None:
                raise NotFound()
            if execution.status in TERMINAL_EXECUTION_STATES:
                return execution
            execution.status = "running"
            execution.started_at = timezone.now()
            execution.transition_history = [
                *execution.transition_history,
                _record("start", execution.actor_id, execution.async_job.correlation_id),
            ]
            execution.save(update_fields=("status", "started_at", "transition_history", "updated_at"))
        started = timezone.now()
        query = execution.query_definition
        logger.info(
            "bi.execution.started",
            extra={
                "tenant_id": str(tenant),
                "actor_id": execution.actor_id,
                "resource_id": str(execution.id),
                "dataset_key": query.dataset_key,
                "status": "running",
                "correlation_id": execution.async_job.correlation_id,
            },
        )
        try:
            provider = _registry_get(query.dataset_key)
            spec = {field.name: getattr(query, field.name) for field in QueryDefinition._meta.concrete_fields}
            execution_parameters = dict(execution.parameters)
            additional_filters = execution_parameters.pop("__bi_filters", [])
            if additional_filters:
                spec["filters"] = [*spec.get("filters", []), *additional_filters]
            validated = provider.validate(tenant, spec)
            cache_key = cls.cache_key(tenant, provider, query, execution.parameters)
            try:
                cached = cache.get(cache_key) if query.cache_ttl_seconds else None
            except Exception:
                cached = None
            result = cached if cached is not None else provider.execute(tenant, validated, execution_parameters)
            result_data = _descriptor_dict(result)
            columns = list(result_data.get("columns", []))
            raw_rows = list(result_data.get("rows", []))
            rows, bounded_truncation = cls._bound_rows(raw_rows)
            truncated = bool(result_data.get("truncated", False)) or bounded_truncation
            freshness_token = str(result_data.get("freshness_token", ""))
            data_as_of = result_data.get("data_as_of")
            if cached is None and query.cache_ttl_seconds:
                try:
                    cache.set(
                        cache_key,
                        {
                            "columns": columns,
                            "rows": rows,
                            "row_count": int(result_data.get("row_count", len(raw_rows))),
                            "truncated": truncated,
                            "freshness_token": freshness_token,
                            "data_as_of": data_as_of,
                        },
                        query.cache_ttl_seconds,
                    )
                except Exception:
                    pass
            with transaction.atomic():
                execution = QueryExecution.objects.for_tenant(tenant).select_for_update().get(pk=execution.id)
                if execution.status == "cancelled":
                    return execution
                execution.status = "succeeded"
                execution.result_columns = columns
                execution.result_rows = rows
                execution.row_count = int(result_data.get("row_count", len(raw_rows)))
                execution.truncated = truncated
                execution.cache_hit = cached is not None
                execution.dataset_version, execution.dataset_schema_fingerprint = _dataset_provenance(provider)
                execution.effective_query_fingerprint = str(getattr(validated, "fingerprint", ""))
                execution.freshness_token = freshness_token
                execution.data_as_of = data_as_of
                execution.duration_ms = max(0, int((timezone.now() - started).total_seconds() * 1000))
                execution.completed_at = timezone.now()
                execution.transition_history = [
                    *execution.transition_history,
                    _record("succeed", execution.actor_id, execution.async_job.correlation_id),
                ]
                execution.save()
            logger.info(
                "bi.execution.succeeded",
                extra={
                    "tenant_id": str(tenant),
                    "actor_id": execution.actor_id,
                    "resource_id": str(execution.id),
                    "dataset_key": query.dataset_key,
                    "duration_ms": execution.duration_ms,
                    "row_count": execution.row_count,
                    "status": "succeeded",
                    "correlation_id": execution.async_job.correlation_id,
                },
            )
            return execution
        except Exception as exc:
            with transaction.atomic():
                execution = QueryExecution.objects.for_tenant(tenant).select_for_update().get(pk=execution.id)
                if execution.status not in TERMINAL_EXECUTION_STATES:
                    execution.status = "failed"
                    execution.result_columns = []
                    execution.result_rows = []
                    execution.error_code = "PROVIDER_FAILURE"
                    execution.error_message = "The dataset provider could not complete this execution."
                    execution.completed_at = timezone.now()
                    execution.transition_history = [
                        *execution.transition_history,
                        _record("fail", execution.actor_id, execution.async_job.correlation_id),
                    ]
                    execution.save()
            logger.warning(
                "bi.execution.failed",
                extra={
                    "tenant_id": str(tenant),
                    "actor_id": execution.actor_id,
                    "resource_id": str(execution.id),
                    "dataset_key": query.dataset_key,
                    "status": "failed",
                    "correlation_id": execution.async_job.correlation_id,
                },
            )
            raise CapabilityUnavailable() from exc

    @staticmethod
    def _bound_rows(rows: list[Any]) -> tuple[list[Any], bool]:
        bounded = rows[:1000]
        while bounded and len(json.dumps(bounded, default=str).encode("utf-8")) > 2 * 1024 * 1024:
            bounded.pop()
        return bounded, len(bounded) < len(rows)

    @staticmethod
    def cache_key(
        tenant_id: uuid.UUID | str, provider: object, query: QueryDefinition, parameters: Mapping[str, Any]
    ) -> str:
        descriptor = _descriptor_dict(provider.describe())
        freshness_getter = getattr(provider, "freshness_token", None)
        freshness = (
            freshness_getter(_tenant_uuid(tenant_id))
            if callable(freshness_getter)
            else descriptor.get("version", "unknown")
        )
        canonical = json.dumps(parameters, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        return f"bi:{tenant_id}:{descriptor.get('version')}:{query.version}:{freshness}:{digest}"

    @classmethod
    def cancel(
        cls, tenant_id: uuid.UUID | str, execution_id: object, actor_id: str, correlation_id: str, idempotency_key: str
    ) -> QueryExecution:
        tenant = _tenant_uuid(tenant_id)
        _required_text(idempotency_key, "idempotency_key")
        with transaction.atomic():
            execution = QueryExecution.objects.for_tenant(tenant).select_for_update().filter(pk=execution_id).first()
            if execution is None:
                raise NotFound()
            if execution.status in TERMINAL_EXECUTION_STATES:
                return execution
            execution.status = "cancelled"
            execution.completed_at = timezone.now()
            execution.transition_history = [*execution.transition_history, _record("cancel", actor_id, correlation_id)]
            execution.save(update_fields=("status", "completed_at", "transition_history", "updated_at"))
            try:
                async_jobs.transition(
                    execution.async_job_id, tenant, "cancelled", actor_id=actor_id, reason="BI execution cancelled"
                )
            except async_jobs.InvalidJobTransition:
                pass
        return execution

    @staticmethod
    def get_result(tenant_id: uuid.UUID | str, execution_id: object) -> QueryExecution:
        execution = _get(QueryExecution, tenant_id, execution_id, include_deleted=True)
        if execution.status != "succeeded":
            raise BIConflict("Results are available only after successful execution.", code="RESULT_NOT_READY")
        return execution

    @staticmethod
    def purge_expired_results(tenant_id: uuid.UUID | str, cutoff: datetime) -> int:
        tenant = _tenant_uuid(tenant_id)
        queryset = QueryExecution.objects.for_tenant(tenant).filter(completed_at__lt=cutoff, status="succeeded")
        return queryset.update(result_rows=[], result_purged_at=timezone.now())


__all__ = [
    "BIConflict",
    "CapabilityUnavailable",
    "DashboardService",
    "DatasetCatalogService",
    "ExecutionService",
    "QueryService",
    "ReportService",
]
