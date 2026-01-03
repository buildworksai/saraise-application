<!-- SPDX-License-Identifier: Apache-2.0 -->
# Purchase Management - User Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-02

---

## Overview

This guide provides instructions for using the Purchase Management module.

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

**Module**: `purchase`
**Category**: Core Business
**Version**: 1.0.0

---

## Overview

This guide documents all customization points available in the Purchase Management module. Use these customization capabilities to extend procurement workflows, customize purchase order processing, automate supplier management, and integrate with external procurement systems.

---

## Customization Points

### 1. Purchase Order Model

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_submit`, `after_submit`, `before_cancel`, `after_cancel`

**Use Cases**:
- Auto-generate PO numbers
- Validate purchase order data
- Calculate totals and taxes
- Trigger approval workflows
- Sync to external systems

**Example Server Script**:
```python
# Auto-calculate purchase order totals
def before_save(doc, method):
    """Calculate PO totals"""
    total = 0
    for item in doc.items:
        item.amount = item.quantity * item.rate
        total += item.amount
    doc.total_amount = total
    if doc.tax_rate:
        doc.tax_amount = (total * doc.tax_rate) / 100
        doc.grand_total = total + doc.tax_amount
```

### 2. Purchase Requisition Model

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_submit`, `after_submit`

**Use Cases**:
- Validate requisition data
- Auto-approve based on rules
- Convert to purchase orders
- Check budget availability

### 3. Supplier Model

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`

**Use Cases**:
- Validate supplier data
- Calculate supplier performance
- Sync suppliers to external systems

### 4. GRN (Goods Receipt Note) Model

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_submit`, `after_submit`

**Use Cases**:
- Validate GRN against PO
- Update inventory on receipt
- Trigger quality checks

---

## Custom API Endpoints

### Example: Supplier Performance Analysis

```python
# API Script: Analyze supplier performance
# Endpoint: POST /api/v1/customization/custom-endpoints/purchase_supplier_analysis

@frappe.whitelist(allow_guest=False)
def analyze_supplier_performance(supplier_id, start_date=None, end_date=None):
    """Analyze supplier performance metrics"""
    # Implementation for supplier analysis
    return {"supplier_id": supplier_id, "metrics": {...}}
```

---

## Webhooks

### Available Events

| Event Type | Description |
|------------|-------------|
| `purchase.requisition.created` | Purchase requisition created |
| `purchase.order.created` | Purchase order created |
| `purchase.order.approved` | Purchase order approved |
| `purchase.grn.received` | Goods receipt note received |
| `purchase.invoice.received` | Purchase invoice received |

---

## AI-Powered Code Generation

Ask Amani can generate customizations:
- "Create a script that auto-approves purchase orders under $1000"
- "Generate a webhook that syncs purchase orders to SAP"
- "Create an API endpoint to compare supplier quotes"

---

## Best Practices

1. **Approval Workflows**: Implement proper approval workflows
2. **Three-way Matching**: Ensure PO, GRN, and Invoice match
3. **Budget Validation**: Check budget availability before approval
4. **Supplier Management**: Track supplier performance
5. **Audit Trail**: Maintain audit logs for all purchase transactions


## Integrations

<!-- SPDX-License-Identifier: Apache-2.0 -->
# Purchase & Procurement - Integration Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-01
**Status:** Integration Reference
**Development Agent:** Agent 66

---

This document describes all integration points for the Purchase & Procurement module, including internal module integrations, external system integrations, and webhook events.

---

## Integration Overview

The Purchase & Procurement module integrates with:

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
| [event.name] | `/api/v1/purchase-management/webhooks/[path]` | [Handler function] | [Use case] |

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

## Overview

This document describes the demo data structure for the Purchase Management module. Demo data provides realistic examples of suppliers, purchase requisitions, RFQs, purchase orders, GRNs, and purchase invoices.

## Demo Data Structure

### Suppliers

**Count:** 10-15 demo suppliers

**Sample Data:**
- Office Supplies Co.
- IT Equipment Inc.
- Raw Materials Supplier
- Marketing Services Agency
- Maintenance Services Provider

**Fields:**
- Supplier name, code
- Contact information, address
- Payment terms, credit limit
- Tax information
- Performance ratings

### Purchase Requisitions

**Count:** 10-15 demo requisitions

**Sample Data:**
- Various departments requesting items
- Different statuses (draft, submitted, approved, rejected)
- Various amounts and priorities

**Fields:**
- Requisition number, date
- Requested by, department
- Requisition items
- Status, approval status

### RFQs (Request for Quotation)

**Count:** 5-10 demo RFQs

**Sample Data:**
- RFQs sent to multiple suppliers
- Various statuses (draft, sent, received, closed)
- Supplier quotes received

**Fields:**
- RFQ number, date
- Items requested
- Supplier quotes
- Status

### Purchase Orders

**Count:** 15-20 demo purchase orders

**Sample Data:**
- Orders from approved requisitions
- Various statuses (draft, sent, confirmed, received, closed)
- Different suppliers and amounts

**Fields:**
- PO number, date, expected delivery
- Supplier reference
- PO items (items, quantities, prices)
- Status, approval status

### GRNs (Goods Receipt Notes)

**Count:** 10-15 demo GRNs

**Sample Data:**
- Receipts against purchase orders
- Various statuses (draft, received, inspected, accepted)
- Partial and full receipts

**Fields:**
- GRN number, date
- Linked purchase order
- GRN items (received quantities)
- Status, quality check

### Purchase Invoices

**Count:** 10-15 demo purchase invoices

**Sample Data:**
- Invoices from suppliers
- Linked to purchase orders and GRNs
- Various statuses (draft, submitted, approved, paid)
- Three-way matching (PO, GRN, Invoice)

**Fields:**
- Invoice number, date
- Supplier reference
- Linked PO and GRN
- Invoice items, amounts, taxes
- Status, payment status

### Purchase Returns

**Count:** 3-5 demo returns

**Sample Data:**
- Returns for defective items
- Returns for wrong items
- Various statuses

## Relationships

- Suppliers → Purchase Orders
- Purchase Requisitions → Purchase Orders
- RFQs → Supplier Quotes → Purchase Orders
- Purchase Orders → GRNs → Purchase Invoices
- Purchase Orders → Purchase Returns

## Data Seeding Script

The demo data seeding script should:

1. Create Suppliers
2. Create Purchase Requisitions
3. Create RFQs and Supplier Quotes
4. Create Purchase Orders (from requisitions)
5. Create GRNs (against purchase orders)
6. Create Purchase Invoices (three-way matching)
7. Create Purchase Returns (if applicable)

## Integration

Add to `seed_demo_tenant.py`:
```python
from backend.scripts.seed_purchase_demo_data import seed_purchase_demo_data

async def seed_demo_tenant():
    # ... existing code ...
    await seed_purchase_demo_data(session, tenant.id, demo_user.id)
```

## Troubleshooting

<!-- TODO: Add troubleshooting guide -->
