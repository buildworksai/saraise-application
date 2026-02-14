"""
DRF ViewSets for Human Resources module.
"""

import uuid
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import Attendance, Department, Employee, LeaveRequest
from .serializers import (
    AttendanceSerializer,
    DepartmentSerializer,
    EmployeeSerializer,
    LeaveRequestSerializer,
)


class DepartmentViewSet(viewsets.ModelViewSet):
    """ViewSet for Department CRUD operations."""

    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter departments by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return Department.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Department.objects.none()

        queryset = Department.objects.filter(tenant_id=tenant_id, is_active=True)
        return queryset.order_by("department_code")

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            raise PermissionDenied("User must belong to a tenant")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise PermissionDenied("Invalid tenant_id format")

        serializer.save(tenant_id=tenant_id)


class EmployeeViewSet(viewsets.ModelViewSet):
    """ViewSet for Employee CRUD operations."""

    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter employees by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return Employee.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Employee.objects.none()

        queryset = Employee.objects.filter(tenant_id=tenant_id, is_active=True)
        return queryset.order_by("employee_number")

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            raise PermissionDenied("User must belong to a tenant")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise PermissionDenied("Invalid tenant_id format")

        serializer.save(tenant_id=tenant_id)


class AttendanceViewSet(viewsets.ModelViewSet):
    """ViewSet for Attendance CRUD operations."""

    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter attendances by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return Attendance.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Attendance.objects.none()

        queryset = Attendance.objects.filter(tenant_id=tenant_id)
        return queryset.order_by("-attendance_date")

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            raise PermissionDenied("User must belong to a tenant")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise PermissionDenied("Invalid tenant_id format")

        serializer.save(tenant_id=tenant_id)


class LeaveRequestViewSet(viewsets.ModelViewSet):
    """ViewSet for LeaveRequest CRUD operations."""

    serializer_class = LeaveRequestSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter leave requests by tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return LeaveRequest.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return LeaveRequest.objects.none()

        queryset = LeaveRequest.objects.filter(tenant_id=tenant_id)
        return queryset.order_by("-start_date")

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            raise PermissionDenied("User must belong to a tenant")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            raise PermissionDenied("Invalid tenant_id format")

        serializer.save(tenant_id=tenant_id)
