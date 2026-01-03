# Customer Relationship Management - Customization Guide

**Module**: `crm`
**Category**: Core Business
**Version**: 1.0.0

---

## Overview

This guide documents all customization points available in the CRM module. Use these capabilities to extend customer data, automate lead processing, customize sales workflows, and integrate with external marketing or sales tools.

---

## Customization Points

### 1. Lead Model

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_delete`, `after_delete`

**Use Cases**:
- Auto-calculate lead score based on attributes
- Assign leads to sales representatives based on territory
- Validate lead contact information
- Trigger external enrichment (e.g., Clearbit, LinkedIn)

**Example Server Script**:
```python
# Auto-assign lead based on industry
def before_insert(doc, method):
    """Assign lead to industry specialist"""
    if doc.industry == "Technology":
        doc.assigned_to = "tech-sales@example.com"
    elif doc.industry == "Healthcare":
        doc.assigned_to = "pharma-sales@example.com"
```

### 2. Opportunity Resource

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_submit`, `after_submit`

**Use Cases**:
- Validate probability and expected revenue
- Automate stage transitions
- Create tasks for follow-ups upon stage change
- Calculate weighted pipeline value

### 3. Customer Resource

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`

**Use Cases**:
- Generate unique customer codes
- Sync customer data with accounting or ERP systems
- Validate tax IDs or VAT numbers
- Handle duplicate detection logic

### 4. Activity Resource

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`

**Use Cases**:
- Log activities to external systems (e.g., email tracking)
- Update parent Lead/Opportunity "Last Contacted" date automatically

---

## Custom API Endpoints

### Example: Lead Analytics

```python
# API Script: Get lead conversion analytics
# Endpoint: POST /api/v1/customization/custom-endpoints/crm_lead_analytics

@frappe.whitelist(allow_guest=False)
def get_lead_analytics(start_date=None, end_date=None):
    """Get lead conversion rates by source"""
    # Custom logic to aggregate lead data
    return {"analytics": {...}}
```

---

## Webhooks

### Available Events

| Event Type | Description |
|------------|-------------|
| `crm.lead.created` | New lead created |
| `crm.opportunity.won` | Opportunity stage changed to Won |
| `crm.customer.created` | New customer account created |
| `crm.activity.logged` | New activity (call, email) logged |

---

## AI-Powered Code Generation

Ask Amani can generate customizations:
- "Create a script that calculates lead score based on annual revenue"
- "Generate a webhook that notifies Slack when a deal is closed won"
- "Create an API endpoint for fetching high-priority leads"

---

## Best Practices

1. **Data Integrity**: Validate foreign keys and required fields
2. **Performance**: Avoid heavy computations in `before_insert`/`before_update`
3. **Security**: Ensure custom endpoints check appropriate permissions
4. **Testing**: Test scripts in a sandbox environment before deploying to production
