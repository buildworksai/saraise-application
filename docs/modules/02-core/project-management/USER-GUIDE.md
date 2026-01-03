<!-- SPDX-License-Identifier: Apache-2.0 -->
# Project Management - User Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-02

---

## Overview

This guide provides instructions for using the Project Management module.

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

**Module**: `projects`
**Category**: Core Business
**Version**: 1.0.0

---

## Overview

This guide documents all customization points available in the Project Management module. Use these customization capabilities to extend project management, customize task workflows, automate resource allocation, and integrate with external project management systems.

---

## Customization Points

### 1. Project Model

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_delete`, `after_delete`

**Use Cases**:
- Auto-generate project codes
- Validate project data
- Calculate project health
- Trigger project workflows
- Sync to external systems

**Example Server Script**:
```python
# Auto-calculate project health
def after_update(doc, method):
    """Calculate project health score"""
    # Calculate based on budget, timeline, tasks
    budget_variance = (doc.actual_cost / doc.budget) * 100 if doc.budget else 0
    timeline_variance = calculate_timeline_variance(doc)
    task_completion = calculate_task_completion(doc)

    # Health score (0-100)
    health_score = (
        (100 - abs(budget_variance - 100)) * 0.4 +
        (100 - abs(timeline_variance - 100)) * 0.3 +
        task_completion * 0.3
    )
    doc.health_score = round(health_score, 2)
```

### 2. Task Model

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_delete`, `after_delete`

**Use Cases**:
- Auto-assign tasks
- Calculate task duration
- Update project progress
- Trigger task workflows

### 3. Project Budget Model

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`

**Use Cases**:
- Validate budget data
- Calculate budget variance
- Trigger budget alerts

### 4. Project Expense Model

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_submit`, `after_submit`

**Use Cases**:
- Validate expense data
- Update project costs
- Enforce approval workflows

---

## Custom API Endpoints

### Example: Project Health Dashboard

```python
# API Script: Get project health dashboard
# Endpoint: POST /api/v1/customization/custom-endpoints/projects_health_dashboard

@frappe.whitelist(allow_guest=False)
def get_project_health_dashboard(project_ids=None):
    """Get project health dashboard data"""
    # Implementation for project health dashboard
    return {"dashboard": {...}}
```

---

## Webhooks

### Available Events

| Event Type | Description |
|------------|-------------|
| `projects.project.created` | Project created |
| `projects.task.completed` | Task completed |
| `projects.milestone.achieved` | Milestone achieved |
| `projects.budget.exceeded` | Budget exceeded |

---

## AI-Powered Code Generation

Ask Amani can generate customizations:
- "Create a script that auto-assigns tasks based on skills"
- "Generate a webhook that syncs projects to Jira"
- "Create an API endpoint to calculate project ROI"

---

## Best Practices

1. **Resource Management**: Optimize resource allocation
2. **Timeline Tracking**: Monitor project timelines
3. **Budget Control**: Track and control project budgets
4. **Risk Management**: Identify and mitigate project risks
5. **Communication**: Maintain project communication channels


## Demo Data

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

## Troubleshooting

<!-- TODO: Add troubleshooting guide -->
