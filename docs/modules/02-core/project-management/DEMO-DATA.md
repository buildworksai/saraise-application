# Project Management Module - Demo Data

## Overview

This document describes the demo data structure for the Project Management module. Demo data provides realistic examples of projects, tasks, resources, budgets, expenses, milestones, and time entries.

## Demo Data Structure

### Projects

**Count:** 5-10 demo projects

**Sample Data:**
- Product Development Project
- Marketing Campaign Project
- Infrastructure Upgrade Project
- Customer Implementation Project
- Research & Development Project

**Fields:**
- Project name, code
- Description, status
- Start date, end date
- Project manager, team members
- Budget, actual costs

### Tasks

**Count:** 30-50 demo tasks

**Sample Data:**
- Various task types (development, design, testing, documentation)
- Different statuses (not_started, in_progress, completed, blocked)
- Different priorities (low, medium, high)
- Task dependencies

**Fields:**
- Task name, description
- Project reference
- Assigned to, status, priority
- Start date, due date, completed date
- Estimated hours, actual hours
- Dependencies

### Project Resources

**Count:** 15-20 demo resource assignments

**Sample Data:**
- Employees assigned to projects
- Resource allocation percentages
- Different roles (developer, designer, tester, manager)

**Fields:**
- Project, employee
- Role, allocation percentage
- Start date, end date

### Project Budgets

**Count:** 5-10 demo budgets

**Sample Data:**
- Budgets for different projects
- Budget categories (labor, materials, overhead)
- Budget vs actual tracking

**Fields:**
- Project reference
- Budget category
- Budgeted amount, actual amount
- Variance

### Project Expenses

**Count:** 20-30 demo expenses

**Sample Data:**
- Various expense types (travel, software, hardware, services)
- Different projects
- Various statuses (draft, submitted, approved, paid)

**Fields:**
- Project reference
- Expense type, description
- Amount, date
- Status, approval status

### Project Milestones

**Count:** 15-20 demo milestones

**Sample Data:**
- Key project milestones
- Various statuses (upcoming, achieved, delayed)
- Different dates

**Fields:**
- Project reference
- Milestone name, description
- Target date, achieved date
- Status

### Project Time Entries

**Count:** 50-100 demo time entries

**Sample Data:**
- Time logged on tasks
- Various employees and projects
- Different dates and hours

**Fields:**
- Project, task, employee
- Date, hours worked
- Description, billable flag

## Relationships

- Projects → Tasks (project tasks)
- Projects → Resources (team assignments)
- Projects → Budgets (budget tracking)
- Projects → Expenses (expense tracking)
- Projects → Milestones (key milestones)
- Projects → Time Entries (time tracking)
- Tasks → Dependencies (task relationships)
- Tasks → Time Entries (time logged)

## Data Seeding Script

The demo data seeding script should:

1. Create Projects
2. Create Tasks (with dependencies)
3. Create Project Resources (team assignments)
4. Create Project Budgets
5. Create Project Expenses
6. Create Project Milestones
7. Create Project Time Entries

## Integration

Add to `seed_demo_tenant.py`:
```python
from backend.scripts.seed_projects_demo_data import seed_projects_demo_data

async def seed_demo_tenant():
    # ... existing code ...
    await seed_projects_demo_data(session, tenant.id, demo_user.id)
```
