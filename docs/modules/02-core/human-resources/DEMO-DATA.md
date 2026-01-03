# Human Resources Module - Demo Data

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
