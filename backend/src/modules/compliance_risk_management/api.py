"""Governed v2 API controllers for compliance risk management."""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from src.core.access import RequiresAccess
from src.core.api.profile import GovernedAPIViewMixin
from src.core.async_jobs.models import AsyncJob
from src.core.auth_utils import get_user_tenant_id

from .models import (
    ComplianceCalendarEntry,
    ComplianceRequirement,
    Control,
    ControlTest,
    RemediationAction,
    RiskAssessment,
)
from .health import get_module_health
from .filters import (
    ComplianceRequirementFilterSet,
    ControlFilterSet,
    ControlTestFilterSet,
    DashboardFilterSet,
    HeatmapFilterSet,
    RemediationActionFilterSet,
    RiskAssessmentFilterSet,
)
from .permissions import ActionAccessMixin, GovernedSessionAuthentication
from .serializers import (
    CalendarEntryCreateSerializer,
    CalendarEntryDetailSerializer,
    CalendarEntryListSerializer,
    CalendarEntryTransitionSerializer,
    CalendarEntryUpdateSerializer,
    ConfigurationImportSerializer,
    ConfigurationRollbackSerializer,
    ControlCreateSerializer,
    ControlDetailSerializer,
    ControlListSerializer,
    ControlTestCancelSerializer,
    ControlTestCreateSerializer,
    ControlTestDetailSerializer,
    ControlTestListSerializer,
    ControlTestResultSerializer,
    ControlTestTransitionSerializer,
    ControlTestUpdateSerializer,
    ControlTransitionSerializer,
    ControlUpdateSerializer,
    DashboardSummarySerializer,
    HeatmapCellSerializer,
    RemediationCreateSerializer,
    RemediationDetailSerializer,
    RemediationListSerializer,
    RemediationTransitionSerializer,
    RemediationUpdateSerializer,
    RequirementCreateSerializer,
    RequirementDetailSerializer,
    RequirementListSerializer,
    RequirementTransitionSerializer,
    RequirementUpdateSerializer,
    RiskAssessmentCreateSerializer,
    RiskAssessmentDetailSerializer,
    RiskAssessmentListSerializer,
    RiskAssessmentUpdateSerializer,
    RiskConfigurationPreviewSerializer,
    RiskConfigurationPublishSerializer,
    RiskConfigurationSerializer,
    RiskConfigurationVersionSerializer,
    RiskScorePreviewSerializer,
    RiskScoreResultSerializer,
    RiskTransitionSerializer,
)
from .services import (
    ComplianceCalendarService,
    ComplianceRequirementService,
    ControlService,
    ControlTestService,
    RemediationService,
    RiskAssessmentService,
    RiskConfigurationService,
)


class TenantGovernedViewSet(GovernedAPIViewMixin, ActionAccessMixin, viewsets.GenericViewSet[Any]):
    """Resolve trusted tenant and actor identities and common response behavior."""

    def tenant_id(self) -> UUID:
        raw = get_user_tenant_id(self.request.user)
        try:
            tenant = UUID(str(raw))
        except (TypeError, ValueError, AttributeError) as exc:
            raise PermissionDenied("Authenticated identity has no valid tenant.") from exc
        self.request.tenant_id = tenant
        return tenant

    def actor_id(self) -> UUID:
        raw = getattr(self.request.user, "id", None)
        if raw is None:
            raise PermissionDenied("Authenticated identity has no valid actor.")
        try:
            return UUID(str(raw))
        except (TypeError, ValueError, AttributeError):
            return uuid5(NAMESPACE_URL, f"saraise:user:{raw}")

    def object_or_404(self, queryset: Any, pk: object | None = None) -> Any:
        try:
            value = queryset.filter(pk=pk or self.kwargs.get("pk")).first()
        except (DjangoValidationError, TypeError, ValueError) as exc:
            raise NotFound() from exc
        if value is None:
            raise NotFound()
        self.check_object_permissions(self.request, value)
        return value

    def paginated(self, queryset: Any, serializer: type) -> Response:
        page = self.paginate_queryset(queryset)
        if page is None:
            raise RuntimeError("Governed pagination is required for collection endpoints.")
        return self.get_paginated_response(serializer(page, many=True).data)

    def _filters(self, allowed: set[str]) -> dict[str, str]:
        protocol = {"page", "page_size", "ordering", "format"}
        unknown = set(self.request.query_params) - allowed - protocol
        if unknown:
            raise ValidationError({name: "Unsupported filter." for name in sorted(unknown)})
        for name, maximum in (("page", None), ("page_size", 100)):
            raw = self.request.query_params.get(name)
            if raw in (None, ""):
                continue
            try:
                value = int(raw)
            except (TypeError, ValueError) as exc:
                raise ValidationError({name: "Must be a positive integer."}) from exc
            if value < 1 or (maximum is not None and value > maximum):
                raise ValidationError({name: f"Must be between 1 and {maximum}." if maximum else "Must be positive."})
        return {
            key: self.request.query_params[key]
            for key in allowed
            if self.request.query_params.get(key) not in (None, "")
        }

    def filtered(self, filter_class: type, queryset: Any) -> Any:
        filterset = filter_class(self.request.query_params, queryset=queryset)
        if not filterset.is_valid():
            raise ValidationError(filterset.errors)
        return filterset.qs


class RiskAssessmentViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "compliance_risk.risk:read",
        "retrieve": "compliance_risk.risk:read",
        "create": "compliance_risk.risk:create",
        "partial_update": "compliance_risk.risk:update",
        "destroy": "compliance_risk.risk:delete",
        "transition": "compliance_risk.risk:transition",
        "score_preview": "compliance_risk.risk:read",
        "controls": "compliance_risk.control:read",
        "remediations": "compliance_risk.remediation:read",
    }

    def get_queryset(self):
        return self.filtered(RiskAssessmentFilterSet, RiskAssessmentService.list_risks(self.tenant_id()))

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), RiskAssessmentListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(RiskAssessmentDetailSerializer(self.object_or_404(self.get_queryset())).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = RiskAssessmentCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        key = self.request.headers.get("Idempotency-Key") or data.pop("idempotency_key", None)
        if not key:
            raise ValidationError({"idempotency_key": "Idempotency-Key header is required."})
        value = RiskAssessmentService.create_risk(self.tenant_id(), self.actor_id(), data, key)
        return Response(RiskAssessmentDetailSerializer(value).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.object_or_404(self.get_queryset())
        serializer = RiskAssessmentUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        value = RiskAssessmentService.update_risk(
            self.tenant_id(), self.actor_id(), value.id, serializer.validated_data
        )
        return Response(RiskAssessmentDetailSerializer(value).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.object_or_404(self.get_queryset())
        RiskAssessmentService.soft_delete_risk(self.tenant_id(), self.actor_id(), value.id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def transition(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        value = self.object_or_404(self.get_queryset())
        serializer = RiskTransitionSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = RiskAssessmentService.transition_risk(
            self.tenant_id(), self.actor_id(), value.id, **serializer.validated_data
        )
        return Response(RiskAssessmentDetailSerializer(value).data)

    @action(detail=False, methods=["post"], url_path="score-preview")
    def score_preview(self, request: object) -> Response:
        del request
        serializer = RiskScorePreviewSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        result = RiskAssessmentService.preview_score(self.tenant_id(), serializer.validated_data)
        return Response(RiskScoreResultSerializer(result).data)

    def get_permissions(self) -> list[object]:
        if getattr(self, "action", "") == "controls" and self.request.method == "POST":
            self.action_permissions = {**type(self).action_permissions, "controls": "compliance_risk.control:create"}
        if getattr(self, "action", "") == "remediations" and self.request.method == "POST":
            self.action_permissions = {
                **type(self).action_permissions,
                "remediations": "compliance_risk.remediation:create",
            }
        return super().get_permissions()

    @action(detail=True, methods=["get", "post"])
    def controls(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        risk = self.object_or_404(RiskAssessment.objects.for_tenant(self.tenant_id()).filter(is_deleted=False))
        if self.request.method == "POST":
            serializer = ControlCreateSerializer(data=self.request.data)
            serializer.is_valid(raise_exception=True)
            value = ControlService.create_control(self.tenant_id(), self.actor_id(), risk.id, serializer.validated_data)
            return Response(ControlDetailSerializer(value).data, status=status.HTTP_201_CREATED)
        return self.paginated(
            ControlService.list_controls(self.tenant_id(), {"risk_id": risk.id}), ControlListSerializer
        )

    @action(detail=True, methods=["get", "post"])
    def remediations(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        risk = self.object_or_404(RiskAssessment.objects.for_tenant(self.tenant_id()).filter(is_deleted=False))
        if self.request.method == "POST":
            serializer = RemediationCreateSerializer(data=self.request.data)
            serializer.is_valid(raise_exception=True)
            value = RemediationService.create_action(
                self.tenant_id(), self.actor_id(), risk.id, serializer.validated_data
            )
            return Response(RemediationDetailSerializer(value).data, status=status.HTTP_201_CREATED)
        return self.paginated(
            RemediationService.list_actions(self.tenant_id(), {"risk_id": risk.id}), RemediationListSerializer
        )


class ControlViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "compliance_risk.control:read",
        "retrieve": "compliance_risk.control:read",
        "create": "compliance_risk.control:create",
        "partial_update": "compliance_risk.control:update",
        "destroy": "compliance_risk.control:delete",
        "transition": "compliance_risk.control:transition",
        "tests": "compliance_risk.test:read",
    }

    def get_queryset(self):
        return self.filtered(ControlFilterSet, ControlService.list_controls(self.tenant_id()))

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), ControlListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(ControlDetailSerializer(self.object_or_404(self.get_queryset())).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        risk_id = self.request.data.get("risk_id")
        if not risk_id:
            raise ValidationError({"risk_id": "This field is required."})
        payload = dict(self.request.data)
        payload.pop("risk_id", None)
        serializer = ControlCreateSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        value = ControlService.create_control(self.tenant_id(), self.actor_id(), risk_id, serializer.validated_data)
        return Response(ControlDetailSerializer(value).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.object_or_404(self.get_queryset())
        serializer = ControlUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(
            ControlDetailSerializer(
                ControlService.update_control(self.tenant_id(), self.actor_id(), value.id, serializer.validated_data)
            ).data
        )

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.object_or_404(self.get_queryset())
        ControlService.soft_delete_control(self.tenant_id(), self.actor_id(), value.id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def transition(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        value = self.object_or_404(self.get_queryset())
        serializer = ControlTransitionSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            ControlDetailSerializer(
                ControlService.transition_control(
                    self.tenant_id(), self.actor_id(), value.id, **serializer.validated_data
                )
            ).data
        )

    def get_permissions(self) -> list[object]:
        if getattr(self, "action", "") == "tests" and self.request.method == "POST":
            self.action_permissions = {**type(self).action_permissions, "tests": "compliance_risk.test:schedule"}
        return super().get_permissions()

    @action(detail=True, methods=["get", "post"])
    def tests(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        control = self.object_or_404(self.get_queryset())
        if self.request.method == "POST":
            serializer = ControlTestCreateSerializer(data=self.request.data)
            serializer.is_valid(raise_exception=True)
            data = dict(serializer.validated_data)
            key = data.pop("idempotency_key")
            value = ControlTestService.schedule_test(self.tenant_id(), self.actor_id(), control.id, data, key)
            return Response(ControlTestDetailSerializer(value).data, status=status.HTTP_201_CREATED)
        return self.paginated(
            ControlTestService.list_tests(self.tenant_id(), {"control_id": control.id}), ControlTestListSerializer
        )


class ControlTestViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "compliance_risk.test:read",
        "retrieve": "compliance_risk.test:read",
        "partial_update": "compliance_risk.test:schedule",
        "start": "compliance_risk.test:execute",
        "result": "compliance_risk.test:execute",
        "cancel": "compliance_risk.test:execute",
    }

    def get_queryset(self):
        return self.filtered(ControlTestFilterSet, ControlTestService.list_tests(self.tenant_id()))

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), ControlTestListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(ControlTestDetailSerializer(self.object_or_404(self.get_queryset())).data)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.object_or_404(self.get_queryset())
        serializer = ControlTestUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(
            ControlTestDetailSerializer(
                ControlTestService.update_scheduled_test(
                    self.tenant_id(), self.actor_id(), value.id, serializer.validated_data
                )
            ).data
        )

    @action(detail=True, methods=["post"])
    def start(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        value = self.object_or_404(self.get_queryset())
        serializer = ControlTestTransitionSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            ControlTestDetailSerializer(
                ControlTestService.start_test(
                    self.tenant_id(), self.actor_id(), value.id, serializer.validated_data["transition_key"]
                )
            ).data
        )

    @action(detail=True, methods=["post"])
    def result(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        value = self.object_or_404(self.get_queryset())
        serializer = ControlTestResultSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        key = data.pop("transition_key")
        return Response(
            ControlTestDetailSerializer(
                ControlTestService.record_result(self.tenant_id(), self.actor_id(), value.id, data, key)
            ).data
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        value = self.object_or_404(self.get_queryset())
        serializer = ControlTestCancelSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            ControlTestDetailSerializer(
                ControlTestService.cancel_test(self.tenant_id(), self.actor_id(), value.id, **serializer.validated_data)
            ).data
        )


class RequirementViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "compliance_risk.requirement:read",
        "retrieve": "compliance_risk.requirement:read",
        "create": "compliance_risk.requirement:create",
        "partial_update": "compliance_risk.requirement:update",
        "destroy": "compliance_risk.requirement:delete",
        "assess": "compliance_risk.requirement:assess",
    }

    def get_queryset(self):
        return self.filtered(
            ComplianceRequirementFilterSet, ComplianceRequirementService.list_requirements(self.tenant_id())
        )

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), RequirementListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(RequirementDetailSerializer(self.object_or_404(self.get_queryset())).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = RequirementCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = ComplianceRequirementService.create_requirement(
            self.tenant_id(), self.actor_id(), serializer.validated_data
        )
        return Response(RequirementDetailSerializer(value).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.object_or_404(self.get_queryset())
        serializer = RequirementUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(
            RequirementDetailSerializer(
                ComplianceRequirementService.update_requirement(
                    self.tenant_id(), self.actor_id(), value.id, serializer.validated_data
                )
            ).data
        )

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.object_or_404(self.get_queryset())
        ComplianceRequirementService.soft_delete_requirement(self.tenant_id(), self.actor_id(), value.id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def assess(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        value = self.object_or_404(self.get_queryset())
        serializer = RequirementTransitionSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            RequirementDetailSerializer(
                ComplianceRequirementService.assess_requirement(
                    self.tenant_id(), self.actor_id(), value.id, **serializer.validated_data
                )
            ).data
        )


class CalendarViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "compliance_risk.calendar:read",
        "retrieve": "compliance_risk.calendar:read",
        "create": "compliance_risk.calendar:create",
        "partial_update": "compliance_risk.calendar:update",
        "destroy": "compliance_risk.calendar:delete",
        "transition": "compliance_risk.calendar:transition",
    }

    def get_queryset(self):
        filters = self._filters(
            {
                "date_from",
                "date_to",
                "type",
                "event_type",
                "status",
                "requirement",
                "requirement_id",
                "assignee",
                "assigned_to_id",
            }
        )
        if "event_type" in filters:
            filters["type"] = filters.pop("event_type")
        if "requirement_id" in filters:
            filters["requirement"] = filters.pop("requirement_id")
        if "assigned_to_id" in filters:
            filters["assignee"] = filters.pop("assigned_to_id")
        raw_from, raw_to = filters.pop("date_from", None), filters.pop("date_to", None)
        date_from, date_to = parse_date(str(raw_from or "")), parse_date(str(raw_to or ""))
        if date_from is None or date_to is None:
            raise ValidationError({"date_from": "Both date_from and date_to must be ISO 8601 dates."})
        if date_to < date_from:
            raise ValidationError({"date_to": "Must be on or after date_from."})
        if filters.get("type") and filters["type"] not in {"deadline", "review", "submission", "audit", "renewal"}:
            raise ValidationError({"type": "Unsupported calendar event type."})
        if filters.get("status") and filters["status"] not in {"upcoming", "overdue", "completed", "cancelled"}:
            raise ValidationError({"status": "Unsupported calendar status."})
        for name in ("requirement", "assignee"):
            if filters.get(name):
                try:
                    UUID(filters[name])
                except (TypeError, ValueError, AttributeError) as exc:
                    raise ValidationError({name: "Must be a valid UUID."}) from exc
        return ComplianceCalendarService.list_entries(
            self.tenant_id(), date_from, date_to, filters, self.request.query_params.get("ordering", "scheduled_date")
        )

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), CalendarEntryListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(
            CalendarEntryDetailSerializer(
                self.object_or_404(
                    ComplianceCalendarEntry.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)
                )
            ).data
        )

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = CalendarEntryCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = ComplianceCalendarService.create_entry(self.tenant_id(), self.actor_id(), serializer.validated_data)
        return Response(CalendarEntryDetailSerializer(value).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.object_or_404(
            ComplianceCalendarEntry.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)
        )
        serializer = CalendarEntryUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(
            CalendarEntryDetailSerializer(
                ComplianceCalendarService.update_entry(
                    self.tenant_id(), self.actor_id(), value.id, serializer.validated_data
                )
            ).data
        )

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.object_or_404(
            ComplianceCalendarEntry.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)
        )
        ComplianceCalendarService.soft_delete_entry(self.tenant_id(), self.actor_id(), value.id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def transition(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        value = self.object_or_404(
            ComplianceCalendarEntry.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)
        )
        serializer = CalendarEntryTransitionSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            CalendarEntryDetailSerializer(
                ComplianceCalendarService.transition_entry(
                    self.tenant_id(), self.actor_id(), value.id, **serializer.validated_data
                )
            ).data
        )


class RemediationViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "compliance_risk.remediation:read",
        "retrieve": "compliance_risk.remediation:read",
        "create": "compliance_risk.remediation:create",
        "partial_update": "compliance_risk.remediation:update",
        "destroy": "compliance_risk.remediation:delete",
        "transition": "compliance_risk.remediation:transition",
    }

    def get_queryset(self):
        return self.filtered(RemediationActionFilterSet, RemediationService.list_actions(self.tenant_id()))

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), RemediationListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(RemediationDetailSerializer(self.object_or_404(self.get_queryset())).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        risk_id = self.request.data.get("risk_id")
        if not risk_id:
            raise ValidationError({"risk_id": "This field is required."})
        payload = dict(self.request.data)
        payload.pop("risk_id", None)
        serializer = RemediationCreateSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        value = RemediationService.create_action(self.tenant_id(), self.actor_id(), risk_id, serializer.validated_data)
        return Response(RemediationDetailSerializer(value).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.object_or_404(self.get_queryset())
        serializer = RemediationUpdateSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(
            RemediationDetailSerializer(
                RemediationService.update_action(self.tenant_id(), self.actor_id(), value.id, serializer.validated_data)
            ).data
        )

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.object_or_404(self.get_queryset())
        RemediationService.soft_delete_action(self.tenant_id(), self.actor_id(), value.id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def transition(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        value = self.object_or_404(self.get_queryset())
        serializer = RemediationTransitionSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            RemediationDetailSerializer(
                RemediationService.transition_action(
                    self.tenant_id(), self.actor_id(), value.id, **serializer.validated_data
                )
            ).data
        )


class DashboardViewSet(TenantGovernedViewSet):
    action_permissions = {"list": "compliance_risk.dashboard:read"}

    def get_queryset(self):
        return RiskAssessment.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        filters = self._filters({"category", "owner_id", "date_from", "date_to", "review_from", "review_to"})
        if "date_from" in filters:
            filters["review_from"] = filters.pop("date_from")
        if "date_to" in filters:
            filters["review_to"] = filters.pop("date_to")
        check = DashboardFilterSet(filters, queryset=self.get_queryset())
        if not check.is_valid():
            raise ValidationError(check.errors)
        data = RiskAssessmentService.dashboard_summary(self.tenant_id(), filters)
        return Response(DashboardSummarySerializer(data).data)


class HeatmapViewSet(TenantGovernedViewSet):
    action_permissions = {"list": "compliance_risk.dashboard:read"}

    def get_queryset(self):
        return RiskAssessment.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        filters = self._filters({"category", "owner_id", "status"})
        check = HeatmapFilterSet(self.request.query_params, queryset=self.get_queryset())
        if not check.is_valid():
            raise ValidationError(check.errors)
        return Response(
            HeatmapCellSerializer(RiskAssessmentService.heatmap(self.tenant_id(), **filters), many=True).data
        )


class ConfigurationViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "compliance_risk.configuration:read",
        "update": "compliance_risk.configuration:manage",
        "preview": "compliance_risk.configuration:manage",
        "versions": "compliance_risk.configuration:read",
        "version_detail": "compliance_risk.configuration:read",
        "rollback": "compliance_risk.configuration:rollback",
        "export": "compliance_risk.configuration:read",
        "import_document": "compliance_risk.configuration:manage",
    }

    def environment(self) -> str:
        return self.request.query_params.get("environment", "development")

    def get_queryset(self):
        return RiskConfigurationService.list_versions(self.tenant_id(), self.environment())

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(
            RiskConfigurationSerializer(RiskConfigurationService.get_active(self.tenant_id(), self.environment())).data
        )

    def update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = RiskConfigurationPublishSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        environment, expected, candidate = (
            data.pop("environment"),
            data.pop("expected_version"),
            dict(data.pop("candidate")),
        )
        candidate["change_summary"] = data.pop("change_summary")
        return Response(
            RiskConfigurationSerializer(
                RiskConfigurationService.publish(self.tenant_id(), self.actor_id(), environment, candidate, expected)
            ).data
        )

    @action(detail=False, methods=["post"])
    def preview(self, request: object) -> Response:
        del request
        serializer = RiskConfigurationPreviewSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        environment, candidate = data.pop("environment"), dict(data.pop("candidate"))
        return Response(RiskConfigurationService.preview(self.tenant_id(), self.actor_id(), environment, candidate))

    @action(detail=False, methods=["get"])
    def versions(self, request: object) -> Response:
        del request
        return self.paginated(self.get_queryset(), RiskConfigurationVersionSerializer)

    @action(detail=False, methods=["get", "patch", "delete"], url_path=r"versions/(?P<version>\d+)")
    def version_detail(self, request: object, version: str | None = None) -> Response:
        if self.request.method != "GET":
            raise MethodNotAllowed(self.request.method or "")
        del request
        return Response(
            RiskConfigurationVersionSerializer(
                RiskConfigurationService.get_version(self.tenant_id(), self.environment(), int(version or 0))
            ).data
        )

    @action(detail=False, methods=["post"])
    def rollback(self, request: object) -> Response:
        del request
        serializer = ConfigurationRollbackSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        environment = data.pop("environment")
        data.pop("change_summary", None)
        return Response(
            RiskConfigurationSerializer(
                RiskConfigurationService.rollback(self.tenant_id(), self.actor_id(), environment, **data)
            ).data
        )

    @action(detail=False, methods=["get"])
    def export(self, request: object) -> Response:
        del request
        return Response(RiskConfigurationService.export_document(self.tenant_id(), self.environment()))

    @action(detail=False, methods=["post"], url_path="import")
    def import_document(self, request: object) -> Response:
        del request
        serializer = ConfigurationImportSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = RiskConfigurationService.import_document(
            self.tenant_id(), self.actor_id(), data["environment"], data["document"], data["dry_run"]
        )
        return Response(result if isinstance(result, dict) else RiskConfigurationSerializer(result).data)


class JobViewSet(TenantGovernedViewSet):
    action_permissions = {"retrieve": "compliance_risk.dashboard:read"}

    def get_queryset(self):
        return AsyncJob.objects.for_tenant(self.tenant_id()).filter(command__startswith="compliance_risk.")

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        job = self.object_or_404(self.get_queryset())
        return Response(
            {
                "id": job.id,
                "command": job.command,
                "status": job.status,
                "attempts": job.attempts,
                "created_at": job.created_at,
                "completed_at": job.completed_at,
                "result": job.result,
            }
        )


class HealthAPIView(GovernedAPIViewMixin, APIView):
    authentication_classes = (GovernedSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    required_permission = "compliance_risk.health:read"
    required_entitlement = "compliance_risk_management"
    quota_resource = "compliance_risk.health_reads"

    def get(self, request: object, probe: str) -> Response:
        if probe == "live":
            return Response(
                {
                    "status": "healthy",
                    "module": "compliance_risk_management",
                    "live": True,
                    "checked_at": timezone.now(),
                }
            )
        report = get_module_health(getattr(self.request, "tenant_id", None))
        return Response(report.as_dict(), status=report.status_code)


# Compatibility name for imports from the former scaffold.
ComplianceRiskViewSet = RiskAssessmentViewSet
