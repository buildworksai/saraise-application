<!-- SPDX-License-Identifier: Apache-2.0 -->
# Accounting & Finance Module

**Module Code**: `accounting`
**Category**: Core Business
**Priority**: Critical - Financial Management
**Version**: 1.0.0
**Status**: Implementation Complete

---

## Executive Summary

The Accounting & Finance module provides comprehensive **financial management** from general ledger to financial reporting, multi-currency support, and advanced analytics. Powered by AI agents, this module automates journal entries, bank reconciliation, financial consolidation, and predictive analytics—delivering a world-class financial management experience that rivals SAP S/4HANA, Oracle NetSuite, Microsoft Dynamics 365, and Odoo.

### Vision

**"Every financial transaction, intelligently managed from entry to insight, ensuring real-time accuracy and compliance."**

---

## World-Class Features

### 1. Chart of Accounts (COA)
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Account Structure**:
```python
account_structure = {
    "segments": {
        "account_code": "Hierarchical numbering (1000-9999)",
        "account_type": "Asset, Liability, Equity, Revenue, Expense",
        "account_subtype": "Current Asset, Fixed Asset, etc.",
        "cost_center": "Department/division",
        "profit_center": "Business unit",
        "project": "Project tracking dimension"
    },
    "account_types": {
        "1000-1999": "Assets",
        "2000-2999": "Liabilities",
        "3000-3999": "Equity",
        "4000-4999": "Revenue",
        "5000-9999": "Expenses"
    }
}
```

**Account Features**:
```python
account_properties = {
    "basic": ["code", "name", "type", "parent_account"],
    "classification": ["account_group", "root_type", "is_group"],
    "controls": ["allow_manual_posting", "require_cost_center", "frozen"],
    "reporting": ["balance_type", "include_in_gross", "report_category"],
    "multi_currency": ["account_currency", "allow_multi_currency"],
    "consolidation": ["consolidation_account", "inter_company_account"]
}
```

**COA Templates**:
- US GAAP
- IFRS
- Industry-specific (Manufacturing, Retail, Services)
- Country-specific (UK, EU, India, Singapore)
- Custom COA builder

### 2. General Ledger
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Journal Entry Types**:
```python
journal_types = {
    "standard": "Manual journal entries",
    "sales": "Auto from sales invoices",
    "purchase": "Auto from purchase invoices",
    "payment": "Auto from payments",
    "bank": "Bank transactions",
    "payroll": "Payroll entries",
    "depreciation": "Auto depreciation",
    "opening": "Opening balances",
    "closing": "Period close entries",
    "inter_company": "Between entities",
    "reversal": "Reversing entries",
    "recurring": "Template-based recurring"
}
```

**Journal Entry Workflow**:
```python
entry_workflow = {
    "draft": "Being prepared",
    "submitted": "Awaiting approval",
    "approved": "Manager approved",
    "posted": "Posted to GL (immutable)",
    "cancelled": "Voided (audit trail maintained)"
}
```

**Double-Entry Validation**:
```python
validation_rules = {
    "balanced": "Debits must equal credits",
    "account_valid": "Account must exist and be active",
    "date_valid": "Posting date within open period",
    "dimension_required": "Cost center required if configured",
    "currency_match": "Multi-currency entries balanced",
    "approval_limits": "Amount within user limits"
}
```

**Batch Posting**:
- Import from Excel/CSV
- Bulk journal entry creation
- Template-based entries
- Approval workflow
- Error validation before posting

### 3. Accounts Payable (AP)
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Supplier Invoice Management**:
```python
ap_workflow = {
    "invoice_capture": {
        "manual_entry": "Manual invoice creation",
        "ocr_scan": "AI-powered invoice scanning",
        "email_parsing": "Extract from email attachments",
        "api_integration": "Supplier portal upload"
    },
    "validation": {
        "3_way_match": "PO ↔ Receipt ↔ Invoice",
        "2_way_match": "PO ↔ Invoice",
        "tolerance_check": "Price/quantity variance",
        "duplicate_detection": "Prevent duplicate payments",
        "gl_coding": "Auto-assign GL accounts"
    },
    "approval": {
        "workflow_routing": "Based on amount, department",
        "parallel_approval": "Multiple approvers",
        "delegation": "Temporary delegation",
        "escalation": "Auto-escalate if delayed"
    },
    "payment": {
        "payment_terms": "Net 30, Net 60, etc.",
        "early_payment_discount": "2/10 Net 30",
        "payment_batch": "Batch payment processing",
        "payment_methods": "Check, ACH, Wire, Card"
    }
}
```

**AI Invoice Processing**:
```python
ai_features = {
    "ocr_extraction": "Extract invoice fields (vendor, amount, date, items)",
    "gl_prediction": "Predict GL account based on history",
    "fraud_detection": "Flag suspicious invoices",
    "duplicate_check": "Compare against existing invoices",
    "vendor_matching": "Match to supplier database",
    "approval_routing": "Auto-route based on rules"
}
```

**Aging Analysis**:
```
Payables Aging Report:
0-30 days:    $150,000  (60%)
31-60 days:   $75,000   (30%)
61-90 days:   $20,000   (8%)
90+ days:     $5,000    (2%)
Total:        $250,000
```

### 4. Accounts Receivable (AR)
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Customer Invoice Management**:
```python
ar_workflow = {
    "invoice_creation": {
        "sales_order": "Auto from sales order",
        "contract": "Subscription billing",
        "time_materials": "From timesheet/expenses",
        "milestone": "Project milestone billing",
        "recurring": "Recurring invoices",
        "adhoc": "One-off invoices"
    },
    "delivery": {
        "email": "PDF via email",
        "portal": "Customer portal access",
        "print": "Postal mail",
        "edi": "EDI integration"
    },
    "payment_collection": {
        "credit_card": "Online payment gateway",
        "ach": "Bank transfer",
        "check": "Check deposit",
        "wire": "Wire transfer",
        "cash": "Cash receipt"
    }
}
```

**Payment Gateway Integration**:
- Stripe
- PayPal
- Square
- Authorize.net
- Razorpay (India)
- PCI compliance built-in

**Collections Management**:
```python
collections_automation = {
    "reminders": {
        "day_-7": "Invoice due in 7 days reminder",
        "day_0": "Invoice due today",
        "day_+7": "1st overdue reminder",
        "day_+14": "2nd overdue reminder",
        "day_+30": "Final notice",
        "escalation": "Collections agency referral"
    },
    "dunning_levels": {
        "level_1": "Friendly reminder email",
        "level_2": "Payment request + phone call",
        "level_3": "Account on hold warning",
        "level_4": "Credit stop, collections"
    }
}
```

**Aging Analysis**:
```
Receivables Aging Report:
Current:      $500,000  (62.5%)
1-30 days:    $200,000  (25%)
31-60 days:   $75,000   (9.4%)
61-90 days:   $20,000   (2.5%)
90+ days:     $5,000    (0.6%)
Total:        $800,000
DSO: 38 days
```

### 5. Bank Reconciliation
**Status**: Must-Have | **Competitive Parity**: Advanced

**Auto Reconciliation**:
```python
reconciliation_engine = {
    "import_methods": {
        "bank_feeds": "Direct bank integration (Plaid, Yodlee)",
        "file_upload": "CSV, OFX, QIF, BAI2, MT940",
        "manual_entry": "Manual transaction entry"
    },
    "matching_rules": {
        "exact_match": "Amount + reference match",
        "fuzzy_match": "Similar amount + date range",
        "pattern_match": "Vendor name patterns",
        "ml_match": "AI-based matching"
    },
    "auto_actions": {
        "create_payment": "Auto-create payment entry",
        "create_deposit": "Auto-create deposit",
        "create_journal": "Bank charges, interest",
        "flag_review": "Manual review required"
    }
}
```

**Bank Statement Format Support**:
- BAI2 (Bank Administration Institute)
- MT940 (SWIFT)
- CAMT.053 (ISO 20022)
- OFX (Open Financial Exchange)
- QIF (Quicken)
- CSV (Custom mapping)

**Reconciliation Workflow**:
```python
workflow = {
    "1_import": "Import bank statement",
    "2_auto_match": "AI matches 80%+ automatically",
    "3_manual_match": "Review unmatched items",
    "4_adjust": "Create adjusting entries",
    "5_close": "Mark as reconciled",
    "6_report": "Reconciliation report with audit trail"
}
```

### 6. Multi-Currency Support
**Status**: Must-Have | **Competitive Parity**: Advanced

**Currency Features**:
```python
multi_currency = {
    "base_currency": "Company's reporting currency (USD, EUR, etc.)",
    "transaction_currency": "Invoice/payment currency",
    "account_currency": "Foreign currency bank accounts",
    "exchange_rate_sources": {
        "manual": "Manual entry",
        "auto": "Auto-fetch from ECB, Fed, OpenExchangeRates"
    },
    "rate_types": {
        "spot": "Daily spot rate",
        "average": "Monthly average",
        "forward": "Forward contract rate",
        "custom": "Custom rate per transaction"
    }
}
```

**Foreign Exchange (FX) Management**:
```python
fx_features = {
    "revaluation": {
        "frequency": "Monthly, quarterly",
        "accounts": "Foreign currency AR, AP, bank accounts",
        "unrealized_gains_losses": "Mark-to-market",
        "realized_gains_losses": "On settlement"
    },
    "hedging": {
        "forward_contracts": "Lock in future rates",
        "options": "Currency options",
        "hedge_accounting": "IFRS 9, ASC 815 compliance"
    }
}
```

**Exchange Rate Tables**:
```
Currency Exchange Rates (Base: USD)
Date        EUR     GBP     INR     JPY     CNY
2025-11-10  0.85    0.73    83.50   149.20  7.25
2025-11-09  0.84    0.72    83.45   149.50  7.26
```

### 7. Cost Centers & Profit Centers
**Status**: Must-Have | **Competitive Parity**: Advanced

**Cost Center Management**:
```python
cost_centers = {
    "definition": "Department or function that incurs costs",
    "examples": ["HR", "IT", "Marketing", "R&D", "Admin"],
    "budget": "Annual budget per cost center",
    "tracking": "All expenses tagged to cost center",
    "reporting": "Budget vs. actual by cost center",
    "allocation": "Allocate shared costs (rent, utilities)"
}
```

**Profit Center Management**:
```python
profit_centers = {
    "definition": "Business unit with revenue and costs",
    "examples": ["North America", "EMEA", "Product Line A", "Store #123"],
    "p_l": "Full P&L per profit center",
    "transfer_pricing": "Inter-profit-center transactions",
    "reporting": "Profitability analysis by segment"
}
```

**Dimensional Accounting**:
```python
dimensions = {
    "mandatory": ["cost_center", "profit_center"],
    "optional": ["project", "location", "product_line", "customer_segment"],
    "custom": "Define custom dimensions",
    "reporting": "Slice & dice by any dimension"
}
```

### 8. Financial Reporting
**Status**: Must-Have | **Competitive Parity**: Advanced

**Standard Reports**:
```python
financial_reports = {
    "balance_sheet": {
        "frequency": "Monthly, quarterly, annual",
        "formats": "Standard, comparative, consolidated",
        "variants": "Classified, common-size, vertical analysis"
    },
    "income_statement": {
        "formats": "Single-step, multi-step",
        "variants": "By department, by product line, consolidated"
    },
    "cash_flow": {
        "methods": "Direct, indirect",
        "variants": "Operating, investing, financing activities"
    },
    "trial_balance": {
        "types": "Unadjusted, adjusted, post-closing"
    }
}
```

**Management Reports**:
```python
management_reports = {
    "budget_variance": "Budget vs. actual",
    "departmental_p_l": "P&L by department",
    "product_profitability": "Profit by product line",
    "project_profitability": "Profit by project",
    "cash_position": "Daily cash position",
    "working_capital": "Current assets - current liabilities",
    "key_ratios": "Liquidity, profitability, efficiency ratios"
}
```

**Report Builder**:
```python
report_builder = {
    "templates": "Pre-built report templates",
    "custom": "Drag-and-drop report designer",
    "formulas": "Custom calculations",
    "filtering": "By date, account, dimension",
    "scheduling": "Auto-generate and email",
    "export": "PDF, Excel, CSV"
}
```

**Key Financial Ratios**:
```python
ratios = {
    "liquidity": {
        "current_ratio": "Current Assets / Current Liabilities",
        "quick_ratio": "(Current Assets - Inventory) / Current Liabilities",
        "cash_ratio": "Cash / Current Liabilities"
    },
    "profitability": {
        "gross_margin": "Gross Profit / Revenue",
        "operating_margin": "Operating Income / Revenue",
        "net_margin": "Net Income / Revenue",
        "roa": "Net Income / Total Assets",
        "roe": "Net Income / Shareholders' Equity"
    },
    "efficiency": {
        "asset_turnover": "Revenue / Total Assets",
        "inventory_turnover": "COGS / Average Inventory",
        "receivable_turnover": "Revenue / Average AR"
    },
    "leverage": {
        "debt_to_equity": "Total Debt / Total Equity",
        "debt_to_assets": "Total Debt / Total Assets",
        "interest_coverage": "EBIT / Interest Expense"
    }
}
```

### 9. Period Close & Consolidation
**Status**: Must-Have | **Competitive Parity**: Advanced

**Month-End Close Checklist**:
```python
close_tasks = {
    "day_1_5": [
        "Post all transactions",
        "Reconcile bank accounts",
        "Review AR aging",
        "Review AP aging",
        "Accrue unbilled revenue"
    ],
    "day_6_10": [
        "Run depreciation",
        "Post payroll entries",
        "Accrue expenses",
        "Defer revenue",
        "Revalue foreign currency"
    ],
    "day_11_15": [
        "Review trial balance",
        "Post adjusting entries",
        "Run financial statements",
        "Variance analysis",
        "Close period (lock)"
    ]
}
```

**Consolidation Features**:
```python
consolidation = {
    "multi_entity": "Consolidate multiple legal entities",
    "elimination": {
        "inter_company_sales": "Eliminate IC revenue/expense",
        "inter_company_loans": "Eliminate IC receivables/payables",
        "investments": "Equity method, consolidation"
    },
    "currency_translation": "Translate foreign subsidiaries",
    "minority_interest": "Non-controlling interest calculation",
    "reporting": "Consolidated financials"
}
```

**Period Locking**:
```python
period_lock = {
    "hard_lock": "No changes allowed",
    "soft_lock": "Changes require approval",
    "role_based": "Accountant can override, others locked",
    "audit_trail": "All changes logged"
}
```

### 10. Budgeting & Forecasting
**Status**: Must-Have | **Competitive Advantage**: AI-Powered

**Budget Planning**:
```python
budgeting = {
    "types": {
        "annual_budget": "12-month operating budget",
        "capital_budget": "CapEx planning",
        "cash_budget": "Cash flow forecast",
        "project_budget": "Project-specific budget"
    },
    "methods": {
        "top_down": "Executive sets targets, cascade down",
        "bottom_up": "Departments submit, roll up",
        "zero_based": "Justify all expenses from zero",
        "incremental": "Prior year + adjustment"
    },
    "workflow": {
        "1_template": "Distribute budget templates",
        "2_submit": "Department managers submit",
        "3_review": "Finance reviews and consolidates",
        "4_approve": "Executive approval",
        "5_activate": "Load into system"
    }
}
```

**AI-Powered Forecasting**:
```python
ai_forecasting = {
    "revenue_forecast": {
        "inputs": ["Historical sales", "Pipeline", "Seasonality", "Market trends"],
        "method": "Machine learning regression",
        "output": "Monthly revenue forecast (±5% accuracy)"
    },
    "expense_forecast": {
        "inputs": ["Historical expenses", "Headcount plan", "Inflation"],
        "method": "Time series analysis",
        "output": "Expense forecast by category"
    },
    "cash_forecast": {
        "inputs": ["Revenue forecast", "Expense forecast", "AR/AP aging", "Payment terms"],
        "method": "AI-powered prediction",
        "output": "13-week cash flow forecast"
    }
}
```

**Budget vs. Actual Tracking**:
```
Department: Marketing
Budget vs. Actual - October 2025

Category          Budget      Actual      Variance    Variance %
Advertising       $50,000     $48,200     $1,800      3.6% under
Events            $20,000     $24,500     -$4,500     22.5% over
Payroll           $100,000    $100,000    $0          0%
Software          $5,000      $4,800      $200        4% under
Total             $175,000    $177,500    -$2,500     1.4% over
```

### 11. Tax Management
**Status**: Must-Have | **Competitive Parity**: Advanced

**Tax Types**:
```python
tax_types = {
    "sales_tax": {
        "types": ["State sales tax", "County tax", "City tax"],
        "calculation": "Item-level or invoice-level",
        "exemptions": "Tax-exempt customers/products",
        "nexus": "Tax obligations by state"
    },
    "vat_gst": {
        "regions": "EU VAT, India GST, Australia GST",
        "rates": "Standard, reduced, zero-rated",
        "reverse_charge": "B2B cross-border",
        "reporting": "VAT return, GST return"
    },
    "withholding_tax": {
        "types": "WHT on services, rent, interest",
        "rates": "Country-specific rates",
        "certificates": "Track WHT certificates"
    }
}
```

**Tax Compliance**:
```python
compliance = {
    "1099_reporting": "US 1099 forms for contractors",
    "vat_returns": "Monthly/quarterly VAT filing",
    "gst_returns": "GSTR-1, GSTR-3B (India)",
    "tax_audit_trail": "Complete audit trail",
    "e_invoicing": "Government e-invoice integration"
}
```

**Avalara Integration**:
- Real-time tax rate calculation
- Sales tax nexus determination
- Automated filing and remittance
- Exemption certificate management

### 12. Intercompany Accounting
**Status**: Should-Have | **Competitive Parity**: Advanced

**Intercompany Transactions**:
```python
intercompany = {
    "types": {
        "ic_sales": "Sales between entities",
        "ic_services": "Services rendered",
        "ic_loans": "Loans between entities",
        "ic_expenses": "Shared expense allocation"
    },
    "workflow": {
        "create": "Create IC transaction in Entity A",
        "mirror": "Auto-create mirror entry in Entity B",
        "match": "Match and reconcile",
        "eliminate": "Elimination entries for consolidation"
    },
    "settlement": {
        "netting": "Net IC balances before payment",
        "payment": "IC payment processing",
        "reconciliation": "IC reconciliation report"
    }
}
```

### 13. Fixed Asset Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Asset Tracking** (see ASSET-MANAGEMENT.md for full details):
```python
asset_basics = {
    "acquisition": "Purchase, construction, donation",
    "depreciation": "SL, DDB, MACRS, units of production",
    "disposal": "Sale, scrap, trade-in",
    "reporting": "Asset register, depreciation schedule"
}
```

---

## AI Agent Integration

### Finance AI Agents

**1. Invoice Processing Agent**
```python
agent_capabilities = {
    "ocr_extraction": "Extract invoice data from PDF/image",
    "gl_coding": "Predict GL account based on vendor/description",
    "duplicate_detection": "Flag potential duplicate invoices",
    "fraud_detection": "Identify suspicious invoices",
    "approval_routing": "Route to approver based on rules",
    "payment_scheduling": "Optimize payment timing for cash flow"
}
```

**2. Bank Reconciliation Agent**
```python
agent_capabilities = {
    "auto_match": "Match 90%+ of bank transactions automatically",
    "learn_patterns": "Learn vendor payment patterns",
    "anomaly_detection": "Flag unusual transactions",
    "missing_entry_alert": "Identify missing GL entries",
    "reconciliation_report": "Auto-generate reconciliation report"
}
```

**3. Financial Planning Agent**
```python
agent_capabilities = {
    "revenue_forecast": "Predict revenue based on pipeline + history",
    "expense_forecast": "Forecast expenses by category",
    "cash_forecast": "13-week cash flow forecast",
    "budget_variance_alert": "Alert when variance exceeds threshold",
    "scenario_planning": "Model best/worst/likely scenarios"
}
```

**4. Collections Agent**
```python
agent_capabilities = {
    "payment_prediction": "Predict customer payment date",
    "dunning_automation": "Auto-send payment reminders",
    "prioritization": "Prioritize accounts by risk and value",
    "email_drafting": "Draft personalized collection emails",
    "escalation": "Auto-escalate to manager/collections"
}
```

**5. Compliance Agent**
```python
agent_capabilities = {
    "transaction_review": "Flag non-compliant transactions",
    "audit_trail": "Ensure complete audit trail",
    "policy_enforcement": "Enforce accounting policies",
    "report_validation": "Validate financial statements",
    "regulatory_updates": "Alert on accounting standard changes"
}
```

---

## Database Schema

```sql
-- Chart of Accounts
CREATE TABLE accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Account Identification
    account_code VARCHAR(50) NOT NULL,
    account_name VARCHAR(255) NOT NULL,
    parent_account_id UUID REFERENCES accounts(id),

    -- Classification
    account_type VARCHAR(50) NOT NULL, -- asset, liability, equity, revenue, expense
    account_subtype VARCHAR(100),
    root_type VARCHAR(50) NOT NULL, -- asset, liability, equity, income, expense
    is_group BOOLEAN DEFAULT false,

    -- Controls
    allow_manual_posting BOOLEAN DEFAULT true,
    require_cost_center BOOLEAN DEFAULT false,
    require_project BOOLEAN DEFAULT false,
    frozen BOOLEAN DEFAULT false,

    -- Reporting
    balance_type VARCHAR(20) NOT NULL, -- debit, credit
    report_category VARCHAR(100),
    financial_statement VARCHAR(50), -- balance_sheet, income_statement, cash_flow

    -- Multi-Currency
    account_currency VARCHAR(3),
    allow_multi_currency BOOLEAN DEFAULT false,

    -- Consolidation
    consolidation_account_id UUID REFERENCES accounts(id),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, account_code),
    INDEX idx_tenant_type (tenant_id, account_type),
    INDEX idx_parent (parent_account_id)
);

-- Journal Entry
CREATE TABLE journal_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Entry Details
    entry_number VARCHAR(50) NOT NULL,
    posting_date DATE NOT NULL,
    entry_date DATE NOT NULL,

    -- Type & Status
    entry_type VARCHAR(50) NOT NULL, -- standard, sales, purchase, payment, etc.
    workflow_status VARCHAR(50) DEFAULT 'draft', -- draft, submitted, approved, posted, cancelled

    -- Reference
    reference_number VARCHAR(100),
    reference_doc_type VARCHAR(50), -- sales_invoice, purchase_invoice, payment, etc.
    reference_doc_id UUID,

    -- Description
    description TEXT,

    -- Fiscal Period
    fiscal_year INTEGER NOT NULL,
    fiscal_period INTEGER NOT NULL, -- 1-12

    -- Approval
    submitted_by UUID REFERENCES users(id),
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,
    posted_by UUID REFERENCES users(id),
    posted_at TIMESTAMPTZ,

    -- Reversal
    reversal_of UUID REFERENCES journal_entries(id),
    reversed_by UUID REFERENCES journal_entries(id),

    -- Recurring
    is_recurring BOOLEAN DEFAULT false,
    recurrence_pattern JSONB, -- {frequency: 'monthly', day: 1, end_date: '2025-12-31'}

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, entry_number),
    INDEX idx_tenant_status (tenant_id, workflow_status),
    INDEX idx_posting_date (posting_date),
    INDEX idx_fiscal (fiscal_year, fiscal_period)
);

-- Journal Entry Line Items
CREATE TABLE journal_entry_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journal_entry_id UUID REFERENCES journal_entries(id) ON DELETE CASCADE,
    tenant_id UUID REFERENCES tenants(id),

    -- Account
    account_id UUID REFERENCES accounts(id) NOT NULL,

    -- Debit/Credit
    debit_amount DECIMAL(15, 2) DEFAULT 0,
    credit_amount DECIMAL(15, 2) DEFAULT 0,

    -- Multi-Currency
    debit_amount_fc DECIMAL(15, 2), -- Foreign currency
    credit_amount_fc DECIMAL(15, 2),
    currency VARCHAR(3),
    exchange_rate DECIMAL(12, 6),

    -- Dimensions
    cost_center_id UUID REFERENCES cost_centers(id),
    profit_center_id UUID REFERENCES profit_centers(id),
    project_id UUID REFERENCES projects(id),
    department_id UUID,

    -- Description
    line_description TEXT,

    -- Reference
    reference_type VARCHAR(50),
    reference_id UUID,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_journal (journal_entry_id),
    INDEX idx_account (account_id),
    INDEX idx_cost_center (cost_center_id),

    CHECK (debit_amount >= 0 AND credit_amount >= 0),
    CHECK (NOT (debit_amount > 0 AND credit_amount > 0)) -- Can't have both debit and credit
);

-- Cost Centers
CREATE TABLE cost_centers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,

    parent_cost_center_id UUID REFERENCES cost_centers(id),
    is_group BOOLEAN DEFAULT false,

    manager_id UUID REFERENCES users(id),

    active BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, code),
    INDEX idx_tenant (tenant_id)
);

-- Profit Centers
CREATE TABLE profit_centers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,

    parent_profit_center_id UUID REFERENCES profit_centers(id),
    is_group BOOLEAN DEFAULT false,

    manager_id UUID REFERENCES users(id),

    active BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, code),
    INDEX idx_tenant (tenant_id)
);

-- Fiscal Years
CREATE TABLE fiscal_years (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    year INTEGER NOT NULL,
    year_start_date DATE NOT NULL,
    year_end_date DATE NOT NULL,

    is_closed BOOLEAN DEFAULT false,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, year),
    INDEX idx_tenant (tenant_id)
);

-- Accounting Periods
CREATE TABLE accounting_periods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    fiscal_year_id UUID REFERENCES fiscal_years(id),

    period_number INTEGER NOT NULL, -- 1-12
    period_name VARCHAR(50), -- Jan 2025, Q1 2025, etc.
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,

    status VARCHAR(20) DEFAULT 'open', -- open, closed, locked
    closed_by UUID REFERENCES users(id),
    closed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, fiscal_year_id, period_number),
    INDEX idx_tenant_year (tenant_id, fiscal_year_id),
    INDEX idx_dates (start_date, end_date)
);

-- Accounts Payable
CREATE TABLE supplier_invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Invoice Details
    invoice_number VARCHAR(100) NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,

    -- Supplier
    supplier_id UUID REFERENCES suppliers(id) NOT NULL,
    supplier_invoice_number VARCHAR(100), -- Supplier's invoice number

    -- Amounts
    subtotal DECIMAL(15, 2) NOT NULL,
    tax_amount DECIMAL(15, 2) DEFAULT 0,
    total_amount DECIMAL(15, 2) NOT NULL,

    -- Currency
    currency VARCHAR(3) DEFAULT 'USD',
    exchange_rate DECIMAL(12, 6) DEFAULT 1,

    -- Payment
    payment_terms VARCHAR(100), -- Net 30, 2/10 Net 30
    payment_status VARCHAR(50) DEFAULT 'unpaid', -- unpaid, partial, paid
    paid_amount DECIMAL(15, 2) DEFAULT 0,

    -- Workflow
    workflow_status VARCHAR(50) DEFAULT 'draft', -- draft, submitted, approved, posted

    -- 3-Way Match
    purchase_order_id UUID REFERENCES purchase_orders(id),
    goods_receipt_id UUID REFERENCES goods_receipts(id),
    match_status VARCHAR(50), -- matched, variance, no_match
    variance_amount DECIMAL(15, 2),

    -- GL Posting
    journal_entry_id UUID REFERENCES journal_entries(id),

    -- Approval
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, invoice_number),
    INDEX idx_supplier (supplier_id),
    INDEX idx_due_date (due_date),
    INDEX idx_status (payment_status)
);

-- Accounts Receivable
CREATE TABLE customer_invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Invoice Details
    invoice_number VARCHAR(100) NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,

    -- Customer
    customer_id UUID REFERENCES customers(id) NOT NULL,

    -- Amounts
    subtotal DECIMAL(15, 2) NOT NULL,
    tax_amount DECIMAL(15, 2) DEFAULT 0,
    discount_amount DECIMAL(15, 2) DEFAULT 0,
    total_amount DECIMAL(15, 2) NOT NULL,

    -- Currency
    currency VARCHAR(3) DEFAULT 'USD',
    exchange_rate DECIMAL(12, 6) DEFAULT 1,

    -- Payment
    payment_terms VARCHAR(100),
    payment_status VARCHAR(50) DEFAULT 'unpaid',
    paid_amount DECIMAL(15, 2) DEFAULT 0,

    -- Workflow
    workflow_status VARCHAR(50) DEFAULT 'draft',

    -- Reference
    sales_order_id UUID REFERENCES sales_orders(id),

    -- GL Posting
    journal_entry_id UUID REFERENCES journal_entries(id),

    -- Delivery
    sent_at TIMESTAMPTZ,
    viewed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, invoice_number),
    INDEX idx_customer (customer_id),
    INDEX idx_due_date (due_date),
    INDEX idx_status (payment_status)
);

-- Payment Entries
CREATE TABLE payment_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Payment Details
    payment_number VARCHAR(100) NOT NULL,
    payment_date DATE NOT NULL,

    -- Type
    payment_type VARCHAR(50) NOT NULL, -- received, paid

    -- Party
    party_type VARCHAR(50), -- customer, supplier
    party_id UUID,

    -- Amount
    paid_amount DECIMAL(15, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    exchange_rate DECIMAL(12, 6) DEFAULT 1,

    -- Method
    payment_method VARCHAR(50), -- cash, check, card, ach, wire
    reference_number VARCHAR(100), -- Check number, transaction ID

    -- Bank Account
    bank_account_id UUID REFERENCES bank_accounts(id),

    -- GL Posting
    journal_entry_id UUID REFERENCES journal_entries(id),

    -- Status
    status VARCHAR(50) DEFAULT 'draft',
    cleared BOOLEAN DEFAULT false,
    cleared_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, payment_number),
    INDEX idx_party (party_type, party_id),
    INDEX idx_date (payment_date),
    INDEX idx_bank (bank_account_id)
);

-- Payment Allocation (which invoices this payment applies to)
CREATE TABLE payment_allocations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_entry_id UUID REFERENCES payment_entries(id) ON DELETE CASCADE,

    invoice_type VARCHAR(50), -- customer_invoice, supplier_invoice
    invoice_id UUID,

    allocated_amount DECIMAL(15, 2) NOT NULL,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_payment (payment_entry_id),
    INDEX idx_invoice (invoice_type, invoice_id)
);

-- Bank Accounts
CREATE TABLE bank_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Account Details
    account_name VARCHAR(255) NOT NULL,
    account_number VARCHAR(100),
    bank_name VARCHAR(255),
    branch VARCHAR(255),

    -- GL Account
    gl_account_id UUID REFERENCES accounts(id) NOT NULL,

    -- Currency
    currency VARCHAR(3) DEFAULT 'USD',

    -- Bank Integration
    bank_integration_enabled BOOLEAN DEFAULT false,
    bank_connection_id VARCHAR(255), -- Plaid/Yodlee ID
    last_sync_at TIMESTAMPTZ,

    -- Status
    active BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant (tenant_id),
    INDEX idx_gl_account (gl_account_id)
);

-- Bank Transactions (from bank feeds)
CREATE TABLE bank_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    bank_account_id UUID REFERENCES bank_accounts(id),

    -- Transaction Details
    transaction_date DATE NOT NULL,
    description TEXT,
    reference VARCHAR(255),

    -- Amount
    withdrawal DECIMAL(15, 2) DEFAULT 0,
    deposit DECIMAL(15, 2) DEFAULT 0,
    balance DECIMAL(15, 2),

    -- Matching
    matched BOOLEAN DEFAULT false,
    payment_entry_id UUID REFERENCES payment_entries(id),
    journal_entry_id UUID REFERENCES journal_entries(id),

    -- AI Prediction
    predicted_account_id UUID REFERENCES accounts(id),
    confidence_score DECIMAL(5, 2), -- 0-100

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_bank_account (bank_account_id),
    INDEX idx_date (transaction_date),
    INDEX idx_matched (matched)
);

-- Bank Reconciliation
CREATE TABLE bank_reconciliations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    bank_account_id UUID REFERENCES bank_accounts(id),

    -- Period
    reconciliation_date DATE NOT NULL,
    from_date DATE NOT NULL,
    to_date DATE NOT NULL,

    -- Balances
    statement_balance DECIMAL(15, 2) NOT NULL,
    gl_balance DECIMAL(15, 2) NOT NULL,
    difference DECIMAL(15, 2),

    -- Status
    status VARCHAR(50) DEFAULT 'in_progress', -- in_progress, reconciled
    reconciled_by UUID REFERENCES users(id),
    reconciled_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_bank_account (bank_account_id),
    INDEX idx_date (reconciliation_date)
);

-- Currency Exchange Rates
CREATE TABLE exchange_rates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    from_currency VARCHAR(3) NOT NULL,
    to_currency VARCHAR(3) NOT NULL,
    exchange_date DATE NOT NULL,
    rate DECIMAL(12, 6) NOT NULL,

    rate_type VARCHAR(50) DEFAULT 'spot', -- spot, average, forward

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(from_currency, to_currency, exchange_date, rate_type),
    INDEX idx_currencies_date (from_currency, to_currency, exchange_date)
);

-- Budgets
CREATE TABLE budgets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    budget_name VARCHAR(255) NOT NULL,
    fiscal_year_id UUID REFERENCES fiscal_years(id),

    budget_type VARCHAR(50), -- operating, capital, cash

    status VARCHAR(50) DEFAULT 'draft', -- draft, submitted, approved, active

    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant_year (tenant_id, fiscal_year_id)
);

-- Budget Lines
CREATE TABLE budget_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    budget_id UUID REFERENCES budgets(id) ON DELETE CASCADE,

    -- Account & Dimensions
    account_id UUID REFERENCES accounts(id) NOT NULL,
    cost_center_id UUID REFERENCES cost_centers(id),
    profit_center_id UUID REFERENCES profit_centers(id),

    -- Period Amounts (monthly)
    period_1 DECIMAL(15, 2) DEFAULT 0,
    period_2 DECIMAL(15, 2) DEFAULT 0,
    period_3 DECIMAL(15, 2) DEFAULT 0,
    period_4 DECIMAL(15, 2) DEFAULT 0,
    period_5 DECIMAL(15, 2) DEFAULT 0,
    period_6 DECIMAL(15, 2) DEFAULT 0,
    period_7 DECIMAL(15, 2) DEFAULT 0,
    period_8 DECIMAL(15, 2) DEFAULT 0,
    period_9 DECIMAL(15, 2) DEFAULT 0,
    period_10 DECIMAL(15, 2) DEFAULT 0,
    period_11 DECIMAL(15, 2) DEFAULT 0,
    period_12 DECIMAL(15, 2) DEFAULT 0,

    annual_total DECIMAL(15, 2),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_budget (budget_id),
    INDEX idx_account (account_id)
);

-- Tax Templates
CREATE TABLE tax_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    tax_name VARCHAR(255) NOT NULL,
    tax_type VARCHAR(50), -- sales_tax, vat, gst, withholding

    -- Rate
    rate DECIMAL(5, 2) NOT NULL, -- Percentage

    -- GL Accounts
    tax_account_id UUID REFERENCES accounts(id),

    -- Applicability
    applicable_on VARCHAR(50), -- sales, purchases, both

    active BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_tenant (tenant_id)
);
```

---

## API Specification

### Chart of Accounts APIs

```python
# Get Chart of Accounts
GET /api/v1/accounting/accounts
Response: {
    "accounts": [
        {
            "id": "uuid",
            "account_code": "1000",
            "account_name": "Cash",
            "account_type": "asset",
            "parent_account_id": null,
            "balance": 150000.00
        }
    ]
}

# Create Account
POST /api/v1/accounting/accounts
Request: {
    "account_code": "1050",
    "account_name": "Petty Cash",
    "account_type": "asset",
    "parent_account_id": "uuid",
    "allow_manual_posting": true
}

# Get Account Balance
GET /api/v1/accounting/accounts/{id}/balance?as_of=2025-11-10
Response: {
    "account_id": "uuid",
    "balance": 25000.00,
    "debit_total": 100000.00,
    "credit_total": 75000.00,
    "as_of_date": "2025-11-10"
}
```

### Journal Entry APIs

```python
# Create Journal Entry
POST /api/v1/accounting/journal-entries
Request: {
    "posting_date": "2025-11-10",
    "entry_type": "standard",
    "description": "Record consulting revenue",
    "lines": [
        {
            "account_id": "uuid",
            "debit_amount": 10000.00,
            "cost_center_id": "uuid"
        },
        {
            "account_id": "uuid",
            "credit_amount": 10000.00,
            "cost_center_id": "uuid"
        }
    ]
}

# Get Journal Entry
GET /api/v1/accounting/journal-entries/{id}

# Submit for Approval
POST /api/v1/accounting/journal-entries/{id}/submit

# Approve
POST /api/v1/accounting/journal-entries/{id}/approve

# Post to GL
POST /api/v1/accounting/journal-entries/{id}/post

# Cancel
POST /api/v1/accounting/journal-entries/{id}/cancel
```

### Accounts Payable APIs

```python
# Create Supplier Invoice
POST /api/v1/accounting/ap/invoices
Request: {
    "supplier_id": "uuid",
    "invoice_date": "2025-11-10",
    "due_date": "2025-12-10",
    "supplier_invoice_number": "INV-2025-001",
    "payment_terms": "Net 30",
    "items": [
        {
            "description": "IT Services",
            "account_id": "uuid",
            "amount": 5000.00,
            "tax_template_id": "uuid"
        }
    ]
}

# AI Invoice OCR
POST /api/v1/accounting/ap/invoices/ocr
Request: {
    "file": "base64_encoded_pdf_or_image"
}
Response: {
    "extracted_data": {
        "supplier_name": "Acme Corp",
        "invoice_number": "INV-001",
        "invoice_date": "2025-11-10",
        "total_amount": 5000.00,
        "line_items": [...]
    },
    "confidence": 0.95
}

# Get Aging Report
GET /api/v1/accounting/ap/aging?as_of=2025-11-10
Response: {
    "total_payable": 250000.00,
    "buckets": {
        "0_30": 150000.00,
        "31_60": 75000.00,
        "61_90": 20000.00,
        "over_90": 5000.00
    },
    "by_supplier": [...]
}
```

### Accounts Receivable APIs

```python
# Create Customer Invoice
POST /api/v1/accounting/ar/invoices
Request: {
    "customer_id": "uuid",
    "invoice_date": "2025-11-10",
    "due_date": "2025-12-10",
    "payment_terms": "Net 30",
    "items": [
        {
            "description": "Consulting Services",
            "account_id": "uuid",
            "quantity": 40,
            "rate": 150.00,
            "amount": 6000.00
        }
    ]
}

# Send Invoice
POST /api/v1/accounting/ar/invoices/{id}/send
Request: {
    "recipients": ["customer@example.com"],
    "subject": "Invoice INV-2025-001",
    "message": "Please find attached invoice."
}

# Record Payment
POST /api/v1/accounting/ar/payments
Request: {
    "customer_id": "uuid",
    "payment_date": "2025-11-10",
    "amount": 6000.00,
    "payment_method": "check",
    "reference_number": "CHK-12345",
    "allocations": [
        {
            "invoice_id": "uuid",
            "amount": 6000.00
        }
    ]
}

# Get Aging Report
GET /api/v1/accounting/ar/aging?as_of=2025-11-10

# AI Payment Prediction
GET /api/v1/accounting/ar/payment-predictions/{customer_id}
Response: {
    "customer_id": "uuid",
    "outstanding_invoices": [
        {
            "invoice_id": "uuid",
            "invoice_number": "INV-001",
            "amount": 10000.00,
            "due_date": "2025-11-20",
            "predicted_payment_date": "2025-11-18",
            "confidence": 0.85,
            "risk_score": "low"
        }
    ]
}
```

### Bank Reconciliation APIs

```python
# Import Bank Statement
POST /api/v1/accounting/bank-reconciliation/import
Request: {
    "bank_account_id": "uuid",
    "file_format": "csv",
    "file": "base64_encoded_file"
}

# Auto-Match Transactions
POST /api/v1/accounting/bank-reconciliation/auto-match
Request: {
    "bank_account_id": "uuid",
    "from_date": "2025-11-01",
    "to_date": "2025-11-30"
}
Response: {
    "total_transactions": 100,
    "auto_matched": 87,
    "unmatched": 13,
    "match_rate": 0.87
}

# Manual Match
POST /api/v1/accounting/bank-reconciliation/match
Request: {
    "bank_transaction_id": "uuid",
    "payment_entry_id": "uuid"
}

# Create Reconciliation
POST /api/v1/accounting/bank-reconciliation
Request: {
    "bank_account_id": "uuid",
    "reconciliation_date": "2025-11-30",
    "statement_balance": 125000.00
}

# Finalize Reconciliation
POST /api/v1/accounting/bank-reconciliation/{id}/finalize
```

### Financial Reports APIs

```python
# Balance Sheet
GET /api/v1/accounting/reports/balance-sheet
Query Params: ?as_of=2025-11-10&cost_center_id=uuid
Response: {
    "as_of_date": "2025-11-10",
    "assets": {
        "current_assets": {
            "cash": 150000.00,
            "accounts_receivable": 800000.00,
            "total": 950000.00
        },
        "fixed_assets": {...},
        "total_assets": 2000000.00
    },
    "liabilities": {...},
    "equity": {...}
}

# Income Statement
GET /api/v1/accounting/reports/income-statement
Query Params: ?from=2025-11-01&to=2025-11-30&profit_center_id=uuid

# Cash Flow Statement
GET /api/v1/accounting/reports/cash-flow
Query Params: ?from=2025-11-01&to=2025-11-30

# Trial Balance
GET /api/v1/accounting/reports/trial-balance
Query Params: ?as_of=2025-11-30

# General Ledger
GET /api/v1/accounting/reports/general-ledger
Query Params: ?account_id=uuid&from=2025-11-01&to=2025-11-30

# Budget vs Actual
GET /api/v1/accounting/reports/budget-vs-actual
Query Params: ?budget_id=uuid&period=2025-11
```

### Period Close APIs

```python
# Get Close Checklist
GET /api/v1/accounting/period-close/checklist/{period_id}
Response: {
    "period": "November 2025",
    "tasks": [
        {
            "id": "uuid",
            "task": "Reconcile all bank accounts",
            "status": "completed",
            "completed_by": "user@example.com",
            "completed_at": "2025-12-02T10:00:00Z"
        },
        {
            "id": "uuid",
            "task": "Run depreciation",
            "status": "pending"
        }
    ],
    "completion_percentage": 60
}

# Close Period
POST /api/v1/accounting/period-close/close
Request: {
    "period_id": "uuid",
    "close_type": "soft" // soft or hard
}

# Reopen Period
POST /api/v1/accounting/period-close/reopen
Request: {
    "period_id": "uuid",
    "reason": "Adjusting entry required"
}
```

---

## Security Considerations

### Access Controls

```python
accounting_permissions = {
    "accounting.accounts.view": "View chart of accounts",
    "accounting.accounts.create": "Create accounts",
    "accounting.accounts.edit": "Edit accounts",

    "accounting.journal.view": "View journal entries",
    "accounting.journal.create": "Create journal entries",
    "accounting.journal.submit": "Submit for approval",
    "accounting.journal.approve": "Approve journal entries",
    "accounting.journal.post": "Post to general ledger",
    "accounting.journal.cancel": "Cancel posted entries",

    "accounting.ap.view": "View supplier invoices",
    "accounting.ap.create": "Create supplier invoices",
    "accounting.ap.approve": "Approve supplier invoices",

    "accounting.ar.view": "View customer invoices",
    "accounting.ar.create": "Create customer invoices",

    "accounting.payments.view": "View payments",
    "accounting.payments.create": "Create payments",
    "accounting.payments.approve": "Approve payments",

    "accounting.bank_rec.view": "View bank reconciliation",
    "accounting.bank_rec.perform": "Perform reconciliation",

    "accounting.reports.view": "View financial reports",
    "accounting.reports.export": "Export reports",

    "accounting.period_close.perform": "Close accounting period",
    "accounting.period_close.reopen": "Reopen closed period",

    "accounting.budget.view": "View budgets",
    "accounting.budget.create": "Create budgets",
    "accounting.budget.approve": "Approve budgets"
}
```

### Separation of Duties

```python
sod_controls = {
    "rule_1": {
        "conflict": ["accounting.journal.create", "accounting.journal.approve"],
        "reason": "Same user cannot create and approve entries"
    },
    "rule_2": {
        "conflict": ["accounting.ap.create", "accounting.payments.approve"],
        "reason": "Same user cannot create invoice and approve payment"
    },
    "rule_3": {
        "conflict": ["accounting.ar.create", "accounting.payments.create"],
        "reason": "Same user cannot create invoice and record payment"
    }
}
```

### Audit Trail

```python
audit_events = {
    "journal_entry_created": "Who, when, what",
    "journal_entry_approved": "Approver, timestamp",
    "journal_entry_posted": "Posted by, timestamp",
    "journal_entry_cancelled": "Cancelled by, reason, timestamp",
    "period_closed": "Closed by, timestamp",
    "period_reopened": "Reopened by, reason, timestamp",
    "account_modified": "Field changes, modified by, timestamp",
    "payment_created": "Payment details, created by, timestamp"
}
```

### Data Encryption

```python
encryption = {
    "at_rest": "AES-256 encryption for database",
    "in_transit": "TLS 1.3 for all API calls",
    "bank_credentials": "Encrypted vault for bank integration credentials",
    "pii": "Encrypt sensitive financial data"
}
```

---

## Implementation Roadmap

### Phase 1: Core Accounting (Month 1-2)
- [ ] Chart of accounts
- [ ] Journal entries (manual)
- [ ] General ledger
- [ ] Trial balance
- [ ] Basic financial statements (Balance Sheet, Income Statement)

### Phase 2: AP & AR (Month 3)
- [ ] Accounts Payable
- [ ] Accounts Receivable
- [ ] Payment entries
- [ ] Aging reports
- [ ] Invoice templates

### Phase 3: Bank & Reconciliation (Month 4)
- [ ] Bank account management
- [ ] Bank statement import
- [ ] Auto-reconciliation (AI-powered)
- [ ] Payment gateway integration

### Phase 4: Multi-Currency & Dimensions (Month 5)
- [ ] Multi-currency support
- [ ] Exchange rate management
- [ ] Cost centers
- [ ] Profit centers
- [ ] Dimensional reporting

### Phase 5: Advanced Features (Month 6)
- [ ] Budgeting
- [ ] AI forecasting
- [ ] Period close automation
- [ ] Consolidation
- [ ] Tax management

### Phase 6: AI & Automation (Month 7)
- [ ] AI invoice OCR
- [ ] Auto GL coding
- [ ] Collections automation
- [ ] Fraud detection
- [ ] Predictive analytics

---

## Competitive Analysis

| Feature | SARAISE | SAP S/4HANA | Oracle NetSuite | Microsoft D365 | Odoo |
|---------|---------|-------------|-----------------|----------------|------|
| **Chart of Accounts** | ✓ Flexible | ✓ | ✓ | ✓ | ✓ |
| **Multi-Currency** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **AI Invoice OCR** | ✓ | ✓ | ✓ Add-on | ✓ Copilot | ✗ |
| **Auto Bank Rec** | ✓ 90%+ match | ✓ | ✓ | ✓ | ✓ Basic |
| **Dimensional Accounting** | ✓ Unlimited | ✓ | ✓ Limited | ✓ | ✓ Limited |
| **Consolidation** | ✓ | ✓ | ✓ | ✓ | ✓ Limited |
| **AI Forecasting** | ✓ ML-powered | ✓ | ✓ | ✓ | ✗ |
| **Real-time Reports** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Mobile App** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **API-First** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Pricing** | $$ | $$$$ | $$$ | $$$ | $ |

**Verdict**: Matches SAP/Oracle/Microsoft on core features with superior AI and significantly lower cost.

---

## Success Metrics

- **Close Time**: Month-end close in < 5 days
- **Automation Rate**: 80%+ of journal entries auto-generated
- **Bank Rec Efficiency**: 90%+ auto-match rate
- **Forecast Accuracy**: ±5% variance in revenue/expense forecast
- **Invoice Processing**: AI OCR processes 95%+ invoices without manual intervention
- **DSO (Days Sales Outstanding)**: Reduce by 20%
- **User Adoption**: > 95% finance team daily active users
- **Compliance**: Zero audit findings
- **ROI**: 3x return in year 1 (time savings + cash flow improvement)

---

**Document Control**:
- **Author**: SARAISE Architecture Team
- **Last Updated**: 2025-11-10
- **Status**: Planning - Ready for Implementation
