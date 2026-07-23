"""Governed v2 HTTP adapters for the notifications domain."""

from __future__ import annotations

import uuid
from typing import Any, Callable

from django.http import Http404, JsonResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotAuthenticated, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.access.permissions import RequiresAccess
from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination
from src.core.auth_utils import get_user_id, get_user_tenant_id, get_user_tenant_role

from .health import liveness, readiness
from .filters import (
    ConfigurationHistoryFilterSet, DeliveryAttemptFilterSet, DeliveryFilterSet,
    EndpointFilterSet, FilterValidationError, InboxFilterSet, TemplateFilterSet,
)
from .permissions import READ_ACTIONS, StrictSessionAuthentication
from .models import NotificationDelivery, NotificationEndpoint, NotificationTemplateVersion
from .serializers import (
    BulkDispatchSerializer, ConfigurationImportSerializer, ConfigurationReadSerializer,
    ConfigurationRollbackSerializer, ConfigurationSimulationSerializer,
    ConfigurationVersionSerializer, ConfigurationWriteSerializer, DeliveryAttemptSerializer,
    DeliveryCancelSerializer, DeliveryConfirmationSerializer, DeliveryDetailSerializer,
    DeliveryListSerializer, DeliveryRetrySerializer, DispatchCreateSerializer,
    DispatchPreviewSerializer, EndpointDetailSerializer, EndpointListSerializer, EndpointRegisterSerializer,
    EndpointSecretRotationSerializer, EndpointUpdateSerializer, InboxDetailSerializer,
    InboxListSerializer, InboxTransitionSerializer, PreferenceBulkReplacementSerializer,
    PreferenceReadSerializer, TemplateCreateSerializer, TemplateDetailSerializer,
    TemplateListSerializer, TemplatePreviewSerializer, TemplateRollbackSerializer,
    TemplateTransitionSerializer, TemplateVersionCreateSerializer, TemplateVersionSerializer,
    UnsavedTemplatePreviewSerializer,
)
from .services import (
    CapabilityUnavailable, NotificationConfigurationService, NotificationDispatchService,
    NotificationEndpointService, NotificationInboxService, NotificationPreferenceService, NotificationProviderCallbackService,
    NotificationServiceError, NotificationTemplateService, identity_uuid,
)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"


class ServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "capability_unavailable"


def _translate(exc: Exception) -> None:
    if isinstance(exc, (NotificationTemplateVersion.DoesNotExist, NotificationDelivery.DoesNotExist, NotificationEndpoint.DoesNotExist)) or exc.__class__.__name__ == "DoesNotExist":
        raise NotFound("Resource not found.") from exc
    if isinstance(exc, CapabilityUnavailable):
        raise ServiceUnavailable({"code": exc.code, "message": exc.message}) from exc
    if isinstance(exc, NotificationServiceError):
        payload = {"code": exc.code, "message": exc.message, **({"fields": exc.errors} if exc.errors else {})}
        if exc.code in {"CONFLICT", "IDEMPOTENCY_CONFLICT", "ILLEGAL_TRANSITION"}: raise Conflict(payload) from exc
        if exc.code in {"NOT_FOUND", "CALLBACK_NOT_FOUND"}: raise NotFound(payload) from exc
        if exc.code in {"CAPABILITY_UNAVAILABLE", "CONFIGURATION_MISSING"}: raise ServiceUnavailable(payload) from exc
        raise ValidationError(payload) from exc
    raise exc


def _preference_matrix(tenant: uuid.UUID, user: uuid.UUID) -> dict[str, object]:
    stored = list(NotificationPreferenceService.list_for_user(tenant, user))
    categories = sorted({"general", "security_alerts", "password_reset", *(item.category for item in stored)})
    channels = sorted({"in_app", "email", "sms", "push", "webhook"})
    indexed = {(item.channel, item.category): item for item in stored}
    rows: list[dict[str, object]] = []
    for category in categories:
        for channel in channels:
            item = indexed.get((channel, category))
            if item is not None:
                rows.append(dict(PreferenceReadSerializer(item).data)); continue
            effective = NotificationPreferenceService.get_effective(tenant, user, channel, category)
            rows.append({"channel": channel, "category": category, **effective, "mandatory": category in {"security_alerts", "password_reset"}, "source": "mandatory_policy" if category in {"security_alerts", "password_reset"} else "tenant_default"})
    return {"categories": categories, "channels": channels, "preferences": rows}


class GovernedTenantMixin(GovernedAPIViewMixin):
    authentication_classes = [StrictSessionAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = GovernedPageNumberPagination
    action_permissions: dict[str, str] = {}
    action_entitlements: dict[str, str] = {}
    action_quotas: dict[str, str] = {}
    action_quota_costs: dict[str, int] = {}

    @classmethod
    def as_view(cls, actions=None, **initkwargs):
        """Keep published ViewSet route metadata immutable across requests.

        DRF adds an implicit ``head`` entry to the actions mapping captured by
        its request handler.  By publishing a separate copy, route discovery
        continues to describe only the explicitly registered HTTP methods.
        """

        if actions is None:
            return super().as_view(**initkwargs)
        view = super().as_view(actions=dict(actions), **initkwargs)
        view.actions = dict(view.actions)
        return view

    def _identity(self) -> tuple[uuid.UUID, uuid.UUID]:
        if not self.request.user or not self.request.user.is_authenticated: raise NotAuthenticated()
        raw_tenant = get_user_tenant_id(self.request.user)
        if not raw_tenant: raise PermissionDenied("A tenant context is required.")
        try: tenant = uuid.UUID(str(raw_tenant))
        except (TypeError, ValueError) as exc: raise PermissionDenied("The tenant context is invalid.") from exc
        actor = identity_uuid(tenant, get_user_id(self.request.user))
        self.request.tenant_id = tenant
        return tenant, actor

    def get_permissions(self):
        tenant, _ = self._identity()
        self.request.tenant_id = tenant
        action_name = getattr(self, "action", None) or self.request.method.lower()
        method_action = f"{action_name}_{self.request.method.lower()}"
        if method_action in self.action_permissions:
            action_name = method_action
        required = self.action_permissions.get(action_name)
        self.required_permission = required
        self.required_entitlement = self.action_entitlements.get(action_name, required)
        self.quota_resource = self.action_quotas.get(
            action_name,
            "notifications.api_reads" if action_name in READ_ACTIONS or self.request.method in {"GET", "HEAD"} else "notifications.api_writes",
        )
        self.quota_cost = self.action_quota_costs.get(action_name, 1)
        # Missing mappings remain None and RequiresAccess denies by default.
        return [IsAuthenticated(), RequiresAccess()]

    def _paginate(self, queryset, serializer_class):
        page = self.paginate_queryset(queryset)
        if page is None: return Response(serializer_class(queryset, many=True).data)
        return self.get_paginated_response(serializer_class(page, many=True).data)

    def _invoke(self, callback: Callable[[], Any]) -> Any:
        try: return callback()
        except Exception as exc: _translate(exc)


class InboxViewSet(GovernedTenantMixin, viewsets.GenericViewSet):
    action_permissions = {"list": "notifications.inbox:read", "retrieve": "notifications.inbox:read", "mark_read": "notifications.inbox:update", "mark_unread": "notifications.inbox:update", "archive": "notifications.inbox:update", "mark_all_read": "notifications.inbox:update", "unread_count": "notifications.inbox:read"}

    def _ids(self):
        tenant, actor = self._identity(); return tenant, actor

    def get_queryset(self):
        tenant, user = self._ids()
        queryset = NotificationInboxService.list_for_user(tenant, user, self.request.query_params)
        filters = InboxFilterSet(self.request.query_params, queryset)
        if not filters.is_valid(): raise ValidationError(filters.errors)
        return filters.qs

    def list(self, request): return self._paginate(self.get_queryset(), InboxListSerializer)
    def retrieve(self, request, pk=None):
        tenant, user = self._ids(); item = self._invoke(lambda: NotificationInboxService.get_for_user(tenant, user, pk)); return Response(InboxDetailSerializer(item).data)

    def _transition(self, request, pk, command):
        serializer = InboxTransitionSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, user = self._ids()
        item = self._invoke(lambda: getattr(NotificationInboxService, command)(tenant, user, pk, serializer.validated_data["transition_key"])); return Response(InboxDetailSerializer(item).data)

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None): return self._transition(request, pk, "mark_read")
    @action(detail=True, methods=["post"], url_path="mark-unread")
    def mark_unread(self, request, pk=None): return self._transition(request, pk, "mark_unread")
    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None): return self._transition(request, pk, "archive")
    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        serializer = InboxTransitionSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, user = self._ids(); count = self._invoke(lambda: NotificationInboxService.mark_all_read(tenant, user, serializer.validated_data["transition_key"])); return Response({"affected_count": count})
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        tenant, user = self._ids(); return Response({"count": NotificationInboxService.unread_count(tenant, user)})


class TemplateViewSet(GovernedTenantMixin, viewsets.GenericViewSet):
    action_permissions = {"list": "notifications.template:read", "retrieve": "notifications.template:read", "create": "notifications.template:create", "partial_update": "notifications.template:update", "destroy": "notifications.template:archive", "versions": "notifications.template:read", "versions_post": "notifications.template:update", "preview": "notifications.template:read", "preview_draft": "notifications.template:read", "activate": "notifications.template:activate", "restore": "notifications.template:update", "rollback": "notifications.template:activate"}
    def get_queryset(self):
        tenant, _ = self._identity(); queryset = NotificationTemplateService.list_templates(tenant, self.request.query_params); filters = TemplateFilterSet(self.request.query_params, queryset)
        if not filters.is_valid(): raise ValidationError(filters.errors)
        return filters.qs
    def list(self, request): return self._paginate(self.get_queryset(), TemplateListSerializer)
    def retrieve(self, request, pk=None):
        tenant, _ = self._identity(); item = self._invoke(lambda: NotificationTemplateService.get_template(tenant, pk)); return Response(TemplateDetailSerializer(item).data)
    def create(self, request):
        serializer = TemplateCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True); data = dict(serializer.validated_data); key = data.pop("idempotency_key", None) or request.headers.get("X-Idempotency-Key");
        if not key: raise ValidationError({"idempotency_key": "X-Idempotency-Key is required."})
        tenant, actor = self._identity(); item = self._invoke(lambda: NotificationTemplateService.create_template(tenant, actor, data, key)); return Response(TemplateDetailSerializer(item).data, status=status.HTTP_201_CREATED)
    def partial_update(self, request, pk=None):
        serializer = TemplateVersionCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, actor = self._identity(); version = self._invoke(lambda: NotificationTemplateService.create_version(tenant, pk, actor, serializer.validated_data)); return Response(TemplateVersionSerializer(version).data, status=status.HTTP_201_CREATED)
    def destroy(self, request, pk=None):
        payload = request.data if request.data else {"transition_key": request.headers.get("X-Transition-Key")}; serializer = InboxTransitionSerializer(data=payload); serializer.is_valid(raise_exception=True); tenant, actor = self._identity(); item = self._invoke(lambda: NotificationTemplateService.archive(tenant, pk, actor, serializer.validated_data["transition_key"])); return Response(TemplateDetailSerializer(item).data)
    @action(detail=True, methods=["get", "post"])
    def versions(self, request, pk=None):
        tenant, actor = self._identity(); template = self._invoke(lambda: NotificationTemplateService.get_template(tenant, pk))
        if request.method == "POST":
            serializer = TemplateVersionCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True); version = self._invoke(lambda: NotificationTemplateService.create_version(tenant, template.id, actor, serializer.validated_data)); return Response(TemplateVersionSerializer(version).data, status=201)
        return self._paginate(NotificationTemplateVersion.objects.for_tenant(tenant).filter(template=template).order_by("-version"), TemplateVersionSerializer)
    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        serializer = TemplatePreviewSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, _ = self._identity(); result = self._invoke(lambda: NotificationTemplateService.preview(tenant, pk, serializer.validated_data.get("version_id"), serializer.validated_data["context"])); return Response(result)
    @action(detail=False, methods=["post"], url_path="preview-draft")
    def preview_draft(self, request):
        serializer = UnsavedTemplatePreviewSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, _ = self._identity(); return Response(self._invoke(lambda: NotificationTemplateService.preview_unsaved(tenant, serializer.validated_data["draft"], serializer.validated_data["context"])))
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        serializer = TemplateTransitionSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, actor = self._identity(); version_id = serializer.validated_data.get("version_id")
        if version_id is None: version_id = self._invoke(lambda: NotificationTemplateVersion.objects.for_tenant(tenant).get(template_id=pk, version=serializer.validated_data["version"]).id)
        item = self._invoke(lambda: NotificationTemplateService.activate(tenant, pk, version_id, actor, serializer.validated_data["transition_key"])); return Response(TemplateDetailSerializer(item).data)
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        serializer = InboxTransitionSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, actor = self._identity(); item = self._invoke(lambda: NotificationTemplateService.restore(tenant, pk, actor, serializer.validated_data["transition_key"])); return Response(TemplateDetailSerializer(item).data)
    @action(detail=True, methods=["post"])
    def rollback(self, request, pk=None):
        serializer = TemplateRollbackSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, actor = self._identity(); version_id = serializer.validated_data.get("version_id")
        if version_id is None: version_id = self._invoke(lambda: NotificationTemplateVersion.objects.for_tenant(tenant).get(template_id=pk, version=serializer.validated_data["version"]).id)
        item = self._invoke(lambda: NotificationTemplateService.rollback(tenant, pk, version_id, actor, serializer.validated_data["transition_key"])); return Response(TemplateDetailSerializer(item).data)


class DeliveryViewSet(GovernedTenantMixin, viewsets.GenericViewSet):
    action_permissions = {"list": "notifications.delivery:read", "retrieve": "notifications.delivery:read", "create": "notifications.delivery:dispatch", "urgent": "notifications.delivery:dispatch_urgent", "bulk": "notifications.delivery:dispatch_bulk", "preview": "notifications.delivery:dispatch", "attempts": "notifications.delivery:read", "retry": "notifications.delivery:retry", "cancel": "notifications.delivery:cancel", "confirm": "notifications.delivery:dispatch"}
    action_entitlements = {"create": "notifications.delivery", "urgent": "notifications.delivery", "bulk": "notifications.delivery", "preview": "notifications.delivery", "retry": "notifications.delivery", "cancel": "notifications.delivery"}
    action_quotas = {"bulk": "notifications.delivery.dispatch_bulk", "urgent": "notifications.delivery.dispatch_urgent"}
    def get_queryset(self):
        tenant, _ = self._identity(); query = NotificationDelivery.objects.for_tenant(tenant).select_related("template_version").prefetch_related("attempts")
        filters = DeliveryFilterSet(self.request.query_params, query)
        if not filters.is_valid(): raise ValidationError(filters.errors)
        return filters.qs
    def list(self, request): return self._paginate(self.get_queryset(), DeliveryListSerializer)
    def retrieve(self, request, pk=None): return Response(DeliveryDetailSerializer(self._invoke(lambda: self.get_queryset().get(pk=pk))).data)
    def create(self, request):
        serializer = DispatchCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True); data = dict(serializer.validated_data); key = data.pop("idempotency_key"); tenant, actor = self._identity(); result = self._invoke(lambda: NotificationDispatchService.enqueue(tenant, actor, data, key)); return Response(DeliveryDetailSerializer(result.object).data, status=202)
    @action(detail=False, methods=["post"])
    def urgent(self, request):
        serializer = DispatchCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True); data = dict(serializer.validated_data); key = data.pop("idempotency_key"); data["priority"] = 1; data["urgent_authorized"] = True; tenant, actor = self._identity(); result = self._invoke(lambda: NotificationDispatchService.enqueue(tenant, actor, data, key)); return Response(DeliveryDetailSerializer(result.object).data, status=202)
    @action(detail=False, methods=["post"])
    def bulk(self, request):
        serializer = BulkDispatchSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, actor = self._identity(); results = self._invoke(lambda: NotificationDispatchService.enqueue_bulk(tenant, actor, serializer.validated_data["requests"], serializer.validated_data["idempotency_key"])); return Response([DeliveryListSerializer(item.object).data for item in results], status=202)
    @action(detail=False, methods=["post"])
    def preview(self, request):
        serializer = DispatchPreviewSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, actor = self._identity(); return Response(self._invoke(lambda: NotificationDispatchService.preview_dispatch(tenant, actor, serializer.validated_data)))
    @action(detail=True, methods=["get"])
    def attempts(self, request, pk=None):
        tenant, _ = self._identity(); self._invoke(lambda: self.get_queryset().get(pk=pk)); queryset = NotificationDelivery._meta.get_field("attempts").related_model.objects.for_tenant(tenant).filter(delivery_id=pk); filters = DeliveryAttemptFilterSet(request.query_params, queryset)
        if not filters.is_valid(): raise ValidationError(filters.errors)
        return self._paginate(filters.qs, DeliveryAttemptSerializer)
    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        serializer = DeliveryRetrySerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, actor = self._identity(); result = self._invoke(lambda: NotificationDispatchService.retry(tenant, pk, actor, serializer.validated_data["idempotency_key"])); return Response(DeliveryDetailSerializer(result.object).data, status=202)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        serializer = DeliveryCancelSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, actor = self._identity(); item = self._invoke(lambda: NotificationDispatchService.cancel(tenant, pk, actor, serializer.validated_data["transition_key"])); return Response(DeliveryDetailSerializer(item).data)
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        serializer = DeliveryConfirmationSerializer(data=request.data); serializer.is_valid(raise_exception=True); data = dict(serializer.validated_data); key = data.pop("idempotency_key"); tenant, _ = self._identity(); item = self._invoke(lambda: NotificationDispatchService.confirm_delivery(tenant, pk, data, key)); return Response(DeliveryDetailSerializer(item).data)


class PreferenceAPIView(GovernedTenantMixin, APIView):
    action_permissions = {"get": "notifications.preference:read", "put": "notifications.preference:update"}
    def get(self, request):
        tenant, user = self._identity(); return Response(_preference_matrix(tenant, user))
    def put(self, request):
        serializer = PreferenceBulkReplacementSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, user = self._identity(); self._invoke(lambda: NotificationPreferenceService.bulk_replace(tenant, user, user, serializer.validated_data["preferences"])); return Response(_preference_matrix(tenant, user))


class PreferenceResetAPIView(GovernedTenantMixin, APIView):
    action_permissions = {"post": "notifications.preference:update"}
    def post(self, request):
        tenant, user = self._identity(); self._invoke(lambda: NotificationPreferenceService.reset(tenant, user, user)); return Response(_preference_matrix(tenant, user))


class EndpointViewSet(GovernedTenantMixin, viewsets.GenericViewSet):
    action_permissions = {"list": "notifications.endpoint:read", "retrieve": "notifications.endpoint:read", "create": "notifications.endpoint:create", "partial_update": "notifications.endpoint:update", "destroy": "notifications.endpoint:delete", "verify": "notifications.endpoint:verify", "rotate_secret": "notifications.endpoint:update"}
    def get_queryset(self):
        tenant, user = self._identity()
        queryset = NotificationEndpoint.objects.for_tenant(tenant).order_by("kind", "display_name") if get_user_tenant_role(self.request.user) == "tenant_admin" else NotificationEndpointService.list_for_user(tenant, user)
        filters = EndpointFilterSet(self.request.query_params, queryset)
        if not filters.is_valid(): raise ValidationError(filters.errors)
        return filters.qs
    def list(self, request): return self._paginate(self.get_queryset(), EndpointListSerializer)
    def retrieve(self, request, pk=None): return Response(EndpointDetailSerializer(self._invoke(lambda: self.get_queryset().get(pk=pk))).data)
    def create(self, request):
        serializer = EndpointRegisterSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, user = self._identity(); item = self._invoke(lambda: NotificationEndpointService.register(tenant, user, user, serializer.validated_data)); return Response(EndpointDetailSerializer(item).data, status=201)
    def partial_update(self, request, pk=None):
        serializer = EndpointUpdateSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, actor = self._identity(); item = self._invoke(lambda: NotificationEndpointService.update(tenant, pk, actor, serializer.validated_data)); return Response(EndpointDetailSerializer(item).data)
    def destroy(self, request, pk=None):
        tenant, actor = self._identity(); item = self._invoke(lambda: NotificationEndpointService.revoke(tenant, pk, actor)); return Response(EndpointDetailSerializer(item).data)
    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        tenant, actor = self._identity(); item = self._invoke(lambda: NotificationEndpointService.verify(tenant, pk, actor)); return Response({"verified": True, "health": "healthy", "verified_at": item.last_verified_at, "endpoint": EndpointDetailSerializer(item).data})
    @action(detail=True, methods=["post"], url_path="rotate-secret")
    def rotate_secret(self, request, pk=None):
        serializer = EndpointSecretRotationSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, actor = self._identity(); item = self._invoke(lambda: NotificationEndpointService.rotate_secret_ref(tenant, pk, actor, serializer.validated_data["secret_ref"])); return Response(EndpointDetailSerializer(item).data)


class ConfigurationAPIView(GovernedTenantMixin, APIView):
    action_permissions = {"get": "notifications.configuration:read", "patch": "notifications.configuration:update"}
    def get(self, request, environment):
        tenant, actor = self._identity(); item = self._invoke(lambda: NotificationConfigurationService.get_or_create_default(tenant, environment, actor)); return Response(ConfigurationReadSerializer(item).data)
    def patch(self, request, environment):
        tenant, actor = self._identity(); serializer = ConfigurationWriteSerializer(data=request.data, context={"tenant_id": tenant}); serializer.is_valid(raise_exception=True)
        current = self._invoke(lambda: NotificationConfigurationService.get_or_create_default(tenant, environment, actor)); expected = serializer.validated_data.get("expected_version")
        if expected is not None and expected != current.active_version: raise Conflict({"code": "CONFIGURATION_VERSION_CONFLICT", "message": "Configuration changed since it was loaded."})
        item = self._invoke(lambda: NotificationConfigurationService.update(tenant, environment, actor, serializer.validated_data["document"], serializer.validated_data["reason"])); return Response(ConfigurationReadSerializer(item).data)


class ConfigurationSimulateAPIView(GovernedTenantMixin, APIView):
    action_permissions = {"post": "notifications.configuration:update"}
    def post(self, request, environment):
        serializer = ConfigurationSimulationSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, _ = self._identity(); scenario = {**serializer.validated_data["scenario"], "environment": environment}; return Response(NotificationConfigurationService.simulate(tenant, serializer.validated_data["document"], scenario))


class ConfigurationHistoryAPIView(GovernedTenantMixin, APIView):
    action_permissions = {"get": "notifications.configuration:read"}
    def get(self, request, environment):
        tenant, _ = self._identity(); queryset = NotificationConfigurationService.history(tenant, environment); filters = ConfigurationHistoryFilterSet(request.query_params, queryset)
        if not filters.is_valid(): raise ValidationError(filters.errors)
        paginator = GovernedPageNumberPagination(); page = paginator.paginate_queryset(filters.qs, request, view=self); items = []
        for version in page:
            audit = version.audits.order_by("-created_at").first()
            action = {"created": "create", "updated": "update", "imported": "import", "rolled_back": "rollback"}.get(audit.action if audit else "", audit.action if audit else "create")
            audit_data = {"id": str(audit.id) if audit else "", "version": version.version, "actor_id": str(audit.actor_id) if audit else str(version.created_by), "correlation_id": str(audit.correlation_id) if audit else str(version.correlation_id), "action": action, "before_checksum": None, "after_checksum": version.checksum, "changed_paths": [entry.get("path") for entry in (audit.diff if audit else []) if isinstance(entry, dict) and entry.get("path")], "created_at": audit.created_at if audit else version.created_at}
            items.append({"version": ConfigurationVersionSerializer(version).data, "audit": audit_data})
        return paginator.get_paginated_response(items)


class ConfigurationRollbackAPIView(GovernedTenantMixin, APIView):
    action_permissions = {"post": "notifications.configuration:rollback"}
    def post(self, request, environment):
        serializer = ConfigurationRollbackSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, actor = self._identity(); current = self._invoke(lambda: NotificationConfigurationService.get_or_create_default(tenant, environment, actor)); expected = serializer.validated_data.get("expected_version")
        if expected is not None and expected != current.active_version: raise Conflict({"code": "CONFIGURATION_VERSION_CONFLICT", "message": "Configuration changed since it was loaded."})
        item = self._invoke(lambda: NotificationConfigurationService.rollback(tenant, environment, serializer.validated_data["version"], actor, serializer.validated_data["reason"])); return Response(ConfigurationReadSerializer(item).data)


class ConfigurationImportAPIView(GovernedTenantMixin, APIView):
    action_permissions = {"post": "notifications.configuration:import"}
    def post(self, request, environment):
        serializer = ConfigurationImportSerializer(data=request.data); serializer.is_valid(raise_exception=True); tenant, actor = self._identity(); current = self._invoke(lambda: NotificationConfigurationService.get_or_create_default(tenant, environment, actor)); expected = serializer.validated_data.get("expected_version")
        if expected is not None and expected != current.active_version: raise Conflict({"code": "CONFIGURATION_VERSION_CONFLICT", "message": "Configuration changed since it was loaded."})
        result = self._invoke(lambda: NotificationConfigurationService.import_document(tenant, environment, actor, serializer.validated_data["document"], serializer.validated_data["dry_run"])); return Response(ConfigurationReadSerializer(result).data if hasattr(result, "environment") else result)


class ConfigurationExportAPIView(GovernedTenantMixin, APIView):
    action_permissions = {"get": "notifications.configuration:export"}
    def get(self, request, environment):
        tenant, _ = self._identity(); payload = self._invoke(lambda: NotificationConfigurationService.export_document(tenant, environment)); response = Response(payload); response["Content-Disposition"] = f'attachment; filename="notifications-{environment}.json"'; return response


class LivenessAPIView(GovernedAPIViewMixin, APIView):
    authentication_classes = []
    permission_classes = []
    def get(self, request): return Response(liveness())


class ReadinessAPIView(GovernedTenantMixin, APIView):
    action_permissions = {"get": "notifications.health:read"}
    def get(self, request):
        tenant, _ = self._identity(); payload, http_status = readiness(tenant); return Response(payload, status=http_status)


class ProviderCallbackAPIView(GovernedAPIViewMixin, APIView):
    """Signed, replay-protected callback ingress with server-owned tenancy."""

    authentication_classes = []
    permission_classes = []

    def post(self, request, callback_key):
        try:
            result = NotificationProviderCallbackService.accept(callback_key, request.headers, request.body)
        except Exception as exc:
            _translate(exc)
        return Response(result, status=status.HTTP_200_OK if result["replayed"] else status.HTTP_202_ACCEPTED)


# Compatibility aliases. These use the canonical inbox/preference services.
NotificationViewSet = InboxViewSet


class NotificationPreferenceViewSet(GovernedTenantMixin, viewsets.GenericViewSet):
    action_permissions = {"list": "notifications.preference:read", "create": "notifications.preference:update"}
    def list(self, request): return PreferenceAPIView().get(request)
    def create(self, request):
        serializer = PreferenceBulkReplacementSerializer(data={"preferences": [request.data]}); serializer.is_valid(raise_exception=True); tenant, user = self._identity(); item = self._invoke(lambda: NotificationPreferenceService.upsert(tenant, user, user, serializer.validated_data["preferences"][0])); return Response(PreferenceReadSerializer(item).data, status=201)
