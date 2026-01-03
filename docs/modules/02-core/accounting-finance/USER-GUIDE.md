<!-- SPDX-License-Identifier: Apache-2.0 -->
# Accounting Finance - User Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-02

---

## Overview

This guide provides instructions for using the Accounting Finance module.

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

### 1. Invoice Model

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

### 2. Payment Model

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`

**Use Cases**:
- Validate payment amounts
- Process payment through gateway
- Update invoice payment status
- Send payment confirmations

### 3. Journal Entry Model

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


## Demo Data

## Overview

This document describes the demo data structure for the Accounting & Finance module. Demo data provides realistic examples of suppliers, accounts, journal entries, invoices, and payments for testing and demonstration purposes.

## Demo Data Structure

### Suppliers

**Count:** 5-10 demo suppliers

**Sample Data:**
- Office Supplies Co. (Office supplies vendor)
- IT Equipment Inc. (Technology vendor)
- Marketing Agency Ltd. (Marketing services)
- Legal Services Group (Legal services)
- Utilities Provider (Utility services)

**Fields:**
- Supplier name, type
- Contact information, address
- Payment terms, credit limit
- Tax information
- Status (active/inactive)

### Accounting Accounts (Chart of Accounts)

**Count:** 20-30 demo accounts

**Sample Data:**
- Assets: Cash, Accounts Receivable, Inventory, Fixed Assets
- Liabilities: Accounts Payable, Loans, Taxes Payable
- Equity: Capital, Retained Earnings
- Revenue: Sales Revenue, Service Revenue
- Expenses: Cost of Goods Sold, Operating Expenses, Salaries

**Fields:**
- Account name, code, type
- Parent account (for hierarchy)
- Balance, currency
- Is active

### Journal Entries

**Count:** 10-15 demo journal entries

**Sample Data:**
- Monthly closing entries
- Adjusting entries
- Recurring entries
- Various statuses (draft, submitted, approved)

**Fields:**
- Entry date, reference
- Description
- Status, approval status
- Journal entry items (debit/credit)

### Invoices

**Count:** 15-20 demo invoices

**Sample Data:**
- Customer invoices (accounts receivable)
- Supplier invoices (accounts payable)
- Various statuses (draft, submitted, paid, overdue)
- Different amounts and currencies

**Fields:**
- Invoice number, date, due date
- Customer/supplier reference
- Amount, tax amount, total amount
- Status, payment status
- Invoice items

### Payments

**Count:** 10-15 demo payments

**Sample Data:**
- Customer payments (against invoices)
- Supplier payments
- Various payment methods (cash, bank transfer, check)
- Different statuses (pending, completed, failed)

**Fields:**
- Payment date, amount
- Payment method, reference
- Linked invoice(s)
- Status

### Taxes

**Count:** 5-10 demo tax records

**Sample Data:**
- Sales tax (10%)
- VAT (20%)
- Income tax
- Various tax rates and types

**Fields:**
- Tax name, type, rate
- Applicable to (sales/purchases)
- Is active

## Relationships

- Suppliers → Invoices (accounts payable)
- Customers → Invoices (accounts receivable)
- Invoices → Payments (payment tracking)
- Journal Entries → Accounts (accounting entries)
- Taxes → Invoices (tax calculations)

## Data Seeding Script

The demo data seeding script should:

1. Create Chart of Accounts (hierarchical structure)
2. Create Suppliers
3. Create Tax records
4. Create Journal Entries with items
5. Create Invoices (both customer and supplier)
6. Create Payments linked to invoices

## Integration

Add to `seed_demo_tenant.py`:
```python
from backend.scripts.seed_accounting_demo_data import seed_accounting_demo_data

async def seed_demo_tenant():
    # ... existing code ...
    await seed_accounting_demo_data(session, tenant.id, demo_user.id)
```

## Troubleshooting

<!-- TODO: Add troubleshooting guide -->
