"""Governed, tenant-isolated CRM API v2 controllers."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, MethodNotAllowed, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from src.core.access import RequiresAccess
from src.core.api import GovernedAPIViewMixin
from src.core.api.results import OperationFailed
from src.core.async_jobs.models import AsyncJob
from src.core.views.tenant_scoped import TenantScopedModelViewSet

from .configuration import DEFAULT_CRM_CONFIGURATION, effective_configuration
from .jobs import enqueue_lead_scoring_job
from .models import (
    Account,
    AccountType,
    Activity,
    ActivityType,
    Contact,
    CRMConfiguration,
    Lead,
    LeadStatus,
    Opportunity,
    OpportunityStage,
    OpportunityStatus,
    RelatedToType,
)
from .pagination import CRMResultsSetPagination
from .permissions import (
    ACCOUNT_ACTION_PERMISSIONS,
    ACTIVITY_ACTION_PERMISSIONS,
    CONFIGURATION_ACTION_PERMISSIONS,
    CONTACT_ACTION_PERMISSIONS,
    FORECAST_ACTION_PERMISSIONS,
    LEAD_ACTION_PERMISSIONS,
    OPPORTUNITY_ACTION_PERMISSIONS,
    permission_for_job_command,
)
from .serializers import (
    AccountCreateSerializer,
    AccountHierarchySerializer,
    AccountReadSerializer,
    AccountUpdateSerializer,
    ActivityCompleteSerializer,
    ActivityCreateSerializer,
    ActivityReadSerializer,
    ActivityUpdateSerializer,
    AsyncJobReadSerializer,
    AsyncOperationSerializer,
    CloseLostSerializer,
    CloseWonSerializer,
    ContactCreateSerializer,
    ContactReadSerializer,
    ContactUpdateSerializer,
    CRMConfigurationImportSerializer,
    CRMConfigurationRollbackSerializer,
    CRMConfigurationWriteSerializer,
    DuplicateAccountQuerySerializer,
    ForecastQuerySerializer,
    ForecastSerializer,
    LeadConvertSerializer,
    LeadCreateSerializer,
    LeadReadSerializer,
    LeadScoreRequestSerializer,
    LeadTransitionSerializer,
    LeadUpdateSerializer,
    OpportunityCreateSerializer,
    OpportunityReadSerializer,
    OpportunityStageTransitionSerializer,
    OpportunityUpdateSerializer,
    RevenuePredictionRequestSerializer,
    RevenuePredictionSerializer,
    StageForecastSerializer,
    WinRateSerializer,
)
from .services import (
    AccountService,
    ActivityService,
    ContactService,
    CRMConfigurationService,
    CRMIdempotencyService,
    CRMServiceError,
    ForecastingService,
    LeadService,
    OpportunityService,
)


class CsrfSessionAuthentication(SessionAuthentication):
    """Normal session authentication with CSRF and a real 401 challenge."""

    def authenticate_header(self, request: Request) -> str:
        del request
        return "Session"


class CRMIdempotentReplay(APIException):
    """Short-circuit a duplicate mutation with its original response."""

    default_code = "IDEMPOTENT_REPLAY"

    def __init__(self, response_body: object, response_status: int) -> None:
        self.response_body = response_body
        self.status_code = response_status
        super().__init__("The original response was replayed.")


def _actor(request: Request) -> str:
    value = getattr(request.user, "id", getattr(request.user, "pk", None))
    if value is None:
        raise PermissionDenied("Authenticated actor identifier is required.")
    return str(value)


def _parse_uuid(value: object, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({field: "Must be a valid UUID."}) from exc


def _parse_int(value: str | None, field: str, *, minimum: int, maximum: int) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: "Must be an integer."}) from exc
    if not minimum <= parsed <= maximum:
        raise ValidationError({field: f"Must be from {minimum} to {maximum}."})
    return parsed


def _parse_bool(value: str | None, field: str) -> bool | None:
    if value is None:
        return None
    if value.lower() in {"true", "1"}:
        return True
    if value.lower() in {"false", "0"}:
        return False
    raise ValidationError({field: "Must be true or false."})


def _parse_date(value: str | None, field: str) -> date | None:
    if value is None:
        return None
    parsed = parse_date(value)
    if parsed is None:
        raise ValidationError({field: "Must be an ISO-8601 date."})
    return parsed


class GovernedCRMViewSet(GovernedAPIViewMixin, TenantScopedModelViewSet):
    """Deny-default v2 profile shared by all mutable CRM resources."""

    authentication_classes = (CsrfSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    pagination_class = CRMResultsSetPagination
    required_entitlement = "crm"
    permission_map: Mapping[str, str] = {}
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def dispatch(self, *args: Any, **kwargs: Any) -> Response:
        with transaction.atomic():
            return super().dispatch(*args, **kwargs)

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        mutating = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        if not mutating or self.action == "preview":
            return
        key = request.headers.get("Idempotency-Key", "")
        if not key:
            raise ValidationError({"Idempotency-Key": "Required for every mutating CRM request."})
        try:
            record = CRMIdempotencyService.begin(
                self.tenant_id(),
                key=key,
                method=request.method,
                path=request.get_full_path(),
                payload=request.data,
            )
        except CRMServiceError as exc:
            error = APIException(detail=exc.public_message, code=exc.error_code)
            error.status_code = exc.http_status
            raise error from exc
        if record.completed:
            raise CRMIdempotentReplay(
                record.response_body,
                record.response_status or status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        setattr(request, "crm_idempotency_record", record)

    def finalize_response(self, request: Request, response: Response, *args: Any, **kwargs: Any) -> Response:
        finalized = super().finalize_response(request, response, *args, **kwargs)
        record = getattr(request, "crm_idempotency_record", None)
        tenant_id = getattr(request, "tenant_id", None)
        if record is not None and tenant_id is not None:
            CRMIdempotencyService.complete(
                tenant_id,
                record_id=record.id,
                response_status=finalized.status_code,
                response_body=getattr(finalized, "data", None),
            )
        return finalized

    def check_permissions(self, request: Request) -> None:
        method = request.method or ""
        if method.lower() not in self.http_method_names:
            raise MethodNotAllowed(method)
        tenant_id = self._get_tenant_id()
        if tenant_id is not None:
            request.tenant_id = tenant_id  # type: ignore[attr-defined]
        try:
            self.required_permission = self.permission_map[getattr(self, "action", "")]
        except KeyError:
            self.required_permission = ""
        self.quota_resource = f"crm.api.{getattr(self, 'action', 'unknown')}"
        self.quota_cost = int(
            effective_configuration(tenant_id)["api"]["quota_cost"]
            if tenant_id is not None
            else DEFAULT_CRM_CONFIGURATION["api"]["quota_cost"]
        )
        super().check_permissions(request)

    def tenant_id(self) -> UUID:
        return self._require_tenant_id()

    def correlation_id(self) -> str:
        return str(getattr(self.request, "correlation_id", "") or "") or None  # type: ignore[return-value]

    def _validate_query(self, allowed: set[str]) -> None:
        common = {"page", "page_size", "format"}
        unknown = set(self.request.query_params) - allowed - common
        if unknown:
            raise ValidationError({field: "Unknown query parameter." for field in sorted(unknown)})

    def _ordering(self, queryset: QuerySet[Any], allowed: set[str], default: str) -> QuerySet[Any]:
        ordering = self.request.query_params.get("ordering", default)
        fields = ordering.split(",")
        if any(not field or field.lstrip("-") not in allowed for field in fields):
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return queryset.order_by(*fields, "-id")

    def _expected_version(self, values: dict[str, Any], instance: Any) -> int:
        body_version = values.pop("version", None)
        header = self.request.headers.get("If-Match")
        header_version: int | None = None
        if header:
            normalized = header.strip().removeprefix("W/").strip('"')
            try:
                header_version = int(normalized)
            except ValueError as exc:
                raise ValidationError({"If-Match": "Must contain an integer entity version."}) from exc
        if body_version is not None and header_version is not None and body_version != header_version:
            raise ValidationError({"version": "Body version does not match If-Match."})
        expected = header_version if header_version is not None else body_version
        if expected is None and self.request.path.startswith("/api/v1/"):
            expected = instance.version
        if expected is None:
            raise ValidationError({"version": "Version or If-Match is required."})
        return int(expected)

    def _require_additional_permission(self, permission: str) -> None:
        if not RequiresAccess(permission).has_permission(self.request, self):
            raise PermissionDenied("The additional action permission is required.")

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, CRMIdempotentReplay):
            response = Response(exc.response_body, status=exc.status_code)
            response["Idempotent-Replayed"] = "true"
            return response
        if isinstance(exc, CRMServiceError):
            exc = OperationFailed(
                error_code=exc.error_code, message=exc.public_message, detail=exc.detail, http_status=exc.http_status
            )
        elif isinstance(exc, DjangoValidationError):
            detail = getattr(exc, "message_dict", None) or {
                "non_field_errors": getattr(exc, "messages", ["Validation failed."])
            }
            exc = OperationFailed(
                error_code="CRM_VALIDATION_ERROR",
                message="CRM validation failed.",
                detail=detail,
                http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        elif isinstance(exc, IntegrityError):
            exc = OperationFailed(
                error_code="CONFLICT",
                message="The requested change conflicts with existing CRM data.",
                http_status=status.HTTP_409_CONFLICT,
            )
        elif isinstance(exc, ObjectDoesNotExist):
            exc = NotFound()
        return super().handle_exception(exc)


class LeadViewSet(GovernedCRMViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadReadSerializer
    permission_map = LEAD_ACTION_PERMISSIONS

    def get_queryset(self) -> QuerySet[Lead]:
        queryset = super().get_queryset().filter(is_deleted=False)
        if not hasattr(self, "request"):
            return queryset
        self._validate_query({"status", "owner_id", "score_min", "score_max", "source", "search", "ordering"})
        params = self.request.query_params
        if params.get("status"):
            if params["status"] not in LeadStatus.values:
                raise ValidationError({"status": "Unsupported lead status."})
            queryset = queryset.filter(status=params["status"])
        if params.get("owner_id"):
            queryset = queryset.filter(owner_id=_parse_uuid(params["owner_id"], "owner_id"))
        score_configuration = effective_configuration(self.tenant_id())["lead"]
        score_minimum = int(score_configuration["score_min"])
        score_maximum = int(score_configuration["score_max"])
        minimum = _parse_int(
            params.get("score_min"),
            "score_min",
            minimum=score_minimum,
            maximum=score_maximum,
        )
        maximum = _parse_int(
            params.get("score_max"),
            "score_max",
            minimum=score_minimum,
            maximum=score_maximum,
        )
        if minimum is not None:
            queryset = queryset.filter(score__gte=minimum)
        if maximum is not None:
            queryset = queryset.filter(score__lte=maximum)
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValidationError({"score_min": "Cannot exceed score_max."})
        if params.get("source"):
            queryset = queryset.filter(source=params["source"])
        if params.get("search"):
            search = params["search"].strip()
            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(company__icontains=search)
                | Q(email__icontains=search)
            )
        return self._ordering(
            queryset, {"created_at", "updated_at", "last_name", "company", "score", "status"}, "-created_at"
        )

    def get_serializer_class(self) -> type[Any]:
        return {"create": LeadCreateSerializer, "partial_update": LeadUpdateSerializer}.get(
            self.action, LeadReadSerializer
        )

    def create(self, request: Request) -> Response:
        serializer = LeadCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lead = LeadService.create_lead(
            self.tenant_id(),
            data=serializer.validated_data,
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(LeadReadSerializer(lead).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        serializer = LeadUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        expected = self._expected_version(values, instance)
        lead = LeadService.update_lead(
            self.tenant_id(), lead_id=instance.id, data=values, expected_version=expected, actor_id=_actor(request)
        )
        return Response(LeadReadSerializer(lead).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        expected = self._expected_version({}, instance)
        LeadService.delete_lead(
            self.tenant_id(), lead_id=instance.id, expected_version=expected, actor_id=_actor(request)
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def transition(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        serializer = LeadTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        lead = LeadService.transition_lead(
            self.tenant_id(),
            lead_id=instance.id,
            command=values["command"],
            transition_key=values["transition_key"],
            context=values.get("context", {}),
            actor_id=_actor(request),
            expected_version=values["expected_version"],
        )
        return Response(LeadReadSerializer(lead).data)

    @action(detail=True, methods=["post"])
    def convert(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        payload = dict(request.data)
        if request.path.startswith("/api/v1/"):
            payload = LeadService.prepare_legacy_conversion(self.tenant_id(), instance, payload)
        serializer = LeadConvertSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        if request.path.startswith("/api/v1/"):
            opportunity = LeadService.convert_legacy(
                self.tenant_id(),
                lead_id=instance.id,
                validated_data=values,
                actor_id=_actor(request),
            )
            return Response(
                OpportunityReadSerializer(opportunity).data,
                status=status.HTTP_201_CREATED,
            )
        expected = values.pop("expected_version")
        key = values.pop("transition_key")
        conversion = LeadService.convert_lead(
            self.tenant_id(),
            lead_id=instance.id,
            data=values,
            expected_version=expected,
            transition_key=key,
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(
            {
                "lead": LeadReadSerializer(conversion.lead).data,
                "account": AccountReadSerializer(conversion.account).data,
                "contact": ContactReadSerializer(conversion.contact).data if conversion.contact else None,
                "opportunity": OpportunityReadSerializer(conversion.opportunity).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def score(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        serializer = LeadScoreRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if values.get("async_execution"):
            job = enqueue_lead_scoring_job(
                self.tenant_id(),
                lead_id=instance.id,
                idempotency_key=values["idempotency_key"],
                actor_id=_actor(request),
                correlation_id=self.correlation_id(),
            )
            return Response(AsyncOperationSerializer(job).data, status=status.HTTP_202_ACCEPTED)
        result = LeadService.score_lead(
            self.tenant_id(), lead_id=instance.id, actor_id=_actor(request), correlation_id=self.correlation_id()
        )
        lead = result.unwrap()
        return Response(LeadReadSerializer(lead).data)


class AccountViewSet(GovernedCRMViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountReadSerializer
    permission_map = ACCOUNT_ACTION_PERMISSIONS

    def get_queryset(self) -> QuerySet[Account]:
        queryset = super().get_queryset().filter(is_deleted=False)
        if not hasattr(self, "request"):
            return queryset
        self._validate_query(
            {"account_type", "owner_id", "parent_account_id", "industry", "search", "ordering", "name", "website"}
            if self.action == "duplicates"
            else {"account_type", "owner_id", "parent_account_id", "industry", "search", "ordering"}
        )
        params = self.request.query_params
        if params.get("account_type"):
            if params["account_type"] not in AccountType.values:
                raise ValidationError({"account_type": "Unsupported account type."})
            queryset = queryset.filter(account_type=params["account_type"])
        for field in ("owner_id", "parent_account_id"):
            if params.get(field):
                queryset = queryset.filter(**{field: _parse_uuid(params[field], field)})
        if params.get("industry"):
            queryset = queryset.filter(industry=params["industry"])
        if params.get("search"):
            search = params["search"].strip()
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(website__icontains=search) | Q(industry__icontains=search)
            )
        return self._ordering(
            queryset, {"created_at", "updated_at", "name", "annual_revenue", "employees", "account_type"}, "name"
        )

    def get_serializer_class(self) -> type[Any]:
        return {"create": AccountCreateSerializer, "partial_update": AccountUpdateSerializer}.get(
            self.action, AccountReadSerializer
        )

    def create(self, request: Request) -> Response:
        serializer = AccountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = AccountService.create_account(
            self.tenant_id(),
            data=serializer.validated_data,
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(AccountReadSerializer(account).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        serializer = AccountUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        expected = self._expected_version(values, instance)
        account = AccountService.update_account(
            self.tenant_id(), account_id=instance.id, data=values, expected_version=expected, actor_id=_actor(request)
        )
        return Response(AccountReadSerializer(account).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        AccountService.delete_account(
            self.tenant_id(),
            account_id=instance.id,
            expected_version=self._expected_version({}, instance),
            actor_id=_actor(request),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def hierarchy(self, request: Request, pk: str | None = None) -> Response:
        del request
        instance = self.get_object()
        tree = AccountService.get_hierarchy(self.tenant_id(), account_id=instance.id)
        return Response(AccountHierarchySerializer(tree).data)

    @action(detail=False, methods=["get"])
    def duplicates(self, request: Request) -> Response:
        serializer = DuplicateAccountQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        result = AccountService.find_duplicates(self.tenant_id(), **serializer.validated_data)
        return Response(
            {
                "local_matches": AccountReadSerializer(result.local_matches, many=True).data,
                "external_matches": result.external_matches,
                "enrichment_status": result.enrichment_status,
            }
        )


class ContactViewSet(GovernedCRMViewSet):
    queryset = Contact.objects.all()
    serializer_class = ContactReadSerializer
    permission_map = CONTACT_ACTION_PERMISSIONS

    def get_queryset(self) -> QuerySet[Contact]:
        queryset = super().get_queryset().filter(is_deleted=False)
        if not hasattr(self, "request"):
            return queryset
        self._validate_query({"account_id", "owner_id", "engagement_min", "search", "ordering"})
        params = self.request.query_params
        for field in ("account_id", "owner_id"):
            if params.get(field):
                queryset = queryset.filter(**{field: _parse_uuid(params[field], field)})
        engagement_configuration = effective_configuration(self.tenant_id())["contact"]
        minimum = _parse_int(
            params.get("engagement_min"),
            "engagement_min",
            minimum=int(engagement_configuration["engagement_score_min"]),
            maximum=int(engagement_configuration["engagement_score_max"]),
        )
        if minimum is not None:
            queryset = queryset.filter(engagement_score__gte=minimum)
        if params.get("search"):
            search = params["search"].strip()
            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
                | Q(department__icontains=search)
            )
        return self._ordering(
            queryset, {"created_at", "updated_at", "last_name", "engagement_score", "last_contacted_at"}, "last_name"
        )

    def get_serializer_class(self) -> type[Any]:
        return {"create": ContactCreateSerializer, "partial_update": ContactUpdateSerializer}.get(
            self.action, ContactReadSerializer
        )

    def create(self, request: Request) -> Response:
        serializer = ContactCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        override = bool(values.pop("domain_override_reason", ""))
        if override:
            self._require_additional_permission("crm.contact:override_domain")
        contact = ContactService.create_contact(
            self.tenant_id(),
            data=values,
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
            allow_domain_override=override,
        )
        return Response(ContactReadSerializer(contact).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        serializer = ContactUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        override = bool(values.pop("domain_override_reason", ""))
        if override:
            self._require_additional_permission("crm.contact:override_domain")
        expected = self._expected_version(values, instance)
        contact = ContactService.update_contact(
            self.tenant_id(),
            contact_id=instance.id,
            data=values,
            expected_version=expected,
            actor_id=_actor(request),
            allow_domain_override=override,
        )
        return Response(ContactReadSerializer(contact).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        ContactService.delete_contact(
            self.tenant_id(),
            contact_id=instance.id,
            expected_version=self._expected_version({}, instance),
            actor_id=_actor(request),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class OpportunityViewSet(GovernedCRMViewSet):
    queryset = Opportunity.objects.all()
    serializer_class = OpportunityReadSerializer
    permission_map = OPPORTUNITY_ACTION_PERMISSIONS

    def get_queryset(self) -> QuerySet[Opportunity]:
        queryset = super().get_queryset().filter(is_deleted=False)
        if not hasattr(self, "request"):
            return queryset
        self._validate_query(
            {"status", "stage", "owner_id", "account_id", "close_date_from", "close_date_to", "search", "ordering"}
        )
        params = self.request.query_params
        if params.get("status"):
            if params["status"] not in OpportunityStatus.values:
                raise ValidationError({"status": "Unsupported opportunity status."})
            queryset = queryset.filter(status=params["status"])
        if params.get("stage"):
            if params["stage"] not in OpportunityStage.values:
                raise ValidationError({"stage": "Unsupported opportunity stage."})
            queryset = queryset.filter(stage=params["stage"])
        for field in ("owner_id", "account_id"):
            if params.get(field):
                queryset = queryset.filter(**{field: _parse_uuid(params[field], field)})
        start = _parse_date(params.get("close_date_from"), "close_date_from")
        end = _parse_date(params.get("close_date_to"), "close_date_to")
        if start:
            queryset = queryset.filter(close_date__gte=start)
        if end:
            queryset = queryset.filter(close_date__lte=end)
        if start and end and start > end:
            raise ValidationError({"close_date_from": "Cannot be after close_date_to."})
        if params.get("search"):
            search = params["search"].strip()
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        return self._ordering(
            queryset,
            {"created_at", "updated_at", "name", "amount", "probability", "stage", "close_date", "last_activity_at"},
            "close_date",
        )

    def get_serializer_class(self) -> type[Any]:
        return {"create": OpportunityCreateSerializer, "partial_update": OpportunityUpdateSerializer}.get(
            self.action, OpportunityReadSerializer
        )

    def create(self, request: Request) -> Response:
        serializer = OpportunityCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        opportunity = OpportunityService.create_opportunity(
            self.tenant_id(),
            data=serializer.validated_data,
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(OpportunityReadSerializer(opportunity).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        serializer = OpportunityUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        expected = self._expected_version(values, instance)
        opportunity = OpportunityService.update_opportunity(
            self.tenant_id(),
            opportunity_id=instance.id,
            data=values,
            expected_version=expected,
            actor_id=_actor(request),
        )
        return Response(OpportunityReadSerializer(opportunity).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        OpportunityService.delete_opportunity(
            self.tenant_id(),
            opportunity_id=instance.id,
            expected_version=self._expected_version({}, instance),
            actor_id=_actor(request),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def transition(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        serializer = OpportunityStageTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        backward = str(values["command"]).startswith("reopen_to_")
        if backward:
            self._require_additional_permission("crm.opportunity:reopen_stage")
        opportunity = OpportunityService.transition_stage(
            self.tenant_id(),
            opportunity_id=instance.id,
            command=values["command"],
            transition_key=values["transition_key"],
            expected_version=values["expected_version"],
            actor_id=_actor(request),
            reason=values.get("reason"),
            allow_backward=backward,
        )
        return Response(OpportunityReadSerializer(opportunity).data)

    @action(detail=True, methods=["post"], url_path="close-won")
    def close_won(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        payload = dict(request.data)
        if request.path.startswith("/api/v1/"):
            payload.setdefault("transition_key", f"legacy-close-won:{instance.id}")
            payload.setdefault("expected_version", instance.version)
            payload.setdefault("confirmed", True)
        serializer = CloseWonSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        values.pop("confirmed")
        opportunity = OpportunityService.close_won(
            self.tenant_id(),
            opportunity_id=instance.id,
            actor_id=_actor(request),
            **values,
        )
        return Response(OpportunityReadSerializer(opportunity).data)

    @action(detail=True, methods=["post"], url_path="close-lost")
    def close_lost(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        payload = dict(request.data)
        if request.path.startswith("/api/v1/"):
            payload.setdefault("transition_key", f"legacy-close-lost:{instance.id}")
            payload.setdefault("expected_version", instance.version)
        serializer = CloseLostSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        opportunity = OpportunityService.close_lost(
            self.tenant_id(), opportunity_id=instance.id, actor_id=_actor(request), **serializer.validated_data
        )
        return Response(OpportunityReadSerializer(opportunity).data)


class ActivityViewSet(GovernedCRMViewSet):
    queryset = Activity.objects.all()
    serializer_class = ActivityReadSerializer
    permission_map = ACTIVITY_ACTION_PERMISSIONS
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self) -> QuerySet[Activity]:
        queryset = super().get_queryset().filter(is_deleted=False)
        if not hasattr(self, "request"):
            return queryset
        self._validate_query(
            {
                "related_to_type",
                "related_to_id",
                "activity_type",
                "owner_id",
                "completed",
                "due_from",
                "due_to",
                "ordering",
            }
        )
        params = self.request.query_params
        if params.get("related_to_type"):
            if params["related_to_type"] not in RelatedToType.values:
                raise ValidationError({"related_to_type": "Unsupported CRM relation type."})
            queryset = queryset.filter(related_to_type=params["related_to_type"])
        for field in ("related_to_id", "owner_id"):
            if params.get(field):
                queryset = queryset.filter(**{field: _parse_uuid(params[field], field)})
        if params.get("activity_type"):
            if params["activity_type"] not in ActivityType.values:
                raise ValidationError({"activity_type": "Unsupported activity type."})
            queryset = queryset.filter(activity_type=params["activity_type"])
        completed = _parse_bool(params.get("completed"), "completed")
        if completed is not None:
            queryset = queryset.filter(completed=completed)
        due_from = _parse_date(params.get("due_from"), "due_from")
        due_to = _parse_date(params.get("due_to"), "due_to")
        if due_from:
            queryset = queryset.filter(due_date__date__gte=due_from)
        if due_to:
            queryset = queryset.filter(due_date__date__lte=due_to)
        if due_from and due_to and due_from > due_to:
            raise ValidationError({"due_from": "Cannot be after due_to."})
        return self._ordering(
            queryset, {"created_at", "updated_at", "due_date", "activity_type", "completed", "subject"}, "-created_at"
        )

    def get_serializer_class(self) -> type[Any]:
        return {"create": ActivityCreateSerializer, "partial_update": ActivityUpdateSerializer}.get(
            self.action, ActivityReadSerializer
        )

    def create(self, request: Request) -> Response:
        serializer = ActivityCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        activity = ActivityService.create_activity(
            self.tenant_id(),
            data=serializer.validated_data,
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(ActivityReadSerializer(activity).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        serializer = ActivityUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        expected = self._expected_version(values, instance)
        activity = ActivityService.update_activity(
            self.tenant_id(), activity_id=instance.id, data=values, expected_version=expected, actor_id=_actor(request)
        )
        return Response(ActivityReadSerializer(activity).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        raise MethodNotAllowed("DELETE", detail="CRM activity evidence is append-only and cannot be deleted.")

    @action(detail=True, methods=["post"])
    def complete(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        payload = dict(request.data)
        if request.path.startswith("/api/v1/"):
            payload.setdefault("transition_key", f"legacy-complete:{instance.id}")
            payload.setdefault("expected_version", instance.version)
        serializer = ActivityCompleteSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        activity = ActivityService.complete_activity(
            self.tenant_id(), activity_id=instance.id, actor_id=_actor(request), **serializer.validated_data
        )
        return Response(ActivityReadSerializer(activity).data)


class ForecastingViewSet(GovernedCRMViewSet):
    queryset = Opportunity.objects.none()
    serializer_class = ForecastSerializer
    permission_map = FORECAST_ACTION_PERMISSIONS
    http_method_names = ["get", "post", "head", "options"]

    def _query(self, request: Request) -> dict[str, Any]:
        serializer = ForecastQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    @action(detail=False, methods=["get"])
    def pipeline(self, request: Request) -> Response:
        values = self._query(request)
        forecast = ForecastingService.get_weighted_pipeline(
            self.tenant_id(), owner_id=values.get("owner_id"), period_days=values.get("period")
        )
        if request.path.startswith("/api/v1/"):
            if len(forecast.currencies) > 1:
                raise CRMServiceError(
                    "The v1 forecast cannot represent a multi-currency pipeline; use the currency-grouped v2 endpoint.",
                    code="MULTI_CURRENCY_PIPELINE",
                    http_status=status.HTTP_409_CONFLICT,
                )
            currency = forecast.currencies[0] if forecast.currencies else None
            return Response(
                {
                    "total_pipeline_value": float(currency.total_pipeline_value) if currency else 0.0,
                    "weighted_pipeline_value": float(currency.weighted_pipeline_value) if currency else 0.0,
                    "opportunity_count": currency.opportunity_count if currency else 0,
                    "period_days": forecast.period_days,
                }
            )
        return Response(ForecastSerializer(forecast).data)

    @action(detail=False, methods=["get"], url_path="win-rate")
    def win_rate(self, request: Request) -> Response:
        values = self._query(request)
        result = ForecastingService.get_win_rate(
            self.tenant_id(), owner_id=values.get("owner_id"), period_days=values.get("period")
        )
        return Response(WinRateSerializer(result).data)

    @action(detail=False, methods=["get"], url_path="by-stage")
    def by_stage(self, request: Request) -> Response:
        values = self._query(request)
        rows = ForecastingService.get_pipeline_by_stage(
            self.tenant_id(), owner_id=values.get("owner_id"), period_days=values.get("period")
        )
        return Response(StageForecastSerializer(rows, many=True).data)

    @action(detail=False, methods=["post"])
    def predict(self, request: Request) -> Response:
        serializer = RevenuePredictionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = ForecastingService.predict_revenue(
            self.tenant_id(),
            period_days=serializer.validated_data.get("period"),
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        prediction = result.unwrap()
        return Response(RevenuePredictionSerializer(prediction).data)


class CRMConfigurationViewSet(GovernedCRMViewSet):
    """Singleton tenant configuration endpoint backed only by the service layer."""

    queryset = CRMConfiguration.objects.all()
    serializer_class = CRMConfigurationWriteSerializer
    permission_map = CONFIGURATION_ACTION_PERMISSIONS
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def _environment(self, request: Request) -> str:
        unknown = set(request.query_params) - {"environment", "format"}
        if unknown:
            raise ValidationError({field: "Unknown query parameter." for field in sorted(unknown)})
        return request.query_params.get("environment", "production")

    def list(self, request: Request) -> Response:
        return Response(CRMConfigurationService.get(self.tenant_id(), environment=self._environment(request)))

    def _write(self, request: Request) -> Response:
        serializer = CRMConfigurationWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        payload.setdefault("environment", self._environment(request))
        raw_version = request.headers.get("If-Match")
        if raw_version is None:
            raise ValidationError({"If-Match": "Current configuration version is required."})
        try:
            expected_version = int(raw_version.strip().removeprefix("W/").strip('"'))
        except ValueError as exc:
            raise ValidationError({"If-Match": "Must contain a non-negative configuration version."}) from exc
        if expected_version < 0:
            raise ValidationError({"If-Match": "Must contain a non-negative configuration version."})
        value = CRMConfigurationService.write(
            self.tenant_id(),
            payload=payload,
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
            expected_version=expected_version,
        )
        return Response(value)

    def update(self, request: Request) -> Response:
        return self._write(request)

    def partial_update(self, request: Request) -> Response:
        return self._write(request)

    def preview(self, request: Request) -> Response:
        serializer = CRMConfigurationWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        payload.setdefault("environment", self._environment(request))
        return Response(CRMConfigurationService.preview(self.tenant_id(), payload=payload))

    def versions(self, request: Request) -> Response:
        return Response(CRMConfigurationService.versions(self.tenant_id(), environment=self._environment(request)))

    def rollback(self, request: Request) -> Response:
        serializer = CRMConfigurationRollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        return Response(
            CRMConfigurationService.rollback(
                self.tenant_id(),
                environment=values.get("environment", self._environment(request)),
                version=values["version"],
                actor_id=_actor(request),
                correlation_id=self.correlation_id(),
            )
        )

    def import_configuration(self, request: Request) -> Response:
        serializer = CRMConfigurationImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            CRMConfigurationService.import_document(
                self.tenant_id(),
                exported=serializer.validated_data,
                actor_id=_actor(request),
                correlation_id=self.correlation_id(),
            )
        )

    def export_configuration(self, request: Request) -> Response:
        return Response(CRMConfigurationService.export(self.tenant_id(), environment=self._environment(request)))


class AsyncJobViewSet(GovernedCRMViewSet):
    queryset = AsyncJob.objects.all()
    serializer_class = AsyncJobReadSerializer
    http_method_names = ["get", "head", "options"]
    permission_map = {"retrieve": "crm.lead:score"}

    def get_queryset(self) -> QuerySet[AsyncJob]:
        return super().get_queryset()

    def check_permissions(self, request: Request) -> None:
        tenant_id = self._get_tenant_id()
        if tenant_id is not None and getattr(self, "action", "") == "retrieve":
            job = AsyncJob.objects.filter(tenant_id=tenant_id, id=self.kwargs.get("pk")).only("command").first()
            try:
                permission = permission_for_job_command(job.command) if job else ""
            except PermissionError:
                permission = ""
            self.permission_map = {"retrieve": permission}
        super().check_permissions(request)


__all__ = [
    "AccountViewSet",
    "ActivityViewSet",
    "AsyncJobViewSet",
    "ContactViewSet",
    "CRMConfigurationViewSet",
    "ForecastingViewSet",
    "GovernedCRMViewSet",
    "LeadViewSet",
    "OpportunityViewSet",
]
