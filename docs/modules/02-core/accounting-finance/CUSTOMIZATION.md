# Accounting & Finance Module - Customization Guide

**Module**: `accounting`
**Category**: Core Business
**Version**: 1.0.0

---

## Overview

This guide documents all customization points available in the Accounting & Finance module. Use these customization capabilities to extend financial management, customize invoice processing, automate payment workflows, and integrate with external accounting systems.

**Related Documentation**:
- [Customization Framework](../../01-foundation/customization-framework/README.md)
- [Event System](../../../architecture/11-event-system.md)

---

## Customization Points

### 1. Invoice Resource

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_delete`, `after_delete`, `before_submit`, `after_submit`

**Use Cases**:
- Auto-calculate tax amounts
- Validate invoice data
- Sync invoices to external accounting systems
- Generate invoice numbers
- Apply discounts automatically

**Example Server Script**:
```python
# Auto-calculate tax on invoice
def before_save(doc, method):
    """Calculate tax amount"""
    if doc.tax_rate and doc.amount:
        doc.tax_amount = (doc.amount * doc.tax_rate) / 100
        doc.total_amount = doc.amount + doc.tax_amount
```

### 2. Payment Resource

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`

**Use Cases**:
- Validate payment amounts
- Process payment through gateway
- Update invoice payment status
- Send payment confirmations

### 3. Journal Entry Resource

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_submit`, `after_submit`

**Use Cases**:
- Validate balanced entries
- Auto-generate journal entry numbers
- Enforce approval workflows
- Post to general ledger

### 4. Accounting Account Resource

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`

**Use Cases**:
- Validate account hierarchy
- Auto-generate account codes
- Enforce chart of accounts structure

---

## Custom API Endpoints

### Example: Financial Report Generator

```python
# API Script: Generate custom financial reports
# Endpoint: POST /api/v1/customization/custom-endpoints/accounting_financial_report

@frappe.whitelist(allow_guest=False)
def generate_financial_report(report_type, start_date, end_date):
    """Generate custom financial report"""
    # Implementation for generating financial reports
    return {"report_type": report_type, "data": {...}}
```

---

## Webhooks

### Available Events

| Event Type | Description |
|------------|-------------|
| `accounting.invoice.created` | Invoice created |
| `accounting.invoice.paid` | Invoice paid |
| `accounting.payment.received` | Payment received |
| `accounting.journal_entry.posted` | Journal entry posted |

---

## AI-Powered Code Generation

Ask Amani can generate customizations:
- "Create a script that auto-calculates tax based on customer location"
- "Generate a webhook that syncs invoices to QuickBooks"
- "Create an API endpoint to generate profit & loss statements"

---

## Best Practices

1. **Accuracy**: Ensure financial calculations are accurate
2. **Audit Trail**: Maintain audit logs for all financial transactions
3. **Compliance**: Follow accounting standards and regulations
4. **Validation**: Validate all financial data before processing
5. **Security**: Implement strict access controls for financial data
