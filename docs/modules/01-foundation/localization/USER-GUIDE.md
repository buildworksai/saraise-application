<!-- SPDX-License-Identifier: Apache-2.0 -->
# Localization - User Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-02

---

## Overview

This guide provides instructions for using the Localization module.

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

<!-- SPDX-License-Identifier: Apache-2.0 -->
# Regional & Localization - Customization Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-01
**Status:** Customization Reference
**Development Agent:** Agent 77

---

This guide explains how to customize the Regional & Localization module to meet your specific business requirements using SARAISE's low-code customization features.

## Customization Options

The Regional & Localization module supports extensive customization through:

1. **Custom Fields** - Add business-specific fields via Resource customization
2. **Custom Resources** - Create new document types
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


### Common Custom Fields for Regional & Localization

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
  "module": "localization",
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
    "localization.[Resource Type].before_save": "localization.customizations.[resource_type].before_save"
}
```

---

## 8. Integration Customization

### Custom API Endpoints

#### Endpoint: [Name]
**Path:** `/api/v1/localization/[path]`
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
- Prefix custom fields with module name: `localization_custom_field`
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

**Last Updated:** 2025-12-01
**License:** Apache-2.0


## Integrations

<!-- SPDX-License-Identifier: Apache-2.0 -->
# Regional & Localization - Integration Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-01
**Status:** Integration Reference
**Development Agent:** Agent 77

---

This document describes all integration points for the Regional & Localization module, including internal module integrations, external system integrations, and webhook events.

---

## Integration Overview

The Regional & Localization module integrates with:

- **Internal Modules**: [List of SARAISE modules]
- **External Systems**: [List of external systems]
- **Third-Party APIs**: [List of APIs]

---

## Internal Module Integration

### Integration Matrix

| Module | Integration Type | Data Flow | Trigger | Frequency |
|--------|------------------|-----------|---------|-----------|
| [Module] | API/Event/Shared Data | [Direction] | [Trigger] | Real-time/Batch |

### Integration: [Module Name]

**Type:** [API/Event/Shared Data]
**Purpose:** [Why this integration exists]

**Data Flow:**
```
[Module] → [This Module] → [Action]
```

**Implementation:**
```python
# Integration code example
from src.modules.[module] import [Service]

async def integrate_with_[module](data):
    """Integration logic"""
    pass
```

**Configuration:**
```json
{
  "module": "[module_name]",
  "type": "[type]",
  "enabled": true
}
```

[Repeat for all internal integrations]

---

## External System Integration

### Integration Matrix

| System | Protocol | Purpose | Authentication | Status |
|--------|----------|---------|----------------|--------|
| [System] | REST/SOAP/Webhook | [Purpose] | OAuth/API Key | Active/Planned |

### Integration: [System Name]

**Protocol:** REST/SOAP/Webhook
**Purpose:** [What this integration does]
**Status:** Active/Planned

**Authentication:**
- **Method:** OAuth 2.0 / API Key
- **Credentials:** Stored in Vault
- **Refresh:** Automatic / Manual

**API Endpoints:**
- **GET** `https://api.example.com/v1/resource`
  - **Purpose:** [What it does]
  - **Request:**
  ```json
  {
    "param1": "value1"
  }
  ```
  - **Response:**
  ```json
  {
    "data": [...]
  }
  ```

**Error Handling:**
- **401**: Unauthorized - Refresh token
- **429**: Rate limited - Retry with backoff
- **500**: Server error - Log and alert

**Configuration:**
```json
{
  "system": "[system_name]",
  "base_url": "https://api.example.com",
  "auth": {
    "type": "oauth2",
    "credentials": "[stored in vault]"
  }
}
```

[Repeat for all external integrations]

---

## Webhook Events

### Outgoing Webhooks

| Event | Payload | Use Case | Recipient |
|-------|---------|----------|-----------|
| [event.created] | [Payload structure] | [Use case] | [System] |

#### Webhook: [event.name]

**Description:** [What this webhook notifies]
**Trigger:** [When it fires]
**Payload:**
```json
{
  "event": "[event.name]",
  "timestamp": "[ISO 8601]",
  "data": {
    "id": "[resource_id]",
    "type": "[resource_type]",
    "changes": {...}
  }
}
```

**Security:**
- **Signature:** HMAC-SHA256
- **Verification:** [How recipient verifies]
- **Retry:** 3 attempts with exponential backoff

[Repeat for all outgoing webhooks]

### Incoming Webhooks

| Event | Endpoint | Handler | Use Case |
|-------|----------|---------|----------|
| [event.name] | `/api/v1/localization/webhooks/[path]` | [Handler function] | [Use case] |

#### Webhook Endpoint: [path]

**Event:** [event.name]
**Method:** POST
**Authentication:** API Key / Signature

**Request:**
```json
{
  "event": "[event.name]",
  "data": {...}
}
```

**Handler:**
```python
@router.post("/webhooks/[path]")
async def handle_webhook(payload: dict):
    """Handle incoming webhook"""
    # Handler logic
    pass
```

**Response:**
```json
{
  "status": "success",
  "message": "Webhook processed"
}
```

[Repeat for all incoming webhooks]

---

## Data Synchronization

### Sync Strategies

#### Strategy: Real-time Sync
**Type:** Event-driven
**Frequency:** Immediate
**Direction:** Bidirectional
**Conflict Resolution:** Last-write-wins / Manual resolution

**Implementation:**
```python
async def sync_realtime(event):
    """Real-time synchronization"""
    # Sync logic
    pass
```

#### Strategy: Batch Sync
**Type:** Scheduled
**Frequency:** Daily/Hourly
**Direction:** Unidirectional
**Conflict Resolution:** Source system wins

**Implementation:**
```python
async def sync_batch():
    """Batch synchronization"""
    # Sync logic
    pass
```

---

## Integration Testing

### Test Scenarios

#### Scenario 1: [Integration Name] - [Test Name]
**Integration:** [System/Module]
**Setup:** [Initial state]
**Steps:**
1. [Step 1]
2. [Step 2]
**Expected Result:** [What should happen]
**Validation:** [How to verify]

[Repeat for all integration scenarios]

---

## Troubleshooting

### Common Issues

#### Issue: Authentication Failures
**Symptoms:** 401 errors, token expired
**Cause:** Expired credentials, invalid tokens
**Solution:** Refresh credentials, verify token validity
**Prevention:** Automatic token refresh, monitoring

#### Issue: Rate Limiting
**Symptoms:** 429 errors, throttling
**Cause:** Exceeding API rate limits
**Solution:** Implement backoff, reduce request frequency
**Prevention:** Rate limit monitoring, request queuing

---

**Last Updated:** 2025-12-01
**License:** Apache-2.0


## Demo Data

<!-- SPDX-License-Identifier: Apache-2.0 -->
# Regional & Localization - Demo Data

**Version:** 1.0.0
**Last Updated:** 2025-12-01
**Status:** Demo Data Reference
**Development Agent:** Agent 77

---

This document describes the comprehensive demo data included with the Regional & Localization module for testing and training purposes.

## Overview

The demo data seed script (`backend/scripts/seed_localization_demo.py`) creates a fully functional Regional & Localization setup for the demo tenant `demo@saraise.com` with:

- [Number] [entities] (e.g., 10 customers, 5 products)
- [Number] [entities]
- [Number] [entities]

---

## Sample Data Sets

### Basic Demo (10 records)

**Purpose:** Minimal data for quick demos and initial testing.

**Includes:**
- [Entity type 1]: [Number] records
- [Entity type 2]: [Number] records
- [Entity type 3]: [Number] records

**Usage:**
```bash
python backend/scripts/seed_localization_demo.py --size basic
```

### Full Demo (100+ records)

**Purpose:** Comprehensive data for thorough testing, training, and demonstrations.

**Includes:**
- [Entity type 1]: [Number] records
- [Entity type 2]: [Number] records
- [Entity type 3]: [Number] records
- [Entity type 4]: [Number] records

**Usage:**
```bash
python backend/scripts/seed_localization_demo.py --size full
```

---

## Demo Data Structure

### Entity 1: [Name]

**Count:** [Number]
**Purpose:** [What this entity represents]

**Sample Record:**

```json
{
  "id": "[id]",
  "name": "[Name]",
  "field1": "[value]",
  "field2": "[value]"
}
```

**Key Fields:**
| Field | Value | Description |
|-------|-------|-------------|
| [field] | [value] | [description] |

[Repeat for all entity types]

---

## Relationships & Dependencies

The demo data includes realistic relationships between entities:

- **[Entity A]** → **[Entity B]**: [How they relate]
- **[Entity B]** → **[Entity C]**: [How they relate]

### Data Dependency Order

The following order ensures all dependencies are created correctly:

1. [Base entity] (no dependencies)
2. [Dependent entity 1] (depends on step 1)
3. [Dependent entity 2] (depends on steps 1-2)

---

## Data Generation Scripts

### Main Seed Script

**File:** `backend/scripts/seed_localization_demo.py`

**Usage:**
```bash
# Basic demo
python backend/scripts/seed_localization_demo.py --size basic --tenant demo@saraise.com

# Full demo
python backend/scripts/seed_localization_demo.py --size full --tenant demo@saraise.com

# Custom count
python backend/scripts/seed_localization_demo.py --count 50 --tenant demo@saraise.com
```

**Options:**
- `--size`: `basic` or `full` (default: `basic`)
- `--count`: Custom number of records per entity
- `--tenant`: Tenant ID or email (default: `demo@saraise.com`)
- `--reset`: Clear existing demo data before seeding

### Helper Functions

#### `generate_localization_data(count)`
**Purpose:** Generate [entity type] records
**Parameters:**
- `count` (int): Number of records to generate

```python
def generate_localization_data(count: int):
    """Generate demo data"""
    # Implementation
    pass
```

---

## Sample Data Examples

### Example 1: [Entity Name]

**Type:** [Resource Type]
**Description:** [What this example demonstrates]

**Data:**
```json
{
  "name": "Example Record",
  "field1": "value1",
  "field2": "value2"
}
```

**Use Case:** [When to use this example]

[Repeat for key examples]

---

## Reset Instructions

### Clearing Demo Data

**Method 1: Using Script**
```bash
python backend/scripts/seed_localization_demo.py --reset --tenant demo@saraise.com
```

**Method 2: Manual Deletion**
1. Delete dependent entities first
2. Delete base entities
3. Verify all data cleared

### Verification

After reset, verify:
- [ ] All demo records deleted
- [ ] No orphaned relationships
- [ ] Database constraints satisfied

---

## Testing Scenarios

### Scenario 1: Basic Functionality

**Data Required:** Basic demo set
**Steps:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

### Scenario 2: Advanced Features

**Data Required:** Full demo set
**Steps:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

---

## Data Quality Standards

### Realistic Data
- All data values are realistic and representative
- Relationships follow business logic
- Dates are within valid ranges

### Completeness
- All required fields populated
- No null values in critical fields
- Relationships properly linked

### Consistency
- Naming conventions followed
- Data formats consistent
- Business rules validated

---

## Customization

### Extending Demo Data

To add custom demo data:

1. **Create Custom Seed Function:**
```python
def generate_custom_data():
    """Generate custom demo data"""
    # Your custom logic
    pass
```

2. **Add to Seed Script:**
```python
if __name__ == "__main__":
    # ... existing code ...
    generate_custom_data()
```

3. **Run:**
```bash
python backend/scripts/seed_localization_demo.py --custom
```

---

**Last Updated:** 2025-12-01
**License:** Apache-2.0

## Troubleshooting

<!-- TODO: Add troubleshooting guide -->
