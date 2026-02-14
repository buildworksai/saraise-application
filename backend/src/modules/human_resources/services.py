"""
Business logic services for Human Resources module.
"""

from typing import Optional

from .models import Department, Employee


class DepartmentService:
    """Service for department operations."""

    @staticmethod
    def create_department(tenant_id: str, department_code: str, department_name: str, **kwargs) -> Department:
        """Create a new department."""
        return Department.objects.create(
            tenant_id=tenant_id,
            department_code=department_code,
            department_name=department_name,
            **kwargs,
        )


class EmployeeService:
    """Service for employee operations."""

    @staticmethod
    def create_employee(tenant_id: str, employee_number: str, first_name: str, last_name: str, **kwargs) -> Employee:
        """Create a new employee."""
        return Employee.objects.create(
            tenant_id=tenant_id,
            employee_number=employee_number,
            first_name=first_name,
            last_name=last_name,
            **kwargs,
        )
