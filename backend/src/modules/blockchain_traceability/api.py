"""Governed, tenant-isolated API v2 for blockchain traceability.

Controllers adapt HTTP requests only.  Domain validation, state transitions,
hashing, idempotency, provider calls, and durable job persistence remain in
``services.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime
from math import ceil
from typing import Any, TypeVar
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Q, QuerySet
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.api.profile import GovernedAPIViewMixin
from src.core.api.results import OperationFailed, OperationResult
from src.core.state_machine import (
    GuardFailedError,
    IdempotencyConflictError,
    IllegalTransitionError,
    UnknownCommandError,
)
from src.core.views.tenant_scoped import TenantScopedModelViewSet, TenantScopedReadOnlyModelViewSet

from .health import module_health
from .models import (
    AuthenticityCredential,
    ComplianceEvidence,
    LedgerAnchor,
    LedgerNetwork,
    TraceabilityAsset,
    TraceabilityEvent,
    VerificationAttempt,
)
from .permissions import (
    ANCHOR_CREATE,
    ANCHOR_READ,
    ANCHOR_RETRY,
    ANCHOR_VERIFY,
    ASSET_CREATE,
    ASSET_DELETE,
    ASSET_READ,
    ASSET_TRANSITION,
    ASSET_UPDATE,
    ActionAccessMixin,
    COMPLIANCE_CREATE,
    COMPLIANCE_DELETE,
    COMPLIANCE_FINALIZE,
    COMPLIANCE_READ,
    COMPLIANCE_UPDATE,
    COMPLIANCE_VERIFY,
    CREDENTIAL_ISSUE,
    CREDENTIAL_READ,
    CREDENTIAL_REVOKE,
    CREDENTIAL_VERIFY,
    EVENT_APPEND,
    EVENT_READ,
    EVENT_VERIFY,
    HEALTH_READ,
    NETWORK_MANAGE,
    NETWORK_PROBE,
    NETWORK_READ,
    SessionAuthentication401,
    VERIFICATION_READ,
)
from .providers import ProviderUnavailableError
from .serializers import (
    AuthenticityCredentialDetailSerializer,
    AuthenticityCredentialIssueSerializer,
    AuthenticityCredentialListSerializer,
    AuthenticityVerificationSerializer,
    ChainVerificationSerializer,
    ComplianceEvidenceCreateSerializer,
    ComplianceEvidenceDetailSerializer,
    ComplianceEvidenceListSerializer,
    ComplianceEvidenceUpdateSerializer,
    CredentialRevokeSerializer,
    EvidenceSupersedeSerializer,
    LedgerAnchorCreateSerializer,
    LedgerAnchorDetailSerializer,
    LedgerAnchorListSerializer,
    LedgerNetworkCreateSerializer,
    LedgerNetworkDetailSerializer,
    LedgerNetworkListSerializer,
    LedgerNetworkUpdateSerializer,
    RecallSerializer,
    TraceabilityAssetCreateSerializer,
    TraceabilityAssetDetailSerializer,
    TraceabilityAssetListSerializer,
    TraceabilityAssetUpdateSerializer,
    TraceabilityEventCreateSerializer,
    TraceabilityEventDetailSerializer,
    TraceabilityEventListSerializer,
    TransitionSerializer,
    VerificationAttemptDetailSerializer,
    VerificationAttemptListSerializer,
)
from .services import (
    AuthenticityService,
    ComplianceEvidenceService,
    DomainNotFoundError,
    LedgerAnchorService,
    LedgerNetworkService,
    TraceabilityAssetService,
    TraceabilityEventService,
    VerificationService,
)

T = TypeVar("T")


def _service_call(operation: Callable[[], T]) -> T:
    """Map known domain failures without disclosing implementation details."""

    try:
        return operation()
    except (ObjectDoesNotExist, DomainNotFoundError) as exc:
        raise NotFound("The requested resource was not found.") from exc
    except ProviderUnavailableError as exc:
        raise OperationFailed(
            error_code="CAPABILITY_UNAVAILABLE",
            message="The configured provider is currently unavailable.",
            detail={"capability": "blockchain_traceability.provider"},
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    except (IntegrityError, ProtectedError) as exc:
        raise OperationFailed(
            error_code="RESOURCE_CONFLICT",
            message="The operation conflicts with existing traceability evidence.",
            http_status=status.HTTP_409_CONFLICT,
        ) from exc
    except (IllegalTransitionError, GuardFailedError, IdempotencyConflictError, UnknownCommandError) as exc:
        raise OperationFailed(
            error_code="STATE_CONFLICT",
            message=str(exc),
            http_status=status.HTTP_409_CONFLICT,
        ) from exc
    except DjangoValidationError as exc:
        detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or ["Request is invalid."]
        raise ValidationError(detail) from exc
    except (ValueError, TypeError) as exc:
        # Domain state/idempotency exceptions subclass ValueError in the module
        # contract and carry stable ``code`` metadata.
        code = getattr(exc, "code", None)
        if isinstance(code, str) and code:
            raise OperationFailed(
                error_code=code,
                message=str(exc),
                http_status=status.HTTP_409_CONFLICT,
            ) from exc
        raise ValidationError({"non_field_errors": [str(exc)]}) from exc


def _unwrap_result(result: T | OperationResult[T]) -> T:
    if isinstance(result, OperationResult):
        return result.unwrap()
    return result


def _serialize_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    return value


def _operation_payload(value: object, *, code: str, message: str) -> dict[str, object]:
    """Expose a proven service result without leaking internal evidence."""

    return {"ok": True, "code": code, "message": message, "value": value}


def _asset_history_payload(tenant_id: UUID, asset: TraceabilityAsset, history: object) -> dict[str, object]:
    """Build the discriminated, complete timeline wire contract in bounded queries."""

    items = tuple(getattr(history, "items", ()))
    identifiers: dict[str, set[UUID]] = {
        "event": set(),
        "anchor": set(),
        "credential": set(),
        "compliance": set(),
    }
    for item in items:
        kind = str(getattr(item, "kind", ""))
        if kind not in identifiers:
            raise OperationFailed(
                error_code="HISTORY_EVIDENCE_INVALID",
                message="Asset history contains an unsupported evidence type.",
                http_status=status.HTTP_409_CONFLICT,
            )
        identifiers[kind].add(_parse_uuid(getattr(item, "identifier", None), "history_item_id"))

    events = TraceabilityEvent.objects.filter(tenant_id=tenant_id, id__in=identifiers["event"]).in_bulk()
    anchors = (
        LedgerAnchor.objects.filter(tenant_id=tenant_id, id__in=identifiers["anchor"])
        .select_related("asset", "network")
        .in_bulk()
    )
    credentials = (
        AuthenticityCredential.objects.filter(tenant_id=tenant_id, id__in=identifiers["credential"])
        .select_related("asset")
        .in_bulk()
    )
    evidence = (
        ComplianceEvidence.objects.filter(tenant_id=tenant_id, id__in=identifiers["compliance"])
        .select_related("asset", "event", "supersedes")
        .in_bulk()
    )
    records: Mapping[str, Mapping[UUID, object]] = {
        "event": events,
        "anchor": anchors,
        "credential": credentials,
        "compliance": evidence,
    }
    serializers_by_kind = {
        "event": ("event", TraceabilityEventDetailSerializer),
        "anchor": ("anchor", LedgerAnchorDetailSerializer),
        "credential": ("credential", AuthenticityCredentialDetailSerializer),
        "compliance": ("evidence", ComplianceEvidenceDetailSerializer),
    }
    timeline: list[dict[str, object]] = []
    for item in items:
        kind = str(getattr(item, "kind"))
        identifier = _parse_uuid(getattr(item, "identifier"), "history_item_id")
        model = records[kind].get(identifier)
        if model is None:
            raise OperationFailed(
                error_code="HISTORY_EVIDENCE_MISSING",
                message="Referenced asset-history evidence is unavailable.",
                http_status=status.HTTP_409_CONFLICT,
            )
        field_name, serializer_class = serializers_by_kind[kind]
        sequence = getattr(item, "sequence", None)
        if sequence is None and kind == "anchor":
            sequence = getattr(model, "end_sequence")
        if sequence is None and kind == "compliance":
            related_event = getattr(model, "event", None)
            sequence = getattr(related_event, "sequence", None)
        # Zero is the explicit off-chain sentinel; event sequences begin at one.
        timeline.append(
            {
                "kind": kind,
                "occurred_at": str(getattr(item, "occurred_at")),
                "sequence": sequence if isinstance(sequence, int) else 0,
                field_name: serializer_class(model).data,
            }
        )

    pagination = getattr(history, "pagination", {})
    if not isinstance(pagination, Mapping):
        raise OperationFailed(
            error_code="HISTORY_PAGINATION_INVALID",
            message="Asset history pagination evidence is invalid.",
            http_status=status.HTTP_409_CONFLICT,
        )
    page = int(pagination.get("page", 1))
    page_size = int(pagination.get("page_size", 25))
    count = int(pagination.get("total", 0))
    proof_status = {
        "Locally consistent — not externally anchored": "locally_consistent",
        "Externally verified": "externally_verified",
        "Invalid proof": "invalid",
        "Verification unavailable": "unavailable",
    }.get(str(getattr(history, "proof_status", "")), "unavailable")
    return {
        "asset": TraceabilityAssetDetailSerializer(asset).data,
        "items": timeline,
        "proof_status": proof_status,
        "failing_sequence": getattr(history, "failing_sequence", None),
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_pages": ceil(count / page_size) if count else 0,
            "count": count,
            "has_next": bool(pagination.get("has_next", False)),
            "has_previous": page > 1,
        },
    }


def _parse_uuid(value: object, field_name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValidationError({field_name: ["Must be a valid UUID."]}) from exc


def _parse_date(value: str, field_name: str) -> datetime:
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValidationError({field_name: ["Must be a valid RFC 3339 date-time."]})
    return parsed


class GovernedTenantMixin(ActionAccessMixin):
    """Common identity, bounded list, filter, and ordering helpers."""

    @property
    def tenant_id(self) -> UUID:
        return self._require_tenant_id()

    @property
    def actor_id(self) -> str:
        identifier = getattr(self.request.user, "pk", None)
        if identifier is None:
            raise ValidationError({"actor": ["Authenticated identity is incomplete."]})
        return str(identifier)

    def _paginate(self, queryset: QuerySet[Any], serializer_class: type) -> Response:
        page = self.paginate_queryset(queryset)
        if page is None:
            raise RuntimeError("Governed collection endpoints require bounded pagination.")
        serializer = serializer_class(page, many=True)
        return self.get_paginated_response(serializer.data)

    def _exact_filters(self, queryset: QuerySet[Any], names: tuple[str, ...]) -> QuerySet[Any]:
        for name in names:
            value = self.request.query_params.get(name)
            if value is not None and value != "":
                queryset = queryset.filter(**{name: value})
        return queryset

    def _uuid_filter(self, queryset: QuerySet[Any], parameter: str, field: str | None = None) -> QuerySet[Any]:
        value = self.request.query_params.get(parameter)
        if not value:
            return queryset
        return queryset.filter(**{field or parameter: _parse_uuid(value, parameter)})

    def _date_filters(
        self,
        queryset: QuerySet[Any],
        *,
        field: str,
        after: str,
        before: str,
    ) -> QuerySet[Any]:
        if value := self.request.query_params.get(after):
            queryset = queryset.filter(**{f"{field}__gte": _parse_date(value, after)})
        if value := self.request.query_params.get(before):
            queryset = queryset.filter(**{f"{field}__lte": _parse_date(value, before)})
        return queryset

    def _ordering(
        self,
        queryset: QuerySet[Any],
        *,
        allowed: Mapping[str, str],
        default: str,
    ) -> QuerySet[Any]:
        requested = self.request.query_params.get("ordering", default)
        descending = requested.startswith("-")
        key = requested[1:] if descending else requested
        if key not in allowed:
            raise ValidationError({"ordering": [f"Unsupported ordering field '{key}'."]})
        field = allowed[key]
        return queryset.order_by(f"-{field}" if descending else field, "id")


class GovernedTenantModelViewSet(
    GovernedAPIViewMixin,
    GovernedTenantMixin,
    TenantScopedModelViewSet,
):
    """Mutable tenant boundary; concrete controllers still delegate writes."""


class GovernedTenantReadOnlyViewSet(
    GovernedAPIViewMixin,
    GovernedTenantMixin,
    TenantScopedReadOnlyModelViewSet,
):
    """Immutable tenant boundary for audit evidence."""


class LedgerNetworkViewSet(GovernedTenantModelViewSet):
    queryset = LedgerNetwork.objects.all()
    service = LedgerNetworkService()
    http_method_names = ("get", "post", "patch", "delete", "head", "options")
    unsupported_method_permission = NETWORK_MANAGE
    action_permissions = {
        "list": NETWORK_READ,
        "retrieve": NETWORK_READ,
        "create": NETWORK_MANAGE,
        "partial_update": NETWORK_MANAGE,
        "destroy": NETWORK_MANAGE,
        "activate": NETWORK_MANAGE,
        "disable": NETWORK_MANAGE,
        "probe": NETWORK_PROBE,
    }

    def get_queryset(self) -> QuerySet[LedgerNetwork]:
        queryset = super().get_queryset().filter(is_deleted=False)
        if self.action == "list":
            queryset = self._exact_filters(queryset, ("status", "provider_type"))
            if search := self.request.query_params.get("search"):
                queryset = queryset.filter(Q(network_key__icontains=search) | Q(name__icontains=search))
            queryset = self._ordering(
                queryset,
                allowed={"name": "name", "created_at": "created_at"},
                default="name",
            )
        return queryset

    def get_serializer_class(self) -> type:
        return {
            "list": LedgerNetworkListSerializer,
            "create": LedgerNetworkCreateSerializer,
            "partial_update": LedgerNetworkUpdateSerializer,
        }.get(self.action, LedgerNetworkDetailSerializer)

    def list(self, request: Request) -> Response:
        del request
        return self._paginate(self.get_queryset(), LedgerNetworkListSerializer)

    def create(self, request: Request) -> Response:
        serializer = LedgerNetworkCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        network = _service_call(
            lambda: self.service.create_network(self.tenant_id, self.actor_id, dict(serializer.validated_data))
        )
        return Response(LedgerNetworkDetailSerializer(network).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = LedgerNetworkUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        network = _service_call(
            lambda: self.service.update_network(
                self.tenant_id,
                _parse_uuid(pk, "id"),
                self.actor_id,
                dict(serializer.validated_data),
            )
        )
        return Response(LedgerNetworkDetailSerializer(network).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        del request
        self.get_object()
        _service_call(lambda: self.service.delete_network(self.tenant_id, _parse_uuid(pk, "id"), self.actor_id))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",))
    def activate(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = _service_call(
            lambda: self.service.activate_network(
                self.tenant_id,
                _parse_uuid(pk, "id"),
                self.actor_id,
                serializer.validated_data["transition_key"],
            )
        )
        return Response(LedgerNetworkDetailSerializer(value).data)

    @action(detail=True, methods=("post",))
    def disable(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = _service_call(
            lambda: self.service.disable_network(
                self.tenant_id,
                _parse_uuid(pk, "id"),
                self.actor_id,
                serializer.validated_data["transition_key"],
            )
        )
        return Response(LedgerNetworkDetailSerializer(value).data)

    @action(detail=True, methods=("post",))
    def probe(self, request: Request, pk: str | None = None) -> Response:
        del request
        network = self.get_object()
        result = _service_call(lambda: self.service.probe_network(self.tenant_id, _parse_uuid(pk, "id"), self.actor_id))
        health = _unwrap_result(result)
        checked_at = getattr(health, "checked_at", None) or timezone.now()
        provider_health = {
            "status": "healthy" if bool(getattr(health, "available", False)) else "unavailable",
            "code": str(getattr(health, "code", "PROVIDER_HEALTH_UNKNOWN")),
            "checked_at": checked_at.isoformat(),
            "provider_type": network.provider_type,
            "simulated": bool(getattr(health, "simulated", False)),
        }
        latency_ms = getattr(health, "latency_ms", None)
        if isinstance(latency_ms, int) and latency_ms >= 0:
            provider_health["latency_ms"] = latency_ms
        return Response(
            _operation_payload(
                provider_health,
                code="PROBE_COMPLETED",
                message="The configured provider returned bounded health evidence.",
            )
        )


class TraceabilityAssetViewSet(GovernedTenantModelViewSet):
    queryset = TraceabilityAsset.objects.all()
    service = TraceabilityAssetService()
    event_service = TraceabilityEventService()
    http_method_names = ("get", "post", "patch", "delete", "head", "options")
    unsupported_method_permission = ASSET_UPDATE
    action_permissions = {
        "list": ASSET_READ,
        "retrieve": ASSET_READ,
        "create": ASSET_CREATE,
        "partial_update": ASSET_UPDATE,
        "destroy": ASSET_DELETE,
        "activate": ASSET_TRANSITION,
        "recall": ASSET_TRANSITION,
        "release_recall": ASSET_TRANSITION,
        "retire": ASSET_TRANSITION,
        "history": ASSET_READ,
        "verify_chain": EVENT_VERIFY,
    }

    def get_queryset(self) -> QuerySet[TraceabilityAsset]:
        queryset = super().get_queryset().filter(is_deleted=False)
        if self.action == "list":
            queryset = self._exact_filters(
                queryset,
                ("status", "product_ref", "batch_ref", "serial_number", "gtin", "asset_type"),
            )
            if search := self.request.query_params.get("search"):
                queryset = queryset.filter(Q(asset_key__icontains=search) | Q(name__icontains=search))
            queryset = self._ordering(
                queryset,
                allowed={"name": "name", "created_at": "created_at", "asset_key": "asset_key"},
                default="-created_at",
            )
        return queryset

    def get_serializer_class(self) -> type:
        return {
            "list": TraceabilityAssetListSerializer,
            "create": TraceabilityAssetCreateSerializer,
            "partial_update": TraceabilityAssetUpdateSerializer,
        }.get(self.action, TraceabilityAssetDetailSerializer)

    def list(self, request: Request) -> Response:
        del request
        return self._paginate(self.get_queryset(), TraceabilityAssetListSerializer)

    def create(self, request: Request) -> Response:
        serializer = TraceabilityAssetCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = _service_call(
            lambda: self.service.register_asset(self.tenant_id, self.actor_id, dict(serializer.validated_data))
        )
        return Response(TraceabilityAssetDetailSerializer(value).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = TraceabilityAssetUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        value = _service_call(
            lambda: self.service.update_asset(
                self.tenant_id,
                _parse_uuid(pk, "id"),
                self.actor_id,
                dict(serializer.validated_data),
            )
        )
        return Response(TraceabilityAssetDetailSerializer(value).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        del request
        self.get_object()
        _service_call(lambda: self.service.delete_asset(self.tenant_id, _parse_uuid(pk, "id"), self.actor_id))
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _transition(self, request: Request, pk: str | None, method_name: str) -> Response:
        self.get_object()
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        method = getattr(self.service, method_name)
        value = _service_call(
            lambda: method(
                self.tenant_id,
                _parse_uuid(pk, "id"),
                self.actor_id,
                serializer.validated_data["transition_key"],
            )
        )
        return Response(TraceabilityAssetDetailSerializer(value).data)

    @action(detail=True, methods=("post",))
    def activate(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, pk, "activate_asset")

    @action(detail=True, methods=("post",), url_path="release-recall")
    def release_recall(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, pk, "release_recall")

    @action(detail=True, methods=("post",))
    def retire(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, pk, "retire_asset")

    @action(detail=True, methods=("post",))
    def recall(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = RecallSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = _service_call(
            lambda: self.service.recall_asset(
                self.tenant_id,
                _parse_uuid(pk, "id"),
                self.actor_id,
                serializer.validated_data["reason"],
                serializer.validated_data["transition_key"],
            )
        )
        return Response(TraceabilityAssetDetailSerializer(value).data)

    @action(detail=True, methods=("get",))
    def history(self, request: Request, pk: str | None = None) -> Response:
        asset = self.get_object()
        page = request.query_params.get("page", "1")
        page_size = request.query_params.get("page_size", "25")
        try:
            parsed_page = max(1, int(page))
            parsed_size = min(100, max(1, int(page_size)))
        except ValueError as exc:
            raise ValidationError({"pagination": ["page and page_size must be integers."]}) from exc
        value = _service_call(
            lambda: self.service.product_history(
                self.tenant_id,
                _parse_uuid(pk, "id"),
                parsed_page,
                parsed_size,
            )
        )
        return Response(_asset_history_payload(self.tenant_id, asset, value))

    @action(detail=True, methods=("post",), url_path="verify-chain")
    def verify_chain(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = ChainVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = _service_call(
            lambda: self.event_service.verify_chain(
                self.tenant_id,
                _parse_uuid(pk, "id"),
                self.actor_id,
                serializer.validated_data["idempotency_key"],
            )
        )
        return Response(VerificationAttemptDetailSerializer(value).data)


class TraceabilityEventViewSet(GovernedTenantModelViewSet):
    queryset = TraceabilityEvent.objects.select_related("asset").all()
    service = TraceabilityEventService()
    http_method_names = ("get", "post", "head", "options")
    unsupported_method_permission = EVENT_READ
    action_permissions = {"list": EVENT_READ, "retrieve": EVENT_READ, "create": EVENT_APPEND}

    def get_queryset(self) -> QuerySet[TraceabilityEvent]:
        queryset = super().get_queryset().select_related("asset")
        if self.action == "list":
            queryset = self._exact_filters(queryset, ("event_type", "actor_ref"))
            queryset = self._uuid_filter(queryset, "asset_id")
            queryset = self._date_filters(
                queryset,
                field="occurred_at",
                after="occurred_after",
                before="occurred_before",
            )
            queryset = self._ordering(
                queryset,
                allowed={"sequence": "sequence", "occurred_at": "occurred_at", "recorded_at": "recorded_at"},
                default="-recorded_at",
            )
        return queryset

    def get_serializer_class(self) -> type:
        return {
            "list": TraceabilityEventListSerializer,
            "create": TraceabilityEventCreateSerializer,
        }.get(self.action, TraceabilityEventDetailSerializer)

    def list(self, request: Request) -> Response:
        del request
        return self._paginate(self.get_queryset(), TraceabilityEventListSerializer)

    def create(self, request: Request) -> Response:
        serializer = TraceabilityEventCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = _service_call(
            lambda: self.service.append_event(self.tenant_id, self.actor_id, dict(serializer.validated_data))
        )
        return Response(TraceabilityEventDetailSerializer(value).data, status=status.HTTP_201_CREATED)


class LedgerAnchorViewSet(GovernedTenantModelViewSet):
    queryset = LedgerAnchor.objects.select_related("asset", "network").all()
    service = LedgerAnchorService()
    http_method_names = ("get", "post", "head", "options")
    unsupported_method_permission = ANCHOR_READ
    action_permissions = {
        "list": ANCHOR_READ,
        "retrieve": ANCHOR_READ,
        "create": ANCHOR_CREATE,
        "retry": ANCHOR_RETRY,
        "refresh": ANCHOR_VERIFY,
        "verify": ANCHOR_VERIFY,
    }

    def get_queryset(self) -> QuerySet[LedgerAnchor]:
        queryset = super().get_queryset().select_related("asset", "network")
        if self.action == "list":
            queryset = self._exact_filters(queryset, ("status",))
            queryset = self._uuid_filter(queryset, "asset_id")
            queryset = self._uuid_filter(queryset, "network_id")
            queryset = self._date_filters(
                queryset,
                field="created_at",
                after="created_after",
                before="created_before",
            )
            queryset = self._ordering(
                queryset,
                allowed={"created_at": "created_at", "end_sequence": "end_sequence", "status": "status"},
                default="-created_at",
            )
        return queryset

    def get_serializer_class(self) -> type:
        return {
            "list": LedgerAnchorListSerializer,
            "create": LedgerAnchorCreateSerializer,
        }.get(self.action, LedgerAnchorDetailSerializer)

    def list(self, request: Request) -> Response:
        del request
        return self._paginate(self.get_queryset(), LedgerAnchorListSerializer)

    @staticmethod
    def _accepted(anchor: LedgerAnchor, job: object) -> Response:
        return Response(
            {
                "anchor": LedgerAnchorDetailSerializer(anchor).data,
                "job": {
                    "id": str(getattr(job, "id")),
                    "status": "queued",
                    "command": "blockchain_traceability.submit_anchor",
                    "correlation_id": str(getattr(job, "correlation_id")),
                },
                "queued": True,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    def create(self, request: Request) -> Response:
        serializer = LedgerAnchorCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        anchor, job = _service_call(
            lambda: self.service.request_anchor(self.tenant_id, self.actor_id, dict(serializer.validated_data))
        )
        return self._accepted(anchor, job)

    @action(detail=True, methods=("post",))
    def retry(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        anchor, job = _service_call(
            lambda: self.service.retry_anchor(
                self.tenant_id,
                _parse_uuid(pk, "id"),
                self.actor_id,
                serializer.validated_data["transition_key"],
            )
        )
        return self._accepted(anchor, job)

    @action(detail=True, methods=("post",))
    def refresh(self, request: Request, pk: str | None = None) -> Response:
        del request
        self.get_object()
        result = _service_call(
            lambda: self.service.refresh_receipt(self.tenant_id, _parse_uuid(pk, "id"), self.actor_id)
        )
        anchor = _unwrap_result(result)
        return Response(
            _operation_payload(
                LedgerAnchorDetailSerializer(anchor).data,
                code="RECEIPT_REFRESHED",
                message="The provider receipt was refreshed with authoritative evidence.",
            )
        )

    @action(detail=True, methods=("post",))
    def verify(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = ChainVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = _service_call(
            lambda: self.service.verify_anchor(
                self.tenant_id,
                _parse_uuid(pk, "id"),
                self.actor_id,
                serializer.validated_data["idempotency_key"],
            )
        )
        return Response(VerificationAttemptDetailSerializer(value).data)


class AuthenticityCredentialViewSet(GovernedTenantModelViewSet):
    queryset = AuthenticityCredential.objects.select_related("asset").all()
    service = AuthenticityService()
    http_method_names = ("get", "post", "head", "options")
    unsupported_method_permission = CREDENTIAL_READ
    action_permissions = {
        "list": CREDENTIAL_READ,
        "retrieve": CREDENTIAL_READ,
        "create": CREDENTIAL_ISSUE,
        "revoke": CREDENTIAL_REVOKE,
        "verify": CREDENTIAL_VERIFY,
    }

    def get_queryset(self) -> QuerySet[AuthenticityCredential]:
        queryset = super().get_queryset().select_related("asset")
        if self.action == "list":
            queryset = self._exact_filters(queryset, ("status", "credential_type"))
            queryset = self._uuid_filter(queryset, "asset_id")
            queryset = self._date_filters(
                queryset,
                field="expires_at",
                after="expires_after",
                before="expires_before",
            )
            queryset = self._ordering(
                queryset,
                allowed={"created_at": "created_at", "expires_at": "expires_at", "status": "status"},
                default="-created_at",
            )
        return queryset

    def get_serializer_class(self) -> type:
        return {
            "list": AuthenticityCredentialListSerializer,
            "create": AuthenticityCredentialIssueSerializer,
        }.get(self.action, AuthenticityCredentialDetailSerializer)

    def list(self, request: Request) -> Response:
        del request
        return self._paginate(self.get_queryset(), AuthenticityCredentialListSerializer)

    def create(self, request: Request) -> Response:
        serializer = AuthenticityCredentialIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        issued = _service_call(
            lambda: self.service.issue_credential(
                self.tenant_id,
                data["asset_id"],
                self.actor_id,
                data["claims"],
                data.get("expires_at"),
            )
        )
        credential = getattr(issued, "credential")
        token = getattr(issued, "token")
        return Response(
            {
                "credential": AuthenticityCredentialDetailSerializer(credential).data,
                "token": token,
                "token_recoverable": False,
            },
            status=status.HTTP_201_CREATED,
            headers={"Cache-Control": "no-store"},
        )

    @action(detail=True, methods=("post",))
    def revoke(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = CredentialRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = _service_call(
            lambda: self.service.revoke_credential(
                self.tenant_id,
                _parse_uuid(pk, "id"),
                self.actor_id,
                serializer.validated_data["reason"],
                serializer.validated_data["transition_key"],
            )
        )
        return Response(AuthenticityCredentialDetailSerializer(value).data)

    @action(detail=False, methods=("post",))
    def verify(self, request: Request) -> Response:
        serializer = AuthenticityVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        value = _service_call(
            lambda: self.service.verify_authenticity(
                self.tenant_id,
                self.actor_id,
                data["public_id"],
                data["token"],
                data["idempotency_key"],
            )
        )
        return Response(VerificationAttemptDetailSerializer(value).data)


class ComplianceEvidenceViewSet(GovernedTenantModelViewSet):
    queryset = ComplianceEvidence.objects.select_related("asset", "event", "supersedes").all()
    service = ComplianceEvidenceService()
    http_method_names = ("get", "post", "patch", "delete", "head", "options")
    unsupported_method_permission = COMPLIANCE_UPDATE
    action_permissions = {
        "list": COMPLIANCE_READ,
        "retrieve": COMPLIANCE_READ,
        "create": COMPLIANCE_CREATE,
        "partial_update": COMPLIANCE_UPDATE,
        "destroy": COMPLIANCE_DELETE,
        "finalize": COMPLIANCE_FINALIZE,
        "supersede": COMPLIANCE_FINALIZE,
        "verify": COMPLIANCE_VERIFY,
    }

    def get_queryset(self) -> QuerySet[ComplianceEvidence]:
        queryset = super().get_queryset().filter(is_deleted=False).select_related("asset", "event", "supersedes")
        if self.action == "list":
            queryset = self._exact_filters(
                queryset,
                ("evidence_type", "standard", "jurisdiction", "result", "status"),
            )
            queryset = self._uuid_filter(queryset, "asset_id")
            queryset = self._date_filters(
                queryset,
                field="observed_at",
                after="observed_after",
                before="observed_before",
            )
            queryset = self._ordering(
                queryset,
                allowed={"created_at": "created_at", "observed_at": "observed_at", "status": "status"},
                default="-observed_at",
            )
        return queryset

    def get_serializer_class(self) -> type:
        return {
            "list": ComplianceEvidenceListSerializer,
            "create": ComplianceEvidenceCreateSerializer,
            "partial_update": ComplianceEvidenceUpdateSerializer,
        }.get(self.action, ComplianceEvidenceDetailSerializer)

    def list(self, request: Request) -> Response:
        del request
        return self._paginate(self.get_queryset(), ComplianceEvidenceListSerializer)

    def create(self, request: Request) -> Response:
        serializer = ComplianceEvidenceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = _service_call(
            lambda: self.service.create_draft(self.tenant_id, self.actor_id, dict(serializer.validated_data))
        )
        return Response(ComplianceEvidenceDetailSerializer(value).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = ComplianceEvidenceUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        value = _service_call(
            lambda: self.service.update_draft(
                self.tenant_id,
                _parse_uuid(pk, "id"),
                self.actor_id,
                dict(serializer.validated_data),
            )
        )
        return Response(ComplianceEvidenceDetailSerializer(value).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        del request
        self.get_object()
        _service_call(lambda: self.service.delete_draft(self.tenant_id, _parse_uuid(pk, "id"), self.actor_id))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",))
    def finalize(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = _service_call(
            lambda: self.service.finalize(
                self.tenant_id,
                _parse_uuid(pk, "id"),
                self.actor_id,
                serializer.validated_data["transition_key"],
            )
        )
        return Response(ComplianceEvidenceDetailSerializer(value).data)

    @action(detail=True, methods=("post",))
    def supersede(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = EvidenceSupersedeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        replacement = dict(serializer.validated_data)
        transition_key = str(replacement.pop("transition_key"))
        value = _service_call(
            lambda: self.service.supersede(
                self.tenant_id,
                _parse_uuid(pk, "id"),
                self.actor_id,
                replacement,
                transition_key,
            )
        )
        return Response(ComplianceEvidenceDetailSerializer(value).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("post",))
    def verify(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = ChainVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = _service_call(
            lambda: self.service.verify_evidence(
                self.tenant_id,
                _parse_uuid(pk, "id"),
                self.actor_id,
                serializer.validated_data["idempotency_key"],
            )
        )
        return Response(VerificationAttemptDetailSerializer(value).data)


class VerificationAttemptViewSet(GovernedTenantReadOnlyViewSet):
    queryset = VerificationAttempt.objects.select_related("asset", "anchor", "credential", "compliance_evidence").all()
    service = VerificationService()
    http_method_names = ("get", "head", "options")
    unsupported_method_permission = VERIFICATION_READ
    action_permissions = {"list": VERIFICATION_READ, "retrieve": VERIFICATION_READ}

    def get_queryset(self) -> QuerySet[VerificationAttempt]:
        queryset = super().get_queryset().select_related("asset", "anchor", "credential", "compliance_evidence")
        if self.action == "list":
            queryset = self._exact_filters(queryset, ("verification_type", "outcome", "reason_code"))
            queryset = self._uuid_filter(queryset, "asset_id")
            queryset = self._date_filters(
                queryset,
                field="created_at",
                after="created_after",
                before="created_before",
            )
            queryset = self._ordering(
                queryset,
                allowed={"created_at": "created_at", "outcome": "outcome", "verification_type": "verification_type"},
                default="-created_at",
            )
        return queryset

    def get_serializer_class(self) -> type:
        return VerificationAttemptListSerializer if self.action == "list" else VerificationAttemptDetailSerializer

    def list(self, request: Request) -> Response:
        del request
        return self._paginate(self.get_queryset(), VerificationAttemptListSerializer)


class BlockchainTraceabilityHealthView(GovernedAPIViewMixin, APIView):
    authentication_classes = (SessionAuthentication401,)
    action_permissions = {"health": HEALTH_READ}

    def get_permissions(self) -> list[object]:
        from rest_framework.permissions import IsAuthenticated

        from src.core.access.permissions import RequiresAccess

        user = getattr(self.request, "user", None)
        profile = getattr(user, "profile", None)
        raw_tenant_id = getattr(profile, "tenant_id", None)
        try:
            self.request.tenant_id = UUID(str(raw_tenant_id)) if raw_tenant_id else None
        except (AttributeError, TypeError, ValueError):
            self.request.tenant_id = None
        self.required_permission = HEALTH_READ
        self.required_entitlement = HEALTH_READ
        self.quota_resource = "blockchain_traceability.api_reads"
        self.quota_cost = 1
        return [IsAuthenticated(), RequiresAccess()]

    def get(self, request: Request) -> Response:
        tenant_id = getattr(request, "tenant_id", None)
        if not isinstance(tenant_id, UUID):
            raise NotFound("Tenant health context was not found.")
        payload, response_status = module_health(tenant_id)
        return Response(payload, status=response_status)


__all__ = [name for name in globals() if name.endswith("ViewSet") or name.endswith("HealthView")]
