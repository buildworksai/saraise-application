"""Governed v2 controllers and the deprecated v1 company compatibility API."""

from __future__ import annotations

from datetime import date, datetime
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable
from uuid import UUID

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q, QuerySet
from django.http import JsonResponse
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination, OperationFailed
from src.core.api.envelope import correlation_id_for_request
from src.core.async_jobs.models import AsyncJob
from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .extensions import ExtensionContext, extension_registry, immutable_mapping
from .health import get_module_health
from .models import (
    Company,
    CompanyAccessGrant,
    ConsolidationRun,
    EliminationEntry,
    IntercompanyTransaction,
    MultiCompanyConfigurationVersion,
    TransferPricingRule,
)
from .permissions import MultiCompanyAccessMixin, PERMISSIONS
from .serializers import (
    ApplyTransferPricingSerializer,
    ApprovalDecisionSerializer,
    AsyncJobSerializer,
    CancelSerializer,
    CompanyAccessGrantCreateSerializer,
    CompanyAccessGrantSerializer,
    CompanyAccessRevokeSerializer,
    CompanyCreateSerializer,
    CompanyDetailSerializer,
    CompanyHierarchySerializer,
    CompanyListSerializer,
    CompanyUpdateSerializer,
    CompanyV1CompatibilitySerializer,
    ConfigurationDraftSerializer,
    ConfigurationImportSerializer,
    ConfigurationPreviewSerializer,
    ConfigurationRollbackSerializer,
    ConfigurationVersionSerializer,
    ConsolidatedReportSerializer,
    ConsolidationRunCreateSerializer,
    ConsolidationRunDetailSerializer,
    ConsolidationRunListSerializer,
    ConsolidationRunUpdateSerializer,
    DisputeSerializer,
    EliminationEntrySerializer,
    ExtensionCatalogEntrySerializer,
    ExpectedVersionSerializer,
    HealthSerializer,
    ManualEliminationCreateSerializer,
    ResolveDisputeSerializer,
    ReverseSerializer,
    RulePreviewSerializer,
    TransactionCreateSerializer,
    TransactionDetailSerializer,
    TransactionListSerializer,
    TransactionSubmitSerializer,
    TransactionUpdateSerializer,
    TransferPriceCalculateSerializer,
    TransferPriceResultSerializer,
    TransferPricingRuleCreateSerializer,
    TransferPricingRuleDetailSerializer,
    TransferPricingRuleListSerializer,
    TransferPricingRuleVersionSerializer,
)
from .services import (
    ALLOWED_CURRENCIES,
    CompanyAccessService,
    CompanyRegistryService,
    ConfigurationUnavailable,
    ConsolidationService,
    ConflictError,
    DomainError,
    IntercompanyTransactionService,
    MultiCompanyConfigurationService,
    NotFoundError,
    TransferPricingService,
    runtime_environment,
)
from .integrations import IntegrationError


class MultiCompanyPagination(GovernedPageNumberPagination):
    page_size = 25
    max_page_size = 100

    def get_page_size(self, request: Any) -> int:
        raw = request.query_params.get(self.page_size_query_param)
        if raw in (None, ""):
            return self.page_size
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"page_size": "Use an integer."}) from exc
        if not 1 <= value <= self.max_page_size:
            raise ValidationError({"page_size": f"Use a value from 1 to {self.max_page_size}."})
        return value


def _uuid(value: object, field: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({field: "Use a valid UUID."}) from exc


def _boolean(value: object, field: str) -> bool:
    normalized = str(value).lower()
    if normalized not in {"true", "false"}:
        raise ValidationError({field: "Use true or false."})
    return normalized == "true"


def _date(value: object, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: "Use an ISO-8601 date."}) from exc


def _datetime(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: "Use an ISO-8601 timestamp."}) from exc
    return parsed


def _ordering(value: object, allowed: set[str], default: str) -> tuple[str, ...]:
    fields = tuple(part.strip() for part in str(value or default).split(",") if part.strip())
    if not fields or any(field.lstrip("-") not in allowed for field in fields):
        raise ValidationError({"ordering": "Unsupported ordering field."})
    return fields


def _choice(value: object, field: str, choices: set[str]) -> str:
    normalized = str(value)
    if normalized not in choices:
        raise ValidationError({field: "Unsupported filter value."})
    return normalized


def _validate_query_keys(params: Any, allowed: set[str]) -> None:
    pagination = {"page", "page_size", "format"}
    unknown = set(params.keys()) - allowed - pagination
    if unknown:
        raise ValidationError({key: "Unsupported filter." for key in sorted(unknown)})


def _sort_projection(rows: Iterable[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    result = list(rows)
    for field in reversed(fields):
        descending = field.startswith("-")
        name = field.lstrip("-")
        result.sort(
            key=lambda row: (
                row.get(name, row.get("source_amount") if name == "amount" else None) is None,
                row.get(name, row.get("source_amount") if name == "amount" else None),
            ),
            reverse=descending,
        )
    return result


class TenantGovernedViewSet(GovernedAPIViewMixin, MultiCompanyAccessMixin, viewsets.GenericViewSet):
    """Common request authority and mandatory pagination helpers."""

    pagination_class = MultiCompanyPagination

    def tenant_id(self) -> UUID:
        value = getattr(self.request, "tenant_id", None)
        if not isinstance(value, UUID):
            raise PermissionDenied("Authenticated identity has no valid tenant.")
        return value

    def actor_id(self) -> str:
        value = getattr(self.request.user, "id", None)
        if value is None:
            raise PermissionDenied("Authenticated identity has no valid actor.")
        return str(value)

    def correlation_id(self) -> str:
        return correlation_id_for_request(self.request)

    def idempotency_key(self) -> str:
        value = str(self.request.headers.get("Idempotency-Key", "")).strip()
        if not value:
            raise ValidationError({"Idempotency-Key": "This header is required."})
        if len(value) > 255:
            raise ValidationError({"Idempotency-Key": "Must not exceed 255 characters."})
        return value

    def paginated(self, rows: Iterable[Any], serializer: type, **context: Any) -> Response:
        page = self.paginate_queryset(rows)
        if page is None:
            raise RuntimeError("Governed pagination is mandatory.")
        serializer_context = {"request": self.request, **context}
        return self.get_paginated_response(serializer(page, many=True, context=serializer_context).data)

    def handle_exception(self, exc: Exception) -> Response:
        return super().handle_exception(_translate_service_exception(exc))


def _translate_service_exception(exc: Exception) -> Exception:
    if isinstance(exc, NotFoundError):
        return NotFound()
    if isinstance(exc, ConfigurationUnavailable):
        return OperationFailed(error_code=exc.code, message="Required multi-company configuration is unavailable.", http_status=503)
    if isinstance(exc, ConflictError):
        return OperationFailed(error_code=exc.code, message="The operation conflicts with current resource state.", http_status=409)
    if isinstance(exc, IntegrationError):
        return OperationFailed(error_code=exc.code, message="A required financial capability is unavailable.", http_status=503)
    if isinstance(exc, DjangoValidationError):
        detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or {}
        return ValidationError(detail)
    if isinstance(exc, DjangoPermissionDenied):
        return PermissionDenied()
    if isinstance(exc, DomainError):
        return OperationFailed(error_code=exc.code, message="The requested operation could not be completed.", http_status=422)
    return exc


class GovernedServiceAPIView(GovernedAPIViewMixin, MultiCompanyAccessMixin, APIView):
    def handle_exception(self, exc: Exception) -> Response:
        return super().handle_exception(_translate_service_exception(exc))


class ExtensionCatalogAPIView(GovernedServiceAPIView):
    """Expose provider readiness without importing paid implementations in the UI."""

    permission_action = "read"
    action_permissions = {"read": "multi_company.extension:read"}

    def get(self, request: Any) -> Response:
        environment = runtime_environment()
        configuration = MultiCompanyConfigurationService.get_active(request.tenant_id, environment)
        raw_entitlements = getattr(request.user, "entitlements", ())
        if callable(raw_entitlements):
            raw_entitlements = raw_entitlements()
        context = ExtensionContext(
            tenant_id=request.tenant_id,
            actor_id=str(request.user.id),
            correlation_id=correlation_id_for_request(request),
            environment=environment,
            configuration_version=configuration.version,
            settings=immutable_mapping(configuration.settings),
            entitlements=frozenset(str(value) for value in (raw_entitlements or ())),
            permissions=frozenset(
                set(request.user.get_all_permissions())
                | {permission for permission in PERMISSIONS if request.user.has_perm(permission)}
            ),
        )
        entries = extension_registry.catalog(context)
        return Response(ExtensionCatalogEntrySerializer(entries, many=True).data)


class CompanyV2ViewSet(TenantGovernedViewSet):
    service_class = CompanyRegistryService
    action_permissions = {
        "list": "multi_company.company:read", "retrieve": "multi_company.company:read",
        "create": "multi_company.company:create", "partial_update": "multi_company.company:update",
        "destroy": "multi_company.company:delete", "deactivate": "multi_company.company:deactivate",
        "reactivate": "multi_company.company:update", "hierarchy": "multi_company.company:read",
        "subsidiaries": "multi_company.company:read", "consolidation_group": "multi_company.company:read",
    }
    action_quotas = {key: "multi_company.api_reads" for key in ("list", "retrieve", "hierarchy", "subsidiaries", "consolidation_group")}

    def get_queryset(self) -> QuerySet[Company]:
        return Company.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        params = self.request.query_params
        _validate_query_keys(params, {"search", "company_code", "is_active", "parent_company_id", "consolidation_group", "currency", "ordering"})
        filters: dict[str, Any] = {}
        for field in ("search", "company_code", "consolidation_group", "currency"):
            if params.get(field) not in (None, ""):
                filters[field] = params[field]
        if "currency" in filters:
            filters["currency"] = _choice(str(filters["currency"]).upper(), "currency", set(ALLOWED_CURRENCIES))
        if params.get("is_active") not in (None, ""):
            filters["is_active"] = _boolean(params["is_active"], "is_active")
        if params.get("parent_company_id") not in (None, ""):
            filters["parent_company_id"] = _uuid(params["parent_company_id"], "parent_company_id")
        filters["ordering"] = _ordering(params.get("ordering"), {"company_code", "company_name", "currency", "created_at", "updated_at"}, "company_code")
        rows = self.service_class().list_companies(self.tenant_id(), filters).order_by(*filters["ordering"], "id")
        return self.paginated(rows, CompanyListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        company = self.service_class().get_company(self.tenant_id(), self.kwargs["pk"])
        return Response(CompanyDetailSerializer(company, context={"request": self.request}).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = CompanyCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        idempotency_key = payload.pop("idempotency_key")
        company = self.service_class().create_company(
            self.tenant_id(), self.actor_id(), self.correlation_id(), payload, idempotency_key
        )
        return Response(CompanyDetailSerializer(company, context={"request": self.request}).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = CompanyUpdateSerializer(data=self.request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        changes = dict(serializer.validated_data)
        expected_version = changes.pop("expected_version")
        company = self.service_class().update_company(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(), expected_version, changes
        )
        return Response(CompanyDetailSerializer(company, context={"request": self.request}).data)

    def update(self, request: object, *args: object, **kwargs: object) -> Response:
        raise MethodNotAllowed("PUT")

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = ExpectedVersionSerializer(data={
            "expected_version": self.request.query_params.get("expected_version")
            or self.request.data.get("expected_version")
        })
        serializer.is_valid(raise_exception=True)
        self.service_class().delete_company(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(),
            serializer.validated_data["expected_version"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def deactivate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        serializer = ExpectedVersionSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        company = self.service_class().deactivate_company(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(),
            serializer.validated_data["expected_version"],
        )
        return Response(CompanyDetailSerializer(company, context={"request": self.request}).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        serializer = ExpectedVersionSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        company = self.service_class().reactivate_company(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(),
            serializer.validated_data["expected_version"],
        )
        return Response(CompanyDetailSerializer(company, context={"request": self.request}).data)

    @action(detail=False, methods=["get"])
    def hierarchy(self, request: object) -> Response:
        del request
        _validate_query_keys(self.request.query_params, {"root_company_id"})
        root = self.request.query_params.get("root_company_id")
        value = self.service_class().get_hierarchy(self.tenant_id(), _uuid(root, "root_company_id") if root else None)
        return Response(CompanyHierarchySerializer(value, many=isinstance(value, (list, tuple))).data)

    @action(detail=True, methods=["get"])
    def subsidiaries(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        _validate_query_keys(self.request.query_params, {"recursive"})
        recursive = _boolean(self.request.query_params.get("recursive", "false"), "recursive")
        rows = self.service_class().get_subsidiaries(self.tenant_id(), self.kwargs["pk"], recursive)
        return Response(CompanyListSerializer(rows, many=True, context={"request": self.request}).data) if recursive else self.paginated(rows, CompanyListSerializer)

    @action(detail=False, methods=["get"], url_path=r"consolidation-groups/(?P<group>[^/.]+)")
    def consolidation_group(self, request: object, group: str | None = None) -> Response:
        del request
        if not group or len(group) > 50:
            raise ValidationError({"group": "A valid consolidation group is required."})
        return self.paginated(self.service_class().get_consolidation_group(self.tenant_id(), group), CompanyListSerializer)


class CompanyAccessViewSet(TenantGovernedViewSet):
    service_class = CompanyAccessService
    action_permissions = {
        "list": "multi_company.company_access:read", "retrieve": "multi_company.company_access:read",
        "create": "multi_company.company_access:grant", "revoke": "multi_company.company_access:revoke",
    }

    def get_queryset(self) -> QuerySet[CompanyAccessGrant]:
        return CompanyAccessGrant.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        params = self.request.query_params
        _validate_query_keys(params, {"company_id", "subject_id", "role", "active_at"})
        filters: dict[str, Any] = {key: params[key] for key in ("subject_id", "role") if params.get(key)}
        if "role" in filters:
            filters["role"] = _choice(filters["role"], "role", set(CompanyAccessGrant.Role.values))
        if params.get("company_id"): filters["company_id"] = _uuid(params["company_id"], "company_id")
        if params.get("active_at"): filters["active_at"] = _datetime(params["active_at"], "active_at")
        rows = self.service_class().list_grants(
            self.tenant_id(), company_id=filters.get("company_id"), subject_id=filters.get("subject_id")
        )
        if filters.get("role"): rows = rows.filter(role=filters["role"])
        if filters.get("active_at"):
            rows = rows.filter(valid_from__lte=filters["active_at"]).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=filters["active_at"]))
        return self.paginated(rows, CompanyAccessGrantSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.get_queryset().filter(pk=self.kwargs["pk"]).first()
        if value is None: raise NotFound()
        return Response(CompanyAccessGrantSerializer(value, context={"request": self.request}).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = CompanyAccessGrantCreateSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        value = self.service_class().grant_access(self.tenant_id(), self.actor_id(), self.correlation_id(), dict(serializer.validated_data))
        return Response(CompanyAccessGrantSerializer(value, context={"request": self.request}).data, status=201)

    @action(detail=True, methods=["post"])
    def revoke(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        serializer = CompanyAccessRevokeSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        value = self.service_class().revoke_access(self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(), serializer.validated_data["reason"])
        return Response(CompanyAccessGrantSerializer(value, context={"request": self.request}).data)


class TransactionViewSet(TenantGovernedViewSet):
    service_class = IntercompanyTransactionService
    action_permissions = {
        "list": "multi_company.transaction:read", "retrieve": "multi_company.transaction:read",
        "create": "multi_company.transaction:create", "partial_update": "multi_company.transaction:update",
        "submit": "multi_company.transaction:submit", "approve": "multi_company.transaction:approve",
        "dispute": "multi_company.transaction:dispute", "resolve_dispute": "multi_company.transaction:dispute",
        "apply_transfer_pricing": "multi_company.transfer_pricing:calculate", "post": "multi_company.transaction:post",
        "retry_posting": "multi_company.transaction:post", "cancel": "multi_company.transaction:cancel",
        "reverse": "multi_company.transaction:reverse",
    }

    def get_queryset(self) -> QuerySet[IntercompanyTransaction]:
        return IntercompanyTransaction.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        params = self.request.query_params
        _validate_query_keys(params, {"search", "source_company_id", "target_company_id", "transaction_type", "status", "currency", "date_from", "date_to", "ordering"})
        filters: dict[str, Any] = {key: params[key] for key in ("search", "transaction_type", "status", "currency") if params.get(key)}
        if "transaction_type" in filters:
            filters["transaction_type"] = _choice(filters["transaction_type"], "transaction_type", set(IntercompanyTransaction.TransactionType.values))
        if "status" in filters:
            filters["status"] = _choice(filters["status"], "status", set(IntercompanyTransaction.Status.values))
        if "currency" in filters:
            filters["currency"] = _choice(str(filters["currency"]).upper(), "currency", set(ALLOWED_CURRENCIES))
        for field in ("source_company_id", "target_company_id"):
            if params.get(field): filters[field] = _uuid(params[field], field)
        for field in ("date_from", "date_to"):
            if params.get(field): filters[field] = _date(params[field], field)
        filters["ordering"] = _ordering(params.get("ordering"), {"reference", "transaction_date", "amount", "status", "created_at"}, "-transaction_date")
        rows = self.service_class().list_transactions(self.tenant_id(), filters).order_by(*filters["ordering"], "id")
        return self.paginated(rows, TransactionListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.service_class().get_transaction(self.tenant_id(), self.kwargs["pk"])
        return Response(TransactionDetailSerializer(value, context={"request": self.request}).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = TransactionCreateSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data); idempotency_key = payload.pop("idempotency_key")
        value = self.service_class().create_transaction(self.tenant_id(), self.actor_id(), self.correlation_id(), payload, idempotency_key)
        return Response(TransactionDetailSerializer(value, context={"request": self.request}).data, status=201)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = TransactionUpdateSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        changes = dict(serializer.validated_data); expected = changes.pop("expected_version")
        value = self.service_class().update_draft(self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(), expected, changes)
        return Response(TransactionDetailSerializer(value, context={"request": self.request}).data)

    def update(self, request: object, *args: object, **kwargs: object) -> Response: raise MethodNotAllowed("PUT")
    def destroy(self, request: object, *args: object, **kwargs: object) -> Response: raise MethodNotAllowed("DELETE")

    def _transition(self, serializer_type: type, method: str) -> Response:
        serializer = serializer_type(data=self.request.data); serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data); transition_key = data.pop("transition_key")
        value = getattr(self.service_class(), method)(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(),
            transition_key=transition_key, **data,
        )
        return Response(TransactionDetailSerializer(value, context={"request": self.request}).data)

    @action(detail=True, methods=["post"])
    def submit(self, request: object, pk: str | None = None) -> Response: del request, pk; return self._transition(TransactionSubmitSerializer, "submit")
    @action(detail=True, methods=["post"])
    def approve(self, request: object, pk: str | None = None) -> Response: del request, pk; return self._transition(ApprovalDecisionSerializer, "record_approval")
    @action(detail=True, methods=["post"])
    def dispute(self, request: object, pk: str | None = None) -> Response: del request, pk; return self._transition(DisputeSerializer, "dispute")
    @action(detail=True, methods=["post"], url_path="resolve-dispute")
    def resolve_dispute(self, request: object, pk: str | None = None) -> Response: del request, pk; return self._transition(ResolveDisputeSerializer, "resolve_dispute")
    @action(detail=True, methods=["post"])
    def cancel(self, request: object, pk: str | None = None) -> Response: del request, pk; return self._transition(CancelSerializer, "cancel")

    @action(detail=True, methods=["post"], url_path="apply-transfer-pricing")
    def apply_transfer_pricing(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        serializer = ApplyTransferPricingSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        value = self.service_class().apply_transfer_pricing(self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(), serializer.validated_data.get("rule_id"))
        return Response(TransactionDetailSerializer(value, context={"request": self.request}).data)

    def _enqueue(self, retry: bool) -> Response:
        serializer = TransactionSubmitSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        method = "retry_posting" if retry else "post"
        job = getattr(self.service_class(), method)(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(),
            self.idempotency_key(), serializer.validated_data["transition_key"],
        )
        return Response(AsyncJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def post(self, request: object, pk: str | None = None) -> Response: del request, pk; return self._enqueue(False)
    @action(detail=True, methods=["post"], url_path="retry-posting")
    def retry_posting(self, request: object, pk: str | None = None) -> Response: del request, pk; return self._enqueue(True)

    @action(detail=True, methods=["post"])
    def reverse(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        serializer = ReverseSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        value = self.service_class().reverse(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(),
            serializer.validated_data["reason"], self.idempotency_key(),
        )
        return Response(TransactionDetailSerializer(value, context={"request": self.request}).data, status=201)


class ReconciliationViewSet(mixins.ListModelMixin, TenantGovernedViewSet):
    service_class = IntercompanyTransactionService
    action_permissions = {"list": "multi_company.transaction:read"}

    def get_queryset(self) -> QuerySet[IntercompanyTransaction]:
        return IntercompanyTransaction.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        params = self.request.query_params
        _validate_query_keys(params, {"source_company_id", "target_company_id", "currency", "period_start", "period_end", "variance_status", "search", "ordering"})
        filters = dict(params.items())
        for field in ("source_company_id", "target_company_id"):
            if field in filters: filters[field] = _uuid(filters[field], field)
        if "period_start" in filters: filters["date_from"] = _date(filters.pop("period_start"), "period_start")
        if "period_end" in filters: filters["date_to"] = _date(filters.pop("period_end"), "period_end")
        filters["ordering"] = _ordering(filters.get("ordering"), {"reference", "transaction_date", "variance", "amount"}, "-transaction_date")
        rows = self.service_class().get_reconciliation(self.tenant_id(), filters)
        variance_status = filters.get("variance_status")
        if variance_status not in (None, "", "matched", "variance"):
            raise ValidationError({"variance_status": "Use matched or variance."})
        if variance_status == "matched": rows = [row for row in rows if row.get("variance") == 0]
        if variance_status == "variance": rows = [row for row in rows if row.get("variance") != 0]
        rows = _sort_projection(rows, filters["ordering"])
        page = self.paginate_queryset(rows)
        if page is None: raise RuntimeError("Governed pagination is mandatory.")
        return self.get_paginated_response(page)


class ConsolidationRunViewSet(TenantGovernedViewSet):
    service_class = ConsolidationService
    action_permissions = {
        "list": "multi_company.consolidation:read", "retrieve": "multi_company.consolidation:read",
        "create": "multi_company.consolidation:create", "partial_update": "multi_company.consolidation:update",
        "execute": "multi_company.consolidation:execute", "retry": "multi_company.consolidation:execute",
        "approve": "multi_company.consolidation:approve", "publish": "multi_company.consolidation:publish",
        "cancel": "multi_company.consolidation:update", "eliminations": "multi_company.elimination:read",
        "report": "multi_company.consolidation:read",
    }

    def get_queryset(self) -> QuerySet[ConsolidationRun]:
        return ConsolidationRun.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)

    def get_permissions(self) -> list[object]:
        if getattr(self, "action", "") == "eliminations":
            self.action_permissions = {
                **type(self).action_permissions,
                "eliminations": (
                    "multi_company.elimination:create"
                    if self.request.method == "POST"
                    else "multi_company.elimination:read"
                ),
            }
        return super().get_permissions()

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        params = self.request.query_params
        _validate_query_keys(params, {"consolidation_group", "status", "period_start", "period_end", "reporting_currency", "ordering"})
        filters = {key: params[key] for key in ("consolidation_group", "status", "reporting_currency") if params.get(key)}
        if "status" in filters:
            filters["status"] = _choice(filters["status"], "status", set(ConsolidationRun.Status.values))
        if "reporting_currency" in filters:
            filters["reporting_currency"] = _choice(str(filters["reporting_currency"]).upper(), "reporting_currency", set(ALLOWED_CURRENCIES))
        for field in ("period_start", "period_end"):
            if params.get(field): filters[field] = _date(params[field], field)
        filters["ordering"] = _ordering(params.get("ordering"), {"created_at", "period_start", "period_end", "status", "name"}, "-created_at")
        rows = self.service_class().list_runs(self.tenant_id(), filters)
        if filters.get("period_start"): rows = rows.filter(period_end__gte=filters["period_start"])
        if filters.get("period_end"): rows = rows.filter(period_start__lte=filters["period_end"])
        return self.paginated(rows.order_by(*filters["ordering"], "id"), ConsolidationRunListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.service_class().get_run(self.tenant_id(), self.kwargs["pk"])
        return Response(ConsolidationRunDetailSerializer(value, context={"request": self.request}).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = ConsolidationRunCreateSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        value = self.service_class().create_run(self.tenant_id(), self.actor_id(), self.correlation_id(), payload)
        return Response(ConsolidationRunDetailSerializer(value, context={"request": self.request}).data, status=201)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = ConsolidationRunUpdateSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        changes = dict(serializer.validated_data); expected = changes.pop("expected_version")
        value = self.service_class().update_draft(self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(), expected, changes)
        return Response(ConsolidationRunDetailSerializer(value, context={"request": self.request}).data)

    def update(self, request: object, *args: object, **kwargs: object) -> Response: raise MethodNotAllowed("PUT")
    def destroy(self, request: object, *args: object, **kwargs: object) -> Response: raise MethodNotAllowed("DELETE")

    def _command(self, method: str, serializer_type: type = TransactionSubmitSerializer) -> Response:
        serializer = serializer_type(data=self.request.data); serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data); transition_key = data.pop("transition_key")
        value = getattr(self.service_class(), method)(self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(), transition_key=transition_key, **data)
        return Response(ConsolidationRunDetailSerializer(value, context={"request": self.request}).data)

    @action(detail=True, methods=["post"])
    def execute(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        serializer = TransactionSubmitSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        job = self.service_class().execute(self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(), self.idempotency_key(), serializer.validated_data["transition_key"])
        return Response(AsyncJobSerializer(job).data, status=202)

    @action(detail=True, methods=["post"])
    def retry(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        serializer = TransactionSubmitSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        job = self.service_class().retry(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(),
            self.idempotency_key(), serializer.validated_data["transition_key"],
        )
        return Response(AsyncJobSerializer(job).data, status=202)
    @action(detail=True, methods=["post"])
    def approve(self, request: object, pk: str | None = None) -> Response: del request, pk; return self._command("approve")
    @action(detail=True, methods=["post"])
    def publish(self, request: object, pk: str | None = None) -> Response: del request, pk; return self._command("publish")
    @action(detail=True, methods=["post"])
    def cancel(self, request: object, pk: str | None = None) -> Response: del request, pk; return self._command("cancel", CancelSerializer)

    @action(detail=True, methods=["get", "post"])
    def eliminations(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        if self.request.method == "GET":
            self.required_permission = "multi_company.elimination:read"
            params = self.request.query_params
            _validate_query_keys(params, {"elimination_type", "source_company_id", "target_company_id", "is_auto_generated"})
            filters = dict(params.items())
            for field in ("source_company_id", "target_company_id"):
                if field in filters: filters[field] = _uuid(filters[field], field)
            if "is_auto_generated" in filters: filters["is_auto_generated"] = _boolean(filters["is_auto_generated"], "is_auto_generated")
            rows = self.service_class().list_eliminations(self.tenant_id(), self.kwargs["pk"], filters)
            return self.paginated(rows, EliminationEntrySerializer)
        serializer = ManualEliminationCreateSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        value = self.service_class().create_manual_elimination(self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(), dict(serializer.validated_data))
        return Response(EliminationEntrySerializer(value).data, status=201)

    @action(detail=True, methods=["get"])
    def report(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        value = self.service_class().get_report(self.tenant_id(), self.kwargs["pk"])
        return Response(ConsolidatedReportSerializer(value).data)


class EliminationViewSet(mixins.RetrieveModelMixin, TenantGovernedViewSet):
    action_permissions = {"retrieve": "multi_company.elimination:read"}
    def get_queryset(self) -> QuerySet[EliminationEntry]: return EliminationEntry.objects.for_tenant(self.tenant_id())
    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.get_queryset().filter(pk=self.kwargs["pk"]).first()
        if value is None: raise NotFound()
        return Response(EliminationEntrySerializer(value).data)


class TransferPricingRuleViewSet(TenantGovernedViewSet):
    service_class = TransferPricingService
    action_permissions = {
        "list": "multi_company.transfer_pricing:read", "retrieve": "multi_company.transfer_pricing:read",
        "create": "multi_company.transfer_pricing:create", "partial_update": "multi_company.transfer_pricing:update",
        "destroy": "multi_company.transfer_pricing:delete",
    }

    def get_queryset(self) -> QuerySet[TransferPricingRule]: return TransferPricingRule.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        params = self.request.query_params
        _validate_query_keys(params, {"source_company_id", "target_company_id", "product_category", "transaction_type", "pricing_method", "active_date", "ordering"})
        filters = {key: params[key] for key in ("product_category", "transaction_type", "pricing_method") if params.get(key)}
        if "transaction_type" in filters:
            filters["transaction_type"] = _choice(filters["transaction_type"], "transaction_type", set(IntercompanyTransaction.TransactionType.values))
        if "pricing_method" in filters:
            filters["pricing_method"] = _choice(filters["pricing_method"], "pricing_method", set(TransferPricingRule.PricingMethod.values))
        for field in ("source_company_id", "target_company_id"):
            if params.get(field): filters[field] = _uuid(params[field], field)
        if params.get("active_date"): filters["active_date"] = _date(params["active_date"], "active_date")
        filters["ordering"] = _ordering(params.get("ordering"), {"name", "effective_from", "rule_version", "created_at"}, "-effective_from")
        rows = self.service_class().list_rules(self.tenant_id(), filters)
        if filters.get("active_date"):
            rows = rows.filter(effective_from__lte=filters["active_date"]).filter(
                Q(effective_to__isnull=True) | Q(effective_to__gte=filters["active_date"])
            )
        return self.paginated(rows.order_by(*filters["ordering"], "id"), TransferPricingRuleListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.service_class().get_rule(self.tenant_id(), self.kwargs["pk"])
        return Response(TransferPricingRuleDetailSerializer(value, context={"request": self.request}).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = TransferPricingRuleCreateSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        value = self.service_class().create_rule(self.tenant_id(), self.actor_id(), self.correlation_id(), payload)
        return Response(TransferPricingRuleDetailSerializer(value, context={"request": self.request}).data, status=201)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = TransferPricingRuleVersionSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        changes = dict(serializer.validated_data); expected = changes.pop("expected_version")
        value = self.service_class().create_rule_version(self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(), expected, changes)
        return Response(TransferPricingRuleDetailSerializer(value, context={"request": self.request}).data)

    def update(self, request: object, *args: object, **kwargs: object) -> Response: raise MethodNotAllowed("PUT")
    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = ExpectedVersionSerializer(data={
            "expected_version": self.request.query_params.get("expected_version")
            or self.request.data.get("expected_version")
        })
        serializer.is_valid(raise_exception=True)
        self.service_class().delete_unused_draft_rule(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(),
            serializer.validated_data["expected_version"],
        )
        return Response(status=204)


class TransferPriceCalculateAPIView(GovernedServiceAPIView):
    permission_action = "calculate"
    action_permissions = {"calculate": "multi_company.transfer_pricing:calculate"}
    service_class = TransferPricingService
    def post(self, request: Any) -> Response:
        serializer = TransferPriceCalculateSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        if not payload.get("rule_id"):
            rule = self.service_class().resolve_rule(
                request.tenant_id, payload["source_company_id"], payload["target_company_id"],
                payload["product_category"], payload["transaction_type"], payload["effective_date"],
            )
            payload["rule_id"] = rule.id
        value = self.service_class().calculate_price(request.tenant_id, payload)
        return Response(TransferPriceResultSerializer(value).data)


class TransferPricePreviewAPIView(TransferPriceCalculateAPIView):
    def post(self, request: Any) -> Response:
        serializer = RulePreviewSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data); scenarios = data.pop("scenarios")
        if not data.get("rule_id"):
            rule = self.service_class().resolve_rule(
                request.tenant_id, data["source_company_id"], data["target_company_id"],
                data["product_category"], data["transaction_type"], data["effective_date"],
            )
            data["rule_id"] = rule.id
        value = self.service_class().preview_rule(request.tenant_id, data, scenarios)
        return Response(TransferPriceResultSerializer(value, many=True).data)


class ConfigurationVersionViewSet(TenantGovernedViewSet):
    service_class = MultiCompanyConfigurationService
    action_permissions = {
        "list": "multi_company.configuration:read", "retrieve": "multi_company.configuration:read",
        "create": "multi_company.configuration:write", "partial_update": "multi_company.configuration:write",
        "validate_draft": "multi_company.configuration:write", "preview": "multi_company.configuration:write",
        "activate": "multi_company.configuration:activate", "rollback": "multi_company.configuration:rollback",
    }

    def get_queryset(self) -> QuerySet[MultiCompanyConfigurationVersion]: return MultiCompanyConfigurationVersion.objects.for_tenant(self.tenant_id())

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        _validate_query_keys(self.request.query_params, {"environment"})
        environment = self.request.query_params.get("environment")
        if not environment: raise ValidationError({"environment": "This filter is required."})
        environment = _choice(environment, "environment", set(MultiCompanyConfigurationVersion.Environment.values))
        return self.paginated(self.service_class().list_versions(self.tenant_id(), environment), ConfigurationVersionSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.get_queryset().filter(pk=self.kwargs["pk"]).first()
        if value is None: raise NotFound()
        return Response(ConfigurationVersionSerializer(value, context={"request": self.request}).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = ConfigurationDraftSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        value = self.service_class().create_draft(
            self.tenant_id(), self.actor_id(), self.correlation_id(), data["environment"],
            data["settings"], data["change_summary"], data["schema_version"],
        )
        return Response(ConfigurationVersionSerializer(value, context={"request": self.request}).data, status=201)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = ConfigurationDraftSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if data.pop("expected_version", None) is None: raise ValidationError({"expected_version": "This field is required."})
        value = self.service_class().update_draft(
            self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id(),
            data["settings"], data.get("change_summary"),
        )
        return Response(ConfigurationVersionSerializer(value, context={"request": self.request}).data)

    def update(self, request: object, *args: object, **kwargs: object) -> Response: raise MethodNotAllowed("PUT")

    @action(detail=True, methods=["post"], url_path="validate")
    def validate_draft(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        result = self.service_class().validate_draft(self.tenant_id(), self.kwargs["pk"])
        return Response(asdict(result) if is_dataclass(result) else result)

    @action(detail=True, methods=["post"])
    def preview(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        value = self.service_class().preview_impact(self.tenant_id(), self.kwargs["pk"])
        return Response(ConfigurationPreviewSerializer(value).data)

    @action(detail=True, methods=["post"])
    def activate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        value = self.service_class().activate(self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id())
        return Response(ConfigurationVersionSerializer(value, context={"request": self.request}).data)

    @action(detail=True, methods=["post"])
    def rollback(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        value = self.service_class().rollback(self.tenant_id(), self.kwargs["pk"], self.actor_id(), self.correlation_id())
        return Response(ConfigurationVersionSerializer(value, context={"request": self.request}).data, status=201)


class ConfigurationExportAPIView(GovernedServiceAPIView):
    permission_action = "export"
    action_permissions = {"export": "multi_company.configuration:export"}
    def get(self, request: Any) -> Response:
        _validate_query_keys(request.query_params, {"environment", "version"})
        environment = request.query_params.get("environment")
        if not environment: raise ValidationError({"environment": "This field is required."})
        environment = _choice(environment, "environment", set(MultiCompanyConfigurationVersion.Environment.values))
        version = request.query_params.get("version")
        if version is not None:
            try: version = int(version)
            except (TypeError, ValueError) as exc: raise ValidationError({"version": "Use an integer."}) from exc
        document = MultiCompanyConfigurationService().export_document(
            request.tenant_id, environment, version, str(request.user.id), correlation_id_for_request(request)
        )
        return Response(document)


class ConfigurationImportAPIView(GovernedServiceAPIView):
    permission_action = "import"
    action_permissions = {"import": "multi_company.configuration:import"}
    def post(self, request: Any) -> Response:
        serializer = ConfigurationImportSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        value = MultiCompanyConfigurationService().import_document(
            request.tenant_id, str(request.user.id), correlation_id_for_request(request),
            serializer.validated_data["document"],
        )
        return Response(ConfigurationVersionSerializer(value, context={"request": request}).data, status=201)


class AsyncJobViewSet(mixins.RetrieveModelMixin, TenantGovernedViewSet):
    # Command-specific authorization is additionally checked by the service/policy
    # that created the job. Read access itself fails closed at transaction:read.
    action_permissions = {"retrieve": "multi_company.transaction:read"}
    COMMAND_PERMISSIONS = {
        "multi_company.transaction.post": "multi_company.transaction:post",
        "multi_company.transaction.reverse": "multi_company.transaction:reverse",
        "multi_company.consolidation.execute": "multi_company.consolidation:execute",
        "multi_company.transaction.expire_drafts": "multi_company.transaction:update",
    }
    def get_permissions(self) -> list[object]:
        raw_tenant = get_user_tenant_id(getattr(self.request, "user", None))
        try:
            tenant_id = UUID(str(raw_tenant))
            job_id = UUID(str(self.kwargs.get("pk")))
        except (TypeError, ValueError, AttributeError):
            pass
        else:
            command = AsyncJob.objects.for_tenant(tenant_id).filter(pk=job_id, command__startswith="multi_company.").values_list("command", flat=True).first()
            if command:
                self.action_permissions = {**type(self).action_permissions, "retrieve": self.COMMAND_PERMISSIONS.get(command)}
        return super().get_permissions()
    def get_queryset(self) -> QuerySet[AsyncJob]: return AsyncJob.objects.for_tenant(self.tenant_id()).filter(command__startswith="multi_company.")
    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.get_queryset().filter(pk=self.kwargs["pk"]).first()
        if value is None: raise NotFound()
        return Response(AsyncJobSerializer(value).data)


class ModuleHealthAPIView(GovernedServiceAPIView):
    permission_action = "health"
    action_permissions = {"health": "multi_company.health:read"}
    def get(self, request: Any) -> Response:
        result = get_module_health(request.tenant_id)
        serializer = HealthSerializer(result)
        return Response(serializer.data, status=503 if result["status"] == "unhealthy" else 200)


class DeprecatedV1HeadersMixin:
    """Advertise the migration without changing the legacy JSON shape."""
    sunset = "Wed, 31 Dec 2026 23:59:59 GMT"
    def finalize_response(self, request: Any, response: Any, *args: Any, **kwargs: Any) -> Any:
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Deprecation"] = "true"
        response["Sunset"] = self.sunset
        response["Link"] = '</api/v2/multi-company/>; rel="successor-version"'
        return response


class CompanyViewSet(DeprecatedV1HeadersMixin, viewsets.ModelViewSet):
    """Deprecated v1 company surface backed by the same domain service."""
    serializer_class = CompanyV1CompatibilitySerializer
    permission_classes = (IsAuthenticated,)
    authentication_classes = (RelaxedCsrfSessionAuthentication,)
    http_method_names = ("get", "post", "patch", "delete", "head", "options")

    def _tenant_id(self) -> UUID:
        raw = get_user_tenant_id(self.request.user)
        try: return UUID(str(raw))
        except (TypeError, ValueError, AttributeError) as exc: raise PermissionDenied("User must belong to a tenant.") from exc

    def get_queryset(self) -> QuerySet[Company]:
        return Company.objects.for_tenant(self._tenant_id()).filter(is_deleted=False).order_by("company_code")

    def perform_create(self, serializer: Any) -> None:
        data = dict(serializer.validated_data)
        actor = str(self.request.user.id)
        correlation = str(getattr(self.request, "correlation_id", "legacy-v1"))
        company_code = str(data.get("company_code", "")).strip().upper()
        value = CompanyRegistryService().create_company(
            self._tenant_id(),
            actor,
            correlation,
            data,
            f"v1:{company_code}",
        )
        serializer.instance = value

    def perform_update(self, serializer: Any) -> None:
        value = CompanyRegistryService().update_company(self._tenant_id(), serializer.instance.pk, str(self.request.user.id), str(getattr(self.request, "correlation_id", "legacy-v1")), serializer.instance.version, dict(serializer.validated_data))
        serializer.instance = value

    def perform_destroy(self, instance: Company) -> None:
        CompanyRegistryService().delete_company(self._tenant_id(), instance.pk, str(self.request.user.id), str(getattr(self.request, "correlation_id", "legacy-v1")), instance.version)


def health_check(request: Any) -> JsonResponse:
    """Legacy import compatibility; health is only routed through governed v2."""
    del request
    return JsonResponse({"status": "unavailable", "code": "USE_GOVERNED_V2_HEALTH"}, status=503)


__all__ = [name for name in globals() if name.endswith(("APIView", "ViewSet"))]
