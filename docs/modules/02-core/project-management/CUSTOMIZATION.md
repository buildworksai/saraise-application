# Project Management Module - Customization Guide

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

### 2. Task Resource

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_delete`, `after_delete`

**Use Cases**:
- Auto-assign tasks
- Calculate task duration
- Update project progress
- Trigger task workflows

### 3. Project Budget Resource

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`

**Use Cases**:
- Validate budget data
- Calculate budget variance
- Trigger budget alerts

### 4. Project Expense Resource

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
