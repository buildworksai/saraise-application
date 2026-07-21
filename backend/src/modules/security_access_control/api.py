"""Governed, tenant-safe API v2 for security administration and evidence."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import mixins, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from src.core.api import GovernedAPIViewMixin, OperationFailed
from src.core.api.envelope import correlation_id_for_request
from src.core.tenancy import get_current_tenant_id

from .models import (
    FieldSecurity,
    Permission,
    PermissionSet,
    Role,
    RowSecurityRule,
    SecurityAuditLog,
    SecurityProfile,
    SecurityProfileAssignment,
    UserPermissionSet,
    UserRole,
)
from .permissions import requires_access
from .serializers import (
    AccessDecisionSerializer,
    AccessSimulationSerializer,
    FieldSecurityCreateSerializer,
    FieldSecurityDetailSerializer,
    FieldSecurityListSerializer,
    FieldSecurityUpdateSerializer,
    PermissionDetailSerializer,
    PermissionListSerializer,
    PermissionSetCreateSerializer,
    PermissionSetDetailSerializer,
    PermissionSetListSerializer,
    PermissionSetUpdateSerializer,
    ReplacePermissionSetPermissionsSerializer,
    RoleCreateSerializer,
    RoleDetailSerializer,
    RoleListSerializer,
    RoleUpdateSerializer,
    RowSecurityRuleCreateSerializer,
    RowSecurityRuleDetailSerializer,
    RowSecurityRuleListSerializer,
    RowSecurityRuleUpdateSerializer,
    SecurityAuditLogDetailSerializer,
    SecurityAuditLogListSerializer,
    SecurityProfileAssignmentCreateSerializer,
    SecurityProfileAssignmentDetailSerializer,
    SecurityProfileAssignmentListSerializer,
    SecurityProfileAssignmentUpdateSerializer,
    SecurityProfileCreateSerializer,
    SecurityProfileDetailSerializer,
    SecurityProfileListSerializer,
    SecurityProfileUpdateSerializer,
    SetRolePermissionSerializer,
    UserPermissionSetCreateSerializer,
    UserPermissionSetDetailSerializer,
    UserPermissionSetListSerializer,
    UserPermissionSetUpdateSerializer,
    UserRoleCreateSerializer,
    UserRoleDetailSerializer,
    UserRoleListSerializer,
    UserRoleUpdateSerializer,
)
from .services import (
    AccessEvaluationService,
    FieldSecurityService,
    PermissionCatalogService,
    PermissionSetService,
    RoleService,
    RowSecurityService,
    SecurityConflict,
    SecurityNotFound,
    SecurityProfileService,
    SecurityValidationError,
)


class RequiredSessionAuthentication(SessionAuthentication):
    """Ensure missing session credentials are rendered as 401, with CSRF intact."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


class SecurityRateThrottle(SimpleRateThrottle):
    scope = "security_access_control"
    rate = "240/min"

    def get_cache_key(self, request: Any, view: object) -> str | None:
        if not getattr(request.user, "is_authenticated", False):
            return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
        return self.cache_format % {"scope": self.scope, "ident": str(request.user.pk)}


def _tenant(request: Any) -> UUID:
    raw = getattr(request, "tenant_id", None) or get_current_tenant_id()
    if raw is None:
        raw = getattr(getattr(getattr(request, "user", None), "profile", None), "tenant_id", None)
    try:
        tenant = raw if isinstance(raw, UUID) else UUID(str(raw))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PermissionDenied("Authenticated tenant context is required.") from exc
    request.tenant_id = tenant
    return tenant


def _actor(request: Any) -> UUID:
    raw = getattr(getattr(request, "user", None), "id", None)
    try:
        return raw if isinstance(raw, UUID) else UUID(str(raw))
    except (TypeError, ValueError, AttributeError):
        if raw is None:
            raise PermissionDenied("Authenticated actor context is required.")
        return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{raw}")


def _call(operation: Callable[..., Any], *args: object, **kwargs: object) -> Any:
    try:
        return operation(*args, **kwargs)
    except SecurityNotFound as exc:
        raise NotFound() from exc
    except SecurityConflict as exc:
        raise OperationFailed(error_code="CONFLICT", message=str(exc), http_status=409) from exc
    except SecurityValidationError as exc:
        raise ValidationError(exc.detail or {"non_field_errors": [str(exc)]}) from exc


def _ensure_local_policy_ownership() -> None:
    if str(getattr(settings, "SARAISE_MODE", "development")).lower() == "saas":
        raise OperationFailed(
            error_code="CONTROL_PLANE_OWNED",
            message="Policy definitions are managed by the SaaS control plane.",
            detail={"mode": "saas"},
            http_status=409,
        )


def _deletion_reason(request: Any) -> str:
    reason = str(request.query_params.get("reason", "")).strip()
    if not reason:
        raise ValidationError({"reason": ["A revocation or deletion reason is required."]})
    return reason


def _apply_filters(queryset: QuerySet[Any], params: Mapping[str, str], fields: Mapping[str, str]) -> QuerySet[Any]:
    for parameter, lookup in fields.items():
        if parameter in params and params[parameter] != "":
            value: object = params[parameter]
            if value in {"true", "false"}:
                value = value == "true"
            queryset = queryset.filter(**{lookup: value})
    return queryset


class GovernedSecurityViewSet(GovernedAPIViewMixin, viewsets.GenericViewSet):
    authentication_classes = (RequiredSessionAuthentication,)
    permission_classes = (IsAuthenticated,)
    throttle_classes = (SecurityRateThrottle,)
    permission_map: Mapping[str, str] = {}
    catalog_objects = False
    search_fields: tuple[str, ...] = ()
    ordering_fields: tuple[str, ...] = ()
    default_ordering: tuple[str, ...] = ("id",)

    def initial(self, request: Any, *args: object, **kwargs: object) -> None:
        """Reject locally owned mutations before mode-specific authentication.

        SaaS sessions are normally validated by the platform middleware.  A
        local policy mutation is unavailable in SaaS regardless of the caller,
        so surface the stable ownership contract before DRF attempts request
        authentication.  Runtime simulation remains available in SaaS.
        """
        is_unsafe_method = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        is_local_mutation = is_unsafe_method and self.action != "simulate"
        if is_local_mutation:
            _ensure_local_policy_ownership()
        super().initial(request, *args, **kwargs)

    @property
    def tenant_id(self) -> UUID:
        return _tenant(self.request)

    @property
    def actor_id(self) -> UUID:
        return _actor(self.request)

    @property
    def correlation_id(self) -> str:
        supplied = str(self.request.headers.get("X-Correlation-ID", "")).strip()
        if supplied and len(supplied) <= 128 and re.fullmatch(r"[A-Za-z0-9._:-]+", supplied):
            self.request.correlation_id = supplied
            return supplied
        return correlation_id_for_request(self.request)

    def get_permissions(self) -> list[object]:
        if not bool(getattr(self.request.user, "is_authenticated", False)):
            return [IsAuthenticated()]
        _tenant(self.request)
        code = self.permission_map.get(getattr(self, "action", ""))
        if code is None:
            return [IsAuthenticated(), requires_access("")]
        return [IsAuthenticated(), requires_access(code, catalog=self.catalog_objects)]

    def query(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        search = self.request.query_params.get("search", "").strip()
        if search and self.search_fields:
            criteria = Q()
            for field in self.search_fields:
                criteria |= Q(**{f"{field}__icontains": search})
            queryset = queryset.filter(criteria)
        ordering = self.request.query_params.get("ordering", "")
        values = tuple(part.strip() for part in ordering.split(",") if part.strip()) or self.default_ordering
        if any(value.removeprefix("-") not in self.ordering_fields for value in values):
            raise ValidationError({"ordering": ["Contains an unsupported ordering field."]})
        return queryset.order_by(*values)

    def paginated(self, queryset: QuerySet[Any], serializer_class: type) -> Response:
        page = self.paginate_queryset(queryset)
        if page is None:
            raise RuntimeError("Governed pagination is required")
        return self.get_paginated_response(serializer_class(page, many=True).data)


class RoleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedSecurityViewSet):
    permission_map = {
        "list": "security.roles:read",
        "retrieve": "security.roles:read",
        "create": "security.roles:create",
        "partial_update": "security.roles:update",
        "destroy": "security.roles:delete",
        "set_permission": "security.roles:update",
        "remove_permission": "security.roles:update",
    }
    search_fields = ("name", "code", "description")
    ordering_fields = ("name", "created_at", "updated_at")
    default_ordering = ("name",)

    def get_queryset(self) -> QuerySet[Role]:
        queryset = Role.objects.for_tenant(self.tenant_id).filter(is_deleted=False)
        return self.query(
            _apply_filters(
                queryset,
                self.request.query_params,
                {"role_type": "role_type", "is_active": "is_active", "parent_role_id": "parent_role_id"},
            )
        )

    def get_serializer_class(self) -> type:
        return {
            "list": RoleListSerializer,
            "retrieve": RoleDetailSerializer,
            "create": RoleCreateSerializer,
            "partial_update": RoleUpdateSerializer,
        }.get(self.action, RoleDetailSerializer)

    def create(self, request: Any) -> Response:
        _ensure_local_policy_ownership()
        serializer = RoleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = _call(
            RoleService.create_role,
            self.tenant_id,
            **serializer.validated_data,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(RoleDetailSerializer(item).data, status=201)

    def partial_update(self, request: Any, pk: str | None = None) -> Response:
        self.get_object()
        _ensure_local_policy_ownership()
        serializer = RoleUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = _call(
            RoleService.update_role,
            self.tenant_id,
            UUID(str(pk)),
            changes=serializer.validated_data,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(RoleDetailSerializer(item).data)

    def destroy(self, request: Any, pk: str | None = None) -> Response:
        self.get_object()
        _ensure_local_policy_ownership()
        _call(
            RoleService.delete_role,
            self.tenant_id,
            UUID(str(pk)),
            actor_id=self.actor_id,
            reason=_deletion_reason(request),
            correlation_id=self.correlation_id,
        )
        return Response(status=204)

    @action(detail=True, methods=("post",), url_path="permissions")
    def set_permission(self, request: Any, pk: str | None = None) -> Response:
        _ensure_local_policy_ownership()
        serializer = SetRolePermissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = _call(
            RoleService.set_role_permission,
            self.tenant_id,
            UUID(str(pk)),
            serializer.validated_data["permission_id"],
            is_granted=serializer.validated_data["is_granted"],
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        from .serializers import RolePermissionSerializer

        return Response(RolePermissionSerializer(item).data, status=200)

    @action(detail=True, methods=("delete",), url_path=r"permissions/(?P<permission_id>[0-9a-f-]+)")
    def remove_permission(self, request: Any, pk: str | None = None, permission_id: str | None = None) -> Response:
        del request
        _ensure_local_policy_ownership()
        _call(
            RoleService.remove_role_permission,
            self.tenant_id,
            UUID(str(pk)),
            UUID(str(permission_id)),
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(status=204)


class PermissionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedSecurityViewSet):
    permission_map = {"list": "security.permissions:read", "retrieve": "security.permissions:read"}
    catalog_objects = True
    search_fields = ("name", "description")
    ordering_fields = ("module", "resource", "action")
    default_ordering = ("module", "resource", "action")

    def get_queryset(self) -> QuerySet[Permission]:
        queryset = PermissionCatalogService.list_permissions(
            self.tenant_id,
            module=self.request.query_params.get("module"),
            resource=self.request.query_params.get("resource"),
            action=self.request.query_params.get("action"),
            search=self.request.query_params.get("search"),
        )
        if self.request.query_params.get("risk_level"):
            queryset = queryset.filter(risk_level=self.request.query_params["risk_level"])
        return self.query(queryset)

    def get_serializer_class(self) -> type:
        return PermissionListSerializer if self.action == "list" else PermissionDetailSerializer


class UserRoleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedSecurityViewSet):
    permission_map = {
        "list": "security.assignments:read",
        "retrieve": "security.assignments:read",
        "create": "security.assignments:create",
        "partial_update": "security.assignments:update",
        "destroy": "security.assignments:delete",
    }
    ordering_fields = ("valid_from", "created_at")
    default_ordering = ("-valid_from",)

    def get_queryset(self) -> QuerySet[UserRole]:
        queryset = UserRole.objects.for_tenant(self.tenant_id).select_related("role")
        queryset = _apply_filters(queryset, self.request.query_params, {"user_id": "user_id", "role_id": "role_id"})
        if self.request.query_params.get("revoked") in {"true", "false"}:
            queryset = queryset.filter(revoked_at__isnull=self.request.query_params["revoked"] == "false")
        active_at = self.request.query_params.get("active_at")
        if active_at:
            moment = parse_datetime(active_at)
            if moment is None:
                raise ValidationError({"active_at": ["Must be an ISO datetime."]})
            queryset = queryset.filter(valid_from__lte=moment, revoked_at__isnull=True).filter(
                Q(valid_until__isnull=True) | Q(valid_until__gt=moment)
            )
        return self.query(queryset)

    def get_serializer_class(self) -> type:
        return {
            "list": UserRoleListSerializer,
            "retrieve": UserRoleDetailSerializer,
            "create": UserRoleCreateSerializer,
            "partial_update": UserRoleUpdateSerializer,
        }.get(self.action, UserRoleDetailSerializer)

    def create(self, request: Any) -> Response:
        _ensure_local_policy_ownership()
        serializer = UserRoleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = _call(
            RoleService.assign_role,
            self.tenant_id,
            serializer.validated_data.pop("user_id"),
            serializer.validated_data.pop("role_id"),
            **serializer.validated_data,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(UserRoleDetailSerializer(item).data, status=201)

    def partial_update(self, request: Any, pk: str | None = None) -> Response:
        self.get_object()
        _ensure_local_policy_ownership()
        serializer = UserRoleUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = {"valid_from": None, "valid_until": None, "reason": None, **serializer.validated_data}
        item = _call(
            RoleService.update_role_assignment,
            self.tenant_id,
            UUID(str(pk)),
            **values,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(UserRoleDetailSerializer(item).data)

    def destroy(self, request: Any, pk: str | None = None) -> Response:
        self.get_object()
        _ensure_local_policy_ownership()
        _call(
            RoleService.revoke_role_assignment,
            self.tenant_id,
            UUID(str(pk)),
            reason=_deletion_reason(request),
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(status=204)


class PermissionSetViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedSecurityViewSet):
    permission_map = {
        "list": "security.permission-sets:read",
        "retrieve": "security.permission-sets:read",
        "create": "security.permission-sets:create",
        "partial_update": "security.permission-sets:update",
        "destroy": "security.permission-sets:delete",
        "replace_permissions": "security.permission-sets:update",
    }
    search_fields = ("name", "description")
    ordering_fields = ("name", "created_at")
    default_ordering = ("name",)

    def get_queryset(self) -> QuerySet[PermissionSet]:
        queryset = (
            PermissionSet.objects.for_tenant(self.tenant_id)
            .filter(is_deleted=False)
            .prefetch_related("memberships__permission")
        )
        return self.query(_apply_filters(queryset, self.request.query_params, {"is_active": "is_active"}))

    def get_serializer_class(self) -> type:
        return {
            "list": PermissionSetListSerializer,
            "retrieve": PermissionSetDetailSerializer,
            "create": PermissionSetCreateSerializer,
            "partial_update": PermissionSetUpdateSerializer,
        }.get(self.action, PermissionSetDetailSerializer)

    def create(self, request: Any) -> Response:
        _ensure_local_policy_ownership()
        serializer = PermissionSetCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        permission_ids = values.pop("permission_ids", ())
        item = _call(
            PermissionSetService.create_permission_set,
            self.tenant_id,
            **values,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        if permission_ids:
            item = _call(
                PermissionSetService.set_permissions,
                self.tenant_id,
                item.id,
                permission_ids=permission_ids,
                actor_id=self.actor_id,
                correlation_id=self.correlation_id,
            )
        return Response(PermissionSetDetailSerializer(item).data, status=201)

    def partial_update(self, request: Any, pk: str | None = None) -> Response:
        self.get_object()
        _ensure_local_policy_ownership()
        serializer = PermissionSetUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = _call(
            PermissionSetService.update_permission_set,
            self.tenant_id,
            UUID(str(pk)),
            changes=serializer.validated_data,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(PermissionSetDetailSerializer(item).data)

    def destroy(self, request: Any, pk: str | None = None) -> Response:
        self.get_object()
        _ensure_local_policy_ownership()
        _call(
            PermissionSetService.delete_permission_set,
            self.tenant_id,
            UUID(str(pk)),
            actor_id=self.actor_id,
            reason=_deletion_reason(request),
            correlation_id=self.correlation_id,
        )
        return Response(status=204)

    @action(detail=True, methods=("put",), url_path="permissions")
    def replace_permissions(self, request: Any, pk: str | None = None) -> Response:
        _ensure_local_policy_ownership()
        serializer = ReplacePermissionSetPermissionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = _call(
            PermissionSetService.set_permissions,
            self.tenant_id,
            UUID(str(pk)),
            permission_ids=serializer.validated_data["permission_ids"],
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(PermissionSetDetailSerializer(item).data)


class UserPermissionSetViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedSecurityViewSet):
    permission_map = {
        "list": "security.assignments:read",
        "retrieve": "security.assignments:read",
        "create": "security.assignments:create",
        "partial_update": "security.assignments:update",
        "destroy": "security.assignments:delete",
    }
    ordering_fields = ("granted_at", "expires_at", "created_at")
    default_ordering = ("-granted_at",)

    def get_queryset(self) -> QuerySet[UserPermissionSet]:
        queryset = UserPermissionSet.objects.for_tenant(self.tenant_id).select_related("permission_set")
        queryset = _apply_filters(
            queryset, self.request.query_params, {"user_id": "user_id", "permission_set_id": "permission_set_id"}
        )
        if self.request.query_params.get("revoked") in {"true", "false"}:
            queryset = queryset.filter(revoked_at__isnull=self.request.query_params["revoked"] == "false")
        active_at = self.request.query_params.get("active_at")
        if active_at:
            moment = parse_datetime(active_at)
            if moment is None:
                raise ValidationError({"active_at": ["Must be an ISO datetime."]})
            queryset = queryset.filter(granted_at__lte=moment, expires_at__gt=moment, revoked_at__isnull=True)
        return self.query(queryset)

    def get_serializer_class(self) -> type:
        return {
            "list": UserPermissionSetListSerializer,
            "retrieve": UserPermissionSetDetailSerializer,
            "create": UserPermissionSetCreateSerializer,
            "partial_update": UserPermissionSetUpdateSerializer,
        }.get(self.action, UserPermissionSetDetailSerializer)

    def create(self, request: Any) -> Response:
        _ensure_local_policy_ownership()
        serializer = UserPermissionSetCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        item = _call(
            PermissionSetService.grant_to_user,
            self.tenant_id,
            values.pop("permission_set_id"),
            values.pop("user_id"),
            expires_at=values.pop("expires_at", None),
            duration_days=values.pop("duration_days", None),
            **values,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(UserPermissionSetDetailSerializer(item).data, status=201)

    def partial_update(self, request: Any, pk: str | None = None) -> Response:
        self.get_object()
        _ensure_local_policy_ownership()
        serializer = UserPermissionSetUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = _call(
            PermissionSetService.update_user_grant,
            self.tenant_id,
            UUID(str(pk)),
            **serializer.validated_data,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(UserPermissionSetDetailSerializer(item).data)

    def destroy(self, request: Any, pk: str | None = None) -> Response:
        self.get_object()
        _ensure_local_policy_ownership()
        _call(
            PermissionSetService.revoke_user_grant,
            self.tenant_id,
            UUID(str(pk)),
            reason=_deletion_reason(request),
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(status=204)


class _RuleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedSecurityViewSet):
    service: Any
    list_serializer: type
    detail_serializer: type
    create_serializer: type
    update_serializer: type

    def get_serializer_class(self) -> type:
        return {
            "list": self.list_serializer,
            "retrieve": self.detail_serializer,
            "create": self.create_serializer,
            "partial_update": self.update_serializer,
        }.get(self.action, self.detail_serializer)

    def create(self, request: Any) -> Response:
        _ensure_local_policy_ownership()
        serializer = self.create_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = _call(
            self.service.create_rule,
            self.tenant_id,
            **serializer.validated_data,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(self.detail_serializer(item).data, status=201)

    def partial_update(self, request: Any, pk: str | None = None) -> Response:
        self.get_object()
        _ensure_local_policy_ownership()
        serializer = self.update_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = _call(
            self.service.update_rule,
            self.tenant_id,
            UUID(str(pk)),
            changes=serializer.validated_data,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(self.detail_serializer(item).data)

    def destroy(self, request: Any, pk: str | None = None) -> Response:
        self.get_object()
        _ensure_local_policy_ownership()
        _call(
            self.service.delete_rule,
            self.tenant_id,
            UUID(str(pk)),
            actor_id=self.actor_id,
            reason=_deletion_reason(request),
            correlation_id=self.correlation_id,
        )
        return Response(status=204)


class FieldSecurityViewSet(_RuleViewSet):
    permission_map = {
        "list": "security.field-security:read",
        "retrieve": "security.field-security:read",
        "create": "security.field-security:create",
        "partial_update": "security.field-security:update",
        "destroy": "security.field-security:delete",
    }
    service = FieldSecurityService
    list_serializer = FieldSecurityListSerializer
    detail_serializer = FieldSecurityDetailSerializer
    create_serializer = FieldSecurityCreateSerializer
    update_serializer = FieldSecurityUpdateSerializer
    ordering_fields = ("module", "resource", "field", "created_at")
    default_ordering = ("module", "resource", "field")

    def get_queryset(self) -> QuerySet[FieldSecurity]:
        queryset = FieldSecurity.objects.for_tenant(self.tenant_id).filter(is_deleted=False).select_related("role")
        return self.query(
            _apply_filters(
                queryset,
                self.request.query_params,
                {
                    "module": "module",
                    "resource": "resource",
                    "field": "field",
                    "role_id": "role_id",
                    "visibility": "visibility",
                    "edit_control": "edit_control",
                    "is_active": "is_active",
                },
            )
        )


class RowSecurityRuleViewSet(_RuleViewSet):
    permission_map = {
        "list": "security.row-security:read",
        "retrieve": "security.row-security:read",
        "create": "security.row-security:create",
        "partial_update": "security.row-security:update",
        "destroy": "security.row-security:delete",
    }
    service = RowSecurityService
    list_serializer = RowSecurityRuleListSerializer
    detail_serializer = RowSecurityRuleDetailSerializer
    create_serializer = RowSecurityRuleCreateSerializer
    update_serializer = RowSecurityRuleUpdateSerializer
    ordering_fields = ("priority", "module", "resource", "created_at")
    default_ordering = ("-priority", "module", "resource")

    def get_queryset(self) -> QuerySet[RowSecurityRule]:
        queryset = RowSecurityRule.objects.for_tenant(self.tenant_id).filter(is_deleted=False).select_related("role")
        return self.query(
            _apply_filters(
                queryset,
                self.request.query_params,
                {
                    "module": "module",
                    "resource": "resource",
                    "role_id": "role_id",
                    "rule_type": "rule_type",
                    "is_active": "is_active",
                },
            )
        )


class SecurityProfileViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedSecurityViewSet):
    permission_map = {
        "list": "security.security-profiles:read",
        "retrieve": "security.security-profiles:read",
        "create": "security.security-profiles:create",
        "partial_update": "security.security-profiles:update",
        "destroy": "security.security-profiles:delete",
    }
    search_fields = ("name", "description")
    ordering_fields = ("name", "created_at", "updated_at")
    default_ordering = ("name",)

    def get_queryset(self) -> QuerySet[SecurityProfile]:
        queryset = SecurityProfile.objects.for_tenant(self.tenant_id).filter(is_deleted=False)
        return self.query(
            _apply_filters(
                queryset,
                self.request.query_params,
                {"profile_type": "profile_type", "mfa_required": "mfa_required", "is_active": "is_active"},
            )
        )

    def get_serializer_class(self) -> type:
        return {
            "list": SecurityProfileListSerializer,
            "retrieve": SecurityProfileDetailSerializer,
            "create": SecurityProfileCreateSerializer,
            "partial_update": SecurityProfileUpdateSerializer,
        }.get(self.action, SecurityProfileDetailSerializer)

    def create(self, request: Any) -> Response:
        _ensure_local_policy_ownership()
        serializer = SecurityProfileCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = _call(
            SecurityProfileService.create_profile,
            self.tenant_id,
            **serializer.validated_data,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(SecurityProfileDetailSerializer(item).data, status=201)

    def partial_update(self, request: Any, pk: str | None = None) -> Response:
        self.get_object()
        _ensure_local_policy_ownership()
        serializer = SecurityProfileUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = _call(
            SecurityProfileService.update_profile,
            self.tenant_id,
            UUID(str(pk)),
            changes=serializer.validated_data,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(SecurityProfileDetailSerializer(item).data)

    def destroy(self, request: Any, pk: str | None = None) -> Response:
        self.get_object()
        _ensure_local_policy_ownership()
        _call(
            SecurityProfileService.delete_profile,
            self.tenant_id,
            UUID(str(pk)),
            actor_id=self.actor_id,
            reason=_deletion_reason(request),
            correlation_id=self.correlation_id,
        )
        return Response(status=204)


class SecurityProfileAssignmentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedSecurityViewSet):
    permission_map = {
        "list": "security.assignments:read",
        "retrieve": "security.assignments:read",
        "create": "security.assignments:create",
        "partial_update": "security.assignments:update",
        "destroy": "security.assignments:delete",
    }
    ordering_fields = ("precedence", "valid_from", "created_at")
    default_ordering = ("-precedence", "-valid_from")

    def get_queryset(self) -> QuerySet[SecurityProfileAssignment]:
        queryset = SecurityProfileAssignment.objects.for_tenant(self.tenant_id).select_related(
            "security_profile", "role"
        )
        queryset = _apply_filters(
            queryset,
            self.request.query_params,
            {"profile_id": "security_profile_id", "user_id": "user_id", "role_id": "role_id"},
        )
        if self.request.query_params.get("revoked") in {"true", "false"}:
            queryset = queryset.filter(revoked_at__isnull=self.request.query_params["revoked"] == "false")
        active_at = self.request.query_params.get("active_at")
        if active_at:
            moment = parse_datetime(active_at)
            if moment is None:
                raise ValidationError({"active_at": ["Must be an ISO datetime."]})
            queryset = queryset.filter(valid_from__lte=moment, revoked_at__isnull=True).filter(
                Q(valid_until__isnull=True) | Q(valid_until__gt=moment)
            )
        return self.query(queryset)

    def get_serializer_class(self) -> type:
        return {
            "list": SecurityProfileAssignmentListSerializer,
            "retrieve": SecurityProfileAssignmentDetailSerializer,
            "create": SecurityProfileAssignmentCreateSerializer,
            "partial_update": SecurityProfileAssignmentUpdateSerializer,
        }.get(self.action, SecurityProfileAssignmentDetailSerializer)

    def create(self, request: Any) -> Response:
        _ensure_local_policy_ownership()
        serializer = SecurityProfileAssignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        item = _call(
            SecurityProfileService.assign_profile,
            self.tenant_id,
            values.pop("security_profile_id"),
            **values,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(SecurityProfileAssignmentDetailSerializer(item).data, status=201)

    def partial_update(self, request: Any, pk: str | None = None) -> Response:
        self.get_object()
        _ensure_local_policy_ownership()
        serializer = SecurityProfileAssignmentUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = _call(
            SecurityProfileService.update_profile_assignment,
            self.tenant_id,
            UUID(str(pk)),
            changes=serializer.validated_data,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(SecurityProfileAssignmentDetailSerializer(item).data)

    def destroy(self, request: Any, pk: str | None = None) -> Response:
        self.get_object()
        _ensure_local_policy_ownership()
        _call(
            SecurityProfileService.revoke_profile_assignment,
            self.tenant_id,
            UUID(str(pk)),
            reason=_deletion_reason(request),
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        return Response(status=204)


class SecurityAuditLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedSecurityViewSet):
    permission_map = {"list": "security.audit-logs:read", "retrieve": "security.audit-logs:read"}
    ordering_fields = ("timestamp", "action", "decision")
    default_ordering = ("-timestamp",)

    def get_queryset(self) -> QuerySet[SecurityAuditLog]:
        queryset = SecurityAuditLog.objects.for_tenant(self.tenant_id)
        queryset = _apply_filters(
            queryset,
            self.request.query_params,
            {
                "action": "action",
                "actor_type": "actor_type",
                "actor_id": "actor_id",
                "resource_type": "resource_type",
                "resource_id": "resource_id",
                "decision": "decision",
                "correlation_id": "correlation_id",
            },
        )
        start = parse_datetime(self.request.query_params["from"]) if "from" in self.request.query_params else None
        end = parse_datetime(self.request.query_params["to"]) if "to" in self.request.query_params else None
        if "from" in self.request.query_params and start is None or "to" in self.request.query_params and end is None:
            raise ValidationError({"range": ["from and to must be ISO datetimes."]})
        end = end or timezone.now()
        start = start or end - timedelta(days=90)
        if end < start or end - start > timedelta(days=90):
            raise ValidationError({"range": ["Audit range cannot exceed 90 days."]})
        return self.query(queryset.filter(timestamp__gte=start, timestamp__lte=end))

    def get_serializer_class(self) -> type:
        return SecurityAuditLogListSerializer if self.action == "list" else SecurityAuditLogDetailSerializer


class AccessDecisionViewSet(GovernedSecurityViewSet):
    permission_map = {"simulate": "security.access:simulate"}

    @action(detail=False, methods=("post",), url_path="simulate")
    def simulate(self, request: Any) -> Response:
        serializer = AccessSimulationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = _call(
            AccessEvaluationService.simulate,
            self.tenant_id,
            serializer.validated_data["subject_id"],
            serializer.validated_data["permission_code"],
            resource_context=serializer.validated_data.get("resource_context", {}),
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
        )
        payload = {
            **asdict(result),
            "subject_id": str(serializer.validated_data["subject_id"]),
            "decision": "allow" if result.allowed else "deny",
            "entitlement": {"required": False, "allowed": True},
            "quota": {"required": False, "allowed": True, "remaining": None},
            "field_decisions": [],
            "row_explanation": None,
            "audit_log_id": result.audit_id,
            "correlation_id": self.correlation_id,
            "evaluated_at": timezone.now(),
        }
        return Response(AccessDecisionSerializer(payload).data)


__all__ = [name for name in globals() if name.endswith("ViewSet")]
