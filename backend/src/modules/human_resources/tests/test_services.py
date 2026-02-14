"""
Service tests for Human Resources module.
"""

import uuid
import pytest
from datetime import date

from src.modules.human_resources.models import Department, Employee
from src.modules.human_resources.services import DepartmentService, EmployeeService


@pytest.mark.django_db
class TestDepartmentService:
    """Test DepartmentService."""

    def test_create_department(self):
        """Test creating a department via service."""
        tenant_id = uuid.uuid4()
        department = DepartmentService.create_department(
            tenant_id=str(tenant_id),
            department_code="DEPT-001",
            department_name="Engineering",
        )

        assert department.department_code == "DEPT-001"
        assert department.department_name == "Engineering"
        assert str(department.tenant_id) == str(tenant_id)


@pytest.mark.django_db
class TestEmployeeService:
    """Test EmployeeService."""

    def test_create_employee(self):
        """Test creating an employee via service."""
        tenant_id = uuid.uuid4()
        employee = EmployeeService.create_employee(
            tenant_id=str(tenant_id),
            employee_number="EMP-001",
            first_name="John",
            last_name="Doe",
            hire_date=date(2024, 1, 1),
        )

        assert employee.employee_number == "EMP-001"
        assert employee.first_name == "John"
        assert str(employee.tenant_id) == str(tenant_id)
