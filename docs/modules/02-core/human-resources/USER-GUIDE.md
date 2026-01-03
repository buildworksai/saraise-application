<!-- SPDX-License-Identifier: Apache-2.0 -->
# Human Resources - User Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-02

---

## Overview

This guide provides instructions for using the Human Resources module.

## Getting Started

<!-- TODO: Add getting started instructions -->

## Features

<!-- TODO: Add feature documentation -->

## Usage

<!-- TODO: Add usage instructions -->

## Customization

<!-- TODO: Add customization options -->

## Integrations

<!-- TODO: Add integration information -->


## Customization

**Module**: `hr`
**Category**: Core Business
**Version**: 1.0.0

---

## Overview

This guide documents all customization points available in the HR module. Use these customization capabilities to extend employee management, customize payroll processing, automate onboarding workflows, and integrate with external HR systems.

---

## Customization Points

### 1. Employee Model

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_delete`, `after_delete`

**Use Cases**:
- Auto-generate employee IDs
- Validate employee data
- Trigger onboarding workflows
- Sync employees to external HR systems
- Calculate employee tenure

**Example Server Script**:
```python
# Auto-generate employee ID
def before_insert(doc, method):
    """Generate employee ID if not provided"""
    if not doc.employee_id:
        # Generate: EMP-YYYY-XXX
        year = frappe.utils.today().split("-")[0]
        last_emp = frappe.db.get_value(
            "Employee",
            {"employee_id": ["like", f"EMP-{year}%"]},
            "employee_id",
            order_by="employee_id desc"
        )
        seq = int(last_emp.split("-")[-1]) + 1 if last_emp else 1
        doc.employee_id = f"EMP-{year}-{seq:03d}"
```

### 2. Leave Request Model

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_submit`, `after_submit`

**Use Cases**:
- Validate leave balance
- Auto-approve based on rules
- Calculate leave days
- Update leave balance

### 3. Payroll Run Model

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_submit`, `after_submit`

**Use Cases**:
- Calculate payroll amounts
- Validate payroll data
- Process payroll payments
- Generate payroll reports

### 4. Performance Review Model

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`

**Use Cases**:
- Auto-calculate performance scores
- Generate review summaries
- Trigger development plans

---

## Custom API Endpoints

### Example: Employee Analytics

```python
# API Script: Get employee analytics
# Endpoint: POST /api/v1/customization/custom-endpoints/hr_employee_analytics

@frappe.whitelist(allow_guest=False)
def get_employee_analytics(department_id=None, start_date=None, end_date=None):
    """Get employee analytics"""
    # Implementation for employee analytics
    return {"analytics": {...}}
```

---

## Webhooks

### Available Events

| Event Type | Description |
|------------|-------------|
| `hr.employee.created` | Employee created |
| `hr.employee.terminated` | Employee terminated |
| `hr.leave_request.approved` | Leave request approved |
| `hr.payroll.processed` | Payroll processed |

---

## AI-Powered Code Generation

Ask Amani can generate customizations:
- "Create a script that auto-assigns employees to departments"
- "Generate a webhook that syncs employees to ADP"
- "Create an API endpoint to calculate employee turnover rate"

---

## Best Practices

1. **Privacy**: Protect employee personal information
2. **Compliance**: Follow labor laws and regulations
3. **Accuracy**: Ensure payroll calculations are accurate
4. **Audit Trail**: Maintain audit logs for HR actions
5. **Security**: Implement strict access controls


## Demo Data

## Overview

This document describes the demo data structure for the HR module. Demo data provides realistic examples of departments, employees, job requisitions, attendance, leave requests, payroll, and performance reviews.

## Demo Data Structure

### Departments

**Count:** 5-8 demo departments

**Sample Data:**
- Engineering
- Sales & Marketing
- Human Resources
- Finance & Accounting
- Operations
- Customer Support

**Fields:**
- Department name, code
- Manager, parent department
- Budget, headcount
- Is active

### Employees

**Count:** 20-30 demo employees

**Sample Data:**
- Mix of roles (managers, individual contributors)
- Various departments
- Different employment types (full-time, part-time, contract)
- Various statuses (active, on leave, terminated)

**Fields:**
- Personal information (name, email, phone, address)
- Employment details (employee ID, hire date, department, manager)
- Job details (title, band, salary)
- Status, is_active

### Job Requisitions & Postings

**Count:** 5-10 demo requisitions

**Sample Data:**
- Open positions
- Various departments and roles
- Different statuses (draft, approved, posted, filled)

### Attendance & Timesheets

**Count:** 50-100 demo attendance records

**Sample Data:**
- Daily attendance for employees
- Various statuses (present, absent, late, half-day)
- Timesheet entries with projects/tasks

### Leave Requests

**Count:** 15-20 demo leave requests

**Sample Data:**
- Various leave types (vacation, sick, personal)
- Different statuses (pending, approved, rejected)
- Different durations (1 day to 2 weeks)

### Payroll

**Count:** 5-10 demo payroll runs

**Sample Data:**
- Monthly payroll cycles
- Various statuses (draft, processing, completed)
- Payroll entries for employees

### Performance Reviews

**Count:** 10-15 demo performance reviews

**Sample Data:**
- Annual and quarterly reviews
- Various ratings and feedback
- Goal tracking (OKRs)

## Relationships

- Departments → Employees (department assignment)
- Employees → Managers (reporting structure)
- Employees → Attendance (daily records)
- Employees → Leave Requests
- Employees → Payroll (payroll entries)
- Employees → Performance Reviews

## Data Seeding Script

The demo data seeding script should:

1. Create Departments
2. Create Employees (with reporting structure)
3. Create Job Requisitions
4. Create Attendance records
5. Create Leave Requests
6. Create Payroll cycles and runs
7. Create Performance Reviews

## Integration

Add to `seed_demo_tenant.py`:
```python
from backend.scripts.seed_hr_demo_data import seed_hr_demo_data

async def seed_demo_tenant():
    # ... existing code ...
    await seed_hr_demo_data(session, tenant.id, demo_user.id)
```

## Troubleshooting

<!-- TODO: Add troubleshooting guide -->
