<!-- SPDX-License-Identifier: Apache-2.0 -->
# Sales Management - Customization Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-02
**Status:** Customization Reference
**Development Agent:** Agent 67

---

This guide explains how to customize the Sales Management module to meet your specific business requirements using SARAISE's low-code customization features.

## Customization Options

The Sales Management module supports extensive customization through:

1. **Custom Fields** - Add business-specific fields via Model customization
2. **Custom Models** - Create new data models
3. **Workflow Customization** - Modify or create new workflows
4. **Server Scripts** - Add custom business logic
5. **Client Scripts** - Enhance UI behavior
6. **Report Customization** - Create custom reports
7. **Dashboard Customization** - Add custom widgets
8. **Integration Customization** - Connect to third-party systems

---

## 1. Adding Custom Fields

### Example: Add Custom Field to [Resource Type]

**Use Case:** [Why you need this field]
**Steps:**

1. Navigate to **Customization Studio** → **Resources**
2. Search for "[Resource Name]"
3. Click "Customize"
4. Add Custom Field:

```json
{
  "fieldname": "custom_field_name",
  "label": "Custom Field Label",
  "fieldtype": "Data",
  "insert_after": "existing_field"
}
```

5. **Save** and **Update Resource**

**Result:** [What happens after adding the field]


### Common Custom Fields for Sales Management

| Field | Resource | Type | Use Case |
|-------|---------|------|----------|
| [Field Name] | [Resource Type] | [Type] | [Use case] |
| [Field Name] | [Resource Type] | [Type] | [Use case] |

---

## 2. Creating Custom Resources

### Example: Custom "[Resource Name]"

**Requirement:** [What you need to track]
**Resource Definition:**

```json
{
  "name": "Custom Resource",
  "module": "sales-management",
  "is_submittable": 0,
  "fields": [
    {"fieldname": "field1", "label": "Field 1", "fieldtype": "Data", "reqd": 1},
    {"fieldname": "field2", "label": "Field 2", "fieldtype": "Select", "options": "Option1\nOption2"},
  ],
  "permissions": [
    {"role": "System Manager", "read": 1, "write": 1, "create": 1}
  ]
}
```


---

## 3. Custom Workflows

### Example: [Workflow Name]

**Use Case:** [What this workflow automates]
**Workflow Definition:**

```json
{
  "workflow_name": "Custom Workflow",
  "resource_type": "[Resource Type]",
  "states": [
    {"state": "Draft", "action": "Submit", "next_state": "Pending"},
    {"state": "Pending", "action": "Approve", "next_state": "Approved"},
  ],
  "transitions": [
    {"from_state": "Draft", "to_state": "Pending", "action": "Submit", "allowed": "Owner"},
  ]
}
```

---

## 4. Server Scripts

### Example: Custom Validation

**Use Case:** [What validation you need]
```python
# Server Script: Custom Validation
def validate(doc, method):
    """Custom validation logic"""
    if doc.field1 and doc.field2:
        if doc.field1 > doc.field2:
            raise ValidationError("Field1 cannot be greater than Field2")
```

### Example: Custom Calculation

```python
# Server Script: Custom Calculation
def before_save(doc, method):
    """Calculate custom field before saving"""
    doc.custom_total = doc.field1 + doc.field2
```

---

## 5. Client Scripts

### Example: Dynamic Field Behavior

**Use Case:** [What UI behavior you want]
```javascript
// Client Script: Dynamic Field Behavior
frappe.ui.form.on('[Resource Type]', {
    field1: function(frm) {
        if (frm.doc.field1) {
            frm.set_df_property('field2', 'hidden', 0);
        } else {
            frm.set_df_property('field2', 'hidden', 1);
        }
    }
});
```

---

## 6. Custom Reports

### Example: [Report Name]

**Purpose:** [What this report shows]
**Report Definition:**

```json
{
  "report_name": "Custom Report",
  "ref_resource": "[Resource Type]",
  "columns": [
    {"fieldname": "field1", "label": "Field 1", "fieldtype": "Data"},
    {"fieldname": "field2", "label": "Field 2", "fieldtype": "Currency"},
  ],
  "filters": [
    {"fieldname": "status", "label": "Status", "fieldtype": "Select"},
  ]
}
```

---

## 7. Hooks & Events

| Hook | Description | Use Case | Example |
|------|-------------|----------|---------|
| before_insert | Runs before document is inserted | Custom validation | Validate business rules |
| before_save | Runs before document is saved | Calculate fields | Auto-calculate totals |
| after_insert | Runs after document is inserted | Send notifications | Email confirmation |
| on_update | Runs when document is updated | Sync with external systems | Update CRM |

### Hook Implementation Example

```python
# hooks.py
hooks = {
    "sales-management.[Resource Type].before_save": "sales-management.customizations.[resource_type].before_save"
}
```

---

## 8. Integration Customization

### Custom API Endpoints

#### Endpoint: [Name]
**Path:** `/api/v1/sales-management/[path]`
**Method:** POST
**Purpose:** [What it does]

```python
@router.post("/[path]")
async def custom_endpoint(...):
    """Custom endpoint logic"""
    pass
```

### Webhook Customization

#### Webhook: [Name]
**Event:** [event.name]
**Payload:**
```json
{
    "event": "[event]",
    "data": {...}
}
```

**Use Case:** [What triggers this webhook]

---

## Best Practices

### Naming Conventions
- Use descriptive field names: `customer_preferred_contact_method` not `field1`
- Prefix custom fields with module name: `sales-management_custom_field`
- Use consistent naming across Resources

### Performance Considerations
- Avoid complex calculations in client scripts
- Use server scripts for heavy processing
- Index frequently queried custom fields

### Maintenance
- Document all customizations
- Version control custom scripts
- Test customizations in staging before production

---

**Last Updated:** 2025-12-02
**License:** Apache-2.0
