"""Governed, tenant-isolated Human Resources API v2 controllers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, cast
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import DecimalField, ExpressionWrapper, F, Q, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from src.core.access import RequiresAccess
from src.core.api import CapabilityUnavailable, GovernedAPIViewMixin, GovernedPageNumberPagination
from src.core.api.results import OperationFailed
from src.core.state_machine import StateMachineError
from src.core.views.tenant_scoped import TenantScopedModelViewSet

from .models import Attendance, Department, Employee, LeaveBalance, LeaveRequest
from .permissions import AccessRequirement, GovernedSessionAuthentication
from .serializers import (
    AttendanceCreateSerializer,
    AttendanceDetailSerializer,
    AttendanceListSerializer,
    AttendanceUpdateSerializer,
    ClockInSerializer,
    ClockOutSerializer,
    DepartmentCreateSerializer,
    DepartmentDetailSerializer,
    DepartmentListSerializer,
    DepartmentTreeSerializer,
    DepartmentUpdateSerializer,
    EmployeeCreateSerializer,
    EmployeeDetailSerializer,
    EmployeeListSerializer,
    EmployeeTransitionSerializer,
    EmployeeTreeSerializer,
    EmployeeUpdateSerializer,
    LeaveApprovalSerializer,
    LeaveBalanceCreateSerializer,
    LeaveBalanceDetailSerializer,
    LeaveBalanceListSerializer,
    LeaveBalanceUpdateSerializer,
    LeaveCancellationSerializer,
    LeaveRejectionSerializer,
    LeaveRequestCreateSerializer,
    LeaveRequestDetailSerializer,
    LeaveRequestListSerializer,
    LeaveRequestUpdateSerializer,
)
from .services import (
    AttendanceService,
    DepartmentService,
    EmployeeService,
    HumanResourcesServiceError,
    LeaveBalanceService,
    LeaveRequestService,
)


def _actor(request: Request) -> str:
    actor = getattr(request.user, "id", getattr(request.user, "pk", None))
    if actor is None:
        raise PermissionDenied("Authenticated actor identifier is required.")
    return str(actor)


def _parse_uuid(value: str | None, field: str) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValidationError({field: ["Must be a valid UUID."]}) from exc


def _parse_date(value: str | None, field: str) -> date | None:
    if value is None:
        return None
    parsed = parse_date(value)
    if parsed is None:
        raise ValidationError({field: ["Must be an ISO-8601 date."]})
    return parsed


def _parse_bool(value: str | None, field: str) -> bool | None:
    if value is None:
        return None
    if value.lower() in {"true", "1"}:
        return True
    if value.lower() in {"false", "0"}:
        return False
    raise ValidationError({field: ["Must be true or false."]})


def _parse_choice(value: str | None, field: str, choices: set[str]) -> str | None:
    if value is not None and value not in choices:
        raise ValidationError({field: ["Unsupported value."]})
    return value


def _idempotency_key(request: Request, body_key: object | None = None) -> str:
    header_key = request.headers.get("Idempotency-Key", "").strip()
    normalized_body = str(body_key).strip() if body_key is not None else ""
    if header_key and normalized_body and header_key != normalized_body:
        raise ValidationError({"idempotency_key": ["Body and Idempotency-Key header must match."]})
    key = header_key or normalized_body
    if not key:
        raise ValidationError({"idempotency_key": ["An idempotency key is required."]})
    if len(key) > 255:
        raise ValidationError({"idempotency_key": ["Must contain at most 255 characters."]})
    return key


class HumanResourcesViewSet(GovernedAPIViewMixin, TenantScopedModelViewSet):  # type: ignore[misc]
    """Shared v2 governance, strict queries, and service-only mutation boundary."""

    authentication_classes = (GovernedSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    pagination_class = GovernedPageNumberPagination
    access_requirements: Mapping[str, AccessRequirement] = {}
    http_method_names = ("get", "post", "patch", "delete", "head", "options")

    def get_permissions(self) -> Sequence[Any]:
        tenant_id = self._get_tenant_id()
        if tenant_id is not None:
            self.request.tenant_id = tenant_id
        requirement = self.access_requirements.get(getattr(self, "action", ""))
        self.required_permission = requirement.permission if requirement else None
        self.required_entitlement = requirement.entitlement if requirement else None
        self.quota_resource = requirement.quota_resource if requirement else None
        self.quota_cost = requirement.quota_cost if requirement else 0
        return super().get_permissions()

    def check_permissions(self, request: Request) -> None:
        method = request.method or ""
        if method.lower() not in self.http_method_names:
            raise MethodNotAllowed(method)
        super().check_permissions(request)

    def tenant_id(self) -> UUID:
        return self._require_tenant_id()

    def correlation_id(self) -> str:
        return str(getattr(self.request, "correlation_id", "") or "")

    def _queryset(self, model: type[Any]) -> QuerySet[Any, Any]:
        self._validate_model(model)
        return model.objects.for_tenant(self.tenant_id()).filter(deleted_at__isnull=True)

    def _validate_query(self, allowed: set[str]) -> None:
        unknown = set(self.request.query_params) - allowed - {"page", "page_size", "format"}
        if unknown:
            raise ValidationError({field: ["Unknown query parameter."] for field in sorted(unknown)})

    def _ordered(
        self,
        queryset: QuerySet[Any, Any],
        mapping: Mapping[str, str],
        default: str,
    ) -> QuerySet[Any, Any]:
        requested = self.request.query_params.get("ordering", default)
        fields: list[str] = []
        for requested_field in requested.split(","):
            descending = requested_field.startswith("-")
            key = requested_field[1:] if descending else requested_field
            if not key or key not in mapping:
                raise ValidationError({"ordering": ["Unsupported ordering field."]})
            resolved = mapping[key]
            fields.append(f"-{resolved}" if descending else resolved)
        return queryset.order_by(*fields, "id")

    def _paginated(self, queryset: QuerySet[Any, Any], serializer_class: type[Any]) -> Response:
        page = self.paginate_queryset(queryset)
        if page is None:
            raise RuntimeError("Governed pagination is required for HR collections.")
        serializer = serializer_class(page, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, HumanResourcesServiceError):
            exc = OperationFailed(
                error_code=exc.error_code,
                message=exc.public_message,
                detail=exc.details,
                http_status=exc.http_status,
            )
        elif isinstance(exc, ObjectDoesNotExist):
            exc = NotFound()
        elif isinstance(exc, StateMachineError):
            exc = OperationFailed(
                error_code="INVALID_STATE_TRANSITION",
                message="The requested state transition is not valid.",
                http_status=status.HTTP_409_CONFLICT,
            )
        elif isinstance(exc, IntegrityError):
            exc = OperationFailed(
                error_code="HR_CONFLICT",
                message="The requested change conflicts with existing HR data.",
                http_status=status.HTTP_409_CONFLICT,
            )
        elif isinstance(exc, DjangoValidationError):
            detail = getattr(exc, "message_dict", None) or {
                "non_field_errors": getattr(exc, "messages", ["Validation failed."])
            }
            exc = OperationFailed(
                error_code="HR_VALIDATION_ERROR",
                message="HR validation failed.",
                detail=detail,
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        return super().handle_exception(exc)


class DepartmentViewSet(HumanResourcesViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentDetailSerializer

    from .permissions import DEPARTMENT_ACTION_PERMISSIONS as access_requirements

    def get_queryset(self) -> QuerySet[Department, Department]:
        queryset = self._queryset(Department).select_related("parent_department", "manager")
        if not hasattr(self, "request"):
            return queryset
        self._validate_query({"is_active", "parent_department", "manager", "search", "ordering"})
        params = self.request.query_params
        active = _parse_bool(params.get("is_active"), "is_active")
        if active is not None:
            queryset = queryset.filter(is_active=active)
        parent_id = _parse_uuid(params.get("parent_department"), "parent_department")
        if parent_id is not None:
            queryset = queryset.filter(parent_department_id=parent_id)
        manager_id = _parse_uuid(params.get("manager"), "manager")
        if manager_id is not None:
            queryset = queryset.filter(manager_id=manager_id)
        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(Q(department_code__icontains=search) | Q(department_name__icontains=search))
        return self._ordered(
            queryset,
            {"department_code": "department_code", "department_name": "department_name", "created_at": "created_at"},
            "department_code",
        )

    def get_serializer_class(self) -> type[Any]:
        return {
            "list": DepartmentListSerializer,
            "create": DepartmentCreateSerializer,
            "partial_update": DepartmentUpdateSerializer,
            "tree": DepartmentTreeSerializer,
        }.get(self.action, DepartmentDetailSerializer)

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        del request, args, kwargs
        return self._paginated(self.get_queryset(), DepartmentListSerializer)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        del args, kwargs
        serializer = DepartmentCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        department = DepartmentService.create_department(
            self.tenant_id(),
            code=values["department_code"],
            name=values["department_name"],
            parent_id=values.get("parent_department_id"),
            manager_id=values.get("manager_id"),
            description=values.get("description", ""),
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(DepartmentDetailSerializer(department).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        department = cast(Department, self.get_object())
        serializer = DepartmentUpdateSerializer(data=request.data, partial=True, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        active_change = values.pop("is_active", None)
        if active_change is True:
            raise OperationFailed(
                error_code="HR_INVALID_TRANSITION",
                message="Department activation is not available through this lifecycle surface.",
                http_status=status.HTTP_409_CONFLICT,
            )
        deactivate = active_change is False
        if values:
            department = DepartmentService.update_department(
                self.tenant_id(),
                department.id,
                changes=values,
                actor_id=_actor(request),
                correlation_id=self.correlation_id(),
            )
        if deactivate:
            department = DepartmentService.deactivate_department(
                self.tenant_id(),
                department.id,
                actor_id=_actor(request),
                correlation_id=self.correlation_id(),
            )
        return Response(DepartmentDetailSerializer(department).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        department = cast(Department, self.get_object())
        DepartmentService.delete_department(
            self.tenant_id(),
            department.id,
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=("get",), url_path="tree")
    def tree(self, request: Request) -> Response:
        self._validate_query({"root_id", "include_inactive"})
        root_id = _parse_uuid(request.query_params.get("root_id"), "root_id")
        include_inactive = _parse_bool(request.query_params.get("include_inactive"), "include_inactive")
        nodes = DepartmentService.get_hierarchy(
            self.tenant_id(), root_id=root_id, include_inactive=bool(include_inactive)
        )
        return Response(DepartmentTreeSerializer(nodes, many=True).data)


class EmployeeViewSet(HumanResourcesViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeDetailSerializer

    from .permissions import EMPLOYEE_ACTION_PERMISSIONS as access_requirements

    def get_queryset(self) -> QuerySet[Employee, Employee]:
        queryset = self._queryset(Employee).select_related("department", "manager")
        if not hasattr(self, "request"):
            return queryset
        if self.action == "reporting_tree":
            self._validate_query({"depth"})
            return queryset
        self._validate_query(
            {
                "department",
                "manager",
                "employment_type",
                "employment_status",
                "hire_date_from",
                "hire_date_to",
                "is_active",
                "search",
                "ordering",
            }
        )
        params = self.request.query_params
        for name in ("department", "manager"):
            value = _parse_uuid(params.get(name), name)
            if value is not None:
                queryset = queryset.filter(**{f"{name}_id": value})
        employment_type = _parse_choice(
            params.get("employment_type"), "employment_type", {"full_time", "part_time", "contractor", "temporary"}
        )
        employment_status = _parse_choice(
            params.get("employment_status"),
            "employment_status",
            {"active", "on_leave", "inactive", "terminated"},
        )
        if employment_type:
            queryset = queryset.filter(employment_type=employment_type)
        if employment_status:
            queryset = queryset.filter(employment_status=employment_status)
        start = _parse_date(params.get("hire_date_from"), "hire_date_from")
        end = _parse_date(params.get("hire_date_to"), "hire_date_to")
        if start and end and start > end:
            raise ValidationError({"hire_date_from": ["Cannot be after hire_date_to."]})
        if start:
            queryset = queryset.filter(hire_date__gte=start)
        if end:
            queryset = queryset.filter(hire_date__lte=end)
        active = _parse_bool(params.get("is_active"), "is_active")
        if active is not None:
            queryset = queryset.filter(is_active=active)
        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(employee_number__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )
        return self._ordered(
            queryset,
            {
                "employee_number": "employee_number",
                "last_name": "last_name",
                "hire_date": "hire_date",
                "created_at": "created_at",
            },
            "employee_number",
        )

    def get_serializer_class(self) -> type[Any]:
        return {
            "list": EmployeeListSerializer,
            "create": EmployeeCreateSerializer,
            "partial_update": EmployeeUpdateSerializer,
            "reporting_tree": EmployeeTreeSerializer,
            "activate": EmployeeTransitionSerializer,
            "deactivate": EmployeeTransitionSerializer,
            "place_on_leave": EmployeeTransitionSerializer,
            "return_from_leave": EmployeeTransitionSerializer,
            "terminate": EmployeeTransitionSerializer,
        }.get(self.action, EmployeeDetailSerializer)

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        del request, args, kwargs
        return self._paginated(self.get_queryset(), EmployeeListSerializer)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        del args, kwargs
        serializer = EmployeeCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        employee = EmployeeService.create_employee(
            self.tenant_id(),
            data=dict(serializer.validated_data),
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(EmployeeDetailSerializer(employee).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        employee = cast(Employee, self.get_object())
        serializer = EmployeeUpdateSerializer(data=request.data, partial=True, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        employee = EmployeeService.update_employee(
            self.tenant_id(),
            employee.id,
            changes=dict(serializer.validated_data),
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(EmployeeDetailSerializer(employee).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        employee = cast(Employee, self.get_object())
        EmployeeService.delete_employee(
            self.tenant_id(),
            employee.id,
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("get",), url_path="reporting-tree")
    def reporting_tree(self, request: Request, pk: str | None = None) -> Response:
        employee = cast(Employee, self.get_object())
        raw_depth = request.query_params.get("depth", "5")
        try:
            depth = int(raw_depth)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"depth": ["Must be an integer."]}) from exc
        if not 1 <= depth <= 10:
            raise ValidationError({"depth": ["Must be between 1 and 10."]})
        tree = EmployeeService.get_reporting_tree(self.tenant_id(), employee.id, depth=depth)
        return Response(EmployeeTreeSerializer(tree).data)

    def _transition(self, request: Request, command: str) -> Response:
        employee = cast(Employee, self.get_object())
        serializer = EmployeeTransitionSerializer(
            data=request.data,
            context={**self.get_serializer_context(), "command": command},
        )
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        key = _idempotency_key(request, values["transition_key"])
        employee = EmployeeService.transition_employee(
            self.tenant_id(),
            employee.id,
            command=command,
            transition_key=key,
            effective_date=values.get("effective_date"),
            reason=values.get("reason", ""),
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(EmployeeDetailSerializer(employee).data)

    @action(detail=True, methods=("post",))
    def activate(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, "activate")

    @action(detail=True, methods=("post",))
    def deactivate(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, "deactivate")

    @action(detail=True, methods=("post",), url_path="place-on-leave")
    def place_on_leave(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, "place_on_leave")

    @action(detail=True, methods=("post",), url_path="return-from-leave")
    def return_from_leave(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, "return_from_leave")

    @action(detail=True, methods=("post",))
    def terminate(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, "terminate")


class AttendanceViewSet(HumanResourcesViewSet):
    queryset = Attendance.objects.all()
    serializer_class = AttendanceDetailSerializer

    from .permissions import ATTENDANCE_ACTION_PERMISSIONS as access_requirements

    def get_queryset(self) -> QuerySet[Attendance, Attendance]:
        queryset = self._queryset(Attendance).select_related("employee")
        if not hasattr(self, "request"):
            return queryset
        self._validate_query(
            {"employee", "status", "source", "attendance_date_from", "attendance_date_to", "search", "ordering"}
        )
        params = self.request.query_params
        employee = _parse_uuid(params.get("employee"), "employee")
        if employee:
            queryset = queryset.filter(employee_id=employee)
        attendance_status = _parse_choice(
            params.get("status"), "status", {"present", "absent", "late", "half_day", "on_leave"}
        )
        source = _parse_choice(params.get("source"), "source", {"manual", "clock", "import"})
        if attendance_status:
            queryset = queryset.filter(status=attendance_status)
        if source:
            queryset = queryset.filter(source=source)
        start = _parse_date(params.get("attendance_date_from"), "attendance_date_from")
        end = _parse_date(params.get("attendance_date_to"), "attendance_date_to")
        if start and end and start > end:
            raise ValidationError({"attendance_date_from": ["Cannot be after attendance_date_to."]})
        if start:
            queryset = queryset.filter(attendance_date__gte=start)
        if end:
            queryset = queryset.filter(attendance_date__lte=end)
        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(employee__employee_number__icontains=search)
                | Q(employee__first_name__icontains=search)
                | Q(employee__last_name__icontains=search)
            )
        return self._ordered(
            queryset,
            {"attendance_date": "attendance_date", "hours_worked": "hours_worked", "created_at": "created_at"},
            "-attendance_date",
        )

    def get_serializer_class(self) -> type[Any]:
        return {
            "list": AttendanceListSerializer,
            "create": AttendanceCreateSerializer,
            "partial_update": AttendanceUpdateSerializer,
            "clock_in": ClockInSerializer,
            "clock_out": ClockOutSerializer,
        }.get(self.action, AttendanceDetailSerializer)

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        del request, args, kwargs
        return self._paginated(self.get_queryset(), AttendanceListSerializer)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        del args, kwargs
        serializer = AttendanceCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        attendance = AttendanceService.create_attendance(
            self.tenant_id(),
            data=dict(serializer.validated_data),
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(AttendanceDetailSerializer(attendance).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        attendance = cast(Attendance, self.get_object())
        serializer = AttendanceUpdateSerializer(data=request.data, partial=True, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        attendance = AttendanceService.update_attendance(
            self.tenant_id(),
            attendance.id,
            changes=dict(serializer.validated_data),
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(AttendanceDetailSerializer(attendance).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        attendance = cast(Attendance, self.get_object())
        AttendanceService.delete_attendance(
            self.tenant_id(),
            attendance.id,
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=("post",), url_path="clock-in")
    def clock_in(self, request: Request) -> Response:
        serializer = ClockInSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        key = _idempotency_key(request, values["idempotency_key"])
        attendance = AttendanceService.clock_in(
            self.tenant_id(),
            employee_id=values["employee_id"],
            occurred_at=values.get("occurred_at"),
            actor_id=_actor(request),
            idempotency_key=key,
            correlation_id=self.correlation_id(),
        )
        return Response(AttendanceDetailSerializer(attendance).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("post",), url_path="clock-out")
    def clock_out(self, request: Request, pk: str | None = None) -> Response:
        attendance = cast(Attendance, self.get_object())
        serializer = ClockOutSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        key = _idempotency_key(request, values["idempotency_key"])
        attendance = AttendanceService.clock_out(
            self.tenant_id(),
            attendance.id,
            occurred_at=values.get("occurred_at"),
            actor_id=_actor(request),
            idempotency_key=key,
            correlation_id=self.correlation_id(),
        )
        return Response(AttendanceDetailSerializer(attendance).data)


class LeaveBalanceViewSet(HumanResourcesViewSet):
    queryset = LeaveBalance.objects.all()
    serializer_class = LeaveBalanceDetailSerializer

    from .permissions import LEAVE_BALANCE_ACTION_PERMISSIONS as access_requirements

    def get_queryset(self) -> QuerySet[LeaveBalance, LeaveBalance]:
        queryset = self._queryset(LeaveBalance).select_related("employee")
        if not hasattr(self, "request"):
            return queryset
        self._validate_query({"employee", "leave_type", "period_start", "period_end", "active_period", "ordering"})
        params = self.request.query_params
        employee = _parse_uuid(params.get("employee"), "employee")
        if employee:
            queryset = queryset.filter(employee_id=employee)
        leave_type = _parse_choice(
            params.get("leave_type"),
            "leave_type",
            {"annual", "sick", "personal", "maternity", "paternity", "unpaid"},
        )
        if leave_type:
            queryset = queryset.filter(leave_type=leave_type)
        period_start = _parse_date(params.get("period_start"), "period_start")
        period_end = _parse_date(params.get("period_end"), "period_end")
        if period_start and period_end and period_start > period_end:
            raise ValidationError({"period_start": ["Cannot be after period_end."]})
        if period_start:
            queryset = queryset.filter(period_start__gte=period_start)
        if period_end:
            queryset = queryset.filter(period_end__lte=period_end)
        active = _parse_bool(params.get("active_period"), "active_period")
        if active is not None:
            today = timezone.localdate()
            if active:
                queryset = queryset.filter(period_start__lte=today, period_end__gte=today)
            else:
                queryset = queryset.filter(Q(period_start__gt=today) | Q(period_end__lt=today))
        queryset = queryset.annotate(
            _remaining_days=ExpressionWrapper(
                F("entitled_days") + F("carried_days") - F("used_days") - F("pending_days"),
                output_field=DecimalField(max_digits=7, decimal_places=2),
            )
        )
        return self._ordered(
            queryset,
            {
                "employee": "employee__employee_number",
                "leave_type": "leave_type",
                "period_start": "period_start",
                "remaining_days": "_remaining_days",
            },
            "-period_start",
        )

    def get_serializer_class(self) -> type[Any]:
        return {
            "list": LeaveBalanceListSerializer,
            "create": LeaveBalanceCreateSerializer,
            "partial_update": LeaveBalanceUpdateSerializer,
        }.get(self.action, LeaveBalanceDetailSerializer)

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        del request, args, kwargs
        return self._paginated(self.get_queryset(), LeaveBalanceListSerializer)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        del args, kwargs
        serializer = LeaveBalanceCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        balance = LeaveBalanceService.create_balance(
            self.tenant_id(),
            data=dict(serializer.validated_data),
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(LeaveBalanceDetailSerializer(balance).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        balance = cast(LeaveBalance, self.get_object())
        serializer = LeaveBalanceUpdateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        balance = LeaveBalanceService.update_allocation(
            self.tenant_id(),
            balance.id,
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
            **serializer.validated_data,
        )
        return Response(LeaveBalanceDetailSerializer(balance).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        balance = cast(LeaveBalance, self.get_object())
        LeaveBalanceService.delete_balance(
            self.tenant_id(),
            balance.id,
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class LeaveRequestViewSet(HumanResourcesViewSet):
    queryset = LeaveRequest.objects.all()
    serializer_class = LeaveRequestDetailSerializer

    from .permissions import LEAVE_REQUEST_ACTION_PERMISSIONS as access_requirements

    def get_queryset(self) -> QuerySet[LeaveRequest, LeaveRequest]:
        queryset = self._queryset(LeaveRequest).select_related("employee", "leave_balance")
        if not hasattr(self, "request"):
            return queryset
        self._validate_query(
            {"employee", "leave_type", "status", "start_date", "end_date", "scope", "search", "ordering"}
        )
        params = self.request.query_params
        scope = params.get("scope", "all")
        if scope not in {"all", "self", "team", "approval_queue"}:
            raise ValidationError({"scope": ["Unsupported leave scope."]})
        if scope in {"self", "team"}:
            raise CapabilityUnavailable(
                capability="human_resources.actor_employee_scope",
                detail={"scope": scope, "reason_code": "ACTOR_EMPLOYEE_RESOLUTION_UNAVAILABLE"},
            )
        if scope == "approval_queue":
            queryset = queryset.filter(status="pending")
        employee = _parse_uuid(params.get("employee"), "employee")
        if employee:
            queryset = queryset.filter(employee_id=employee)
        leave_type = _parse_choice(
            params.get("leave_type"),
            "leave_type",
            {"annual", "sick", "personal", "maternity", "paternity", "unpaid"},
        )
        request_status = _parse_choice(params.get("status"), "status", {"pending", "approved", "rejected", "cancelled"})
        if leave_type:
            queryset = queryset.filter(leave_type=leave_type)
        if request_status:
            queryset = queryset.filter(status=request_status)
        overlap_start = _parse_date(params.get("start_date"), "start_date")
        overlap_end = _parse_date(params.get("end_date"), "end_date")
        if overlap_start and overlap_end and overlap_start > overlap_end:
            raise ValidationError({"start_date": ["Cannot be after end_date."]})
        if overlap_start:
            queryset = queryset.filter(end_date__gte=overlap_start)
        if overlap_end:
            queryset = queryset.filter(start_date__lte=overlap_end)
        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(employee__employee_number__icontains=search)
                | Q(employee__first_name__icontains=search)
                | Q(employee__last_name__icontains=search)
            )
        return self._ordered(
            queryset,
            {
                "start_date": "start_date",
                "days_requested": "days_requested",
                "status": "status",
                "created_at": "created_at",
            },
            "-start_date",
        )

    def get_serializer_class(self) -> type[Any]:
        return {
            "list": LeaveRequestListSerializer,
            "create": LeaveRequestCreateSerializer,
            "partial_update": LeaveRequestUpdateSerializer,
            "approve": LeaveApprovalSerializer,
            "reject": LeaveRejectionSerializer,
            "cancel": LeaveCancellationSerializer,
        }.get(self.action, LeaveRequestDetailSerializer)

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        del request, args, kwargs
        return self._paginated(self.get_queryset(), LeaveRequestListSerializer)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        del args, kwargs
        serializer = LeaveRequestCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        key = _idempotency_key(request, values.pop("idempotency_key"))
        leave_request = LeaveRequestService.submit_request(
            self.tenant_id(),
            data=values,
            actor_id=_actor(request),
            idempotency_key=key,
            correlation_id=self.correlation_id(),
        )
        return Response(LeaveRequestDetailSerializer(leave_request).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        leave_request = cast(LeaveRequest, self.get_object())
        serializer = LeaveRequestUpdateSerializer(
            data=request.data, partial=True, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        leave_request = LeaveRequestService.update_pending_request(
            self.tenant_id(),
            leave_request.id,
            changes=dict(serializer.validated_data),
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(LeaveRequestDetailSerializer(leave_request).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        leave_request = cast(LeaveRequest, self.get_object())
        transition_key = _idempotency_key(request)
        LeaveRequestService.delete_request(
            self.tenant_id(),
            leave_request.id,
            transition_key=transition_key,
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",))
    def approve(self, request: Request, pk: str | None = None) -> Response:
        leave_request = cast(LeaveRequest, self.get_object())
        serializer = LeaveApprovalSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        key = _idempotency_key(request, serializer.validated_data["transition_key"])
        leave_request = LeaveRequestService.approve_request(
            self.tenant_id(),
            leave_request.id,
            transition_key=key,
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(LeaveRequestDetailSerializer(leave_request).data)

    @action(detail=True, methods=("post",))
    def reject(self, request: Request, pk: str | None = None) -> Response:
        leave_request = cast(LeaveRequest, self.get_object())
        serializer = LeaveRejectionSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        key = _idempotency_key(request, values["transition_key"])
        leave_request = LeaveRequestService.reject_request(
            self.tenant_id(),
            leave_request.id,
            transition_key=key,
            rejection_reason=values["rejection_reason"],
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(LeaveRequestDetailSerializer(leave_request).data)

    @action(detail=True, methods=("post",))
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        leave_request = cast(LeaveRequest, self.get_object())
        serializer = LeaveCancellationSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        key = _idempotency_key(request, serializer.validated_data["transition_key"])
        leave_request = LeaveRequestService.cancel_request(
            self.tenant_id(),
            leave_request.id,
            transition_key=key,
            actor_id=_actor(request),
            correlation_id=self.correlation_id(),
        )
        return Response(LeaveRequestDetailSerializer(leave_request).data)


__all__ = [
    "AttendanceViewSet",
    "DepartmentViewSet",
    "EmployeeViewSet",
    "HumanResourcesViewSet",
    "LeaveBalanceViewSet",
    "LeaveRequestViewSet",
]
