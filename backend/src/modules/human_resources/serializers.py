"""
DRF Serializers for Human Resources module.
"""

from rest_framework import serializers

from .models import Attendance, Department, Employee, LeaveRequest


class DepartmentSerializer(serializers.ModelSerializer):
    """Department serializer."""

    class Meta:
        model = Department
        fields = [
            "id",
            "tenant_id",
            "department_code",
            "department_name",
            "parent_department_id",
            "manager_id",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class EmployeeSerializer(serializers.ModelSerializer):
    """Employee serializer."""

    class Meta:
        model = Employee
        fields = [
            "id",
            "tenant_id",
            "employee_number",
            "first_name",
            "last_name",
            "email",
            "phone",
            "department",
            "position",
            "hire_date",
            "employment_type",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class AttendanceSerializer(serializers.ModelSerializer):
    """Attendance serializer."""

    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    employee_name = serializers.CharField(source="employee.first_name", read_only=True)

    class Meta:
        model = Attendance
        fields = [
            "id",
            "tenant_id",
            "employee",
            "employee_number",
            "employee_name",
            "attendance_date",
            "check_in_time",
            "check_out_time",
            "hours_worked",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class LeaveRequestSerializer(serializers.ModelSerializer):
    """LeaveRequest serializer."""

    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    employee_name = serializers.CharField(source="employee.first_name", read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "tenant_id",
            "employee",
            "employee_number",
            "employee_name",
            "leave_type",
            "start_date",
            "end_date",
            "days_requested",
            "reason",
            "status",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "approved_by", "approved_at", "created_at", "updated_at"]
