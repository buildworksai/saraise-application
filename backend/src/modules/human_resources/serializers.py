"""Strict operation-specific serializers for the governed HR API v2."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from rest_framework.exceptions import NotFound

from .models import Attendance, Department, Employee, LeaveBalance, LeaveRequest

EMPLOYMENT_TYPES = ("full_time", "part_time", "contractor", "temporary")
ATTENDANCE_STATUSES = ("present", "absent", "late", "half_day", "on_leave")
LEAVE_TYPES = ("annual", "sick", "personal", "maternity", "paternity", "unpaid")

COMMON_READ_FIELDS = (
    "id",
    "tenant_id",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
    "deleted_at",
    "deleted_by",
)


class StrictInputMixin:
    """Reject undeclared properties instead of silently discarding them."""

    def to_internal_value(self, data: Any) -> Any:
        if not isinstance(data, dict):
            raise serializers.ValidationError({"non_field_errors": ["Expected a JSON object."]})
        unknown = set(data) - set(self.fields)  # type: ignore[attr-defined]
        if unknown:
            raise serializers.ValidationError({field: ["Unknown field."] for field in sorted(unknown)})
        return super().to_internal_value(data)  # type: ignore[misc]


class CommandSerializer(StrictInputMixin, serializers.Serializer):
    """Base for service commands; it intentionally has no persistence methods."""


def _tenant_id(serializer: serializers.BaseSerializer[Any]) -> UUID:
    raw = serializer.context.get("tenant_id")
    if raw is None:
        request = serializer.context.get("request")
        user = getattr(request, "user", None)
        try:
            raw = getattr(getattr(user, "profile", None), "tenant_id", None)
        except (AttributeError, ObjectDoesNotExist):
            raw = None
    try:
        return raw if isinstance(raw, UUID) else UUID(str(raw))
    except (AttributeError, TypeError, ValueError) as exc:
        raise serializers.ValidationError("Authenticated tenant context is required.") from exc


def _related_exists(
    serializer: serializers.BaseSerializer[Any],
    model: type[Department] | type[Employee] | type[LeaveBalance],
    value: UUID | None,
    field: str,
) -> UUID | None:
    if value is None:
        return None
    tenant_id = _tenant_id(serializer)
    if not model.objects.for_tenant(tenant_id).filter(pk=value, deleted_at__isnull=True).exists():
        # Deliberately indistinguishable from an unknown identifier.
        raise NotFound(f"The related resource in {field} was not found.")
    return value


class DepartmentListSerializer(serializers.ModelSerializer):
    parent_department = serializers.UUIDField(source="parent_department_id", allow_null=True)
    parent_department_name = serializers.CharField(source="parent_department.department_name", allow_null=True)
    manager = serializers.UUIDField(source="manager_id", allow_null=True)
    manager_name = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = (
            *COMMON_READ_FIELDS,
            "department_code",
            "department_name",
            "parent_department",
            "parent_department_name",
            "manager",
            "manager_name",
            "is_active",
            "description",
        )

    def get_manager_name(self, obj: Department) -> str | None:
        manager = cast(Employee | None, getattr(obj, "manager", None))
        return f"{manager.first_name} {manager.last_name}".strip() if manager else None


class DepartmentDetailSerializer(DepartmentListSerializer):
    """Department detail currently adds no sensitive employee projection."""


class DepartmentCreateSerializer(CommandSerializer):
    department_code = serializers.CharField(max_length=50, trim_whitespace=True)
    department_name = serializers.CharField(max_length=255, trim_whitespace=True)
    parent_department_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    manager_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    description = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_parent_department_id(self, value: UUID | None) -> UUID | None:
        return _related_exists(self, Department, value, "parent_department_id")

    def validate_manager_id(self, value: UUID | None) -> UUID | None:
        return _related_exists(self, Employee, value, "manager_id")


class DepartmentUpdateSerializer(CommandSerializer):
    department_code = serializers.CharField(max_length=50, trim_whitespace=True, required=False)
    department_name = serializers.CharField(max_length=255, trim_whitespace=True, required=False)
    parent_department_id = serializers.UUIDField(required=False, allow_null=True)
    manager_id = serializers.UUIDField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)

    def validate_parent_department_id(self, value: UUID | None) -> UUID | None:
        return _related_exists(self, Department, value, "parent_department_id")

    def validate_manager_id(self, value: UUID | None) -> UUID | None:
        return _related_exists(self, Employee, value, "manager_id")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs:
            raise serializers.ValidationError({"non_field_errors": ["At least one change is required."]})
        return attrs


class DepartmentTreeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    department_code = serializers.CharField()
    department_name = serializers.CharField()
    manager = serializers.UUIDField(source="manager_id", allow_null=True)
    manager_name = serializers.SerializerMethodField()
    is_active = serializers.BooleanField()
    children = serializers.SerializerMethodField()

    def get_manager_name(self, obj: object) -> str | None:
        resolved_name = getattr(obj, "manager_name", None)
        if resolved_name is not None:
            return str(resolved_name)
        manager_id = getattr(obj, "manager_id", None)
        if manager_id is None and isinstance(obj, dict):
            manager_id = obj.get("manager_id") or obj.get("manager")
        names = self.context.get("manager_names", {})
        return names.get(manager_id) if isinstance(names, dict) else None

    def get_children(self, obj: object) -> list[dict[str, Any]]:
        children = getattr(obj, "children", None)
        if children is None and isinstance(obj, dict):
            children = obj.get("children", ())
        return cast(
            list[dict[str, Any]],
            DepartmentTreeSerializer(children or (), many=True, context=self.context).data,
        )


class EmployeeListSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    department = serializers.UUIDField(source="department_id", allow_null=True)
    department_name = serializers.CharField(source="department.department_name", allow_null=True)
    manager = serializers.UUIDField(source="manager_id", allow_null=True)
    manager_name = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = (
            *COMMON_READ_FIELDS,
            "employee_number",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "phone",
            "department",
            "department_name",
            "manager",
            "manager_name",
            "position",
            "hire_date",
            "employment_type",
            "employment_status",
            "is_active",
            "termination_date",
        )

    def get_full_name(self, obj: Employee) -> str:
        return f"{obj.first_name} {obj.last_name}".strip()

    def get_manager_name(self, obj: Employee) -> str | None:
        manager = cast(Employee | None, getattr(obj, "manager", None))
        return f"{manager.first_name} {manager.last_name}".strip() if manager else None


class EmployeeDetailSerializer(EmployeeListSerializer):
    class Meta:
        model = Employee
        fields = (*EmployeeListSerializer.Meta.fields, "termination_reason", "transition_history")


class EmployeeCreateSerializer(CommandSerializer):
    employee_number = serializers.CharField(max_length=50, trim_whitespace=True)
    first_name = serializers.CharField(max_length=100, trim_whitespace=True)
    last_name = serializers.CharField(max_length=100, trim_whitespace=True)
    email = serializers.EmailField(max_length=255)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    department_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    manager_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    position = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    hire_date = serializers.DateField()
    employment_type = serializers.ChoiceField(choices=EMPLOYMENT_TYPES)

    def validate_department_id(self, value: UUID | None) -> UUID | None:
        return _related_exists(self, Department, value, "department_id")

    def validate_manager_id(self, value: UUID | None) -> UUID | None:
        return _related_exists(self, Employee, value, "manager_id")


class EmployeeUpdateSerializer(CommandSerializer):
    employee_number = serializers.CharField(max_length=50, trim_whitespace=True, required=False)
    first_name = serializers.CharField(max_length=100, trim_whitespace=True, required=False)
    last_name = serializers.CharField(max_length=100, trim_whitespace=True, required=False)
    email = serializers.EmailField(max_length=255, required=False)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    department_id = serializers.UUIDField(required=False, allow_null=True)
    manager_id = serializers.UUIDField(required=False, allow_null=True)
    position = serializers.CharField(max_length=100, required=False, allow_blank=True)
    hire_date = serializers.DateField(required=False)
    employment_type = serializers.ChoiceField(choices=EMPLOYMENT_TYPES, required=False)

    def validate_department_id(self, value: UUID | None) -> UUID | None:
        return _related_exists(self, Department, value, "department_id")

    def validate_manager_id(self, value: UUID | None) -> UUID | None:
        return _related_exists(self, Employee, value, "manager_id")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs:
            raise serializers.ValidationError({"non_field_errors": ["At least one change is required."]})
        return attrs


class EmployeeTransitionSerializer(CommandSerializer):
    transition_key = serializers.CharField(min_length=1, max_length=255, trim_whitespace=True)
    effective_date = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if self.context.get("command") == "terminate":
            if attrs.get("effective_date") is None:
                raise serializers.ValidationError({"effective_date": ["This field is required."]})
            if not str(attrs.get("reason", "")).strip():
                raise serializers.ValidationError({"reason": ["This field is required."]})
        return attrs


class EmployeeTreeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    employee_number = serializers.CharField()
    full_name = serializers.CharField()
    position = serializers.CharField()
    employment_status = serializers.CharField()
    direct_reports = serializers.SerializerMethodField()

    def get_direct_reports(self, obj: object) -> list[dict[str, Any]]:
        reports = getattr(obj, "children", None)
        if reports is None and isinstance(obj, dict):
            reports = obj.get("direct_reports", obj.get("children", ()))
        return cast(list[dict[str, Any]], EmployeeTreeSerializer(reports or (), many=True).data)


class AttendanceListSerializer(serializers.ModelSerializer):
    employee = serializers.UUIDField(source="employee_id")
    employee_number = serializers.CharField(source="employee.employee_number")
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = Attendance
        fields = (
            *COMMON_READ_FIELDS,
            "employee",
            "employee_number",
            "employee_name",
            "attendance_date",
            "check_in_time",
            "check_out_time",
            "hours_worked",
            "status",
            "source",
            "notes",
        )

    def get_employee_name(self, obj: Attendance) -> str:
        employee = cast(Employee, getattr(obj, "employee"))
        return f"{employee.first_name} {employee.last_name}".strip()


class AttendanceDetailSerializer(AttendanceListSerializer):
    """Attendance detail excludes all employee contact information."""


class AttendanceCreateSerializer(CommandSerializer):
    employee_id = serializers.UUIDField()
    attendance_date = serializers.DateField()
    check_in_time = serializers.DateTimeField(required=False, allow_null=True, default=None)
    check_out_time = serializers.DateTimeField(required=False, allow_null=True, default=None)
    status = serializers.ChoiceField(choices=ATTENDANCE_STATUSES)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_employee_id(self, value: UUID) -> UUID:
        return _related_exists(self, Employee, value, "employee_id")  # type: ignore[return-value]


class AttendanceUpdateSerializer(CommandSerializer):
    check_in_time = serializers.DateTimeField(required=False, allow_null=True)
    check_out_time = serializers.DateTimeField(required=False, allow_null=True)
    hours_worked = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=24, required=False)
    status = serializers.ChoiceField(choices=ATTENDANCE_STATUSES, required=False)
    notes = serializers.CharField(allow_blank=False, trim_whitespace=True)


class ClockInSerializer(CommandSerializer):
    employee_id = serializers.UUIDField()
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    idempotency_key = serializers.CharField(min_length=1, max_length=255, trim_whitespace=True)

    def validate_employee_id(self, value: UUID) -> UUID:
        return _related_exists(self, Employee, value, "employee_id")  # type: ignore[return-value]


class ClockOutSerializer(CommandSerializer):
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    idempotency_key = serializers.CharField(min_length=1, max_length=255, trim_whitespace=True)


class LeaveBalanceListSerializer(serializers.ModelSerializer):
    employee = serializers.UUIDField(source="employee_id")
    employee_number = serializers.CharField(source="employee.employee_number")
    employee_name = serializers.SerializerMethodField()
    remaining_days = serializers.DecimalField(max_digits=7, decimal_places=2, read_only=True)

    class Meta:
        model = LeaveBalance
        fields = (
            *COMMON_READ_FIELDS,
            "employee",
            "employee_number",
            "employee_name",
            "leave_type",
            "period_start",
            "period_end",
            "entitled_days",
            "carried_days",
            "used_days",
            "pending_days",
            "remaining_days",
            "adjustment_version",
            "last_adjusted_by",
            "adjustment_note",
        )

    def get_employee_name(self, obj: LeaveBalance) -> str:
        employee = cast(Employee, getattr(obj, "employee"))
        return f"{employee.first_name} {employee.last_name}".strip()


class LeaveBalanceDetailSerializer(LeaveBalanceListSerializer):
    """Allocation detail uses the same safe employee projection as the list."""


class LeaveBalanceCreateSerializer(CommandSerializer):
    employee_id = serializers.UUIDField()
    leave_type = serializers.ChoiceField(choices=LEAVE_TYPES)
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    entitled_days = serializers.DecimalField(max_digits=7, decimal_places=2, min_value=0)
    carried_days = serializers.DecimalField(
        max_digits=7,
        decimal_places=2,
        min_value=0,
        required=False,
        default=Decimal("0"),
    )

    def validate_employee_id(self, value: UUID) -> UUID:
        return _related_exists(self, Employee, value, "employee_id")  # type: ignore[return-value]


class LeaveBalanceUpdateSerializer(CommandSerializer):
    entitled_days = serializers.DecimalField(max_digits=7, decimal_places=2, min_value=0)
    carried_days = serializers.DecimalField(max_digits=7, decimal_places=2, min_value=0)
    expected_version = serializers.IntegerField(min_value=1)
    note = serializers.CharField(min_length=1, trim_whitespace=True)


class LeaveRequestListSerializer(serializers.ModelSerializer):
    employee = serializers.UUIDField(source="employee_id")
    employee_number = serializers.CharField(source="employee.employee_number")
    employee_name = serializers.SerializerMethodField()
    leave_balance = serializers.UUIDField(source="leave_balance_id")

    class Meta:
        model = LeaveRequest
        fields = (
            *COMMON_READ_FIELDS,
            "employee",
            "employee_number",
            "employee_name",
            "leave_balance",
            "leave_type",
            "start_date",
            "end_date",
            "days_requested",
            "reason",
            "status",
            "approved_by",
            "approved_at",
            "rejection_reason",
            "cancelled_by",
            "cancelled_at",
        )

    def get_employee_name(self, obj: LeaveRequest) -> str:
        employee = cast(Employee, getattr(obj, "employee"))
        return f"{employee.first_name} {employee.last_name}".strip()


class LeaveRequestDetailSerializer(LeaveRequestListSerializer):
    class Meta:
        model = LeaveRequest
        fields = (*LeaveRequestListSerializer.Meta.fields, "transition_history")


class LeaveRequestCreateSerializer(CommandSerializer):
    employee_id = serializers.UUIDField()
    leave_balance_id = serializers.UUIDField()
    leave_type = serializers.ChoiceField(choices=LEAVE_TYPES)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(min_length=1, max_length=255, trim_whitespace=True, write_only=True)

    def validate_employee_id(self, value: UUID) -> UUID:
        return _related_exists(self, Employee, value, "employee_id")  # type: ignore[return-value]

    def validate_leave_balance_id(self, value: UUID) -> UUID:
        return _related_exists(self, LeaveBalance, value, "leave_balance_id")  # type: ignore[return-value]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        tenant_id = _tenant_id(self)
        balance = (
            LeaveBalance.objects.for_tenant(tenant_id)
            .filter(pk=attrs["leave_balance_id"], deleted_at__isnull=True)
            .first()
        )
        if balance and (balance.employee_id != attrs["employee_id"] or balance.leave_type != attrs["leave_type"]):
            raise serializers.ValidationError(
                {"leave_balance_id": ["The balance does not match the employee and leave type."]}
            )
        return attrs


class LeaveRequestUpdateSerializer(CommandSerializer):
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs:
            raise serializers.ValidationError({"non_field_errors": ["At least one change is required."]})
        return attrs


class LeaveApprovalSerializer(CommandSerializer):
    transition_key = serializers.CharField(min_length=1, max_length=255, trim_whitespace=True)


class LeaveRejectionSerializer(LeaveApprovalSerializer):
    rejection_reason = serializers.CharField(min_length=1, trim_whitespace=True)


class LeaveCancellationSerializer(LeaveApprovalSerializer):
    """Cancellation has the same idempotent transition payload as approval."""


__all__ = [
    "AttendanceCreateSerializer",
    "AttendanceDetailSerializer",
    "AttendanceListSerializer",
    "AttendanceUpdateSerializer",
    "ClockInSerializer",
    "ClockOutSerializer",
    "DepartmentCreateSerializer",
    "DepartmentDetailSerializer",
    "DepartmentListSerializer",
    "DepartmentTreeSerializer",
    "DepartmentUpdateSerializer",
    "EmployeeCreateSerializer",
    "EmployeeDetailSerializer",
    "EmployeeListSerializer",
    "EmployeeTransitionSerializer",
    "EmployeeTreeSerializer",
    "EmployeeUpdateSerializer",
    "LeaveApprovalSerializer",
    "LeaveBalanceCreateSerializer",
    "LeaveBalanceDetailSerializer",
    "LeaveBalanceListSerializer",
    "LeaveBalanceUpdateSerializer",
    "LeaveCancellationSerializer",
    "LeaveRejectionSerializer",
    "LeaveRequestCreateSerializer",
    "LeaveRequestDetailSerializer",
    "LeaveRequestListSerializer",
    "LeaveRequestUpdateSerializer",
]
