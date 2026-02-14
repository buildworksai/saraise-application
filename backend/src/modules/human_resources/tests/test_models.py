"""
Model tests for Human Resources module.
"""

import uuid
import pytest
from datetime import date

from src.modules.human_resources.models import Department, Employee


@pytest.mark.django_db
class TestDepartmentModel:
    """Test Department model."""

    def test_create_department(self):
        """Test creating a department."""
        tenant_id = uuid.uuid4()
        department = Department.objects.create(
            tenant_id=tenant_id,
            department_code="DEPT-001",
            department_name="Engineering",
        )
        assert department.department_code == "DEPT-001"
        assert department.department_name == "Engineering"
        assert department.is_active is True


@pytest.mark.django_db
class TestEmployeeModel:
    """Test Employee model."""

    def test_create_employee(self):
        """Test creating an employee."""
        tenant_id = uuid.uuid4()
        employee = Employee.objects.create(
            tenant_id=tenant_id,
            employee_number="EMP-001",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            hire_date=date(2024, 1, 1),
        )
        assert employee.employee_number == "EMP-001"
        assert employee.first_name == "John"
        assert employee.is_active is True
