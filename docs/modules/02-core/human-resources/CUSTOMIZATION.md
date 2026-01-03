# Human Resources Module - Customization Guide

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

### 2. Leave Request Resource

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_submit`, `after_submit`

**Use Cases**:
- Validate leave balance
- Auto-approve based on rules
- Calculate leave days
- Update leave balance

### 3. Payroll Run Resource

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_submit`, `after_submit`

**Use Cases**:
- Calculate payroll amounts
- Validate payroll data
- Process payroll payments
- Generate payroll reports

### 4. Performance Review Resource

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
