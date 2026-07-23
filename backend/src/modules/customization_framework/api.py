"""Governed, tenant-safe API v2 controllers for customization framework."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q, QuerySet
from rest_framework import mixins, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.access import RequiresAccess
from src.core.api import GovernedAPIViewMixin, OperationFailed
from src.core.api.envelope import correlation_id_for_request, utc_timestamp
from src.core.state_machine import IdempotencyConflictError
from src.core.tenancy import get_current_tenant_id

from .health import get_module_health
from .models import (
    BusinessRule,
    BusinessRuleVersion,
    CustomFieldDefinition,
    CustomFieldValue,
    FormDefinition,
    FormLayoutVersion,
    RuleExecution,
)
from .permissions import requirement_for
from .serializers import (
    ConfigurationAuditRecordSerializer,
    ConfigurationImportSerializer,
    ConfigurationPreviewSerializer,
    ConfigurationRollbackSerializer,
    ConfigurationUpdateSerializer,
    FieldDefinitionCreateSerializer,
    FieldDefinitionDetailSerializer,
    FieldDefinitionListSerializer,
    FieldDefinitionRollbackSerializer,
    FieldDefinitionUpdateSerializer,
    FieldDefinitionVersionSerializer,
    FieldTransitionSerializer,
    FieldValueCreateSerializer,
    FieldValueDetailSerializer,
    FieldValueListSerializer,
    FieldValueUpdateSerializer,
    FormCreateSerializer,
    FormDetailSerializer,
    FormListSerializer,
    FormPublishSerializer,
    FormUpdateSerializer,
    HealthSerializer,
    ImpactReportSerializer,
    LayoutValidationSerializer,
    LayoutVersionCreateSerializer,
    LayoutVersionDetailSerializer,
    ResourceContractSerializer,
    RuleCreateSerializer,
    RuleDetailSerializer,
    RuleEvaluateSerializer,
    RuleExecutionDetailSerializer,
    RuleExecutionListSerializer,
    RuleListSerializer,
    RulePublishSerializer,
    RuleUpdateSerializer,
    RuleVersionCreateSerializer,
    RuleVersionDetailSerializer,
    RuleVersionValidationSerializer,
    RuntimeConfigurationSerializer,
    RuntimeConfigurationVersionSerializer,
    ValueValidationSerializer,
)
from .services import (
    PLATFORM_CEILINGS,
    BusinessRuleService,
    CustomFieldService,
    CustomizationConfigurationService,
    CustomizationNotFound,
    CustomizationRegistry,
    CustomizationValidationError,
    EvaluationIdempotencyConflict,
    FormService,
    OptimisticLockConflict,
    effective_configuration,
)


class RequiredSessionAuthentication(SessionAuthentication):
    """Strict CSRF-enforcing sessions with a v2 401 challenge."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


def _tenant(request: Any) -> UUID:
    """Resolve tenant only from the authenticated request execution context."""

    raw = getattr(request, "tenant_id", None) or get_current_tenant_id()
    if raw is None:
        profile = getattr(getattr(request, "user", None), "profile", None)
        raw = getattr(profile, "tenant_id", None)
    try:
        tenant = raw if isinstance(raw, UUID) else UUID(str(raw))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PermissionDenied("Authenticated tenant context is required.") from exc
    request.tenant_id = tenant
    return tenant


def _actor(request: Any) -> UUID:
    raw = getattr(getattr(request, "user", None), "id", None)
    if raw is None:
        raise PermissionDenied("Authenticated actor context is required.")
    try:
        return UUID(str(raw))
    except (TypeError, ValueError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{raw}")


def _call(operation: Callable[..., Any], *args: object, **kwargs: object) -> Any:
    try:
        return operation(*args, **kwargs)
    except CustomizationNotFound as exc:
        raise NotFound() from exc
    except (OptimisticLockConflict, EvaluationIdempotencyConflict, IdempotencyConflictError) as exc:
        raise OperationFailed(error_code="CONFLICT", message=str(exc), http_status=409) from exc
    except CustomizationValidationError as exc:
        detail = exc.detail or {"non_field_errors": [str(exc)]}
        raise ValidationError(detail) from exc
    except DjangoValidationError as exc:
        raise ValidationError(getattr(exc, "message_dict", {"non_field_errors": exc.messages})) from exc


def _expected_lock(raw: object) -> int:
    try:
        value = int(str(raw))
    except (TypeError, ValueError) as exc:
        raise ValidationError({"expected_lock_version": ["This positive integer is required."]}) from exc
    if value < 1:
        raise ValidationError({"expected_lock_version": ["Must be at least 1."]})
    return value


def _command_idempotency_key(request: Any) -> str:
    raw = request.headers.get("Idempotency-Key")
    if raw is None:
        return str(_request_correlation_id(request))
    value = str(raw).strip()
    if not value:
        raise ValidationError({"Idempotency-Key": ["This header cannot be blank."]})
    if len(value) > PLATFORM_CEILINGS["idempotency_key_length"]:
        raise ValidationError({"Idempotency-Key": ["This header exceeds the platform limit."]})
    return value


def _request_correlation_id(request: Any) -> UUID:
    raw = getattr(request, "correlation_id", None)
    try:
        return raw if isinstance(raw, UUID) else UUID(str(raw))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({"correlation_id": ["A valid request correlation ID is required."]}) from exc


def _validate_choice(value: str | None, field: str, choices: set[str]) -> str | None:
    if value is not None and value not in choices:
        raise ValidationError({field: ["Unsupported value."]})
    return value


class GovernedTenantViewSet(GovernedAPIViewMixin, viewsets.GenericViewSet):
    """Shared session, fail-closed access, search, and bounded pagination."""

    authentication_classes = (RequiredSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    access_name = ""
    search_fields: tuple[str, ...] = ()

    def get_permissions(self) -> list[object]:
        try:
            _tenant(self.request)
        except PermissionDenied:
            self.request.tenant_id = None
        requirement = requirement_for(self.access_name, getattr(self, "action", ""), self.request.method)
        self.required_permission = requirement.permission if requirement else None
        self.required_entitlement = requirement.entitlement if requirement else None
        self.quota_resource = requirement.quota_resource if requirement else None
        self.quota_cost = requirement.quota_cost if requirement else 0
        return super().get_permissions()

    def handle_exception(self, exc: Exception) -> Response:
        """Map service/query validation raised during DRF queryset resolution."""
        if isinstance(exc, CustomizationNotFound):
            exc = NotFound()
        elif isinstance(exc, (OptimisticLockConflict, EvaluationIdempotencyConflict, IdempotencyConflictError)):
            exc = OperationFailed(error_code="CONFLICT", message=str(exc), http_status=409)
        elif isinstance(exc, CustomizationValidationError):
            exc = ValidationError(exc.detail or {"non_field_errors": [str(exc)]})
        elif isinstance(exc, DjangoValidationError):
            exc = ValidationError(getattr(exc, "message_dict", {"non_field_errors": exc.messages}))
        return super().handle_exception(exc)

    @property
    def tenant_id(self) -> UUID:
        return _tenant(self.request)

    @property
    def actor_id(self) -> UUID:
        return _actor(self.request)

    def tenant_or_none(self) -> UUID | None:
        """Resolve tenant context without ever widening a queryset."""

        try:
            return self.tenant_id
        except PermissionDenied:
            return None

    def searched(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        term = self.request.query_params.get("search", "").strip()
        if not term or not self.search_fields:
            return queryset
        query = Q()
        for field in self.search_fields:
            query |= Q(**{f"{field}__icontains": term})
        return queryset.filter(query)

    def paginated(self, queryset: QuerySet[Any], serializer_class: type) -> Response:
        page = self.paginate_queryset(queryset)
        if page is None:
            raise RuntimeError("Governed pagination is required")
        return self.get_paginated_response(serializer_class(page, many=True).data)


class ResourceContractViewSet(GovernedTenantViewSet):
    """Paginated, contract-aware discovery without exposing registry internals."""

    access_name = "resource-contract"

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        include_unavailable = self.request.query_params.get("include_unavailable", "true").lower()
        if include_unavailable not in {"true", "false"}:
            raise ValidationError({"include_unavailable": ["Must be true or false."]})
        contracts = CustomizationRegistry.list_resource_contracts(include_unavailable=include_unavailable == "true")
        return self.paginated(contracts, ResourceContractSerializer)


class FieldDefinitionViewSet(GovernedTenantViewSet):
    access_name = "field-definition"
    service = CustomFieldService()
    search_fields = ("key", "label", "description")

    def get_queryset(self) -> QuerySet[CustomFieldDefinition]:
        tenant_id = self.tenant_or_none()
        if tenant_id is None:
            return CustomFieldDefinition.objects.none()
        filters = {
            key: self.request.query_params[key]
            for key in ("owner_module", "target_resource", "data_type", "status")
            if key in self.request.query_params
        }
        _validate_choice(
            filters.get("data_type"),
            "data_type",
            {
                "text",
                "long_text",
                "integer",
                "decimal",
                "boolean",
                "date",
                "datetime",
                "uuid",
                "choice",
                "multi_choice",
                "json",
            },
        )
        _validate_choice(filters.get("status"), "status", {"draft", "active", "deprecated", "retired"})
        return self.service.list_definitions(
            tenant_id, filters=filters, ordering=self.request.query_params.get("ordering", "key")
        )

    def get_serializer_class(self) -> type:
        return {
            "list": FieldDefinitionListSerializer,
            "create": FieldDefinitionCreateSerializer,
            "partial_update": FieldDefinitionUpdateSerializer,
        }.get(self.action, FieldDefinitionDetailSerializer)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.searched(self.get_queryset()), FieldDefinitionListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = _call(self.service.get_definition, self.tenant_id, definition_id=self.kwargs["pk"])
        return Response(FieldDefinitionDetailSerializer(value).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = FieldDefinitionCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.create_definition,
            self.tenant_id,
            actor_id=self.actor_id,
            data=serializer.validated_data,
            command_idempotency_key=_command_idempotency_key(self.request),
        )
        return Response(FieldDefinitionDetailSerializer(value).data, status=201)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        serializer = FieldDefinitionUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        lock = data.pop("expected_lock_version")
        value = _call(
            self.service.update_definition,
            self.tenant_id,
            definition_id=self.kwargs["pk"],
            expected_lock_version=lock,
            actor_id=self.actor_id,
            data=data,
            command_idempotency_key=_command_idempotency_key(self.request),
        )
        return Response(FieldDefinitionDetailSerializer(value).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        lock = self.request.data.get("expected_lock_version") or self.request.query_params.get("expected_lock_version")
        value = _call(
            self.service.delete_definition,
            self.tenant_id,
            definition_id=self.kwargs["pk"],
            expected_lock_version=_expected_lock(lock),
            actor_id=self.actor_id,
            command_idempotency_key=_command_idempotency_key(self.request),
        )
        return Response(FieldDefinitionDetailSerializer(value).data)

    def _transition(self, command: str) -> Response:
        self.get_object()
        serializer = FieldTransitionSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.transition_definition,
            self.tenant_id,
            definition_id=self.kwargs["pk"],
            command=command,
            transition_key=serializer.validated_data["transition_key"],
            actor_id=self.actor_id,
            command_idempotency_key=_command_idempotency_key(self.request),
        )
        return Response(FieldDefinitionDetailSerializer(value).data)

    @action(detail=True, methods=["post"])
    def activate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._transition("activate")

    @action(detail=True, methods=["post"])
    def deprecate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._transition("deprecate")

    @action(detail=True, methods=["post"])
    def retire(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._transition("retire")

    @action(detail=True, methods=["get"])
    def impact(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        value = _call(self.service.get_definition_impact, self.tenant_id, definition_id=self.kwargs["pk"])
        return Response(ImpactReportSerializer(value).data)

    @action(detail=True, methods=["get"])
    def versions(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        return self.paginated(
            self.service.list_definition_versions(
                self.tenant_id,
                definition_id=self.kwargs["pk"],
            ),
            FieldDefinitionVersionSerializer,
        )

    @action(detail=True, methods=["post"])
    def rollback(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = FieldDefinitionRollbackSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.rollback_definition,
            self.tenant_id,
            definition_id=self.kwargs["pk"],
            actor_id=self.actor_id,
            command_idempotency_key=_command_idempotency_key(self.request),
            **serializer.validated_data,
        )
        return Response(FieldDefinitionDetailSerializer(value).data)

    @action(detail=True, methods=["post"], url_path="validate-value")
    def validate_value(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = ValueValidationSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.validate_value, self.tenant_id, definition_id=self.kwargs["pk"], **serializer.validated_data
        )
        return Response(value)


class FieldValueViewSet(GovernedTenantViewSet):
    access_name = "field-value"
    service = CustomFieldService()

    def get_queryset(self) -> QuerySet[CustomFieldValue]:
        tenant_id = self.tenant_or_none()
        if tenant_id is None:
            return CustomFieldValue.objects.none()
        if getattr(self, "action", "") != "list":
            return self.service.list_values(
                tenant_id,
                filters={},
                require_scope=False,
            )
        filters = {
            key: self.request.query_params[key]
            for key in (
                "definition_id",
                "target_record_id",
                "source",
                "updated_at_after",
                "updated_at_before",
            )
            if key in self.request.query_params
        }
        return self.service.list_values(
            tenant_id,
            filters=filters,
            ordering=self.request.query_params.get("ordering", "-updated_at"),
        )

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), FieldValueListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(FieldValueDetailSerializer(self.get_object()).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = FieldValueCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.upsert_value,
            self.tenant_id,
            actor_id=self.actor_id,
            expected_lock_version=None,
            command_idempotency_key=_command_idempotency_key(self.request),
            **serializer.validated_data,
        )
        return Response(FieldValueDetailSerializer(value).data, status=201)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        current = self.get_object()
        serializer = FieldValueUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.upsert_value,
            self.tenant_id,
            definition_id=current.definition_id,
            target_record_id=current.target_record_id,
            actor_id=self.actor_id,
            command_idempotency_key=_command_idempotency_key(self.request),
            **serializer.validated_data,
        )
        return Response(FieldValueDetailSerializer(value).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        current = self.get_object()
        raw = self.request.data.get("expected_lock_version") or self.request.query_params.get("expected_lock_version")
        value = _call(
            self.service.delete_value,
            self.tenant_id,
            value_id=current.id,
            expected_lock_version=_expected_lock(raw),
            actor_id=self.actor_id,
            command_idempotency_key=_command_idempotency_key(self.request),
        )
        return Response(FieldValueDetailSerializer(value).data)


class FormDefinitionViewSet(GovernedTenantViewSet):
    access_name = "form"
    service = FormService()
    search_fields = ("key", "name", "description")

    def get_queryset(self) -> QuerySet[FormDefinition]:
        tenant_id = self.tenant_or_none()
        if tenant_id is None:
            return FormDefinition.objects.none()
        filters = {
            key: self.request.query_params[key]
            for key in ("owner_module", "target_resource", "status")
            if key in self.request.query_params
        }
        _validate_choice(filters.get("status"), "status", {"draft", "published", "archived"})
        return self.service.list_forms(
            tenant_id, filters=filters, ordering=self.request.query_params.get("ordering", "key")
        )

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.searched(self.get_queryset()), FormListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(
            FormDetailSerializer(_call(self.service.get_form, self.tenant_id, form_id=self.kwargs["pk"])).data
        )

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = FormCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.create_form,
            self.tenant_id,
            actor_id=self.actor_id,
            data=serializer.validated_data,
            command_idempotency_key=_command_idempotency_key(self.request),
        )
        return Response(FormDetailSerializer(value).data, status=201)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        serializer = FormUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        lock = data.pop("expected_lock_version")
        value = _call(
            self.service.update_form,
            self.tenant_id,
            form_id=self.kwargs["pk"],
            expected_lock_version=lock,
            actor_id=self.actor_id,
            data=data,
            command_idempotency_key=_command_idempotency_key(self.request),
        )
        return Response(FormDetailSerializer(value).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        raw = self.request.data.get("expected_lock_version") or self.request.query_params.get("expected_lock_version")
        value = _call(
            self.service.delete_form,
            self.tenant_id,
            form_id=self.kwargs["pk"],
            expected_lock_version=_expected_lock(raw),
            actor_id=self.actor_id,
            command_idempotency_key=_command_idempotency_key(self.request),
        )
        return Response(FormDetailSerializer(value).data)

    @action(detail=True, methods=["get", "post"], url_path="layout-versions")
    def layout_versions(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        form = self.get_object()
        if self.request.method == "GET":
            return self.paginated(
                self.service.list_layout_versions(
                    self.tenant_id,
                    filters={"form_id": form.id},
                    ordering="-version",
                ),
                LayoutVersionDetailSerializer,
            )
        serializer = LayoutVersionCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.create_layout_version,
            self.tenant_id,
            form_id=form.id,
            actor_id=self.actor_id,
            command_idempotency_key=_command_idempotency_key(self.request),
            **serializer.validated_data,
        )
        return Response(LayoutVersionDetailSerializer(value).data, status=201)

    @action(detail=True, methods=["post"], url_path="validate-layout")
    def validate_layout(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        form = self.get_object()
        serializer = LayoutValidationSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            _call(
                self.service.validate_layout,
                self.tenant_id,
                form_id=form.id,
                layout=serializer.validated_data["layout"],
            )
        )

    @action(detail=True, methods=["post"])
    def publish(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = FormPublishSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.publish_layout,
            self.tenant_id,
            form_id=self.kwargs["pk"],
            actor_id=self.actor_id,
            command_idempotency_key=_command_idempotency_key(self.request),
            **serializer.validated_data,
        )
        return Response(LayoutVersionDetailSerializer(value).data)

    @action(detail=True, methods=["post"])
    def archive(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = FieldTransitionSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.archive_form,
            self.tenant_id,
            form_id=self.kwargs["pk"],
            actor_id=self.actor_id,
            command_idempotency_key=_command_idempotency_key(self.request),
            **serializer.validated_data,
        )
        return Response(FormDetailSerializer(value).data)

    @action(detail=True, methods=["get"], url_path="render-schema")
    def render_schema(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        return Response(_call(self.service.get_render_schema, self.tenant_id, form_id=self.kwargs["pk"]))

    @action(detail=True, methods=["get"])
    def impact(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        return Response(
            ImpactReportSerializer(_call(self.service.get_form_impact, self.tenant_id, form_id=self.kwargs["pk"])).data
        )


class FormLayoutVersionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedTenantViewSet):
    access_name = "form-layout"
    serializer_class = LayoutVersionDetailSerializer
    service = FormService()

    def get_queryset(self) -> QuerySet[FormLayoutVersion]:
        tenant_id = self.tenant_or_none()
        if tenant_id is None:
            return FormLayoutVersion.objects.none()
        filters = {
            key: self.request.query_params[key]
            for key in ("form_id", "status", "version")
            if key in self.request.query_params
        }
        _validate_choice(filters.get("status"), "status", {"candidate", "published", "superseded", "rejected"})
        return self.service.list_layout_versions(
            tenant_id,
            filters=filters,
            ordering=self.request.query_params.get("ordering", "-version"),
        )

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), LayoutVersionDetailSerializer)


class BusinessRuleViewSet(GovernedTenantViewSet):
    access_name = "rule"
    service = BusinessRuleService()
    search_fields = ("key", "name", "description")

    def get_queryset(self) -> QuerySet[BusinessRule]:
        tenant_id = self.tenant_or_none()
        if tenant_id is None:
            return BusinessRule.objects.none()
        filters = {
            key: self.request.query_params[key]
            for key in ("owner_module", "target_resource", "trigger", "status")
            if key in self.request.query_params
        }
        _validate_choice(
            filters.get("trigger"), "trigger", {"validate", "before_create", "before_update", "form_change"}
        )
        _validate_choice(filters.get("status"), "status", {"draft", "published", "paused", "retired"})
        return self.service.list_rules(
            tenant_id, filters=filters, ordering=self.request.query_params.get("ordering", "priority")
        )

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.searched(self.get_queryset()), RuleListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(
            RuleDetailSerializer(_call(self.service.get_rule, self.tenant_id, rule_id=self.kwargs["pk"])).data
        )

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = RuleCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.create_rule,
            self.tenant_id,
            actor_id=self.actor_id,
            data=serializer.validated_data,
            command_idempotency_key=_command_idempotency_key(self.request),
        )
        return Response(RuleDetailSerializer(value).data, status=201)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        serializer = RuleUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        lock = data.pop("expected_lock_version")
        value = _call(
            self.service.update_rule,
            self.tenant_id,
            rule_id=self.kwargs["pk"],
            expected_lock_version=lock,
            actor_id=self.actor_id,
            data=data,
            command_idempotency_key=_command_idempotency_key(self.request),
        )
        return Response(RuleDetailSerializer(value).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        raw = self.request.data.get("expected_lock_version") or self.request.query_params.get("expected_lock_version")
        value = _call(
            self.service.delete_rule,
            self.tenant_id,
            rule_id=self.kwargs["pk"],
            expected_lock_version=_expected_lock(raw),
            actor_id=self.actor_id,
            command_idempotency_key=_command_idempotency_key(self.request),
        )
        return Response(RuleDetailSerializer(value).data)

    @action(detail=True, methods=["get", "post"])
    def versions(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        rule = self.get_object()
        if self.request.method == "GET":
            return self.paginated(
                self.service.list_rule_versions(
                    self.tenant_id,
                    filters={"rule_id": rule.id},
                    ordering="-version",
                ),
                RuleVersionDetailSerializer,
            )
        serializer = RuleVersionCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.create_rule_version,
            self.tenant_id,
            rule_id=rule.id,
            actor_id=self.actor_id,
            command_idempotency_key=_command_idempotency_key(self.request),
            **serializer.validated_data,
        )
        return Response(RuleVersionDetailSerializer(value).data, status=201)

    @action(detail=True, methods=["post"], url_path="validate-version")
    def validate_version(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        rule = self.get_object()
        serializer = RuleVersionValidationSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            _call(
                self.service.validate_rule_version,
                self.tenant_id,
                rule_id=rule.id,
                **serializer.validated_data,
            )
        )

    @action(detail=True, methods=["post"])
    def publish(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = RulePublishSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.publish_rule_version,
            self.tenant_id,
            rule_id=self.kwargs["pk"],
            actor_id=self.actor_id,
            command_idempotency_key=_command_idempotency_key(self.request),
            **serializer.validated_data,
        )
        return Response(RuleVersionDetailSerializer(value).data)

    def _transition(self, command: str) -> Response:
        self.get_object()
        serializer = FieldTransitionSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.transition_rule,
            self.tenant_id,
            rule_id=self.kwargs["pk"],
            command=command,
            actor_id=self.actor_id,
            command_idempotency_key=_command_idempotency_key(self.request),
            **serializer.validated_data,
        )
        return Response(RuleDetailSerializer(value).data)

    @action(detail=True, methods=["post"])
    def pause(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._transition("pause")

    @action(detail=True, methods=["post"])
    def resume(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._transition("resume")

    @action(detail=True, methods=["post"])
    def retire(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._transition("retire")

    @action(detail=True, methods=["post"])
    def evaluate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        serializer = RuleEvaluateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        evaluation = dict(serializer.validated_data)
        evaluation.setdefault("target_record_id", None)
        value = _call(
            self.service.evaluate,
            self.tenant_id,
            rule_id=self.kwargs["pk"],
            actor_id=self.actor_id,
            command_idempotency_key=_command_idempotency_key(self.request),
            **evaluation,
        )
        return Response(RuleExecutionDetailSerializer(value).data)

    @action(detail=True, methods=["get"])
    def impact(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        return Response(
            ImpactReportSerializer(_call(self.service.get_rule_impact, self.tenant_id, rule_id=self.kwargs["pk"])).data
        )


class BusinessRuleVersionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedTenantViewSet):
    access_name = "rule-version"
    serializer_class = RuleVersionDetailSerializer
    service = BusinessRuleService()

    def get_queryset(self) -> QuerySet[BusinessRuleVersion]:
        tenant_id = self.tenant_or_none()
        if tenant_id is None:
            return BusinessRuleVersion.objects.none()
        filters = {
            key: self.request.query_params[key]
            for key in ("rule_id", "status", "version")
            if key in self.request.query_params
        }
        _validate_choice(filters.get("status"), "status", {"candidate", "published", "superseded", "rejected"})
        return self.service.list_rule_versions(
            tenant_id,
            filters=filters,
            ordering=self.request.query_params.get("ordering", "-version"),
        )

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), RuleVersionDetailSerializer)


class RuleExecutionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedTenantViewSet):
    access_name = "rule-execution"
    service = BusinessRuleService()

    def get_queryset(self) -> QuerySet[RuleExecution]:
        tenant_id = self.tenant_or_none()
        if tenant_id is None:
            return RuleExecution.objects.none()
        filters = {
            key: self.request.query_params[key]
            for key in (
                "rule_id",
                "rule_version_id",
                "target_record_id",
                "status",
                "executed_after",
                "executed_before",
                "correlation_id",
            )
            if key in self.request.query_params
        }
        return self.service.list_executions(
            tenant_id, filters=filters, ordering=self.request.query_params.get("ordering", "-executed_at")
        )

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), RuleExecutionListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(
            RuleExecutionDetailSerializer(
                _call(self.service.get_execution, self.tenant_id, execution_id=self.kwargs["pk"])
            ).data
        )


class RuntimeConfigurationViewSet(GovernedTenantViewSet):
    """Tenant configuration transport; all behavior remains service-owned."""

    access_name = "configuration"
    service = CustomizationConfigurationService()

    def _current_payload(self) -> object:
        current = self.service.get(self.tenant_id)
        if current is not None:
            return current
        return {
            "id": None,
            "tenant_id": self.tenant_id,
            "version": 0,
            "environment": "default",
            "document": effective_configuration(self.tenant_id),
            "updated_by": None,
            "created_at": None,
            "updated_at": None,
        }

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(RuntimeConfigurationSerializer(self._current_payload()).data)

    @action(detail=False, methods=["put", "patch"], url_path="update")
    def update_configuration(self, request: object) -> Response:
        del request
        serializer = ConfigurationUpdateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.update,
            self.tenant_id,
            actor_id=self.actor_id,
            correlation_id=_request_correlation_id(self.request),
            idempotency_key=_command_idempotency_key(self.request),
            document=serializer.validated_data["document"],
            environment=serializer.validated_data["environment"],
            expected_version=serializer.validated_data["expected_version"],
        )
        return Response(RuntimeConfigurationSerializer(value).data)

    @action(detail=False, methods=["post"])
    def preview(self, request: object) -> Response:
        del request
        serializer = ConfigurationPreviewSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            _call(
                self.service.preview,
                self.tenant_id,
                **serializer.validated_data,
            )
        )

    @action(detail=False, methods=["get"])
    def history(self, request: object) -> Response:
        del request
        return self.paginated(
            self.service.list_audit(self.tenant_id),
            ConfigurationAuditRecordSerializer,
        )

    @action(detail=False, methods=["get"])
    def versions(self, request: object) -> Response:
        del request
        return self.paginated(
            self.service.list_versions(self.tenant_id),
            RuntimeConfigurationVersionSerializer,
        )

    @action(detail=False, methods=["post"])
    def rollback(self, request: object) -> Response:
        del request
        serializer = ConfigurationRollbackSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.rollback,
            self.tenant_id,
            actor_id=self.actor_id,
            correlation_id=_request_correlation_id(self.request),
            idempotency_key=_command_idempotency_key(self.request),
            target_version=serializer.validated_data["target_version"],
            expected_version=serializer.validated_data["expected_version"],
        )
        return Response(RuntimeConfigurationSerializer(value).data)

    @action(detail=False, methods=["post"], url_path="import")
    def import_document(self, request: object) -> Response:
        del request
        serializer = ConfigurationImportSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = _call(
            self.service.import_document,
            self.tenant_id,
            actor_id=self.actor_id,
            correlation_id=_request_correlation_id(self.request),
            idempotency_key=_command_idempotency_key(self.request),
            payload=serializer.validated_data["payload"],
            expected_version=serializer.validated_data["expected_version"],
        )
        return Response(RuntimeConfigurationSerializer(value).data)

    @action(detail=False, methods=["get"], url_path="export")
    def export_document(self, request: object) -> Response:
        del request
        return Response(_call(self.service.export_document, self.tenant_id))


class ModuleHealthAPIView(GovernedAPIViewMixin, APIView):
    authentication_classes = (RequiredSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)

    def get_permissions(self) -> list[object]:
        try:
            _tenant(self.request)
        except PermissionDenied:
            self.request.tenant_id = None
        requirement = requirement_for("health", "get", "get")
        self.required_permission = requirement.permission if requirement else None
        self.required_entitlement = requirement.entitlement if requirement else None
        self.quota_resource = requirement.quota_resource if requirement else None
        self.quota_cost = requirement.quota_cost if requirement else 0
        return super().get_permissions()

    def get(self, request: object) -> Response:
        report = get_module_health()
        payload = HealthSerializer(report.payload).data
        if report.status_code >= 400:
            payload = {
                "data": payload,
                "meta": {
                    "correlation_id": correlation_id_for_request(request),
                    "timestamp": utc_timestamp(),
                },
            }
        return Response(payload, status=report.status_code)


__all__ = [name for name in globals() if name.endswith("ViewSet") or name.endswith("APIView")]
