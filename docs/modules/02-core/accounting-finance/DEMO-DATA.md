# Accounting & Finance Module - Demo Data

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
