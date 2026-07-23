"""Governed, service-only API v2 for Master Data Management."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any, Iterator
from uuid import UUID

from django.db.models import Q, QuerySet
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from src.core.access.permissions import RequiresAccess
from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination
from src.core.async_jobs.models import AsyncJob
from src.core.tenancy import tenant_context
from src.core.views.tenant_scoped import TenantScopedModelViewSet

from . import selectors
from .models import (
    DataQualityIssue,
    DataQualityRule,
    MasterDataConfiguration,
    MasterDataConfigurationVersion,
    MasterDataEntity,
    MasterEntityType,
    MatchCandidate,
    MatchingRule,
    MergeHistory,
)
from .permissions import (
    CONFIGURATION_MANAGE,
    CONFIGURATION_READ,
    DASHBOARD_READ,
    ENTITY_ARCHIVE,
    ENTITY_CREATE,
    ENTITY_READ,
    ENTITY_RESTORE,
    ENTITY_ROLLBACK,
    ENTITY_TYPE_MANAGE,
    ENTITY_TYPE_READ,
    ENTITY_UPDATE,
    MATCH_READ,
    MATCH_REVIEW,
    MATCH_RUN,
    MATCHING_RULE_MANAGE,
    MATCHING_RULE_READ,
    MERGE_EXECUTE,
    MERGE_READ,
    MERGE_REVERSE,
    QUALITY_ISSUE_READ,
    QUALITY_ISSUE_RESOLVE,
    QUALITY_RULE_MANAGE,
    QUALITY_RULE_READ,
    QUALITY_SCAN,
    AccessRule,
)
from .serializers import (
    AsyncJobSerializer,
    ConfigurationPreviewResultSerializer,
    ConfigurationPreviewSerializer,
    ConfigurationRollbackSerializer,
    ConfigurationWriteSerializer,
    DataQualityIssueDetailSerializer,
    DataQualityIssueListSerializer,
    DataQualityRuleDetailSerializer,
    DataQualityRuleListSerializer,
    DataQualityRuleUpdateSerializer,
    DataQualityRuleVersionSerializer,
    DataQualityRuleWriteSerializer,
    DeactivateRuleSerializer,
    DeactivateSerializer,
    LifecycleSerializer,
    MasterDataConfigurationSerializer,
    MasterDataConfigurationVersionSerializer,
    MasterDataEntityCreateSerializer,
    MasterDataEntityDetailSerializer,
    MasterDataEntityListSerializer,
    MasterDataEntityUpdateSerializer,
    MasterDataVersionSerializer,
    MasterEntityTypeCreateSerializer,
    MasterEntityTypeDetailSerializer,
    MasterEntityTypeListSerializer,
    MasterEntityTypeUpdateSerializer,
    MatchCandidateDetailSerializer,
    MatchCandidateListSerializer,
    MatchingRuleDetailSerializer,
    MatchingRuleListSerializer,
    MatchingRuleUpdateSerializer,
    MatchingRuleVersionSerializer,
    MatchingRuleWriteSerializer,
    MatchPreviewRequestSerializer,
    MatchResultSerializer,
    MatchReviewSerializer,
    MDMSummarySerializer,
    MergeHistoryDetailSerializer,
    MergeHistoryListSerializer,
    MergePreviewSerializer,
    MergeRequestSerializer,
    MergeReversalPreviewSerializer,
    MergeReverseSerializer,
    QualityIssueResolutionSerializer,
    QualityReportSerializer,
    RuleImportSerializer,
    RuleRollbackSerializer,
    RollbackSerializer,
    ScanRequestSerializer,
    ValidateRequestSerializer,
)
from .services import (
    ConfigurationService,
    DashboardService,
    DataQualityService,
    EntityTypeService,
    MasterEntityService,
    MatchingService,
    MergeService,
    QualityRuleService,
)


class CsrfSessionAuthentication(SessionAuthentication):
    """Standard session authentication with enforced CSRF and a 401 challenge."""

    def authenticate_header(self, request: Request) -> str:
        del request
        return "Session"


def _actor_id(request: Request) -> UUID:
    value = getattr(request.user, "pk", None)
    if isinstance(value, UUID):
        return value
    return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{value}")


def _uuid(value: object, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({field: "Must be a valid UUID."}) from exc


class GovernedMDMViewSet(GovernedAPIViewMixin, TenantScopedModelViewSet):
    """Deny-default MDM boundary with tenant-context reads and strict query input."""

    authentication_classes = (CsrfSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    pagination_class = GovernedPageNumberPagination
    access_map: Mapping[str, AccessRule] = {}
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def initial(self, request: Request, *args: object, **kwargs: object) -> None:
        super().initial(request, *args, **kwargs)
        scope = tenant_context(self.tenant_id())
        scope.__enter__()
        self._request_tenant_scope = scope

    def finalize_response(self, request: Request, response: Response, *args: object, **kwargs: object) -> Response:
        try:
            return super().finalize_response(request, response, *args, **kwargs)
        finally:
            scope = getattr(self, "_request_tenant_scope", None)
            if scope is not None:
                scope.__exit__(None, None, None)
                self._request_tenant_scope = None

    def check_permissions(self, request: Request) -> None:
        if request.method.lower() not in self.http_method_names:
            raise MethodNotAllowed(request.method)
        tenant_id = self._get_tenant_id()
        if tenant_id is not None:
            request.tenant_id = tenant_id  # type: ignore[attr-defined]
        rule = self.access_map.get(getattr(self, "action", ""))
        if rule is None:
            self.required_permission = ""
            self.required_entitlement = ""
            self.quota_resource = ""
            self.quota_cost = 1
        else:
            self.required_permission = rule.permission
            self.required_entitlement = rule.entitlement
            self.quota_resource = rule.quota_resource
            self.quota_cost = rule.quota_cost
        super().check_permissions(request)

    def tenant_id(self) -> UUID:
        return self._require_tenant_id()

    @contextmanager
    def tenant_scope(self) -> Iterator[UUID]:
        tenant = self.tenant_id()
        with tenant_context(tenant):
            yield tenant

    def get_queryset(self) -> QuerySet[Any]:
        # Both calls are deliberate: the shared base validates ownership and
        # the explicit manager method makes the module's tenant query visible.
        tenant = self._get_tenant_id()
        if tenant is None:
            return self.queryset.model.objects.none()
        return super().get_queryset().for_tenant(tenant)

    def list(self, request: Request, *args: object, **kwargs: object) -> Response:
        with self.tenant_scope():
            return super().list(request, *args, **kwargs)

    def retrieve(self, request: Request, *args: object, **kwargs: object) -> Response:
        with self.tenant_scope():
            return super().retrieve(request, *args, **kwargs)

    def _validate_query(self, allowed: set[str]) -> None:
        common = {"page", "page_size", "search", "ordering", "format"}
        unknown = set(self.request.query_params) - allowed - common
        if unknown:
            raise ValidationError({key: "Unknown query parameter." for key in sorted(unknown)})

    def _ordering(self, queryset: QuerySet[Any], allowed: set[str], default: str) -> QuerySet[Any]:
        ordering = self.request.query_params.get("ordering", default)
        key = ordering.removeprefix("-")
        if key not in allowed:
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return queryset.order_by(ordering)

    def _boolean_query(self, name: str) -> bool | None:
        value = self.request.query_params.get(name)
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
        raise ValidationError({name: "Must be either true or false."})


class MasterEntityTypeViewSet(GovernedMDMViewSet):
    queryset = MasterEntityType.objects.all()
    access_map = {
        "list": ENTITY_TYPE_READ,
        "retrieve": ENTITY_TYPE_READ,
        "create": ENTITY_TYPE_MANAGE,
        "partial_update": ENTITY_TYPE_MANAGE,
        "deactivate": ENTITY_TYPE_MANAGE,
    }

    def get_serializer_class(self) -> type[Any]:
        return {
            "list": MasterEntityTypeListSerializer,
            "retrieve": MasterEntityTypeDetailSerializer,
            "create": MasterEntityTypeCreateSerializer,
            "partial_update": MasterEntityTypeUpdateSerializer,
            "deactivate": DeactivateSerializer,
        }.get(self.action, MasterEntityTypeDetailSerializer)

    def get_queryset(self) -> QuerySet[MasterEntityType]:
        tenant = self._get_tenant_id()
        if tenant is None:
            return MasterEntityType.objects.none()
        self._validate_query({"key", "owner_module", "is_active"})
        queryset = selectors.entity_types(tenant)
        for field in ("key", "owner_module"):
            value = self.request.query_params.get(field)
            if value is not None:
                queryset = queryset.filter(**{field: value})
        is_active = self._boolean_query("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(key__icontains=search) | Q(display_name__icontains=search))
        return self._ordering(queryset, {"key", "display_name", "updated_at"}, "key")

    def create(self, request: Request) -> Response:
        serializer = MasterEntityTypeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        key = str(values.pop("idempotency_key"))
        entity_type = EntityTypeService.create_type(
            self.tenant_id(),
            _actor_id(request),
            owner_module="master_data_management",
            idempotency_key=key,
            **values,
        )
        return Response(
            MasterEntityTypeDetailSerializer(entity_type, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        serializer = MasterEntityTypeUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        expected = int(values.pop("expected_schema_version"))
        key = str(values.pop("idempotency_key"))
        changes = values.pop("changes")
        entity_type = EntityTypeService.update_type(
            self.tenant_id(),
            _actor_id(request),
            _uuid(pk, "id"),
            expected_schema_version=expected,
            changes=changes,
            idempotency_key=key,
        )
        return Response(MasterEntityTypeDetailSerializer(entity_type, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request: Request, pk: str | None = None) -> Response:
        serializer = DeactivateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity_type = EntityTypeService.deactivate_type(
            self.tenant_id(), _actor_id(request), _uuid(pk, "id"), **serializer.validated_data
        )
        return Response(MasterEntityTypeDetailSerializer(entity_type, context={"request": request}).data)


class MasterDataEntityViewSet(GovernedMDMViewSet):
    queryset = MasterDataEntity.objects.all()
    access_map = {
        "list": ENTITY_READ,
        "retrieve": ENTITY_READ,
        "create": ENTITY_CREATE,
        "partial_update": ENTITY_UPDATE,
        "destroy": ENTITY_ARCHIVE,
        "restore": ENTITY_RESTORE,
        "versions": ENTITY_READ,
        "version_detail": ENTITY_READ,
        "rollback": ENTITY_ROLLBACK,
        "validate": ENTITY_UPDATE,
    }

    def get_serializer_class(self) -> type[Any]:
        return MasterDataEntityListSerializer if self.action == "list" else MasterDataEntityDetailSerializer

    def get_queryset(self) -> QuerySet[MasterDataEntity]:
        tenant = self._get_tenant_id()
        if tenant is None:
            return MasterDataEntity.objects.none()
        self._validate_query({"entity_type", "status", "quality_min", "quality_max", "source_system", "deleted"})
        include_deleted = self.action in {"restore", "destroy"} or self._boolean_query("deleted") is True
        queryset = selectors.entities(tenant, include_deleted=include_deleted)
        filters = {
            "entity_type_id": self.request.query_params.get("entity_type"),
            "status": self.request.query_params.get("status"),
            "source_system": self.request.query_params.get("source_system"),
        }
        queryset = queryset.filter(**{key: value for key, value in filters.items() if value})
        if self.request.query_params.get("quality_min"):
            queryset = queryset.filter(quality_score__gte=self.request.query_params["quality_min"])
        if self.request.query_params.get("quality_max"):
            queryset = queryset.filter(quality_score__lte=self.request.query_params["quality_max"])
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(entity_code__icontains=search) | Q(entity_name__icontains=search))
        return self._ordering(
            queryset, {"entity_code", "entity_name", "quality_score", "updated_at", "created_at"}, "entity_code"
        )

    def create(self, request: Request) -> Response:
        serializer = MasterDataEntityCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity = MasterEntityService.create_entity(self.tenant_id(), _actor_id(request), **serializer.validated_data)
        return Response(
            MasterDataEntityDetailSerializer(entity, context={"request": request}).data, status=status.HTTP_201_CREATED
        )

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        serializer = MasterDataEntityUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        expected, reason, key = (
            int(values.pop("expected_version")),
            str(values.pop("reason")),
            str(values.pop("idempotency_key")),
        )
        entity = MasterEntityService.update_entity(
            self.tenant_id(),
            _actor_id(request),
            _uuid(pk, "id"),
            expected_version=expected,
            changes=values["changes"],
            reason=reason,
            idempotency_key=key,
        )
        return Response(MasterDataEntityDetailSerializer(entity, context={"request": request}).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        serializer = LifecycleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        MasterEntityService.archive_entity(
            self.tenant_id(), _actor_id(request), _uuid(pk, "id"), **serializer.validated_data
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def restore(self, request: Request, pk: str | None = None) -> Response:
        serializer = LifecycleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity = MasterEntityService.restore_entity(
            self.tenant_id(), _actor_id(request), _uuid(pk, "id"), **serializer.validated_data
        )
        return Response(MasterDataEntityDetailSerializer(entity, context={"request": request}).data)

    @action(detail=True, methods=["get"])
    def versions(self, request: Request, pk: str | None = None) -> Response:
        queryset = selectors.versions(self.tenant_id(), _uuid(pk, "id"))
        if not MasterDataEntity.objects.for_tenant(self.tenant_id()).filter(pk=pk).exists():
            raise NotFound()
        page = self.paginate_queryset(queryset)
        data = MasterDataVersionSerializer(
            page if page is not None else queryset,
            many=True,
            context={"request": request},
        ).data
        return self.get_paginated_response(data) if page is not None else Response(data)

    @action(detail=True, methods=["get"], url_path=r"versions/(?P<version_number>\d+)")
    def version_detail(self, request: Request, pk: str | None = None, version_number: str | None = None) -> Response:
        version = selectors.versions(self.tenant_id(), _uuid(pk, "id")).filter(version_number=version_number).first()
        if version is None:
            raise NotFound()
        return Response(MasterDataVersionSerializer(version, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def rollback(self, request: Request, pk: str | None = None) -> Response:
        serializer = RollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        version = int(values.pop("version_number"))
        entity = MasterEntityService.rollback_to_version(
            self.tenant_id(), _actor_id(request), _uuid(pk, "id"), version, **values
        )
        return Response(MasterDataEntityDetailSerializer(entity, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def validate(self, request: Request, pk: str | None = None) -> Response:
        serializer = ValidateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = DataQualityService.evaluate_entity(
            self.tenant_id(),
            _actor_id(request),
            _uuid(pk, "id"),
            idempotency_key=str(serializer.validated_data["idempotency_key"]),
        )
        return Response(QualityReportSerializer(report).data)


class DataQualityRuleViewSet(GovernedMDMViewSet):
    queryset = DataQualityRule.objects.all()
    access_map = {
        "list": QUALITY_RULE_READ,
        "retrieve": QUALITY_RULE_READ,
        "create": QUALITY_RULE_MANAGE,
        "partial_update": QUALITY_RULE_MANAGE,
        "destroy": QUALITY_RULE_MANAGE,
        "history": QUALITY_RULE_READ,
        "rollback": QUALITY_RULE_MANAGE,
        "import_document": QUALITY_RULE_MANAGE,
        "export_document": QUALITY_RULE_READ,
    }

    def get_serializer_class(self) -> type[Any]:
        return DataQualityRuleListSerializer if self.action == "list" else DataQualityRuleDetailSerializer

    def get_queryset(self) -> QuerySet[DataQualityRule]:
        tenant = self._get_tenant_id()
        if tenant is None:
            return DataQualityRule.objects.none()
        self._validate_query({"entity_type", "rule_type", "dimension", "severity", "is_active"})
        queryset = selectors.quality_rules(tenant)
        for field in ("entity_type", "rule_type", "dimension", "severity"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{f"{field}_id" if field == "entity_type" else field: value})
        is_active = self._boolean_query("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)
        return self._ordering(queryset, {"name", "severity", "updated_at"}, "name")

    def create(self, request: Request) -> Response:
        serializer = DataQualityRuleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = QualityRuleService.create_rule(self.tenant_id(), _actor_id(request), **serializer.validated_data)
        return Response(DataQualityRuleDetailSerializer(rule).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        serializer = DataQualityRuleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        key = str(values.pop("idempotency_key"))
        rule = QualityRuleService.update_rule(
            self.tenant_id(), _actor_id(request), _uuid(pk, "id"), changes=values["changes"], idempotency_key=key
        )
        return Response(DataQualityRuleDetailSerializer(rule).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        serializer = DeactivateRuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        QualityRuleService.deactivate_rule(
            self.tenant_id(),
            _actor_id(request),
            _uuid(pk, "id"),
            idempotency_key=str(serializer.validated_data["idempotency_key"]),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def history(self, request: Request, pk: str | None = None) -> Response:
        queryset = QualityRuleService.version_history(self.tenant_id(), _uuid(pk, "id"))
        page = self.paginate_queryset(queryset)
        data = DataQualityRuleVersionSerializer(page if page is not None else queryset, many=True).data
        return self.get_paginated_response(data) if page is not None else Response(data)

    @action(detail=True, methods=["post"])
    def rollback(self, request: Request, pk: str | None = None) -> Response:
        serializer = RuleRollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = QualityRuleService.rollback(
            self.tenant_id(), _actor_id(request), _uuid(pk, "id"), **serializer.validated_data
        )
        return Response(DataQualityRuleDetailSerializer(rule).data)

    @action(detail=True, methods=["post"], url_path="import")
    def import_document(self, request: Request, pk: str | None = None) -> Response:
        serializer = RuleImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = QualityRuleService.import_document(
            self.tenant_id(), _actor_id(request), _uuid(pk, "id"), **serializer.validated_data
        )
        return Response(DataQualityRuleDetailSerializer(rule).data)

    @action(detail=True, methods=["get"], url_path="export")
    def export_document(self, request: Request, pk: str | None = None) -> Response:
        del request
        return Response(QualityRuleService.export_document(self.tenant_id(), _uuid(pk, "id")))


class DataQualityIssueViewSet(GovernedMDMViewSet):
    queryset = DataQualityIssue.objects.all()
    access_map = {
        "list": QUALITY_ISSUE_READ,
        "retrieve": QUALITY_ISSUE_READ,
        "assign": QUALITY_ISSUE_RESOLVE,
        "resolve": QUALITY_ISSUE_RESOLVE,
        "waive": QUALITY_ISSUE_RESOLVE,
    }

    def get_serializer_class(self) -> type[Any]:
        return DataQualityIssueListSerializer if self.action == "list" else DataQualityIssueDetailSerializer

    def get_queryset(self) -> QuerySet[DataQualityIssue]:
        tenant = self._get_tenant_id()
        if tenant is None:
            return DataQualityIssue.objects.none()
        self._validate_query({"entity", "entity_type", "status", "severity", "dimension", "assigned_to"})
        queryset = selectors.quality_issues(tenant)
        mapping = {
            "entity": "entity_id",
            "entity_type": "entity__entity_type_id",
            "status": "status",
            "severity": "severity",
            "dimension": "dimension",
            "assigned_to": "assigned_to",
        }
        for parameter, field in mapping.items():
            value = self.request.query_params.get(parameter)
            if value:
                queryset = queryset.filter(**{field: value})
        return self._ordering(queryset, {"created_at", "severity", "status", "updated_at"}, "-created_at")

    @action(detail=True, methods=["post"])
    def assign(self, request: Request, pk: str | None = None) -> Response:
        serializer = QualityIssueResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if "assignee_id" not in serializer.validated_data:
            raise ValidationError({"assignee_id": "This field is required."})
        issue = DataQualityService.assign_issue(
            self.tenant_id(),
            _actor_id(request),
            _uuid(pk, "id"),
            serializer.validated_data["assignee_id"],
            transition_key=str(serializer.validated_data["transition_key"]),
        )
        return Response(DataQualityIssueDetailSerializer(issue).data)

    def _resolve(self, request: Request, pk: str | None, command: str) -> Response:
        serializer = QualityIssueResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if "resolution" not in serializer.validated_data:
            raise ValidationError({"resolution": "This field is required."})
        method = DataQualityService.resolve_issue if command == "resolve" else DataQualityService.waive_issue
        issue = method(
            self.tenant_id(),
            _actor_id(request),
            _uuid(pk, "id"),
            resolution=str(serializer.validated_data["resolution"]),
            transition_key=str(serializer.validated_data["transition_key"]),
        )
        return Response(DataQualityIssueDetailSerializer(issue).data)

    @action(detail=True, methods=["post"])
    def resolve(self, request: Request, pk: str | None = None) -> Response:
        return self._resolve(request, pk, "resolve")

    @action(detail=True, methods=["post"])
    def waive(self, request: Request, pk: str | None = None) -> Response:
        return self._resolve(request, pk, "waive")


class QualityScanViewSet(GovernedMDMViewSet):
    queryset = MasterEntityType.objects.all()
    access_map = {"create": QUALITY_SCAN}
    http_method_names = ["post", "options"]

    def create(self, request: Request) -> Response:
        serializer = ScanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = DataQualityService.enqueue_quality_scan(
            self.tenant_id(),
            _actor_id(request),
            entity_type_id=serializer.validated_data["entity_type_id"],
            idempotency_key=str(serializer.validated_data["idempotency_key"]),
        )
        return Response(AsyncJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class MatchingRuleViewSet(GovernedMDMViewSet):
    queryset = MatchingRule.objects.all()
    access_map = {
        "list": MATCHING_RULE_READ,
        "retrieve": MATCHING_RULE_READ,
        "create": MATCHING_RULE_MANAGE,
        "partial_update": MATCHING_RULE_MANAGE,
        "destroy": MATCHING_RULE_MANAGE,
        "history": MATCHING_RULE_READ,
        "rollback": MATCHING_RULE_MANAGE,
        "import_document": MATCHING_RULE_MANAGE,
        "export_document": MATCHING_RULE_READ,
    }

    def get_serializer_class(self) -> type[Any]:
        return MatchingRuleListSerializer if self.action == "list" else MatchingRuleDetailSerializer

    def get_queryset(self) -> QuerySet[MatchingRule]:
        tenant = self._get_tenant_id()
        if tenant is None:
            return MatchingRule.objects.none()
        self._validate_query({"entity_type", "algorithm", "is_active"})
        queryset = selectors.matching_rules(tenant)
        for parameter, field in (("entity_type", "entity_type_id"), ("algorithm", "algorithm")):
            value = self.request.query_params.get(parameter)
            if value:
                queryset = queryset.filter(**{field: value})
        is_active = self._boolean_query("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return self._ordering(queryset, {"name", "updated_at", "review_threshold"}, "name")

    def create(self, request: Request) -> Response:
        serializer = MatchingRuleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = MatchingService.create_rule(self.tenant_id(), _actor_id(request), **serializer.validated_data)
        return Response(MatchingRuleDetailSerializer(rule).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        serializer = MatchingRuleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        key = str(values.pop("idempotency_key"))
        rule = MatchingService.update_rule(
            self.tenant_id(), _actor_id(request), _uuid(pk, "id"), changes=values["changes"], idempotency_key=key
        )
        return Response(MatchingRuleDetailSerializer(rule).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        serializer = DeactivateRuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        MatchingService.deactivate_rule(
            self.tenant_id(),
            _actor_id(request),
            _uuid(pk, "id"),
            idempotency_key=str(serializer.validated_data["idempotency_key"]),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def history(self, request: Request, pk: str | None = None) -> Response:
        queryset = MatchingService.version_history(self.tenant_id(), _uuid(pk, "id"))
        page = self.paginate_queryset(queryset)
        data = MatchingRuleVersionSerializer(page if page is not None else queryset, many=True).data
        return self.get_paginated_response(data) if page is not None else Response(data)

    @action(detail=True, methods=["post"])
    def rollback(self, request: Request, pk: str | None = None) -> Response:
        serializer = RuleRollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = MatchingService.rollback(
            self.tenant_id(), _actor_id(request), _uuid(pk, "id"), **serializer.validated_data
        )
        return Response(MatchingRuleDetailSerializer(rule).data)

    @action(detail=True, methods=["post"], url_path="import")
    def import_document(self, request: Request, pk: str | None = None) -> Response:
        serializer = RuleImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = MatchingService.import_document(
            self.tenant_id(), _actor_id(request), _uuid(pk, "id"), **serializer.validated_data
        )
        return Response(MatchingRuleDetailSerializer(rule).data)

    @action(detail=True, methods=["get"], url_path="export")
    def export_document(self, request: Request, pk: str | None = None) -> Response:
        del request
        return Response(MatchingService.export_document(self.tenant_id(), _uuid(pk, "id")))


class MatchingOperationsViewSet(GovernedMDMViewSet):
    queryset = MasterDataEntity.objects.all()
    access_map = {"preview": MATCH_READ, "scans": MATCH_RUN}
    http_method_names = ["post", "options"]

    @action(detail=False, methods=["post"])
    def preview(self, request: Request) -> Response:
        serializer = MatchPreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = MatchingService.preview_pair(self.tenant_id(), **serializer.validated_data)
        return Response(MatchResultSerializer(result).data)

    @action(detail=False, methods=["post"])
    def scans(self, request: Request) -> Response:
        serializer = ScanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = MatchingService.enqueue_deduplication_scan(
            self.tenant_id(), _actor_id(request), **serializer.validated_data
        )
        return Response(AsyncJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class MatchCandidateViewSet(GovernedMDMViewSet):
    queryset = MatchCandidate.objects.all()
    access_map = {"list": MATCH_READ, "retrieve": MATCH_READ, "review": MATCH_REVIEW}

    def get_serializer_class(self) -> type[Any]:
        return MatchCandidateListSerializer if self.action == "list" else MatchCandidateDetailSerializer

    def get_queryset(self) -> QuerySet[MatchCandidate]:
        tenant = self._get_tenant_id()
        if tenant is None:
            return MatchCandidate.objects.none()
        self._validate_query({"entity_type", "status", "confidence_min", "confidence_max", "rule"})
        queryset = selectors.match_candidates(tenant)
        mapping = {"entity_type": "left_entity__entity_type_id", "status": "status", "rule": "matching_rule_id"}
        for parameter, field in mapping.items():
            value = self.request.query_params.get(parameter)
            if value:
                queryset = queryset.filter(**{field: value})
        if self.request.query_params.get("confidence_min"):
            queryset = queryset.filter(confidence__gte=self.request.query_params["confidence_min"])
        if self.request.query_params.get("confidence_max"):
            queryset = queryset.filter(confidence__lte=self.request.query_params["confidence_max"])
        return self._ordering(queryset, {"confidence", "created_at", "updated_at"}, "-confidence")

    @action(detail=True, methods=["post"])
    def review(self, request: Request, pk: str | None = None) -> Response:
        serializer = MatchReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        candidate = MatchingService.review_candidate(
            self.tenant_id(), _actor_id(request), _uuid(pk, "id"), **serializer.validated_data
        )
        return Response(MatchCandidateDetailSerializer(candidate, context={"request": request}).data)


class MergeViewSet(GovernedMDMViewSet):
    queryset = MergeHistory.objects.all()
    access_map = {
        "list": MERGE_READ,
        "retrieve": MERGE_READ,
        "create": MERGE_EXECUTE,
        "preview": MERGE_READ,
        "reversal_preview": MERGE_READ,
        "reverse": MERGE_REVERSE,
    }

    def get_serializer_class(self) -> type[Any]:
        return MergeHistoryListSerializer if self.action == "list" else MergeHistoryDetailSerializer

    def get_queryset(self) -> QuerySet[MergeHistory]:
        tenant = self._get_tenant_id()
        if tenant is None:
            return MergeHistory.objects.none()
        self._validate_query({"status", "golden_record"})
        queryset = selectors.merges(tenant)
        golden_record = self.request.query_params.get("golden_record")
        if golden_record:
            queryset = queryset.filter(golden_record_id=golden_record)
        merge_status = self.request.query_params.get("status")
        if merge_status == "applied":
            queryset = queryset.filter(reversal__isnull=True)
        elif merge_status == "reversed":
            queryset = queryset.filter(reversal__isnull=False)
        elif merge_status:
            raise ValidationError({"status": "Must be applied or reversed."})
        return self._ordering(queryset, {"created_at", "status"}, "-created_at")

    def create(self, request: Request) -> Response:
        serializer = MergeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        history = MergeService.merge_entities(self.tenant_id(), _actor_id(request), **serializer.validated_data)
        return Response(
            MergeHistoryDetailSerializer(history, context={"request": request}).data, status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=["post"])
    def preview(self, request: Request) -> Response:
        serializer = MergePreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        preview = MergeService.preview_merge(
            self.tenant_id(),
            _actor_id(request),
            entity_ids=serializer.validated_data["entity_ids"],
            survivorship_overrides=serializer.validated_data.get("survivorship_overrides", {}),
        )
        return Response(MergePreviewSerializer(preview).data)

    @action(detail=True, methods=["get"], url_path="reversal-preview")
    def reversal_preview(self, request: Request, pk: str | None = None) -> Response:
        preview = MergeService.preview_reversal(
            self.tenant_id(),
            _uuid(pk, "id"),
        )
        return Response(MergeReversalPreviewSerializer(preview).data)

    @action(detail=True, methods=["post"])
    def reverse(self, request: Request, pk: str | None = None) -> Response:
        serializer = MergeReverseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        history = MergeService.reverse_merge(
            self.tenant_id(), _actor_id(request), _uuid(pk, "id"), **serializer.validated_data
        )
        return Response(MergeHistoryDetailSerializer(history, context={"request": request}).data)


class DashboardViewSet(GovernedMDMViewSet):
    queryset = MasterDataEntity.objects.all()
    access_map = {"list": DASHBOARD_READ}
    http_method_names = ["get", "options"]

    def list(self, request: Request) -> Response:
        self._validate_query({"entity_type"})
        identifier = request.query_params.get("entity_type")
        summary = DashboardService.get_summary(
            self.tenant_id(), entity_type_id=_uuid(identifier, "entity_type") if identifier else None
        )
        return Response(MDMSummarySerializer(summary).data)


class AsyncJobViewSet(GovernedMDMViewSet):
    queryset = AsyncJob.objects.all()
    access_map = {"retrieve": MATCH_RUN}
    http_method_names = ["get", "options"]
    serializer_class = AsyncJobSerializer

    def get_queryset(self) -> QuerySet[AsyncJob]:
        tenant = self._get_tenant_id()
        if tenant is None:
            return AsyncJob.objects.none()
        return AsyncJob.objects.for_tenant(tenant).filter(
            command__in=("master_data_management.quality_scan", "master_data_management.deduplication_scan")
        )


class MasterDataConfigurationViewSet(GovernedMDMViewSet):
    """Singleton tenant configuration boundary; every mutation delegates."""

    queryset = MasterDataConfiguration.objects.all()
    serializer_class = MasterDataConfigurationSerializer
    access_map = {
        "list": CONFIGURATION_READ,
        "retrieve": CONFIGURATION_READ,
        "create": CONFIGURATION_MANAGE,
        "partial_update": CONFIGURATION_MANAGE,
        "preview": CONFIGURATION_MANAGE,
        "history": CONFIGURATION_READ,
        "rollback": CONFIGURATION_MANAGE,
        "import_document": CONFIGURATION_MANAGE,
        "export_document": CONFIGURATION_READ,
    }
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self) -> QuerySet[MasterDataConfiguration]:
        tenant = self._get_tenant_id()
        if tenant is None:
            return MasterDataConfiguration.objects.none()
        return MasterDataConfiguration.objects.for_tenant(tenant).order_by("-version")

    def list(self, request: Request) -> Response:
        current = self.get_queryset().first()
        if current is None:
            current = ConfigurationService.ensure_defaults(
                self.tenant_id(),
                _actor_id(request),
            )
        return Response(MasterDataConfigurationSerializer(current).data)

    def create(self, request: Request) -> Response:
        serializer = ConfigurationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        current = ConfigurationService.write(
            self.tenant_id(),
            _actor_id(request),
            change_type="create",
            **serializer.validated_data,
        )
        return Response(
            MasterDataConfigurationSerializer(current).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        current = self.get_object()
        serializer = ConfigurationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        values.setdefault("expected_version", current.version)
        updated = ConfigurationService.write(
            self.tenant_id(),
            _actor_id(request),
            change_type="update",
            **values,
        )
        return Response(MasterDataConfigurationSerializer(updated).data)

    @action(detail=False, methods=["post"])
    def preview(self, request: Request) -> Response:
        serializer = ConfigurationPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = ConfigurationService.preview(self.tenant_id(), serializer.validated_data["document"])
        return Response(ConfigurationPreviewResultSerializer(result).data)

    @action(detail=False, methods=["get"])
    def history(self, request: Request) -> Response:
        tenant = self._get_tenant_id()
        if tenant is None:
            versions = MasterDataConfigurationVersion.objects.none()
        else:
            versions = MasterDataConfigurationVersion.objects.for_tenant(tenant).order_by("-version")
        return Response(MasterDataConfigurationVersionSerializer(versions, many=True).data)

    @action(detail=False, methods=["post"])
    def rollback(self, request: Request) -> Response:
        serializer = ConfigurationRollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        current = ConfigurationService.rollback(
            self.tenant_id(),
            _actor_id(request),
            **serializer.validated_data,
        )
        return Response(MasterDataConfigurationSerializer(current).data)

    @action(detail=False, methods=["post"], url_path="import")
    def import_document(self, request: Request) -> Response:
        serializer = ConfigurationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        current = ConfigurationService.write(
            self.tenant_id(),
            _actor_id(request),
            change_type="import",
            **serializer.validated_data,
        )
        return Response(MasterDataConfigurationSerializer(current).data)

    @action(detail=False, methods=["get"], url_path="export")
    def export_document(self, request: Request) -> Response:
        current = self.get_queryset().first()
        if current is None:
            current = ConfigurationService.ensure_defaults(
                self.tenant_id(),
                _actor_id(request),
            )
        return Response(
            {
                "module": "master_data_management",
                "schema_version": 1,
                "configuration_version": current.version,
                "document": current.document,
            }
        )


__all__ = [name for name in globals() if name.endswith("ViewSet")]
