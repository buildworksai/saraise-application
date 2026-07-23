"""Governed API v2 controllers for workflow automation."""

from __future__ import annotations

import uuid
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from django.utils.dateparse import parse_datetime
from rest_framework import mixins, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.access import RequiresAccess
from src.core.api import GovernedAPIViewMixin
from src.core.auth_utils import get_user_tenant_id

from .extensions import (
    AssigneeSearchInvocation,
    WorkflowExtensionNotFound,
    action_registry,
    assignee_registry,
    condition_registry,
    subject_registry,
)
from .health import sanitized_health_payload
from .models import Workflow, WorkflowAutomationConfiguration, WorkflowInstance, WorkflowTask
from .permissions import MODULE_ENTITLEMENT, access_metadata
from .serializers import (
    WorkflowCloneSerializer,
    WorkflowConfigurationImportSerializer,
    WorkflowConfigurationPreviewSerializer,
    WorkflowConfigurationRollbackSerializer,
    WorkflowConfigurationWriteSerializer,
    WorkflowCreateSerializer,
    WorkflowDefinitionValidationSerializer,
    WorkflowDetailSerializer,
    WorkflowInstanceCancelSerializer,
    WorkflowInstanceDetailSerializer,
    WorkflowInstanceListSerializer,
    WorkflowInstanceStartSerializer,
    WorkflowListSerializer,
    WorkflowPublishSerializer,
    WorkflowTaskCompleteSerializer,
    WorkflowTaskDetailSerializer,
    WorkflowTaskListSerializer,
    WorkflowTaskRejectSerializer,
    WorkflowUpdateSerializer,
)
from .services import (
    WorkflowConfigurationService,
    WorkflowDefinitionService,
    WorkflowExecutionService,
    WorkflowTaskService,
)

SUCCESSOR = '</api/v2/workflow-automation/>; rel="successor-version"'


class StrictSessionAuthentication(SessionAuthentication):
    """Standard session/CSRF authentication plus a typed tenant binding."""

    def authenticate(self, request: Request) -> tuple[object, object] | None:
        result = super().authenticate(request)
        if result is None:
            return None
        user, auth = result
        tenant_value = get_user_tenant_id(user)
        try:
            tenant_id = uuid.UUID(str(tenant_value))
        except (TypeError, ValueError) as exc:
            raise PermissionDenied("Authenticated identity has no valid tenant context.") from exc
        request.tenant_id = tenant_id  # type: ignore[attr-defined]
        return user, auth

    def authenticate_header(self, request: Request) -> str:
        del request
        return "Session"


class DeprecatedV1HeadersMixin:
    """Mark the shared compatibility adapter without duplicating business logic."""

    def finalize_response(self, request: Request, response: Response, *args: Any, **kwargs: Any) -> Response:
        response = super().finalize_response(request, response, *args, **kwargs)  # type: ignore[misc]
        if request.path.startswith("/api/v1/workflow-automation/"):
            response["Deprecation"] = "true"
            tenant_id = getattr(request, "tenant_id", None)
            if isinstance(tenant_id, uuid.UUID):
                response["Sunset"] = str(
                    WorkflowConfigurationService.value(tenant_id, "operational.v1_sunset")
                )
            response["Link"] = SUCCESSOR
        return response


class GovernedWorkflowViewSet(DeprecatedV1HeadersMixin, GovernedAPIViewMixin, viewsets.GenericViewSet):
    authentication_classes = (StrictSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    required_entitlement = MODULE_ENTITLEMENT
    access_prefix = ""

    def get_permissions(self) -> list[object]:
        action_name = getattr(self, "action", "")
        try:
            permission, quota = access_metadata(f"{self.access_prefix}_{action_name}")
        except KeyError:
            permission, quota = None, None
        self.required_permission = permission
        self.quota_resource = quota
        tenant_id = getattr(self.request, "tenant_id", None)
        self.quota_cost = (
            WorkflowConfigurationService.value(tenant_id, "operational.api_quota_cost")
            if isinstance(tenant_id, uuid.UUID)
            else None
        )
        return super().get_permissions()

    @property
    def tenant_id(self) -> uuid.UUID:
        tenant_id = getattr(self.request, "tenant_id", None)
        if not isinstance(tenant_id, uuid.UUID):
            raise PermissionDenied("A valid tenant context is required.")
        return tenant_id

    def _object(self, obj: object) -> object:
        self.check_object_permissions(self.request, obj)
        return obj


def _date_filter(request: Request, name: str) -> datetime | None:
    value = request.query_params.get(name)
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValidationError({name: ["Must be an ISO-8601 datetime."]})
    return parsed


def _uuid_filter(request: Request, name: str) -> uuid.UUID | None:
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValidationError({name: ["Must be a valid UUID."]}) from exc


def _etag(workflow: object) -> str:
    updated_at = getattr(workflow, "updated_at")
    return f'"{updated_at.isoformat()}"'


class WorkflowViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    GovernedWorkflowViewSet,
):
    access_prefix = "workflow"

    def get_serializer_class(self) -> type[Any]:
        return {
            "list": WorkflowListSerializer,
            "retrieve": WorkflowDetailSerializer,
            "create": WorkflowCreateSerializer,
            "partial_update": WorkflowUpdateSerializer,
            "validate": WorkflowDefinitionValidationSerializer,
            "publish": WorkflowPublishSerializer,
            "archive": WorkflowPublishSerializer,
            "clone": WorkflowCloneSerializer,
        }.get(self.action, WorkflowDetailSerializer)

    def get_queryset(self):
        tenant_id = getattr(self.request, "tenant_id", None)
        if not isinstance(tenant_id, uuid.UUID):
            return Workflow.objects.none()
        return WorkflowDefinitionService.list_workflows(tenant_id, self._filters())

    def _filters(self) -> dict[str, Any]:
        return {
            "status": self.request.query_params.get("status"),
            "workflow_type": self.request.query_params.get("workflow_type"),
            "trigger_type": self.request.query_params.get("trigger_type"),
            "key": self.request.query_params.get("key"),
            "created_by": self.request.query_params.get("created_by"),
            "updated_after": _date_filter(self.request, "updated_after"),
            "search": self.request.query_params.get("search", ""),
            "ordering": self.request.query_params.get("ordering", "-updated_at"),
        }

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is None:
            raise RuntimeError("Governed workflow pagination is not configured")
        return self.get_paginated_response(WorkflowListSerializer(page, many=True).data)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        workflow = self._object(WorkflowDefinitionService.get_workflow(self.tenant_id, kwargs["pk"]))
        response = Response(WorkflowDetailSerializer(workflow).data)
        response["ETag"] = _etag(workflow)
        return response

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = WorkflowCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workflow = WorkflowDefinitionService.create_workflow(self.tenant_id, request.user, serializer.validated_data)
        response = Response(WorkflowDetailSerializer(workflow).data, status=status.HTTP_201_CREATED)
        response["ETag"] = _etag(workflow)
        return response

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        data = dict(request.data)
        header = request.headers.get("If-Match", "").strip().strip('"')
        if "expected_updated_at" not in data and header:
            data["expected_updated_at"] = header
        serializer = WorkflowUpdateSerializer(data=data, partial=False)
        serializer.is_valid(raise_exception=True)
        workflow = WorkflowDefinitionService.update_workflow(
            self.tenant_id,
            kwargs["pk"],
            request.user,
            serializer.validated_data,
        )
        response = Response(WorkflowDetailSerializer(workflow).data)
        response["ETag"] = _etag(workflow)
        return response

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        WorkflowDefinitionService.delete_draft(self.tenant_id, kwargs["pk"], request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=("post",), url_path="validate")
    def validate(self, request: Request) -> Response:
        serializer = WorkflowDefinitionValidationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = WorkflowDefinitionService.validate_definition(self.tenant_id, serializer.validated_data)
        return Response(result.as_dict())

    @action(detail=True, methods=("post",), url_path="publish")
    def publish(self, request: Request, pk: str | None = None) -> Response:
        serializer = WorkflowPublishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workflow = WorkflowDefinitionService.publish_workflow(
            self.tenant_id,
            pk,
            request.user,
            serializer.validated_data["transition_key"],
        )
        return Response(WorkflowDetailSerializer(workflow).data)

    @action(detail=True, methods=("post",), url_path="archive")
    def archive(self, request: Request, pk: str | None = None) -> Response:
        serializer = WorkflowPublishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workflow = WorkflowDefinitionService.archive_workflow(
            self.tenant_id,
            pk,
            request.user,
            serializer.validated_data["transition_key"],
        )
        return Response(WorkflowDetailSerializer(workflow).data)

    @action(detail=True, methods=("post",), url_path="clone")
    def clone(self, request: Request, pk: str | None = None) -> Response:
        serializer = WorkflowCloneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workflow = WorkflowDefinitionService.clone_version(self.tenant_id, pk, request.user)
        return Response(WorkflowDetailSerializer(workflow).data, status=status.HTTP_201_CREATED)


class WorkflowInstanceViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    GovernedWorkflowViewSet,
):
    access_prefix = "instance"

    def get_serializer_class(self) -> type[Any]:
        return WorkflowInstanceStartSerializer if self.action == "create" else (
            WorkflowInstanceListSerializer if self.action == "list" else WorkflowInstanceDetailSerializer
        )

    def _filters(self) -> dict[str, Any]:
        return {
            "workflow_id": _uuid_filter(self.request, "workflow_id"),
            "state": self.request.query_params.get("state"),
            "entity_type": self.request.query_params.get("entity_type"),
            "entity_id": _uuid_filter(self.request, "entity_id"),
            "started_by": self.request.query_params.get("started_by"),
            "created_after": _date_filter(self.request, "created_after"),
            "created_before": _date_filter(self.request, "created_before"),
            "search": self.request.query_params.get("search", ""),
            "ordering": self.request.query_params.get("ordering", "-created_at"),
        }

    def get_queryset(self):
        tenant_id = getattr(self.request, "tenant_id", None)
        if not isinstance(tenant_id, uuid.UUID):
            return WorkflowInstance.objects.none()
        return WorkflowExecutionService.list_instances(tenant_id, self._filters())

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        if page is None:
            raise RuntimeError("Governed workflow pagination is not configured")
        return self.get_paginated_response(WorkflowInstanceListSerializer(page, many=True).data)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self._object(WorkflowExecutionService.get_instance(self.tenant_id, kwargs["pk"]))
        return Response(WorkflowInstanceDetailSerializer(instance).data)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = WorkflowInstanceStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        instance = WorkflowExecutionService.start_workflow(
            self.tenant_id,
            values["workflow_id"],
            request.user,
            values["context_data"],
            values["idempotency_key"],
            values.get("entity_type"),
            values.get("entity_id"),
            values.get("priority"),
        )
        response_status = status.HTTP_200_OK if instance.state in {"completed", "failed", "cancelled"} else status.HTTP_202_ACCEPTED
        return Response(WorkflowInstanceDetailSerializer(instance).data, status=response_status)

    @action(detail=True, methods=("post",), url_path="cancel")
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        serializer = WorkflowInstanceCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = WorkflowExecutionService.cancel_instance(
            self.tenant_id,
            pk,
            request.user,
            serializer.validated_data["transition_key"],
        )
        return Response(WorkflowInstanceDetailSerializer(instance).data)


class WorkflowTaskViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GovernedWorkflowViewSet,
):
    access_prefix = "task"

    def get_serializer_class(self) -> type[Any]:
        return {
            "list": WorkflowTaskListSerializer,
            "retrieve": WorkflowTaskDetailSerializer,
            "complete": WorkflowTaskCompleteSerializer,
            "reject": WorkflowTaskRejectSerializer,
        }.get(self.action, WorkflowTaskDetailSerializer)

    def _filters(self) -> dict[str, Any]:
        return {
            "status": self.request.query_params.get("status"),
            "workflow_id": _uuid_filter(self.request, "workflow_id"),
            "instance_id": _uuid_filter(self.request, "instance_id"),
            "assignment_kind": self.request.query_params.get("assignment_kind"),
            "overdue": self.request.query_params.get("overdue"),
            "due_before": _date_filter(self.request, "due_before"),
            "scope": self.request.query_params.get("scope", "mine"),
            "search": self.request.query_params.get("search", ""),
            "ordering": self.request.query_params.get("ordering", "due_date,created_at"),
        }

    def get_queryset(self):
        tenant_id = getattr(self.request, "tenant_id", None)
        if not isinstance(tenant_id, uuid.UUID):
            return WorkflowTask.objects.none()
        return WorkflowTaskService.list_tasks(tenant_id, self.request.user, self._filters())

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        if page is None:
            raise RuntimeError("Governed workflow pagination is not configured")
        return self.get_paginated_response(WorkflowTaskListSerializer(page, many=True).data)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        task = self._object(WorkflowTaskService.get_task(self.tenant_id, kwargs["pk"], request.user))
        return Response(WorkflowTaskDetailSerializer(task).data)

    @action(detail=True, methods=("post",), url_path="complete")
    def complete(self, request: Request, pk: str | None = None) -> Response:
        serializer = WorkflowTaskCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = WorkflowTaskService.complete_task(
            self.tenant_id,
            pk,
            request.user,
            serializer.validated_data["meta_data"],
            serializer.validated_data["transition_key"],
        )
        return Response(WorkflowTaskDetailSerializer(task).data)

    @action(detail=True, methods=("post",), url_path="reject")
    def reject(self, request: Request, pk: str | None = None) -> Response:
        serializer = WorkflowTaskRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = WorkflowTaskService.reject_task(
            self.tenant_id,
            pk,
            request.user,
            serializer.validated_data["reason"],
            serializer.validated_data["meta_data"],
            serializer.validated_data["transition_key"],
        )
        return Response(WorkflowTaskDetailSerializer(task).data)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if is_dataclass(value):
        return {field.name: _json_safe(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return value


def _ui_schema(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    schema = raw.get("configuration_schema") or raw.get("condition_schema") or {}
    properties = schema.get("properties", {}) if isinstance(schema, Mapping) else {}
    required = set(schema.get("required", [])) if isinstance(schema, Mapping) else set()
    lookups = {
        item.get("field"): item
        for item in raw.get("lookup_descriptors", [])
        if isinstance(item, Mapping)
    }
    output: list[dict[str, Any]] = []
    for key, definition in properties.items() if isinstance(properties, Mapping) else ():
        if key == "handler" or not isinstance(definition, Mapping):
            continue
        common = {
            "key": key,
            "label": str(definition.get("title") or key.replace("_", " ").title()),
            "required": key in required,
        }
        if definition.get("description"):
            common["description"] = str(definition["description"])
        lookup = lookups.get(key)
        if lookup:
            output.append({**common, "kind": "lookup", "lookup_key": lookup["provider_key"]})
        elif isinstance(definition.get("enum"), list):
            output.append(
                {
                    **common,
                    "kind": "select",
                    "options": [
                        {"value": str(option), "label": str(option).replace("_", " ").title()}
                        for option in definition["enum"]
                    ],
                }
            )
        elif definition.get("type") in {"integer", "number"}:
            output.append(
                {
                    **common,
                    "kind": "number",
                    **({"minimum": definition["minimum"]} if "minimum" in definition else {}),
                    **({"maximum": definition["maximum"]} if "maximum" in definition else {}),
                }
            )
        elif definition.get("type") == "boolean":
            output.append({**common, "kind": "boolean"})
        else:
            output.append({**common, "kind": "text"})
    return output


def _catalog_item(descriptor: object, kind: str) -> dict[str, Any]:
    raw = _json_safe(descriptor)
    availability = raw.get("availability", "available")
    if availability == "unavailable":
        availability = "degraded"
    configuration_schema = raw.get("configuration_schema") or raw.get("condition_schema") or raw.get("result_schema") or {"type": "object"}
    return {
        **raw,
        "kind": kind,
        "availability": availability,
        "reason": raw.get("availability_reason") or None,
        "configuration_schema": configuration_schema,
        "ui_schema": _ui_schema(raw),
        "lookup_descriptors": raw.get("lookup_descriptors", []),
        "descriptor_fingerprint": str(getattr(descriptor, "contract_fingerprint", "")),
        "idempotent": bool(raw.get("idempotency_supported", False)),
        "network_access": bool(raw.get("outbound_network_required", False)),
        "quota_cost": int(raw.get("quota_cost", 0)),
    }


class CatalogViewSet(GovernedWorkflowViewSet):
    access_prefix = "catalog"

    def _catalog(self, registry: object, kind: str) -> Response:
        descriptors = registry.catalog(None)  # type: ignore[attr-defined]
        limits = WorkflowConfigurationService.get_configuration(self.tenant_id).document["limits"]
        default_limit = int(limits["catalog_default_limit"])
        maximum = int(limits["catalog_max_limit"])
        raw_limit = self.request.query_params.get("limit", str(default_limit))
        ordering = self.request.query_params.get("ordering", "key")
        allowed_orderings = WorkflowConfigurationService.value(
            self.tenant_id, "allowed_values.catalog_orderings"
        )
        try:
            limit = int(raw_limit)
        except ValueError as exc:
            raise ValidationError({"limit": ["Must be an integer."]}) from exc
        if limit < 1 or limit > maximum:
            raise ValidationError({"limit": [f"Must be between 1 and {maximum}."]})
        if ordering not in allowed_orderings:
            raise ValidationError({"ordering": ["Unsupported catalog ordering."]})
        items = [_catalog_item(descriptor, kind) for descriptor in descriptors]
        if kind == "action":
            quota_costs = WorkflowConfigurationService.value(
                self.tenant_id,
                "action_quota_costs",
            )
            for item in items:
                key = str(item.get("key", ""))
                if not isinstance(quota_costs, Mapping) or key not in quota_costs:
                    raise OperationFailed(
                        error_code="ACTION_QUOTA_UNCONFIGURED",
                        message="An action catalog entry has no tenant quota policy.",
                        http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                item["quota_cost"] = int(quota_costs[key])
        items.sort(key=lambda item: (str(item.get(ordering, "")).casefold(), str(item.get("key", ""))))
        response = Response(items[:limit])
        response["X-Total-Count"] = str(len(items))
        response["X-Result-Limit"] = str(limit)
        return response

    def _provider_options(self, provider_key: str) -> list[dict[str, Any]]:
        try:
            provider = assignee_registry.get(provider_key)
        except WorkflowExtensionNotFound as exc:
            from src.core.api import CapabilityUnavailable

            raise CapabilityUnavailable(
                capability=provider_key,
                message="The requested lookup provider is unavailable.",
            ) from exc
        limits = WorkflowConfigurationService.get_configuration(self.tenant_id).document["limits"]
        default_limit = int(limits["catalog_default_limit"])
        maximum = int(limits["catalog_max_limit"])
        search_max_length = int(limits["catalog_search_max_length"])
        raw_limit = self.request.query_params.get("limit", str(default_limit))
        try:
            limit = int(raw_limit)
        except ValueError as exc:
            raise ValidationError({"limit": ["Must be an integer."]}) from exc
        if limit < 1 or limit > maximum:
            raise ValidationError({"limit": [f"Must be between 1 and {maximum}."]})
        search = self.request.query_params.get("search", "")
        if len(search) > search_max_length:
            raise ValidationError(
                {"search": [f"Must not exceed {search_max_length} characters."]}
            )
        result = provider.search(
            AssigneeSearchInvocation(
                tenant_id=self.tenant_id,
                query=search,
                limit=limit,
            )
        ).unwrap()
        options: list[dict[str, Any]] = []
        for item in result:
            assignment_key = str(item["assignment_key"])
            prefix, separator, identifier = assignment_key.partition(":")
            if not separator or prefix != item["assignment_kind"] or not identifier:
                raise ValidationError({"provider": ["Lookup provider returned an invalid assignment key."]})
            options.append(
                {
                    "id": identifier,
                    "label": str(item["display_name"]),
                    "description": str(item.get("secondary_text")) if item.get("secondary_text") else None,
                    "kind": str(item["assignment_kind"]),
                }
            )
        return options

    @action(detail=False, methods=("get",), url_path="actions")
    def actions(self, request: Request) -> Response:
        return self._catalog(action_registry, "action")

    @action(detail=False, methods=("get",), url_path="conditions")
    def conditions(self, request: Request) -> Response:
        return self._catalog(condition_registry, "condition")

    @action(detail=False, methods=("get",), url_path="subjects")
    def subjects(self, request: Request) -> Response:
        items: list[dict[str, Any]] = []
        for descriptor in subject_registry.catalog(None):
            raw = _catalog_item(descriptor, "subject")
            for entity_type in raw.get("entity_types", []):
                items.append({**raw, "entity_type": entity_type})
        items.sort(key=lambda item: (str(item.get("entity_type", "")).casefold(), str(item.get("key", ""))))
        maximum = int(WorkflowConfigurationService.value(self.tenant_id, "limits.catalog_max_limit"))
        default = int(WorkflowConfigurationService.value(self.tenant_id, "limits.catalog_default_limit"))
        try:
            limit = int(request.query_params.get("limit", str(default)))
        except ValueError as exc:
            raise ValidationError({"limit": ["Must be an integer."]}) from exc
        if limit < 1 or limit > maximum:
            raise ValidationError({"limit": [f"Must be between 1 and {maximum}."]})
        response = Response(items[:limit])
        response["X-Total-Count"] = str(len(items))
        response["X-Result-Limit"] = str(limit)
        return response

    @action(detail=False, methods=("get",), url_path="assignees")
    def assignees(self, request: Request) -> Response:
        options: list[dict[str, Any]] = []
        for descriptor in assignee_registry.catalog(None):
            if descriptor.availability == "available":
                options.extend(self._provider_options(descriptor.key))
        options.sort(key=lambda item: (item["label"].casefold(), item["id"]))
        cap = int(WorkflowConfigurationService.value(self.tenant_id, "limits.assignee_result_limit"))
        maximum = min(
            cap,
            int(WorkflowConfigurationService.value(self.tenant_id, "limits.catalog_max_limit")),
        )
        default = min(
            maximum,
            int(WorkflowConfigurationService.value(self.tenant_id, "limits.catalog_default_limit")),
        )
        try:
            limit = int(request.query_params.get("limit", str(default)))
        except ValueError as exc:
            raise ValidationError({"limit": ["Must be an integer."]}) from exc
        if limit < 1 or limit > maximum:
            raise ValidationError({"limit": [f"Must be between 1 and {maximum}."]})
        response = Response(options[:limit])
        response["X-Total-Count"] = str(len(options))
        response["X-Result-Limit"] = str(limit)
        return response

    @action(
        detail=False,
        methods=("get",),
        url_path=r"lookups/(?P<provider_key>[^/]+)",
    )
    def lookup(self, request: Request, provider_key: str | None = None) -> Response:
        if not provider_key:
            raise ValidationError({"provider_key": ["This field is required."]})
        return Response(self._provider_options(provider_key))


class WorkflowConfigurationViewSet(GovernedWorkflowViewSet):
    """Singleton tenant configuration surface with versioned commands."""

    access_prefix = "configuration"

    @staticmethod
    def _payload(configuration: WorkflowAutomationConfiguration) -> dict[str, Any]:
        return {
            "id": str(configuration.id),
            "tenant_id": str(configuration.tenant_id),
            "environment": configuration.environment,
            "version": configuration.version,
            "document": configuration.document,
            "updated_by": str(configuration.updated_by_id) if configuration.updated_by_id else None,
            "created_at": configuration.created_at,
            "updated_at": configuration.updated_at,
        }

    def get_queryset(self):
        tenant_id = getattr(self.request, "tenant_id", None)
        if not isinstance(tenant_id, uuid.UUID):
            return WorkflowAutomationConfiguration.objects.none()
        return WorkflowAutomationConfiguration.objects.for_tenant(tenant_id)

    def list(self, request: Request) -> Response:
        environment = request.query_params.get("environment", "production")
        configuration = WorkflowConfigurationService.get_configuration(self.tenant_id, environment)
        return Response(self._payload(configuration))

    def update(self, request: Request, pk: str | None = None) -> Response:
        del pk
        serializer = WorkflowConfigurationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        configuration = WorkflowConfigurationService.update_configuration(
            self.tenant_id,
            request.user,
            values["document"],
            environment=values["environment"],
            expected_version=values["expected_version"],
            change_reason=values["change_reason"],
        )
        return Response(self._payload(configuration))

    @action(detail=False, methods=("post",))
    def preview(self, request: Request) -> Response:
        serializer = WorkflowConfigurationPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        return Response(
            WorkflowConfigurationService.preview(
                self.tenant_id,
                values["document"],
                values["environment"],
            )
        )

    @action(detail=False, methods=("get",))
    def history(self, request: Request) -> Response:
        environment = request.query_params.get("environment", "production")
        revisions = WorkflowConfigurationService.history(self.tenant_id, environment)
        return Response(
            [
                {
                    "id": str(item.id),
                    "version": item.version,
                    "previous_document": item.previous_document,
                    "document": item.document,
                    "actor_id": str(item.actor_id) if item.actor_id else None,
                    "correlation_id": item.correlation_id,
                    "change_reason": item.change_reason,
                    "created_at": item.created_at,
                }
                for item in revisions
            ]
        )

    @action(detail=False, methods=("post",))
    def rollback(self, request: Request) -> Response:
        serializer = WorkflowConfigurationRollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        configuration = WorkflowConfigurationService.rollback(
            self.tenant_id,
            request.user,
            values["target_version"],
            environment=values["environment"],
            expected_version=values["expected_version"],
        )
        return Response(self._payload(configuration))

    @action(detail=False, methods=("post",), url_path="import")
    def import_configuration(self, request: Request) -> Response:
        serializer = WorkflowConfigurationImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        configuration = WorkflowConfigurationService.update_configuration(
            self.tenant_id,
            request.user,
            values["document"],
            environment=values["environment"],
            expected_version=values["expected_version"],
            change_reason=values["change_reason"],
        )
        return Response(self._payload(configuration))

    @action(detail=False, methods=("get",), url_path="export")
    def export_configuration(self, request: Request) -> Response:
        environment = request.query_params.get("environment", "production")
        configuration = WorkflowConfigurationService.get_configuration(self.tenant_id, environment)
        response = Response(
            {
                "schema": "saraise.workflow-automation.configuration/v1",
                "environment": configuration.environment,
                "version": configuration.version,
                "document": configuration.document,
            }
        )
        response["Content-Disposition"] = (
            f'attachment; filename="workflow-automation-{configuration.environment}-v{configuration.version}.json"'
        )
        return response


class HealthView(DeprecatedV1HeadersMixin, GovernedAPIViewMixin, APIView):
    authentication_classes = (StrictSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    required_permission, quota_resource = access_metadata("health")
    required_entitlement = MODULE_ENTITLEMENT
    quota_cost = None

    def get_permissions(self) -> list[object]:
        tenant_id = getattr(self.request, "tenant_id", None)
        self.quota_cost = (
            WorkflowConfigurationService.value(tenant_id, "operational.api_quota_cost")
            if isinstance(tenant_id, uuid.UUID)
            else None
        )
        return super().get_permissions()

    def get(self, request: Request) -> Response:
        tenant_id = getattr(request, "tenant_id", None)
        if not isinstance(tenant_id, uuid.UUID):
            raise PermissionDenied("A valid tenant context is required.")
        payload, response_status = sanitized_health_payload(tenant_id)
        return Response(payload, status=response_status)


# Historical import name retained; the URL now points to the governed view.
health_check = HealthView.as_view()


__all__ = [
    "CatalogViewSet",
    "HealthView",
    "WorkflowConfigurationViewSet",
    "WorkflowInstanceViewSet",
    "WorkflowTaskViewSet",
    "WorkflowViewSet",
]
