# Accounting Module - Database Schema (ERD)

> **Database Design Philosophy**: Normalized (3NF), Scalable, **Multi-tenant (Row-Level Security)**, Event-sourced for audit
>
> **Technology**: PostgreSQL (primary), TimescaleDB (time-series), MongoDB (documents), Redis (cache)

---

## TABLE OF CONTENTS

1. [Core Accounting Tables](#1-core-accounting-tables)
2. [Accounts Payable Tables](#2-accounts-payable-tables)
3. [Accounts Receivable Tables](#3-accounts-receivable-tables)
4. [Cash Management Tables](#4-cash-management-tables)
5. [Fixed Assets Tables](#5-fixed-assets-tables)
6. [Tax Management Tables](#6-tax-management-tables)
7. [Multi-GAAP Tables](#7-multi-gaap-tables)
8. [Workflow & Approval Tables](#8-workflow--approval-tables)
9. [Audit & Security Tables](#9-audit--security-tables)
10. [Master Data Tables](#10-master-data-tables)
11. [Indexes & Performance](#11-indexes--performance)
12. [Partitioning Strategy](#12-partitioning-strategy)

---

## 1. CORE ACCOUNTING TABLES

### 1.1 companies
**Purpose**: Legal entities / organizations

```sql
CREATE TABLE companies (
    company_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL, -- SARAISE Multi-tenancy
    company_code            VARCHAR(20) NOT NULL,
    legal_name              VARCHAR(200) NOT NULL,
    trade_name              VARCHAR(200),
    tax_id                  VARCHAR(50),
    registration_number     VARCHAR(50),
    incorporation_date      DATE,
    base_currency_code      VARCHAR(3) NOT NULL,
    functional_currency_code VARCHAR(3) NOT NULL,
    reporting_currency_code  VARCHAR(3),
    fiscal_year_start       INTEGER NOT NULL CHECK (fiscal_year_start BETWEEN 1 AND 12),
    fiscal_year_end         INTEGER NOT NULL CHECK (fiscal_year_end BETWEEN 1 AND 12),
    primary_gaap            VARCHAR(20) NOT NULL, -- US_GAAP, IFRS, IND_AS
    country_code            VARCHAR(2) NOT NULL,
    parent_company_id       UUID REFERENCES companies(company_id),
    consolidation_method    VARCHAR(20), -- FULL, PROPORTIONATE, EQUITY
    ownership_percentage    DECIMAL(5,2),
    status                  VARCHAR(20) DEFAULT 'ACTIVE',
    logo_url                TEXT,
    created_by              UUID NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by              UUID,
    updated_at              TIMESTAMP,

    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_company_code UNIQUE (tenant_id, company_code),
    CONSTRAINT chk_ownership CHECK (ownership_percentage BETWEEN 0 AND 100)
);

CREATE INDEX idx_companies_tenant ON companies(tenant_id);
CREATE INDEX idx_companies_parent ON companies(parent_company_id);
CREATE INDEX idx_companies_status ON companies(status);
```

---

### 1.2 gl_ledgers
**Purpose**: Support multi-GAAP with parallel ledgers

```sql
CREATE TABLE gl_ledgers (
    ledger_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    company_id              UUID NOT NULL REFERENCES companies(company_id),
    ledger_code             VARCHAR(20) NOT NULL,
    ledger_name             VARCHAR(100) NOT NULL,
    ledger_type             VARCHAR(20) NOT NULL, -- PRIMARY, SECONDARY, TAX, MANAGEMENT, IFRS, US_GAAP
    gaap_standard           VARCHAR(20),
    currency_code           VARCHAR(3) NOT NULL,
    chart_of_accounts_id    UUID NOT NULL,
    status                  VARCHAR(20) DEFAULT 'ACTIVE',
    effective_from          DATE NOT NULL,
    effective_to            DATE,
    created_by              UUID NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_ledger_code UNIQUE (tenant_id, company_id, ledger_code)
);

CREATE INDEX idx_ledgers_tenant ON gl_ledgers(tenant_id);
CREATE INDEX idx_ledgers_company ON gl_ledgers(company_id);
CREATE INDEX idx_ledgers_type ON gl_ledgers(ledger_type);
```

---

### 1.3 accounting_periods
**Purpose**: Accounting period management

```sql
CREATE TABLE accounting_periods (
    period_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    company_id              UUID NOT NULL REFERENCES companies(company_id),
    period_name             VARCHAR(50) NOT NULL,
    period_type             VARCHAR(20) NOT NULL, -- MONTH, QUARTER, YEAR
    fiscal_year             INTEGER NOT NULL,
    period_number           INTEGER NOT NULL,
    start_date              DATE NOT NULL,
    end_date                DATE NOT NULL,
    status                  VARCHAR(20) DEFAULT 'OPEN', -- OPEN, CLOSED, PERMANENTLY_CLOSED
    close_date              TIMESTAMP,
    closed_by               UUID,
    reopen_date             TIMESTAMP,
    reopened_by             UUID,
    created_by              UUID NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_dates CHECK (end_date > start_date),
    CONSTRAINT chk_dates CHECK (end_date > start_date),
    CONSTRAINT uq_period UNIQUE (tenant_id, company_id, fiscal_year, period_number)
);

CREATE INDEX idx_periods_tenant ON accounting_periods(tenant_id);
CREATE INDEX idx_periods_company ON accounting_periods(company_id);
CREATE INDEX idx_periods_status ON accounting_periods(status);
CREATE INDEX idx_periods_dates ON accounting_periods(start_date, end_date);
```

---

### 1.4 chart_of_accounts
**Purpose**: Account master

```sql
CREATE TABLE chart_of_accounts (
    account_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    company_id              UUID NOT NULL REFERENCES companies(company_id),
    account_code            VARCHAR(50) NOT NULL,
    account_name            VARCHAR(200) NOT NULL,
    account_type            VARCHAR(20) NOT NULL, -- ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE
    account_subtype         VARCHAR(50),
    account_category        VARCHAR(50),
    parent_account_id       UUID REFERENCES chart_of_accounts(account_id),
    level                   INTEGER NOT NULL DEFAULT 1,
    hierarchy_path          TEXT, -- e.g., /10000/10100/10110 for quick hierarchy queries
    is_control_account      BOOLEAN DEFAULT FALSE,
    is_reconciliation_required BOOLEAN DEFAULT FALSE,
    is_budget_enabled       BOOLEAN DEFAULT FALSE,
    is_leaf_account         BOOLEAN DEFAULT TRUE, -- Can post transactions
    currency_code           VARCHAR(3),
    allow_multi_currency    BOOLEAN DEFAULT FALSE,
    normal_balance          VARCHAR(10) NOT NULL, -- DEBIT, CREDIT
    opening_balance_debit   DECIMAL(20,2) DEFAULT 0,
    opening_balance_credit  DECIMAL(20,2) DEFAULT 0,
    opening_balance_date    DATE,
    status                  VARCHAR(20) DEFAULT 'ACTIVE',
    effective_from          DATE NOT NULL,
    effective_to            DATE,
    gl_segments             JSONB, -- For multi-segment COA: {"segment1": "value1", ...}
    multi_gaap_mapping      JSONB, -- {"US_GAAP": "account_code", "IFRS": "account_code"}
    tax_code_default        VARCHAR(20),
    description             TEXT,
    created_by              UUID NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by              UUID,
    updated_at              TIMESTAMP,

    updated_at              TIMESTAMP,

    CONSTRAINT uq_account_code UNIQUE (tenant_id, company_id, account_code),
    CONSTRAINT chk_account_type CHECK (account_type IN ('ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE')),
    CONSTRAINT chk_normal_balance CHECK (normal_balance IN ('DEBIT', 'CREDIT'))
);

    CONSTRAINT chk_normal_balance CHECK (normal_balance IN ('DEBIT', 'CREDIT'))
);

CREATE INDEX idx_coa_tenant ON chart_of_accounts(tenant_id);
CREATE INDEX idx_coa_company ON chart_of_accounts(company_id);
CREATE INDEX idx_coa_parent ON chart_of_accounts(parent_account_id);
CREATE INDEX idx_coa_type ON chart_of_accounts(account_type);
CREATE INDEX idx_coa_hierarchy ON chart_of_accounts USING GIST (hierarchy_path gist_trgm_ops);
CREATE INDEX idx_coa_status ON chart_of_accounts(status);
```

---

### 1.5 journal_entries
**Purpose**: Journal entry header

```sql
CREATE TABLE journal_entries (
    journal_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    journal_number          VARCHAR(50) NOT NULL,
    company_id              UUID NOT NULL REFERENCES companies(company_id),
    ledger_id               UUID NOT NULL REFERENCES gl_ledgers(ledger_id),
    period_id               UUID NOT NULL REFERENCES accounting_periods(period_id),
    journal_type            VARCHAR(30) NOT NULL, -- STANDARD, ADJUSTMENT, REVERSING, RECURRING, ACCRUAL
    journal_date            DATE NOT NULL,
    posting_date            DATE NOT NULL,
    currency_code           VARCHAR(3) NOT NULL,
    exchange_rate           DECIMAL(12,6) DEFAULT 1.0,
    description             TEXT NOT NULL,
    reference_number        VARCHAR(100),
    source_type             VARCHAR(30) NOT NULL, -- MANUAL, SYSTEM, INTERFACE, API
    source_module           VARCHAR(50), -- AP, AR, FA, INV, etc.
    source_transaction_id   UUID,
    status                  VARCHAR(20) DEFAULT 'DRAFT', -- DRAFT, PENDING_APPROVAL, APPROVED, POSTED, REVERSED, CANCELLED
    is_reversing_entry      BOOLEAN DEFAULT FALSE,
    reversal_date           DATE,
    reversed_journal_id     UUID REFERENCES journal_entries(journal_id),
    reversal_journal_id     UUID REFERENCES journal_entries(journal_id),
    workflow_instance_id    UUID,
    total_debit             DECIMAL(20,2) DEFAULT 0,
    total_credit            DECIMAL(20,2) DEFAULT 0,
    is_balanced             BOOLEAN GENERATED ALWAYS AS (ABS(total_debit - total_credit) < 0.01) STORED,
    attachment_count        INTEGER DEFAULT 0,
    created_by              UUID NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_by            UUID,
    submitted_at            TIMESTAMP,
    approved_by             UUID,
    approved_at             TIMESTAMP,
    posted_by               UUID,
    posted_at               TIMESTAMP,
    updated_by              UUID,
    updated_at              TIMESTAMP,

    CONSTRAINT chk_balanced CHECK (is_balanced = TRUE OR status IN ('DRAFT', 'PENDING_APPROVAL')),
    CONSTRAINT uq_journal_number UNIQUE (tenant_id, journal_number)
);

CREATE INDEX idx_journal_tenant ON journal_entries(tenant_id);
CREATE INDEX idx_journal_company ON journal_entries(company_id);
CREATE INDEX idx_journal_period ON journal_entries(period_id);
CREATE INDEX idx_journal_ledger ON journal_entries(ledger_id);
CREATE INDEX idx_journal_date ON journal_entries(journal_date);
CREATE INDEX idx_journal_status ON journal_entries(status);
CREATE INDEX idx_journal_source ON journal_entries(source_type, source_module);
CREATE INDEX idx_journal_reversed ON journal_entries(reversed_journal_id) WHERE reversed_journal_id IS NOT NULL;

-- Partition by journal_date (monthly partitions)
-- CREATE TABLE journal_entries_2024_01 PARTITION OF journal_entries FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
```

---

### 1.6 journal_entry_lines
**Purpose**: Journal entry line items

```sql
CREATE TABLE journal_entry_lines (
    line_id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL, -- For direct RLS filtering
    journal_id              UUID NOT NULL REFERENCES journal_entries(journal_id) ON DELETE CASCADE,
    line_number             INTEGER NOT NULL,
    account_id              UUID NOT NULL REFERENCES chart_of_accounts(account_id),
    debit_amount            DECIMAL(20,2) DEFAULT 0 CHECK (debit_amount >= 0),
    credit_amount           DECIMAL(20,2) DEFAULT 0 CHECK (credit_amount >= 0),
    debit_functional        DECIMAL(20,2) DEFAULT 0, -- In functional currency
    credit_functional       DECIMAL(20,2) DEFAULT 0,
    description             TEXT,
    department_id           UUID,
    cost_center_id          UUID,
    project_id              UUID,
    product_id              UUID,
    customer_id             UUID,
    vendor_id               UUID,
    employee_id             UUID,
    tax_code                VARCHAR(20),
    tax_amount              DECIMAL(20,2) DEFAULT 0,
    is_intercompany         BOOLEAN DEFAULT FALSE,
    ic_company_id           UUID REFERENCES companies(company_id),
    dimension_values        JSONB, -- Custom dimensions: {"dimension1": "value1", ...}
    statistical_amount      DECIMAL(20,2), -- For quantity-based reporting
    statistical_uom         VARCHAR(10),
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_debit_credit CHECK (
        (debit_amount > 0 AND credit_amount = 0) OR
        (credit_amount > 0 AND debit_amount = 0) OR
        (debit_amount = 0 AND credit_amount = 0)
    ),
    CONSTRAINT uq_line_number UNIQUE (journal_id, line_number)
);

CREATE INDEX idx_jel_tenant ON journal_entry_lines(tenant_id);
CREATE INDEX idx_jel_journal ON journal_entry_lines(journal_id);
CREATE INDEX idx_jel_account ON journal_entry_lines(account_id);
CREATE INDEX idx_jel_department ON journal_entry_lines(department_id) WHERE department_id IS NOT NULL;
CREATE INDEX idx_jel_project ON journal_entry_lines(project_id) WHERE project_id IS NOT NULL;
CREATE INDEX idx_jel_ic ON journal_entry_lines(ic_company_id) WHERE is_intercompany = TRUE;
CREATE INDEX idx_jel_dimensions ON journal_entry_lines USING GIN (dimension_values);
```

---

### 1.7 account_balances
**Purpose**: Materialized account balances for performance (updated on post)

```sql
CREATE TABLE account_balances (
    balance_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    company_id              UUID NOT NULL REFERENCES companies(company_id),
    ledger_id               UUID NOT NULL REFERENCES gl_ledgers(ledger_id),
    account_id              UUID NOT NULL REFERENCES chart_of_accounts(account_id),
    period_id               UUID NOT NULL REFERENCES accounting_periods(period_id),
    currency_code           VARCHAR(3) NOT NULL,
    opening_debit           DECIMAL(20,2) DEFAULT 0,
    opening_credit          DECIMAL(20,2) DEFAULT 0,
    period_debit            DECIMAL(20,2) DEFAULT 0,
    period_credit           DECIMAL(20,2) DEFAULT 0,
    closing_debit           DECIMAL(20,2) DEFAULT 0,
    closing_credit          DECIMAL(20,2) DEFAULT 0,
    net_movement            DECIMAL(20,2) GENERATED ALWAYS AS (period_debit - period_credit) STORED,
    net_balance             DECIMAL(20,2) GENERATED ALWAYS AS (closing_debit - closing_credit) STORED,
    last_transaction_date   DATE,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_balance UNIQUE (tenant_id, company_id, ledger_id, account_id, period_id, currency_code)
);

CREATE INDEX idx_balances_tenant ON account_balances(tenant_id);
CREATE INDEX idx_balances_company ON account_balances(company_id);
CREATE INDEX idx_balances_period ON account_balances(period_id);
CREATE INDEX idx_balances_account ON account_balances(account_id);
CREATE INDEX idx_balances_ledger ON account_balances(ledger_id);
```

---

### 1.8 gl_transaction_log
**Purpose**: Event-sourced GL transaction log (immutable, append-only for audit)

```sql
CREATE TABLE gl_transaction_log (
    log_id                  BIGSERIAL PRIMARY KEY,
    transaction_id          UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    company_id              UUID NOT NULL,
    ledger_id               UUID NOT NULL,
    account_id              UUID NOT NULL,
    transaction_date        DATE NOT NULL,
    posting_date            DATE NOT NULL,
    period_id               UUID NOT NULL,
    debit_amount            DECIMAL(20,2) DEFAULT 0,
    credit_amount           DECIMAL(20,2) DEFAULT 0,
    currency_code           VARCHAR(3) NOT NULL,
    exchange_rate           DECIMAL(12,6) DEFAULT 1.0,
    journal_id              UUID NOT NULL,
    line_id                 UUID NOT NULL,
    description             TEXT,
    source_type             VARCHAR(30) NOT NULL,
    source_module           VARCHAR(50),
    source_transaction_id   UUID,
    department_id           UUID,
    project_id              UUID,
    dimension_values        JSONB,
    posted_by               UUID NOT NULL,
    posted_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_reversed             BOOLEAN DEFAULT FALSE,
    reversal_log_id         BIGINT REFERENCES gl_transaction_log(log_id)
);

-- TimescaleDB hypertable for time-series optimization
SELECT create_hypertable('gl_transaction_log', 'posted_at', chunk_time_interval => INTERVAL '1 month');

CREATE INDEX idx_gl_log_tenant ON gl_transaction_log(tenant_id, posted_at DESC);
CREATE INDEX idx_gl_log_company ON gl_transaction_log(company_id, posted_at DESC);
CREATE INDEX idx_gl_log_account ON gl_transaction_log(account_id, posted_at DESC);
CREATE INDEX idx_gl_log_journal ON gl_transaction_log(journal_id);
CREATE INDEX idx_gl_log_period ON gl_transaction_log(period_id);
```

---

## 2. ACCOUNTS PAYABLE TABLES

### 2.1 vendors
**Purpose**: Vendor master data

```sql
CREATE TABLE vendors (
    vendor_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    vendor_code             VARCHAR(50) NOT NULL,
    vendor_name             VARCHAR(200) NOT NULL,
    legal_name              VARCHAR(200),
    trade_name              VARCHAR(200),
    vendor_type             VARCHAR(50) NOT NULL, -- SUPPLIER, SERVICE_PROVIDER, CONTRACTOR, CONSULTANT
    parent_vendor_id        UUID REFERENCES vendors(vendor_id),
    vendor_group_id         UUID,
    tax_id                  VARCHAR(50),
    tax_registration_numbers JSONB, -- {"GST": "...", "VAT": "...", "PAN": "..."}
    currency_code           VARCHAR(3) NOT NULL,
    payment_terms_id        UUID,
    payment_method_default  VARCHAR(30), -- CHECK, WIRE, ACH, RTGS, NEFT
    credit_limit            DECIMAL(20,2),
    credit_days             INTEGER,
    discount_percentage     DECIMAL(5,2),
    discount_days           INTEGER,
    is_1099_vendor          BOOLEAN DEFAULT FALSE, -- US tax
    withholding_tax_rate    DECIMAL(5,2),
    status                  VARCHAR(20) DEFAULT 'ACTIVE', -- ACTIVE, INACTIVE, BLOCKED, HOLD
    block_reason            TEXT,
    preferred_vendor        BOOLEAN DEFAULT FALSE,
    risk_rating             VARCHAR(20), -- LOW, MEDIUM, HIGH
    risk_score              INTEGER, -- AI-calculated: 0-100
    last_payment_date       DATE,
    total_purchases_ytd     DECIMAL(20,2) DEFAULT 0,
    total_purchases_ltd     DECIMAL(20,2) DEFAULT 0,
    ap_control_account_id   UUID REFERENCES chart_of_accounts(account_id),
    expense_account_default_id UUID REFERENCES chart_of_accounts(account_id),
    created_by              UUID NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by              UUID,
    updated_at              TIMESTAMP,

    CONSTRAINT uq_vendor_code UNIQUE (tenant_id, vendor_code)
);

CREATE INDEX idx_vendors_tenant ON vendors(tenant_id);
CREATE INDEX idx_vendors_group ON vendors(vendor_group_id);
CREATE INDEX idx_vendors_parent ON vendors(parent_vendor_id);
CREATE INDEX idx_vendors_name ON vendors USING GIN (vendor_name gin_trgm_ops);
```

---

### 2.2 vendor_contacts
**Purpose**: Vendor contact persons

```sql
CREATE TABLE vendor_contacts (
    contact_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_id               UUID NOT NULL REFERENCES vendors(vendor_id) ON DELETE CASCADE,
    contact_type            VARCHAR(20) NOT NULL, -- PRIMARY, BILLING, PAYMENT, PURCHASING
    first_name              VARCHAR(100) NOT NULL,
    last_name               VARCHAR(100) NOT NULL,
    title                   VARCHAR(100),
    email                   VARCHAR(200),
    phone                   VARCHAR(50),
    mobile                  VARCHAR(50),
    is_primary              BOOLEAN DEFAULT FALSE,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_vendor_contacts_vendor ON vendor_contacts(vendor_id);
```

---

### 2.3 vendor_addresses
**Purpose**: Vendor addresses (billing, shipping, etc.)

```sql
CREATE TABLE vendor_addresses (
    address_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_id               UUID NOT NULL REFERENCES vendors(vendor_id) ON DELETE CASCADE,
    address_type            VARCHAR(20) NOT NULL, -- BILLING, SHIPPING, REMITTANCE
    address_line1           VARCHAR(200) NOT NULL,
    address_line2           VARCHAR(200),
    city                    VARCHAR(100),
    state                   VARCHAR(100),
    postal_code             VARCHAR(20),
    country_code            VARCHAR(2) NOT NULL,
    is_primary              BOOLEAN DEFAULT FALSE,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_vendor_addresses_vendor ON vendor_addresses(vendor_id);
```

---

### 2.4 vendor_bank_accounts
**Purpose**: Vendor banking information for payments

```sql
CREATE TABLE vendor_bank_accounts (
    bank_account_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_id               UUID NOT NULL REFERENCES vendors(vendor_id) ON DELETE CASCADE,
    bank_name               VARCHAR(200) NOT NULL,
    account_number          VARCHAR(100) NOT NULL,
    account_holder_name     VARCHAR(200) NOT NULL,
    bank_code               VARCHAR(50), -- SWIFT, IFSC, Routing Number
    iban                    VARCHAR(50),
    currency_code           VARCHAR(3) NOT NULL,
    account_type            VARCHAR(20), -- CHECKING, SAVINGS
    is_primary              BOOLEAN DEFAULT FALSE,
    is_verified             BOOLEAN DEFAULT FALSE,
    verification_date       DATE,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_vendor_banks_vendor ON vendor_bank_accounts(vendor_id);
```

---

### 2.5 ap_invoices
**Purpose**: Purchase invoices

```sql
CREATE TABLE ap_invoices (
    invoice_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    invoice_number          VARCHAR(100) NOT NULL,
    vendor_id               UUID NOT NULL REFERENCES vendors(vendor_id),
    company_id              UUID NOT NULL REFERENCES companies(company_id),
    invoice_date            DATE NOT NULL,
    due_date                DATE NOT NULL,
    payment_terms_id        UUID,
    currency_code           VARCHAR(3) NOT NULL,
    exchange_rate           DECIMAL(12,6) DEFAULT 1.0,
    tax_treatment           VARCHAR(30), -- TAXABLE, EXEMPT, REVERSE_CHARGE
    purchase_order_id       UUID,
    grn_id                  UUID, -- Goods Receipt Note
    department_id           UUID,
    project_id              UUID,
    description             TEXT,
    subtotal                DECIMAL(20,2) NOT NULL,
    tax_amount              DECIMAL(20,2) DEFAULT 0,
    discount_amount         DECIMAL(20,2) DEFAULT 0,
    withholding_tax_amount  DECIMAL(20,2) DEFAULT 0,
    total_amount            DECIMAL(20,2) NOT NULL,
    amount_paid             DECIMAL(20,2) DEFAULT 0,
    amount_due              DECIMAL(20,2) GENERATED ALWAYS AS (total_amount - amount_paid) STORED,
    payment_status          VARCHAR(20) DEFAULT 'UNPAID', -- UNPAID, PARTIAL, PAID
    status                  VARCHAR(20) DEFAULT 'DRAFT', -- DRAFT, PENDING_APPROVAL, APPROVED, POSTED, CANCELLED
    hold_flag               BOOLEAN DEFAULT FALSE,
    hold_reason             TEXT,
    hold_date               TIMESTAMP,
    approval_workflow_id    UUID,
    is_recurring            BOOLEAN DEFAULT FALSE,
    recurrence_rule         JSONB,
    matched_to_po           BOOLEAN DEFAULT FALSE,
    matched_to_grn          BOOLEAN DEFAULT FALSE,
    match_variance_amount   DECIMAL(20,2),
    gl_posted               BOOLEAN DEFAULT FALSE,
    gl_journal_id           UUID,
    created_by              UUID NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_by            UUID,
    submitted_at            TIMESTAMP,
    approved_by             UUID,
    approved_at             TIMESTAMP,
    posted_by               UUID,
    posted_at               TIMESTAMP,
    updated_by              UUID,
    updated_at              TIMESTAMP,

    updated_by              UUID,
    updated_at              TIMESTAMP,

    CONSTRAINT uq_ap_invoice_number UNIQUE (tenant_id, company_id, vendor_id, invoice_number)
);

CREATE INDEX idx_ap_invoices_tenant ON ap_invoices(tenant_id);
CREATE INDEX idx_ap_invoices_vendor ON ap_invoices(vendor_id);
CREATE INDEX idx_ap_invoices_company ON ap_invoices(company_id);
CREATE INDEX idx_ap_invoices_date ON ap_invoices(invoice_date);
CREATE INDEX idx_ap_invoices_due ON ap_invoices(due_date);
CREATE INDEX idx_ap_invoices_status ON ap_invoices(status);
CREATE INDEX idx_ap_invoices_payment ON ap_invoices(payment_status);
CREATE INDEX idx_ap_invoices_po ON ap_invoices(purchase_order_id) WHERE purchase_order_id IS NOT NULL;
```

---

### 2.6 ap_invoice_lines
**Purpose**: Invoice line items

```sql
CREATE TABLE ap_invoice_lines (
    line_id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id              UUID NOT NULL REFERENCES ap_invoices(invoice_id) ON DELETE CASCADE,
    line_number             INTEGER NOT NULL,
    description             TEXT NOT NULL,
    gl_account_id           UUID NOT NULL REFERENCES chart_of_accounts(account_id),
    item_id                 UUID, -- If inventory item
    quantity                DECIMAL(12,3),
    unit_price              DECIMAL(20,4),
    line_amount             DECIMAL(20,2) NOT NULL,
    tax_code                VARCHAR(20),
    tax_amount              DECIMAL(20,2) DEFAULT 0,
    discount_percentage     DECIMAL(5,2),
    discount_amount         DECIMAL(20,2) DEFAULT 0,
    net_amount              DECIMAL(20,2) NOT NULL,
    department_id           UUID,
    project_id              UUID,
    cost_center_id          UUID,
    asset_id                UUID, -- If capitalizing as asset
    is_capitalized          BOOLEAN DEFAULT FALSE,
    dimension_values        JSONB,
    po_line_id              UUID,
    grn_line_id             UUID,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_line_number UNIQUE (invoice_id, line_number)
);

CREATE INDEX idx_ap_lines_invoice ON ap_invoice_lines(invoice_id);
CREATE INDEX idx_ap_lines_account ON ap_invoice_lines(gl_account_id);
CREATE INDEX idx_ap_lines_item ON ap_invoice_lines(item_id) WHERE item_id IS NOT NULL;
CREATE INDEX idx_ap_lines_asset ON ap_invoice_lines(asset_id) WHERE asset_id IS NOT NULL;
```

---

### 2.7 ap_payments
**Purpose**: Vendor payments

```sql
CREATE TABLE ap_payments (
    payment_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    payment_number          VARCHAR(100) NOT NULL,
    vendor_id               UUID NOT NULL REFERENCES vendors(vendor_id),
    company_id              UUID NOT NULL REFERENCES companies(company_id),
    payment_date            DATE NOT NULL,
    payment_method          VARCHAR(30) NOT NULL, -- CHECK, WIRE, ACH, RTGS, NEFT, SWIFT
    bank_account_id         UUID NOT NULL, -- Company bank account
    vendor_bank_account_id  UUID, -- Vendor bank account
    currency_code           VARCHAR(3) NOT NULL,
    exchange_rate           DECIMAL(12,6) DEFAULT 1.0,
    payment_amount          DECIMAL(20,2) NOT NULL,
    payment_amount_functional DECIMAL(20,2) NOT NULL,
    discount_taken          DECIMAL(20,2) DEFAULT 0,
    reference_number        VARCHAR(100), -- Check number, wire reference, etc.
    batch_id                UUID,
    status                  VARCHAR(20) DEFAULT 'DRAFT', -- DRAFT, PENDING_APPROVAL, APPROVED, PROCESSED, CLEARED, CANCELLED
    approval_workflow_id    UUID,
    gl_posted               BOOLEAN DEFAULT FALSE,
    gl_journal_id           UUID,
    reconciled              BOOLEAN DEFAULT FALSE,
    reconciliation_id       UUID,
    payment_file_generated  BOOLEAN DEFAULT FALSE,
    payment_file_path       TEXT,
    created_by              UUID NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_by             UUID,
    approved_at             TIMESTAMP,
    processed_by            UUID,
    processed_at            TIMESTAMP,
    cleared_date            DATE,
    updated_by              UUID,
    updated_at              TIMESTAMP
);

    updated_by              UUID,
    updated_at              TIMESTAMP,

    CONSTRAINT uq_ap_payment_number UNIQUE (tenant_id, payment_number)
);

CREATE INDEX idx_ap_payments_tenant ON ap_payments(tenant_id);
CREATE INDEX idx_ap_payments_vendor ON ap_payments(vendor_id);
CREATE INDEX idx_ap_payments_company ON ap_payments(company_id);
CREATE INDEX idx_ap_payments_date ON ap_payments(payment_date);
CREATE INDEX idx_ap_payments_status ON ap_payments(status);
CREATE INDEX idx_ap_payments_batch ON ap_payments(batch_id) WHERE batch_id IS NOT NULL;
```

---

### 2.8 ap_payment_applications
**Purpose**: Link payments to invoices

```sql
CREATE TABLE ap_payment_applications (
    application_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id              UUID NOT NULL REFERENCES ap_payments(payment_id) ON DELETE CASCADE,
    invoice_id              UUID NOT NULL REFERENCES ap_invoices(invoice_id),
    applied_amount          DECIMAL(20,2) NOT NULL CHECK (applied_amount > 0),
    discount_taken          DECIMAL(20,2) DEFAULT 0,
    applied_date            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_payment_invoice UNIQUE (payment_id, invoice_id)
);

CREATE INDEX idx_ap_appl_payment ON ap_payment_applications(payment_id);
CREATE INDEX idx_ap_appl_invoice ON ap_payment_applications(invoice_id);
```

---

## 3. ACCOUNTS RECEIVABLE TABLES

### 3.1 customers
**Purpose**: Customer master data

```sql
CREATE TABLE customers (
    customer_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    customer_code           VARCHAR(50) NOT NULL,
    customer_name           VARCHAR(200) NOT NULL,
    legal_name              VARCHAR(200),
    customer_type           VARCHAR(50) NOT NULL, -- CORPORATE, INDIVIDUAL, DISTRIBUTOR, FRANCHISE
    parent_customer_id      UUID REFERENCES customers(customer_id),
    customer_group_id       UUID,
    tax_id                  VARCHAR(50),
    tax_registration_numbers JSONB,
    currency_code           VARCHAR(3) NOT NULL,
    payment_terms_id        UUID,
    credit_limit            DECIMAL(20,2),
    credit_days             INTEGER,
    credit_rating           VARCHAR(10), -- AAA, AA, A, B, C, D
    credit_score            INTEGER, -- AI-calculated: 0-100
    discount_percentage     DECIMAL(5,2),
    is_tax_exempt           BOOLEAN DEFAULT FALSE,
    tax_exemption_certificate VARCHAR(100),
    status                  VARCHAR(20) DEFAULT 'ACTIVE',
    credit_hold             BOOLEAN DEFAULT FALSE,
    credit_hold_reason      TEXT,
    industry                VARCHAR(100),
    market_segment          VARCHAR(100),
    last_invoice_date       DATE,
    last_payment_date       DATE,
    total_sales_ytd         DECIMAL(20,2) DEFAULT 0,
    total_sales_ltd         DECIMAL(20,2) DEFAULT 0,
    average_days_to_pay     INTEGER, -- DSO for this customer
    ar_control_account_id   UUID REFERENCES chart_of_accounts(account_id),
    revenue_account_default_id UUID REFERENCES chart_of_accounts(account_id),
    created_by              UUID NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by              UUID,
    updated_at              TIMESTAMP
);

    updated_by              UUID,
    updated_at              TIMESTAMP,

    CONSTRAINT uq_customer_code UNIQUE (tenant_id, customer_code)
);

CREATE INDEX idx_customers_tenant ON customers(tenant_id);
CREATE INDEX idx_customers_status ON customers(status);
CREATE INDEX idx_customers_group ON customers(customer_group_id);
CREATE INDEX idx_customers_name ON customers USING GIN (customer_name gin_trgm_ops);
CREATE INDEX idx_customers_credit_hold ON customers(credit_hold) WHERE credit_hold = TRUE;
```

---

### 3.2 ar_invoices
**Purpose**: Sales invoices

```sql
CREATE TABLE ar_invoices (
    invoice_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    invoice_number          VARCHAR(100) NOT NULL,
    customer_id             UUID NOT NULL REFERENCES customers(customer_id),
    company_id              UUID NOT NULL REFERENCES companies(company_id),
    invoice_date            DATE NOT NULL,
    due_date                DATE NOT NULL,
    payment_terms_id        UUID,
    currency_code           VARCHAR(3) NOT NULL,
    exchange_rate           DECIMAL(12,6) DEFAULT 1.0,
    tax_treatment           VARCHAR(30),
    sales_order_id          UUID,
    delivery_note_id        UUID,
    project_id              UUID,
    salesperson_id          UUID,
    customer_po_number      VARCHAR(100),
    description             TEXT,
    subtotal                DECIMAL(20,2) NOT NULL,
    tax_amount              DECIMAL(20,2) DEFAULT 0,
    discount_amount         DECIMAL(20,2) DEFAULT 0,
    freight_amount          DECIMAL(20,2) DEFAULT 0,
    total_amount            DECIMAL(20,2) NOT NULL,
    amount_received         DECIMAL(20,2) DEFAULT 0,
    amount_due              DECIMAL(20,2) GENERATED ALWAYS AS (total_amount - amount_received) STORED,
    payment_status          VARCHAR(20) DEFAULT 'UNPAID',
    status                  VARCHAR(20) DEFAULT 'DRAFT',
    is_recurring            BOOLEAN DEFAULT FALSE,
    recurrence_rule         JSONB,
    revenue_recognition_rule VARCHAR(50), -- IMMEDIATE, DEFERRED, PERCENTAGE_COMPLETION, MILESTONE
    revenue_recognition_schedule_id UUID,
    contract_liability_amount DECIMAL(20,2) DEFAULT 0, -- Deferred revenue
    gl_posted               BOOLEAN DEFAULT FALSE,
    gl_journal_id           UUID,
    e_invoice_generated     BOOLEAN DEFAULT FALSE,
    e_invoice_irn           VARCHAR(100), -- India: Invoice Reference Number
    e_invoice_ack_number    VARCHAR(100),
    e_invoice_ack_date      TIMESTAMP,
    e_invoice_qr_code       TEXT,
    zatca_uuid              VARCHAR(100), -- Saudi: ZATCA UUID
    zatca_status            VARCHAR(30),
    created_by              UUID NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_by             UUID,
    approved_at             TIMESTAMP,
    posted_by               UUID,
    posted_at               TIMESTAMP,
    updated_by              UUID,
    updated_by              UUID,
    updated_at              TIMESTAMP,

    CONSTRAINT uq_ar_invoice_number UNIQUE (tenant_id, invoice_number)
);

CREATE INDEX idx_ar_invoices_tenant ON ar_invoices(tenant_id);
CREATE INDEX idx_ar_invoices_customer ON ar_invoices(customer_id);
CREATE INDEX idx_ar_invoices_company ON ar_invoices(company_id);
CREATE INDEX idx_ar_invoices_date ON ar_invoices(invoice_date);
CREATE INDEX idx_ar_invoices_due ON ar_invoices(due_date);
CREATE INDEX idx_ar_invoices_status ON ar_invoices(status);
CREATE INDEX idx_ar_invoices_payment ON ar_invoices(payment_status);
```

---

### 3.3 ar_invoice_lines
**Purpose**: Sales invoice line items

```sql
CREATE TABLE ar_invoice_lines (
    line_id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id              UUID NOT NULL REFERENCES ar_invoices(invoice_id) ON DELETE CASCADE,
    line_number             INTEGER NOT NULL,
    item_id                 UUID,
    description             TEXT NOT NULL,
    quantity                DECIMAL(12,3),
    unit_price              DECIMAL(20,4),
    line_amount             DECIMAL(20,2) NOT NULL,
    tax_code                VARCHAR(20),
    tax_amount              DECIMAL(20,2) DEFAULT 0,
    discount_percentage     DECIMAL(5,2),
    discount_amount         DECIMAL(20,2) DEFAULT 0,
    net_amount              DECIMAL(20,2) NOT NULL,
    revenue_account_id      UUID NOT NULL REFERENCES chart_of_accounts(account_id),
    revenue_recognition_rule VARCHAR(50),
    performance_obligation_id UUID,
    revenue_recognized      DECIMAL(20,2) DEFAULT 0,
    revenue_deferred        DECIMAL(20,2) DEFAULT 0,
    project_id              UUID,
    department_id           UUID,
    dimension_values        JSONB,
    so_line_id              UUID,
    dn_line_id              UUID,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_line_number UNIQUE (invoice_id, line_number)
);

CREATE INDEX idx_ar_lines_invoice ON ar_invoice_lines(invoice_id);
CREATE INDEX idx_ar_lines_account ON ar_invoice_lines(revenue_account_id);
CREATE INDEX idx_ar_lines_item ON ar_invoice_lines(item_id) WHERE item_id IS NOT NULL;
```

---

### 3.4 ar_receipts
**Purpose**: Customer receipts/payments

```sql
CREATE TABLE ar_receipts (
    receipt_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    receipt_number          VARCHAR(100) NOT NULL,
    customer_id             UUID NOT NULL REFERENCES customers(customer_id),
    company_id              UUID NOT NULL REFERENCES companies(company_id),
    receipt_date            DATE NOT NULL,
    payment_method          VARCHAR(30) NOT NULL, -- CASH, CHECK, WIRE, CARD, UPI, GATEWAY
    bank_account_id         UUID NOT NULL,
    currency_code           VARCHAR(3) NOT NULL,
    exchange_rate           DECIMAL(12,6) DEFAULT 1.0,
    receipt_amount          DECIMAL(20,2) NOT NULL,
    receipt_amount_functional DECIMAL(20,2) NOT NULL,
    amount_applied          DECIMAL(20,2) DEFAULT 0,
    amount_unapplied        DECIMAL(20,2) GENERATED ALWAYS AS (receipt_amount - amount_applied) STORED,
    reference_number        VARCHAR(100),
    payment_gateway         VARCHAR(50),
    gateway_transaction_id  VARCHAR(200),
    status                  VARCHAR(20) DEFAULT 'UNPOSTED', -- UNPOSTED, POSTED, REVERSED
    gl_posted               BOOLEAN DEFAULT FALSE,
    gl_journal_id           UUID,
    reconciled              BOOLEAN DEFAULT FALSE,
    reconciliation_id       UUID,
    notes                   TEXT,
    created_by              UUID NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    posted_by               UUID,
    posted_at               TIMESTAMP,
    updated_by              UUID,
    updated_by              UUID,
    updated_at              TIMESTAMP,

    CONSTRAINT uq_ar_receipt_number UNIQUE (tenant_id, receipt_number)
);

CREATE INDEX idx_ar_receipts_tenant ON ar_receipts(tenant_id);
CREATE INDEX idx_ar_receipts_customer ON ar_receipts(customer_id);
CREATE INDEX idx_ar_receipts_company ON ar_receipts(company_id);
CREATE INDEX idx_ar_receipts_date ON ar_receipts(receipt_date);
CREATE INDEX idx_ar_receipts_status ON ar_receipts(status);
CREATE INDEX idx_ar_receipts_gateway ON ar_receipts(payment_gateway, gateway_transaction_id);
```

---

### 3.5 ar_receipt_applications
**Purpose**: Link receipts to invoices

```sql
CREATE TABLE ar_receipt_applications (
    application_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    receipt_id              UUID NOT NULL REFERENCES ar_receipts(receipt_id) ON DELETE CASCADE,
    invoice_id              UUID NOT NULL REFERENCES ar_invoices(invoice_id),
    applied_amount          DECIMAL(20,2) NOT NULL CHECK (applied_amount > 0),
    discount_taken          DECIMAL(20,2) DEFAULT 0,
    applied_date            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ai_auto_applied         BOOLEAN DEFAULT FALSE,
    ai_confidence_score     DECIMAL(5,4),

    CONSTRAINT uq_receipt_invoice UNIQUE (receipt_id, invoice_id)
);

CREATE INDEX idx_ar_appl_receipt ON ar_receipt_applications(receipt_id);
CREATE INDEX idx_ar_appl_invoice ON ar_receipt_applications(invoice_id);
```

---

## 4. CASH MANAGEMENT (INTEGRATION)

> **Note**: Core Banking, Bank Accounts, and Reconciliation features are handled by the **[Treasury Management]** module.
> The Accounting module integrates with Treasury to post GL entries for bank transactions.

### Integration Points:
-   **Bank Accounts**: Managed in `treasury_management.bank_accounts`.
-   **Reconciliation**: managed in `treasury_management.bank_reconciliations`.
-   **GL Posting**: Treasury module triggers Journal Entry creation via Accounting Service.

---

---

## 5. FIXED ASSETS TABLES

### 5.1 fixed_assets
**Purpose**: Asset master

```sql
CREATE TABLE fixed_assets (
    asset_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_code              VARCHAR(50) NOT NULL,
    tenant_id               UUID NOT NULL,
    asset_tag               VARCHAR(50), -- Physical tag number
    asset_name              VARCHAR(200) NOT NULL,
    description             TEXT,
    asset_category_id       UUID NOT NULL,
    asset_class             VARCHAR(50), -- BUILDING, MACHINERY, VEHICLE, COMPUTER, FURNITURE
    company_id              UUID NOT NULL REFERENCES companies(company_id),
    location_id             UUID,
    department_id           UUID,
    custodian_id            UUID, -- Employee ID
    manufacturer            VARCHAR(200),
    model_number            VARCHAR(100),
    serial_number           VARCHAR(100),
    acquisition_date        DATE NOT NULL,
    acquisition_type        VARCHAR(30) NOT NULL, -- PURCHASE, LEASE, DONATION, CONSTRUCTION
    acquisition_cost        DECIMAL(20,2) NOT NULL,
    accumulated_depreciation DECIMAL(20,2) DEFAULT 0,
    net_book_value          DECIMAL(20,2) GENERATED ALWAYS AS (acquisition_cost - accumulated_depreciation) STORED,
    salvage_value           DECIMAL(20,2) DEFAULT 0,
    useful_life_months      INTEGER NOT NULL,
    depreciation_method     VARCHAR(30) NOT NULL, -- SLM, WDV, UNITS_OF_PRODUCTION, SUM_OF_YEARS
    depreciation_rate       DECIMAL(7,4),
    placed_in_service_date  DATE,
    retirement_date         DATE,
    disposal_date           DATE,
    disposal_method         VARCHAR(30), -- SALE, SCRAP, DONATION, WRITE_OFF
    disposal_proceeds       DECIMAL(20,2),
    disposal_gain_loss      DECIMAL(20,2),
    status                  VARCHAR(20) DEFAULT 'ACTIVE', -- ACTIVE, UNDER_CONSTRUCTION, DISPOSED, RETIRED
    is_fully_depreciated    BOOLEAN DEFAULT FALSE,
    is_impaired             BOOLEAN DEFAULT FALSE,
    impairment_amount       DECIMAL(20,2),
    impairment_date         DATE,
    last_revaluation_date   DATE,
    revaluation_amount      DECIMAL(20,2),
    insurance_value         DECIMAL(20,2),
    insurance_policy_number VARCHAR(100),
    insurance_expiry_date   DATE,
    warranty_expiry_date    DATE,
    barcode                 VARCHAR(100),
    qr_code                 TEXT,
    image_url               TEXT,
    asset_account_id        UUID REFERENCES chart_of_accounts(account_id),
    depreciation_account_id UUID REFERENCES chart_of_accounts(account_id),
    accumulated_depr_account_id UUID REFERENCES chart_of_accounts(account_id),
    created_by              UUID NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by              UUID,
    updated_at              TIMESTAMP,

    CONSTRAINT uq_asset_code UNIQUE (tenant_id, asset_code)
);

CREATE INDEX idx_assets_tenant ON fixed_assets(tenant_id);
CREATE INDEX idx_assets_company ON fixed_assets(company_id);
CREATE INDEX idx_assets_category ON fixed_assets(asset_category_id);
CREATE INDEX idx_assets_location ON fixed_assets(location_id);
CREATE INDEX idx_assets_status ON fixed_assets(status);
CREATE INDEX idx_assets_custodian ON fixed_assets(custodian_id);
```

---

### 5.2 asset_depreciation_schedules
**Purpose**: Depreciation schedule per asset per period

```sql
CREATE TABLE asset_depreciation_schedules (
    schedule_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    asset_id                UUID NOT NULL REFERENCES fixed_assets(asset_id) ON DELETE CASCADE,
    period_id               UUID NOT NULL REFERENCES accounting_periods(period_id),
    ledger_id               UUID NOT NULL REFERENCES gl_ledgers(ledger_id),
    depreciation_method     VARCHAR(30) NOT NULL,
    opening_nbv             DECIMAL(20,2) NOT NULL,
    depreciation_amount     DECIMAL(20,2) NOT NULL,
    accumulated_depreciation DECIMAL(20,2) NOT NULL,
    closing_nbv             DECIMAL(20,2) NOT NULL,
    posted                  BOOLEAN DEFAULT FALSE,
    journal_id              UUID,
    posted_at               TIMESTAMP,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_asset_period UNIQUE (asset_id, period_id, ledger_id)
);

CREATE INDEX idx_depr_asset ON asset_depreciation_schedules(asset_id);
CREATE INDEX idx_depr_period ON asset_depreciation_schedules(period_id);
CREATE INDEX idx_depr_posted ON asset_depreciation_schedules(posted) WHERE posted = FALSE;
```

---

## 6. TAX MANAGEMENT TABLES

### 6.1 tax_codes
**Purpose**: Tax code master

```sql
CREATE TABLE tax_codes (
    tax_code_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    tax_code                VARCHAR(20) NOT NULL,
    tax_name                VARCHAR(100) NOT NULL,
    tax_type                VARCHAR(30) NOT NULL, -- GST, VAT, SALES_TAX, WITHHOLDING, EXCISE
    jurisdiction            VARCHAR(50) NOT NULL, -- US, IN, AE, SA, QA, etc.
    tax_authority           VARCHAR(100),
    tax_rate                DECIMAL(7,4) NOT NULL,
    effective_from          DATE NOT NULL,
    effective_to            DATE,
    is_compound             BOOLEAN DEFAULT FALSE, -- For compound taxes (e.g., CGST+SGST)
    parent_tax_code_id      UUID REFERENCES tax_codes(tax_code_id),
    is_recoverable          BOOLEAN DEFAULT TRUE, -- Input tax credit available?
    is_reverse_charge       BOOLEAN DEFAULT FALSE,
    tax_account_id          UUID REFERENCES chart_of_accounts(account_id),
    status                  VARCHAR(20) DEFAULT 'ACTIVE',
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_tax_code UNIQUE (tenant_id, tax_code)
);

CREATE INDEX idx_tax_codes_tenant ON tax_codes(tenant_id);

CREATE INDEX idx_tax_codes_type ON tax_codes(tax_type);
CREATE INDEX idx_tax_codes_jurisdiction ON tax_codes(jurisdiction);
CREATE INDEX idx_tax_codes_effective ON tax_codes(effective_from, effective_to);
```

---

### 6.2 tax_transactions
**Purpose**: Tax transaction details

```sql
CREATE TABLE tax_transactions (
    tax_transaction_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id          UUID NOT NULL,
    transaction_type        VARCHAR(30) NOT NULL, -- PURCHASE, SALE, JOURNAL
    transaction_date        DATE NOT NULL,
    company_id              UUID NOT NULL REFERENCES companies(company_id),
    customer_id             UUID,
    vendor_id               UUID,
    tax_code                VARCHAR(20) NOT NULL,
    taxable_amount          DECIMAL(20,2) NOT NULL,
    tax_rate                DECIMAL(7,4) NOT NULL,
    tax_amount              DECIMAL(20,2) NOT NULL,
    recoverable_amount      DECIMAL(20,2) DEFAULT 0,
    non_recoverable_amount  DECIMAL(20,2) DEFAULT 0,
    is_reverse_charge       BOOLEAN DEFAULT FALSE,
    tax_period_id           UUID,
    jurisdiction            VARCHAR(50) NOT NULL,
    tax_return_filed        BOOLEAN DEFAULT FALSE,
    tax_return_id           UUID,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tax_trans_company ON tax_transactions(company_id);
CREATE INDEX idx_tax_trans_date ON tax_transactions(transaction_date);
CREATE INDEX idx_tax_trans_code ON tax_transactions(tax_code);
CREATE INDEX idx_tax_trans_type ON tax_transactions(transaction_type);
```

---

### 6.3 gst_returns (India-specific)
**Purpose**: GST return tracking

```sql
CREATE TABLE gst_returns (
    return_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    company_id              UUID NOT NULL REFERENCES companies(company_id),
    gstin                   VARCHAR(15) NOT NULL,
    return_type             VARCHAR(10) NOT NULL, -- GSTR1, GSTR3B, GSTR9
    return_period           VARCHAR(10) NOT NULL, -- MM-YYYY
    filing_date             DATE,
    status                  VARCHAR(30) DEFAULT 'DRAFT', -- DRAFT, FILED, ACCEPTED, REJECTED
    total_taxable_outward   DECIMAL(20,2) DEFAULT 0,
    total_taxable_inward    DECIMAL(20,2) DEFAULT 0,
    output_tax              DECIMAL(20,2) DEFAULT 0,
    input_tax_credit        DECIMAL(20,2) DEFAULT 0,
    tax_payable             DECIMAL(20,2) DEFAULT 0,
    acknowledgment_number   VARCHAR(50),
    acknowledgment_date     DATE,
    filed_by                UUID,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_gst_return UNIQUE (tenant_id, gstin, return_type, return_period)
);

CREATE INDEX idx_gst_returns_tenant ON gst_returns(tenant_id);
CREATE INDEX idx_gst_returns_company ON gst_returns(company_id);
CREATE INDEX idx_gst_returns_period ON gst_returns(return_period);
CREATE INDEX idx_gst_returns_status ON gst_returns(status);
```

---

### 6.4 e_invoices (India & Saudi)
**Purpose**: E-invoice tracking

```sql
CREATE TABLE e_invoices (
    e_invoice_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id              UUID NOT NULL,
    invoice_type            VARCHAR(10) NOT NULL, -- AR, AP
    country_code            VARCHAR(2) NOT NULL,
    e_invoice_number        VARCHAR(100),
    irn                     VARCHAR(100), -- India: Invoice Reference Number
    ack_number              VARCHAR(100),
    ack_date                TIMESTAMP,
    signed_invoice          TEXT,
    signed_qr_code          TEXT,
    zatca_uuid              VARCHAR(100), -- Saudi: ZATCA UUID
    zatca_status            VARCHAR(30),
    zatca_hash              TEXT,
    zatca_signature         TEXT,
    status                  VARCHAR(30) NOT NULL, -- PENDING, GENERATED, SUBMITTED, ACCEPTED, REJECTED, CANCELLED
    error_message           TEXT,
    submitted_at            TIMESTAMP,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_e_invoices_invoice ON e_invoices(invoice_id, invoice_type);
CREATE INDEX idx_e_invoices_irn ON e_invoices(irn) WHERE irn IS NOT NULL;
CREATE INDEX idx_e_invoices_zatca ON e_invoices(zatca_uuid) WHERE zatca_uuid IS NOT NULL;
```

---

## 7. MULTI-GAAP & REVENUE (INTEGRATION)

### 7.1 Revenue Recognition (ASC 606)

> **Note**: Comprehensive Revenue Recognition handles (Contracts, POs, Allocations) are managed by the **[Revenue Management]** module.

### Integration Points:
-   **Contracts**: Managed in `revenue_management.revenue_contracts`.
-   **Schedules**: Managed in `revenue_management.revenue_recognition_schedules`.
-   **GL Posting**: Revenue module triggers periodic Journal Entries for recognized revenue.

---

---

### 7.2 lease_accounting (ASC 842 / IFRS 16)
**Purpose**: Lease ROU asset & liability tracking

```sql
CREATE TABLE lease_agreements (
    lease_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lease_number            VARCHAR(50) NOT NULL,
    tenant_id               UUID NOT NULL,
    company_id              UUID NOT NULL REFERENCES companies(company_id),
    lessor_name             VARCHAR(200) NOT NULL,
    lease_type              VARCHAR(30) NOT NULL, -- OPERATING, FINANCE (US GAAP) / RIGHT_OF_USE (IFRS)
    asset_description       TEXT NOT NULL,
    lease_start_date        DATE NOT NULL,
    lease_end_date          DATE NOT NULL,
    lease_term_months       INTEGER NOT NULL,
    payment_frequency       VARCHAR(20) NOT NULL, -- MONTHLY, QUARTERLY, ANNUALLY
    periodic_payment        DECIMAL(20,2) NOT NULL,
    discount_rate           DECIMAL(7,4) NOT NULL, -- Incremental borrowing rate
    initial_rou_asset       DECIMAL(20,2) NOT NULL,
    initial_lease_liability DECIMAL(20,2) NOT NULL,
    current_rou_asset       DECIMAL(20,2),
    current_lease_liability DECIMAL(20,2),
    accumulated_amortization DECIMAL(20,2) DEFAULT 0,
    rou_asset_account_id    UUID REFERENCES chart_of_accounts(account_id),
    lease_liability_account_id UUID REFERENCES chart_of_accounts(account_id),
    status                  VARCHAR(20) DEFAULT 'ACTIVE',
    created_by              UUID NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_lease_number UNIQUE (tenant_id, lease_number)
);

CREATE INDEX idx_leases_tenant ON lease_agreements(tenant_id);
CREATE INDEX idx_leases_company ON lease_agreements(company_id);
CREATE INDEX idx_leases_dates ON lease_agreements(lease_start_date, lease_end_date);
```

---

## 8. WORKFLOW & APPROVAL TABLES

### 8.1 workflow_definitions
**Purpose**: Workflow templates

```sql
CREATE TABLE workflow_definitions (
    workflow_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    workflow_name           VARCHAR(100) NOT NULL,
    workflow_type           VARCHAR(50) NOT NULL, -- INVOICE_APPROVAL, PAYMENT_APPROVAL, JOURNAL_APPROVAL
    company_id              UUID REFERENCES companies(company_id),
    is_global               BOOLEAN DEFAULT FALSE,
    workflow_steps          JSONB NOT NULL, -- Array of steps with conditions
    status                  VARCHAR(20) DEFAULT 'ACTIVE',
    created_by              UUID NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_workflows_tenant ON workflow_definitions(tenant_id);
CREATE INDEX idx_workflows_type ON workflow_definitions(workflow_type);
```

---

### 8.2 workflow_instances
**Purpose**: Active workflow instances

```sql
CREATE TABLE workflow_instances (
    instance_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id             UUID NOT NULL REFERENCES workflow_definitions(workflow_id),
    tenant_id               UUID NOT NULL,
    entity_type             VARCHAR(50) NOT NULL, -- INVOICE, PAYMENT, JOURNAL
    entity_id               UUID NOT NULL,
    current_step            INTEGER NOT NULL DEFAULT 1,
    total_steps             INTEGER NOT NULL,
    status                  VARCHAR(30) DEFAULT 'PENDING', -- PENDING, IN_PROGRESS, APPROVED, REJECTED, CANCELLED
    initiated_by            UUID NOT NULL,
    initiated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at            TIMESTAMP,
    completion_status       VARCHAR(30)
);

CREATE INDEX idx_wf_inst_tenant ON workflow_instances(tenant_id);
CREATE INDEX idx_wf_inst_workflow ON workflow_instances(workflow_id);
CREATE INDEX idx_wf_inst_entity ON workflow_instances(entity_type, entity_id);
CREATE INDEX idx_wf_inst_status ON workflow_instances(status);
```

---

### 8.3 workflow_approvals
**Purpose**: Individual approval actions

```sql
CREATE TABLE workflow_approvals (
    approval_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id             UUID NOT NULL REFERENCES workflow_instances(instance_id) ON DELETE CASCADE,
    step_number             INTEGER NOT NULL,
    approver_id             UUID NOT NULL,
    action                  VARCHAR(20), -- APPROVED, REJECTED, DELEGATED
    comments                TEXT,
    action_date             TIMESTAMP,
    response_time_hours     DECIMAL(10,2),

    CONSTRAINT uq_approval UNIQUE (instance_id, step_number, approver_id)
);

CREATE INDEX idx_approvals_instance ON workflow_approvals(instance_id);
CREATE INDEX idx_approvals_approver ON workflow_approvals(approver_id);
```

---

## 9. AUDIT & SECURITY TABLES

### 9.1 audit_log
**Purpose**: Comprehensive audit trail

```sql
CREATE TABLE audit_log (
    audit_id                BIGSERIAL PRIMARY KEY,
    tenant_id               UUID NOT NULL, -- Partition key for multi-tenancy
    company_id              UUID NOT NULL,
    user_id                 UUID NOT NULL,
    session_id              UUID,
    action_type             VARCHAR(30) NOT NULL, -- CREATE, UPDATE, DELETE, APPROVE, POST, REVERSE
    entity_type             VARCHAR(50) NOT NULL,
    entity_id               UUID NOT NULL,
    entity_name             VARCHAR(200),
    field_name              VARCHAR(100),
    old_value               TEXT,
    new_value               TEXT,
    ip_address              INET,
    user_agent              TEXT,
    request_id              UUID,
    action_timestamp        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata                JSONB
);

-- TimescaleDB hypertable
SELECT create_hypertable('audit_log', 'action_timestamp', chunk_time_interval => INTERVAL '1 month');

CREATE INDEX idx_audit_tenant ON audit_log(tenant_id, action_timestamp DESC);
CREATE INDEX idx_audit_company ON audit_log(company_id, action_timestamp DESC);
CREATE INDEX idx_audit_user ON audit_log(user_id, action_timestamp DESC);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_action ON audit_log(action_type, action_timestamp DESC);
```

---

### 9.2 user_access_log
**Purpose**: Track user logins and access

```sql
CREATE TABLE user_access_log (
    log_id                  BIGSERIAL PRIMARY KEY,
    user_id                 UUID NOT NULL,
    session_id              UUID NOT NULL,
    event_type              VARCHAR(30) NOT NULL, -- LOGIN, LOGOUT, SESSION_TIMEOUT, PASSWORD_CHANGE
    ip_address              INET,
    user_agent              TEXT,
    device_info             JSONB,
    location                GEOGRAPHY(POINT),
    login_timestamp         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    logout_timestamp        TIMESTAMP,
    session_duration_minutes INTEGER
);

SELECT create_hypertable('user_access_log', 'login_timestamp', chunk_time_interval => INTERVAL '1 month');

CREATE INDEX idx_access_user ON user_access_log(user_id, login_timestamp DESC);
CREATE INDEX idx_access_session ON user_access_log(session_id);
```

---

## 10. MASTER DATA TABLES

### 10.1 departments
```sql
CREATE TABLE departments (
    department_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    company_id              UUID NOT NULL REFERENCES companies(company_id),
    department_code         VARCHAR(50) NOT NULL,
    department_name         VARCHAR(200) NOT NULL,
    parent_department_id    UUID REFERENCES departments(department_id),
    manager_id              UUID,
    cost_center_flag        BOOLEAN DEFAULT FALSE,
    profit_center_flag      BOOLEAN DEFAULT FALSE,
    status                  VARCHAR(20) DEFAULT 'ACTIVE',
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_dept_code UNIQUE (tenant_id, company_id, department_code)
);

CREATE INDEX idx_departments_tenant ON departments(tenant_id);
```

---

### 10.2 cost_centers
```sql
CREATE TABLE cost_centers (
    cost_center_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    company_id              UUID NOT NULL REFERENCES companies(company_id),
    cost_center_code        VARCHAR(50) NOT NULL,
    cost_center_name        VARCHAR(200) NOT NULL,
    department_id           UUID REFERENCES departments(department_id),
    manager_id              UUID,
    budget_enabled          BOOLEAN DEFAULT TRUE,
    status                  VARCHAR(20) DEFAULT 'ACTIVE',
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_cc_code UNIQUE (tenant_id, company_id, cost_center_code)
);

CREATE INDEX idx_cost_centers_tenant ON cost_centers(tenant_id);
```

---

### 10.3 projects
```sql
CREATE TABLE projects (
    project_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_code            VARCHAR(50) NOT NULL,
    tenant_id               UUID NOT NULL,
    project_name            VARCHAR(200) NOT NULL,
    company_id              UUID NOT NULL REFERENCES companies(company_id),
    customer_id             UUID REFERENCES customers(customer_id),
    project_type            VARCHAR(50), -- TIME_MATERIAL, FIXED_PRICE, COST_PLUS
    project_manager_id      UUID,
    start_date              DATE,
    end_date                DATE,
    budget_amount           DECIMAL(20,2),
    actual_cost             DECIMAL(20,2) DEFAULT 0,
    billed_amount           DECIMAL(20,2) DEFAULT 0,
    status                  VARCHAR(30) DEFAULT 'PLANNING', -- PLANNING, ACTIVE, ON_HOLD, COMPLETED, CANCELLED
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_project_code UNIQUE (tenant_id, project_code)
);

CREATE INDEX idx_projects_tenant ON projects(tenant_id);
CREATE INDEX idx_projects_company ON projects(company_id);
CREATE INDEX idx_projects_customer ON projects(customer_id);
CREATE INDEX idx_projects_status ON projects(status);
```

---

## 11. INDEXES & PERFORMANCE

### Key Indexing Strategy:
1. **Primary Keys**: UUID with `gen_random_uuid()` for distributed systems
2. **Foreign Keys**: Always indexed
3. **Commonly Filtered Columns**: company_id, status, dates
4. **Text Search**: GIN indexes with trigram extension for fuzzy search
5. **JSONB**: GIN indexes for dimension_values, metadata
6. **Audit/Transaction Logs**: TimescaleDB hypertables for time-series optimization

### Performance Optimizations:
```sql
-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- For fuzzy text search
CREATE EXTENSION IF NOT EXISTS "postgis"; -- For location data

-- Materialized views for reporting
CREATE MATERIALIZED VIEW mv_ar_aging AS
SELECT
    company_id,
    customer_id,
    SUM(CASE WHEN CURRENT_DATE - due_date <= 0 THEN amount_due ELSE 0 END) AS current,
    SUM(CASE WHEN CURRENT_DATE - due_date BETWEEN 1 AND 30 THEN amount_due ELSE 0 END) AS days_1_30,
    SUM(CASE WHEN CURRENT_DATE - due_date BETWEEN 31 AND 60 THEN amount_due ELSE 0 END) AS days_31_60,
    SUM(CASE WHEN CURRENT_DATE - due_date BETWEEN 61 AND 90 THEN amount_due ELSE 0 END) AS days_61_90,
    SUM(CASE WHEN CURRENT_DATE - due_date > 90 THEN amount_due ELSE 0 END) AS days_over_90,
    SUM(amount_due) AS total_due
FROM ar_invoices
WHERE payment_status != 'PAID'
GROUP BY company_id, customer_id;

CREATE UNIQUE INDEX ON mv_ar_aging(company_id, customer_id);

-- Refresh strategy (can be automated via cron/scheduler)
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_ar_aging;
```

---

## 12. PARTITIONING STRATEGY

### Time-based Partitioning for Large Tables:

```sql
-- Partition journal_entries by journal_date (monthly)
CREATE TABLE journal_entries (
    -- ... columns ...
) PARTITION BY RANGE (journal_date);

CREATE TABLE journal_entries_2024_01 PARTITION OF journal_entries
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

CREATE TABLE journal_entries_2024_02 PARTITION OF journal_entries
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');
-- ... continue for all months

-- Auto-partition creation can be handled by application or pg_partman extension
```

### Company-based Partitioning (Multi-tenant):
```sql
-- For large multi-tenant deployments
CREATE TABLE ar_invoices (
    -- ... columns ...
) PARTITION BY HASH (company_id);

CREATE TABLE ar_invoices_p0 PARTITION OF ar_invoices FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE ar_invoices_p1 PARTITION OF ar_invoices FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE ar_invoices_p2 PARTITION OF ar_invoices FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE ar_invoices_p3 PARTITION OF ar_invoices FOR VALUES WITH (MODULUS 4, REMAINDER 3);
```

---

## SUMMARY

**Total Tables**: 50+ core tables
**Total Indexes**: 200+ indexes for performance
**Database Size Estimate** (for mid-size company, 5 years):
- Transactional tables: ~500GB - 1TB
- Audit logs: ~200GB - 500GB (with TimescaleDB compression)
- Total: ~1-2TB

**Scalability**:
- Horizontal scaling via table partitioning
- Read replicas for reporting
- TimescaleDB for time-series data (audit logs, transaction logs)
- Connection pooling (PgBouncer)
- Caching layer (Redis) for frequently accessed data

This schema supports **world-class ERP accounting** with full audit trail, multi-GAAP, multi-currency, multi-entity capabilities.

Would you like me to continue with:
1. Microservices architecture design?
2. API Gateway & authentication framework?
3. CI/CD pipeline design?
4. UI wireframes for key pages?

Let me know!
