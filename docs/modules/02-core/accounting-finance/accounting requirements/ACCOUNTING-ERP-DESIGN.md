# Enterprise Accounting ERP - Complete Design Documentation

> **Architecture**: SARAISE Modular Monolith with Row-Level Multitenancy
> **Framework**: Python Django 4.2 + Django REST Framework + Pydantic
> **Database**: PostgreSQL 15+ with Django ORM and Migrations
> **Approach**: Clean module boundaries, session-based auth, Policy Engine authorization
> **Scale**: SMB to Enterprise, Multi-tenant SaaS

---

## 📋 TABLE OF CONTENTS

### PART 1: OVERVIEW & ARCHITECTURE
1. [System Overview](#1-system-overview)
2. [Technology Stack](#2-technology-stack)
3. [resource Framework](#3-resource-framework)
4. [Module Organization](#4-module-organization)

### PART 2: FRONTEND DESIGN
5. [Sidebar Navigation Structure](#5-sidebar-navigation-structure)
6. [Page Designs & UI Specifications](#6-page-designs--ui-specifications)

### PART 3: BACKEND DESIGN
7. [Database Schema](#7-database-schema)
8. [API Endpoints](#8-api-endpoints)
9. [Business Logic & Services](#9-business-logic--services)

### PART 4: FEATURES & COMPLIANCE
10. [Multi-GAAP Framework](#10-multi-gaap-framework)
11. [Country-Specific Compliance](#11-country-specific-compliance)
12. [AI/ML Features](#12-aiml-features)

### PART 5: DEPENDENT MODULES
13. [Integrated Modules](#13-integrated-modules)

### PART 6: IMPLEMENTATION
14. [Complete resource Examples](#14-complete-resource-examples)
15. [Event-Driven Architecture](#15-event-driven-architecture)
16. [Security & Permissions](#16-security--permissions)
17. [Deployment Guide](#17-deployment-guide)

---

## 1. SYSTEM OVERVIEW

### 1.1 Product Vision

**Best-in-class, AI-powered accounting ERP** competing with:
- SAP S/4HANA Finance
- Oracle Fusion Financials
- Microsoft Dynamics 365 Finance
- NetSuite Financials

### 1.2 Key Differentiators

✅ **Universal Industry Support**: Manufacturing, Services, Retail, Construction, Non-profit
✅ **Multi-GAAP**: US GAAP, IFRS, India (Ind AS), GCC (UAE, Qatar, Saudi Arabia)
✅ **Multi-tier**: SMB to Enterprise with single codebase
✅ **AI-Powered**: OCR, auto-matching, forecasting, anomaly detection
✅ **Multi-tenant SaaS**: Ready for cloud deployment
✅ **Rapid Development**: resource framework = 70% faster than traditional coding

### 1.3 Architecture Principles

**resource + Modular Monolith**
- ✅ Single codebase, single deployment
- ✅ Module boundaries enforced via event bus
- ✅ Shared database with logical separation (schemas per module)
- ✅ Strong transactional consistency (ACID)
- ✅ Event-driven internal communication
- ✅ Future-ready for microservices extraction (if needed)

---

## 2. TECHNOLOGY STACK

### 2.1 Backend Stack

```yaml
Framework: Django 4.2 (Python 3.11+)
  - Batteries-included framework
  - ORM with migrations built-in
  - Admin interface for rapid development
  - Middleware-based auth and session management

REST API: Django REST Framework (DRF)
  - Serializers for request/response validation
  - ViewSets for CRUD operations
  - Automatic OpenAPI schema generation
  - Token and session authentication

Database:
  Primary: PostgreSQL 15+
  Extensions:
    - TimescaleDB (time-series for audit logs)
    - pg_trgm (fuzzy text search)
    - PostGIS (location data)
  Cache: Redis 7+

Migrations: Django Migrations
  - Version-controlled schema changes via manage.py
  - Per-module migration directories
  - Automatic dependency resolution

Task Queue: Celery + Redis
  - Background jobs
  - Scheduled tasks
  - Async processing
```

### 2.2 Frontend Stack

```yaml
Framework: React 18 with TypeScript
  - Component-based
  - Strong typing
  - Modern hooks

UI Library: Shadcn/ui + Radix UI
  - Headless component library
  - Form validation
  - Table/Grid with sorting/filtering
  - Date pickers, dialogs, notifications

State Management: Zustand
  - Lightweight
  - TypeScript-friendly
  - No boilerplate

Forms: React Hook Form + Zod
  - Performance-optimized
  - Schema validation
  - Error handling

Data Fetching: TanStack Query (@tanstack/react-query)
  - Server state management
  - Caching
  - Optimistic updates
  - Auto-refetch with stale-while-revalidate

Charts: Apache ECharts
  - Rich visualizations
  - Interactive dashboards
  - Financial charts

HTTP Client: apiClient (custom, uses fetch with credentials: 'include')
  - Session cookie handling
  - Automatic 401/403 error handling
  - Centralized error handling
```

### 2.3 DevOps & Infrastructure

```yaml
Containerization: Docker
Deployment:
  - Docker Compose (development)
  - AWS ECS / GCP Cloud Run (production)

CI/CD: GitHub Actions
  - Automated testing
  - Build & deploy

Monitoring:
  - Application: Prometheus + Grafana
  - Logs: ELK Stack or Loki
  - Errors: Sentry
  - APM: New Relic or Datadog

Storage:
  - Documents: AWS S3 / MinIO
  - Database Backups: Automated daily

Security:
  - Secrets: AWS Secrets Manager / HashiCorp Vault
  - SSL: Let's Encrypt (auto-renewal)
```

---

## 3. MODULE FRAMEWORK

### 3.1 SARAISE Module Structure

A **SARAISE module** is a self-contained business unit with:

```
Module Structure
├── manifest.yaml              # Module contract (name, version, permissions, dependencies)
├── models.py                  # Django ORM models (with tenant_id for multitenancy)
├── serializers.py             # DRF serializers for request/response validation
├── services.py                # Business logic (keep views thin)
├── views.py                   # DRF ViewSets for API endpoints
├── permissions.py             # Custom permission classes
├── policies.py                # Policy Engine rules for ABAC
├── urls.py                    # URL routing for module endpoints
├── migrations/                # Django migrations (per-module)
└── tests/                     # Test suite (≥90% coverage required)
```

**Key SARAISE Principles**:
1. **Row-Level Multitenancy**: ALL tenant-scoped models have `tenant_id` column
2. **Explicit Filtering**: Services manually filter by `tenant_id` (never rely on schema context)
3. **Session-Based Auth**: HTTP-only cookies, no JWT for interactive users
4. **Policy Engine**: Authorization evaluated per-request, not cached in session
5. **Module Isolation**: Modules communicate via services or event bus, never direct DB access
6. **No Module Auth**: Authentication/login only in platform-level services, not in modules

---

## 4. MODULE ORGANIZATION

### 4.1 Project Structure (Django)

```
saraise/
├── backend/
│   ├── src/
│   │   ├── main.py                    # Django app initialization, route registration
│   │   ├── settings.py                # Django settings (DB, middleware, installed apps)
│   │   ├── core/                      # Platform-level services
│   │   │   ├── session_manager.py    # Session/cookie management
│   │   │   ├── policy_engine.py      # Authorization via Policy Engine
│   │   │   ├── auth_decorators.py    # @RequireTenantAdmin, etc.
│   │   │   ├── module_access_middleware.py  # Per-tenant module access control
│   │   │   └── permissions.py        # RBAC definitions
│   │   │
│   │   ├── modules/                  # Business modules (80+)
│   │   │   ├── crm/
│   │   │   │   ├── manifest.yaml
│   │   │   │   ├── models.py         # Django models (with tenant_id)
│   │   │   │   ├── serializers.py    # DRF serializers
│   │   │   │   ├── services.py       # Business logic
│   │   │   │   ├── views.py          # DRF ViewSets
│   │   │   │   ├── permissions.py    # Custom DRF permissions
│   │   │   │   ├── urls.py           # URL routing
│   │   │   │   ├── migrations/       # Django migrations
│   │   │   │   └── tests/            # Tests (≥90% coverage)
│   │   │   │
│   │   │   ├── accounting/
│   │   │   ├── hr/
│   │   │   └── ...80+ more modules
│   │   │
│   │   └── manage.py                 # Django management command
│   │
│   ├── tests/
│   │   └── conftest.py               # Pytest fixtures (db_session, tenant_fixture, user_fixture)
│   │
│   └── pyproject.toml                # Python dependencies, tool config
│
├── frontend/
│   ├── src/
│   │   ├── main.tsx                  # React entry point
│   │   ├── services/
│   │   │   ├── api-client.ts         # HTTP client with session cookie handling
│   │   │   └── {module}-service.ts   # One service per module
│   │   ├── modules/
│   │   │   └── {module}/pages/       # Module pages/components
│   │   └── stores/
│   │       └── auth.ts               # Zustand auth store
│   │
│   └── package.json                  # Node.js dependencies
│
└── docs/
    ├── architecture/                 # System design docs (33+ documents)
    └── modules/                      # Module documentation
```

### 4.2 Module Communication Rules

**✅ ALLOWED:**
- Module A → Event Bus → Module B (preferred)
- Module A → Service Layer of Module B (synchronous)

**❌ NOT ALLOWED:**
- Module A → Direct DB access to Module B's tables

**Example: AP Invoice creates GL Journal**

```python
# ❌ WRONG: AP directly accessing GL database
from app.modules.general_ledger.models import JournalEntry
journal = JournalEntry(...)  # BAD!

# ✅ RIGHT: AP calls GL Service
from app.modules.general_ledger.services import GLService
journal = GLService.create_journal(...)  # GOOD!

# ✅ BEST: AP emits event, GL listens
event_bus.emit('ap.invoice.submitted', invoice_data)
# GL Module has listener that auto-creates journal
```

---

## 5. SIDEBAR NAVIGATION STRUCTURE

```
📊 DASHBOARD
├── Executive Dashboard
├── Financial Dashboard
├── Cash Flow Dashboard
└── KPI Scorecards

💰 GENERAL LEDGER
├── Chart of Accounts
├── Journal Entries
│   ├── Manual Journal
│   ├── Recurring Journals
│   └── Reversing Journals
├── Period Management
├── Consolidation
└── GL Reports

📒 ACCOUNTS PAYABLE
├── Vendor Master
├── Purchase Invoices
│   ├── Invoice Entry
│   ├── OCR Invoice Capture
│   └── 3-Way Matching
├── Payments
│   ├── Payment Processing
│   ├── Payment Batches
│   └── Electronic Payments
└── AP Reports

📗 ACCOUNTS RECEIVABLE
├── Customer Master
├── Sales Invoices
│   ├── Invoice Generation
│   ├── E-invoicing
│   └── Recurring Invoices
├── Receipts & Collections
├── Revenue Recognition
└── AR Reports

💵 CASH MANAGEMENT
├── Bank Accounts
├── Bank Reconciliation
├── Cash Positioning
└── Cash Flow Forecasting

🏦 FIXED ASSETS
├── Asset Register
├── Depreciation
├── Asset Transfers
└── Asset Disposal

💳 EXPENSE MANAGEMENT
├── Expense Claims
├── Corporate Cards
└── Travel & Entertainment

🏗️ PROJECT ACCOUNTING
├── Project Setup
├── Project Costing
├── Project Billing
└── Project Profitability

💼 COST ACCOUNTING
├── Cost Centers
├── Cost Allocation
├── Standard Costing
└── Variance Analysis

📈 BUDGETING
├── Budget Creation
├── Budget Control
├── Forecasting
└── Budget Reports

📑 FINANCIAL REPORTING
├── Financial Statements
├── Management Reports
├── Statutory Reports
└── Custom Reports

⚖️ TAX MANAGEMENT
├── Tax Configuration
├── GST (India)
├── VAT (GCC)
├── E-invoicing
└── Tax Reports

🔄 RECONCILIATION
├── Bank Reconciliation
├── Intercompany Reconciliation
└── Account Reconciliation

⚙️ CONFIGURATION
├── Company Setup
├── Approval Workflows
├── Numbering Series
└── User Management
```

---

## 6. PAGE DESIGNS & UI SPECIFICATIONS

### 6.1 Purchase Invoice Entry Page

**Layout**: Master-Detail with Tabs

```
┌─────────────────────────────────────────────────────────────┐
│ Purchase Invoice                            [Save] [Submit] │
├─────────────────────────────────────────────────────────────┤
│ Invoice Details │ Tax Details │ Additional Info │ Attachments│
├─────────────────────────────────────────────────────────────┤
│                                                               │
│ Vendor: [Dropdown with search]        Invoice #: PINV-001   │
│ Invoice Date: [Date picker]            Due Date: [Auto calc]│
│ Currency: [USD ▼]      Exchange Rate: 1.0000                │
│ PO Reference: [Link to PO]             GRN: [Link to GRN]   │
│                                                               │
│ ┌───────────────────────────────────────────────────────────┐
│ │ Line Items                             [Add Line] [Import]│
│ ├────┬──────────┬────────┬────────┬────────┬────────┬──────┤
│ │ #  │ Account  │ Desc   │ Qty    │ Price  │ Tax    │ Total│
│ ├────┼──────────┼────────┼────────┼────────┼────────┼──────┤
│ │ 1  │ 60010    │ Office │ 10     │ 100    │ VAT 5% │ 1050 │
│ │ 2  │ 60020    │ Rent   │ 1      │ 5000   │ Exempt │ 5000 │
│ └────┴──────────┴────────┴────────┴────────┴────────┴──────┘
│                                                               │
│                                    Subtotal: 6,000.00        │
│                                    Tax:        50.00         │
│                                    Total:   6,050.00         │
└─────────────────────────────────────────────────────────────┘
```

**UI Components**:
- Vendor dropdown: Autocomplete with fuzzy search
- Date pickers: With keyboard shortcuts
- Line items grid: Editable, inline add/delete
- Tax calculation: Real-time on field change
- Validation: Inline error messages

**API Endpoint**:
```
POST /api/v1/ap/invoices
PUT  /api/v1/ap/invoices/{id}
GET  /api/v1/ap/invoices/{id}
```

---

### 6.2 Chart of Accounts Page

**Layout**: Tree View + Detail Panel

```
┌─────────────────────────────────────────────────────────────┐
│ Chart of Accounts                          [+ New] [Import] │
├──────────────────────┬──────────────────────────────────────┤
│ Account Hierarchy    │  Account Details                     │
├──────────────────────┤                                      │
│ ⊟ Assets             │  Account Code: 10000                 │
│   ⊟ Current Assets   │  Account Name: Assets                │
│     - Cash (10100)   │  Account Type: Asset                 │
│     - AR (10200)     │  Parent: (Root)                      │
│     - Inventory      │  Currency: USD                       │
│   ⊟ Non-current      │  Control Account: No                 │
│     - FA (12000)     │  Opening Balance: 0.00               │
│ ⊟ Liabilities        │                                      │
│   ⊟ Current          │  [Edit] [Delete] [View Transactions] │
│     - AP (20100)     │                                      │
│ ⊟ Equity             │                                      │
│ ⊟ Revenue            │                                      │
│ ⊟ Expenses           │                                      │
└──────────────────────┴──────────────────────────────────────┘
```

---

### 6.3 Dashboard - Executive View

```
┌─────────────────────────────────────────────────────────────┐
│ Executive Dashboard                      Period: Q4 2024 ▼  │
├─────────────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│ │ Revenue  │ │ Profit   │ │ Cash     │ │ AR       │        │
│ │ $10.5M   │ │ $2.1M    │ │ $5.2M    │ │ $3.5M    │        │
│ │ ↑ 15%    │ │ ↑ 8%     │ │ ↓ 5%     │ │ → 0%     │        │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘        │
│                                                               │
│ ┌─────────────────────────────┐ ┌─────────────────────────┐ │
│ │ Revenue Trend (12M)         │ │ P&L Summary             │ │
│ │ [Line Chart]                │ │ Revenue:      $10.5M    │ │
│ │                             │ │ COGS:          $6.2M    │ │
│ │                             │ │ Gross Margin:  $4.3M    │ │
│ │                             │ │ Expenses:      $2.2M    │ │
│ └─────────────────────────────┘ │ Net Profit:    $2.1M    │ │
│                                 └─────────────────────────┘ │
│ ┌─────────────────────────────┐ ┌─────────────────────────┐ │
│ │ Cash Flow Waterfall         │ │ AR Aging                │ │
│ │ [Waterfall Chart]           │ │ [Stacked Bar Chart]     │ │
│ └─────────────────────────────┘ └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. DATABASE SCHEMA

### 7.1 Core GL Tables

```sql
-- Chart of Accounts
CREATE TABLE chart_of_accounts (
    account_id UUID PRIMARY KEY,
    company_id UUID NOT NULL,
    account_code VARCHAR(50) UNIQUE NOT NULL,
    account_name VARCHAR(200) NOT NULL,
    account_type VARCHAR(20) NOT NULL,
    parent_account_id UUID,
    currency_code VARCHAR(3),
    status VARCHAR(20) DEFAULT 'ACTIVE',
    multi_gaap_mapping JSONB
);

-- Journal Entries
CREATE TABLE journal_entries (
    journal_id UUID PRIMARY KEY,
    journal_number VARCHAR(50) UNIQUE NOT NULL,
    company_id UUID NOT NULL,
    ledger_id UUID NOT NULL,
    period_id UUID NOT NULL,
    journal_date DATE NOT NULL,
    posting_date DATE NOT NULL,
    currency_code VARCHAR(3) NOT NULL,
    exchange_rate DECIMAL(12,6) DEFAULT 1.0,
    description TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'DRAFT',
    total_debit DECIMAL(20,2),
    total_credit DECIMAL(20,2)
);

-- Journal Lines
CREATE TABLE journal_entry_lines (
    line_id UUID PRIMARY KEY,
    journal_id UUID NOT NULL,
    line_number INTEGER NOT NULL,
    account_id UUID NOT NULL,
    debit_amount DECIMAL(20,2) DEFAULT 0,
    credit_amount DECIMAL(20,2) DEFAULT 0,
    description TEXT,
    department_id UUID,
    project_id UUID,
    dimension_values JSONB
);
```

### 7.2 AP/AR Tables

```sql
-- Vendors
CREATE TABLE vendors (
    vendor_id UUID PRIMARY KEY,
    vendor_code VARCHAR(50) UNIQUE NOT NULL,
    vendor_name VARCHAR(200) NOT NULL,
    tax_id VARCHAR(50),
    currency_code VARCHAR(3) NOT NULL,
    payment_terms_id UUID,
    credit_limit DECIMAL(20,2),
    status VARCHAR(20) DEFAULT 'ACTIVE'
);

-- AP Invoices
CREATE TABLE ap_invoices (
    invoice_id UUID PRIMARY KEY,
    invoice_number VARCHAR(100) UNIQUE NOT NULL,
    vendor_id UUID NOT NULL,
    company_id UUID NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    currency_code VARCHAR(3) NOT NULL,
    total_amount DECIMAL(20,2) NOT NULL,
    amount_paid DECIMAL(20,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'DRAFT'
);

-- Similar structure for customers, ar_invoices, ar_receipts
```

**Full Schema**: See [accounting-database-schema.md](accounting-database-schema.md) for complete DDL (50+ tables)

---

## 8. API ENDPOINTS

### 8.1 General Ledger APIs

```
# Chart of Accounts
GET    /api/v1/gl/accounts
POST   /api/v1/gl/accounts
GET    /api/v1/gl/accounts/{id}
PUT    /api/v1/gl/accounts/{id}
DELETE /api/v1/gl/accounts/{id}
GET    /api/v1/gl/accounts/hierarchy

# Journal Entries
GET    /api/v1/gl/journals
POST   /api/v1/gl/journals
GET    /api/v1/gl/journals/{id}
PUT    /api/v1/gl/journals/{id}
POST   /api/v1/gl/journals/{id}/submit
POST   /api/v1/gl/journals/{id}/post
POST   /api/v1/gl/journals/{id}/reverse

# Reporting
GET    /api/v1/gl/trial-balance
GET    /api/v1/gl/general-ledger
```

### 8.2 Accounts Payable APIs

```
# Vendors
GET    /api/v1/ap/vendors
POST   /api/v1/ap/vendors
GET    /api/v1/ap/vendors/{id}
PUT    /api/v1/ap/vendors/{id}

# Invoices
GET    /api/v1/ap/invoices
POST   /api/v1/ap/invoices
POST   /api/v1/ap/invoices/ocr-capture
POST   /api/v1/ap/invoices/{id}/submit
POST   /api/v1/ap/invoices/{id}/approve
POST   /api/v1/ap/invoices/{id}/post

# Payments
GET    /api/v1/ap/payments
POST   /api/v1/ap/payments/batch
POST   /api/v1/ap/payments/batch/{id}/process
POST   /api/v1/ap/payments/generate-file

# Reports
GET    /api/v1/ap/reports/aging
GET    /api/v1/ap/reports/vendor-statement
```

**Complete API Documentation**: See [accounting-module-design.md](accounting-module-design.md) - Section 3 (200+ endpoints)

---

## 9. BUSINESS LOGIC & SERVICES

### 9.1 GL Service Pattern

```python
# backend/src/modules/accounting/services.py

from django.db import transaction
from decimal import Decimal
from .models import JournalEntry, JournalLine
from src.core.policy_engine import PolicyEngine
from src.core.session_manager import get_current_user_from_session

class GLService:

    @staticmethod
    @transaction.atomic
    def create_journal(
        tenant_id: str,
        journal_date,
        lines: List[Dict],
        description: str
    ) -> JournalEntry:
        """Create GL journal entry with validation"""

        # Validate balanced entry
        total_debit = sum(Decimal(line['debit']) for line in lines)
        total_credit = sum(Decimal(line['credit']) for line in lines)

        if total_debit != total_credit:
            raise ValueError("Journal not balanced")

        # Create journal
        journal = JournalEntry.objects.create(
            tenant_id=tenant_id,
            journal_date=journal_date,
            description=description,
            total_debit=total_debit,
            total_credit=total_credit,
            status='DRAFT'
        )

        # Create journal lines
        for idx, line in enumerate(lines):
            JournalLine.objects.create(
                journal=journal,
                line_number=idx + 1,
                account_id=line['account_id'],
                debit_amount=Decimal(line.get('debit', 0)),
                credit_amount=Decimal(line.get('credit', 0)),
                description=line.get('description', '')
            )

        return journal

    @staticmethod
    def post_journal(journal_id: str, user):
        """Post journal to GL (authorization checked by Policy Engine)"""
        journal = JournalEntry.objects.get(id=journal_id)
        
        # Policy Engine checks if user can post (automatic at view level)
        journal.status = 'POSTED'
        journal.save()

    @staticmethod
    def reverse_journal(journal_id: str) -> JournalEntry:
        """Reverse a posted journal"""
        original = JournalEntry.objects.get(id=journal_id)

        # Create reversing entry
        reversal_journal = JournalEntry.objects.create(
            tenant_id=original.tenant_id,
            journal_date=date.today(),
            description=f"Reversal: {original.description}",
            status='DRAFT'
        )

        # Reverse lines (swap debit/credit)
        for original_line in original.lines.all():
            JournalLine.objects.create(
                journal=reversal_journal,
                account=original_line.account,
                debit_amount=original_line.credit_amount,
                credit_amount=original_line.debit_amount,
                description=f"Reversal: {original_line.description}"
            )

        return reversal_journal
```

---

## 10. MULTI-GAAP FRAMEWORK

### 10.1 Parallel Ledger Approach

**Concept**: Multiple ledgers for different accounting standards

```sql
CREATE TABLE gl_ledgers (
    ledger_id UUID PRIMARY KEY,
    company_id UUID NOT NULL,
    ledger_code VARCHAR(20) NOT NULL,
    ledger_name VARCHAR(100) NOT NULL,
    ledger_type VARCHAR(20) NOT NULL,  -- PRIMARY, IFRS, US_GAAP, TAX
    gaap_standard VARCHAR(20),
    currency_code VARCHAR(3) NOT NULL,
    status VARCHAR(20) DEFAULT 'ACTIVE'
);

-- Journal entries are tagged with ledger_id
ALTER TABLE journal_entries ADD COLUMN ledger_id UUID NOT NULL;
```

**Example Setup**:
```
Ledger 1: US GAAP (Primary)
Ledger 2: IFRS (Secondary)
Ledger 3: Tax Ledger
Ledger 4: Management Reporting
```

**Adjustment Journals**: Differences between GAAP standards handled via adjustment journals

---

## 11. COUNTRY-SPECIFIC COMPLIANCE

### 11.1 India - GST Service

```python
# backend/src/modules/tax_management/services.py

from decimal import Decimal
from django.http import JsonResponse

class GSTService:

    @staticmethod
    def calculate_gst(
        taxable_amount: Decimal,
        gst_rate: Decimal,
        supply_type: str  # 'INTRASTATE' or 'INTERSTATE'
    ) -> dict:
        """Calculate GST (CGST+SGST or IGST)"""

        gst_amount = taxable_amount * (gst_rate / 100)

        if supply_type == 'INTRASTATE':
            # Split into CGST + SGST
            return {
                'cgst': gst_amount / 2,
                'sgst': gst_amount / 2,
                'igst': Decimal('0'),
                'total_gst': gst_amount
            }
        else:  # INTERSTATE
            return {
                'cgst': Decimal('0'),
                'sgst': Decimal('0'),
                'igst': gst_amount,
                'total_gst': gst_amount
            }

    @staticmethod
    def generate_gstr1(company_id: str, period: str):
        """Generate GSTR-1 return (outward supplies)"""
        # Implementation for GSTR-1 JSON generation
        pass

    @staticmethod
    def generate_gstr3b(company_id: str, period: str):
        """Generate GSTR-3B return (summary)"""
        # Implementation
        pass
```

### 11.2 Saudi Arabia - ZATCA E-invoicing

```python
# backend/src/modules/tax_management/services.py

from typing import Dict
import asyncio

class ZATCAService:

    @staticmethod
    async def generate_e_invoice(invoice_id: str) -> Dict:
        """Generate ZATCA-compliant e-invoice"""

        from .models import ARInvoice
        invoice = ARInvoice.objects.get(id=invoice_id)

        # Generate XML in ZATCA format (UBL 2.1)
        xml_invoice = ZATCAService._create_ubl_xml(invoice)

        # Sign with X.509 certificate
        signed_xml = ZATCAService._sign_invoice(xml_invoice)

        # Generate QR code
        qr_code = ZATCAService._generate_qr_code(invoice)

        # Submit to ZATCA portal (Phase 2)
        response = await ZATCAService._submit_to_zatca(signed_xml)

        # Store ZATCA UUID and status
        invoice.zatca_uuid = response['uuid']
        invoice.zatca_status = response['status']
        invoice.e_invoice_qr_code = qr_code
        invoice.save()

        return response
```

---

## 12. AI/ML FEATURES

### 12.1 Invoice OCR

```python
# app/services/ai_service.py

from google.cloud import vision
import pytesseract
from typing import Dict

class AIService:

    @staticmethod
    async def extract_invoice_data(image_path: str) -> Dict:
        """Extract invoice data from image using OCR + AI"""

        # Step 1: OCR extraction
        client = vision.ImageAnnotatorClient()
        with open(image_path, 'rb') as image_file:
            content = image_file.read()

        image = vision.Image(content=content)
        response = client.text_detection(image=image)
        text = response.text_annotations[0].description

        # Step 2: AI extraction using NLP
        extracted = {
            'vendor_name': AIService._extract_vendor(text),
            'invoice_number': AIService._extract_invoice_number(text),
            'invoice_date': AIService._extract_date(text),
            'total_amount': AIService._extract_amount(text),
            'line_items': AIService._extract_line_items(text)
        }

        # Step 3: Vendor matching
        extracted['vendor_id'] = AIService._match_vendor(extracted['vendor_name'])
        extracted['confidence'] = 0.95

        return extracted
```

### 12.2 Auto Cash Application

```python
class AIService:

    @staticmethod
    def auto_match_receipt(receipt_id: str) -> List[Dict]:
        """AI-powered receipt to invoice matching"""

        receipt = ARReceipt.get(receipt_id)

        # Get open invoices for customer
        open_invoices = ARInvoice.get_list(filters={
            'customer_id': receipt.customer_id,
            'payment_status': 'UNPAID'
        })

        # AI matching algorithm
        matches = []
        for invoice in open_invoices:
            score = AIService._calculate_match_score(receipt, invoice)
            if score > 0.7:  # 70% confidence threshold
                matches.append({
                    'invoice_id': invoice.invoice_id,
                    'invoice_number': invoice.invoice_number,
                    'amount': invoice.amount_due,
                    'confidence': score
                })

        # Sort by confidence
        matches.sort(key=lambda x: x['confidence'], reverse=True)
        return matches

    @staticmethod
    def _calculate_match_score(receipt, invoice) -> float:
        """Calculate match confidence score"""
        score = 0.0

        # Exact amount match
        if receipt.receipt_amount == invoice.amount_due:
            score += 0.5

        # Reference number match (fuzzy)
        if invoice.invoice_number in receipt.reference_number:
            score += 0.3

        # Due date proximity
        days_diff = abs((receipt.receipt_date - invoice.due_date).days)
        if days_diff <= 7:
            score += 0.2

        return min(score, 1.0)
```

---

## 13. INTEGRATED MODULES

### 13.1 Required Dependencies

**For full accounting functionality, these modules needed:**

| Module | Purpose | Integration Point |
|--------|---------|------------------|
| **Procurement** | Purchase orders, GRN | AP 3-way matching |
| **Inventory** | Stock valuation, COGS | GL posting, Asset accounting |
| **Sales** | Sales orders, delivery | AR invoice generation |
| **Manufacturing** | Production, WIP | Cost accounting, Inventory |
| **HR & Payroll** | Salaries, benefits | Expense accounting, Payroll GL |
| **CRM** | Customers, opportunities | Customer master sync |
| **Projects** | Time tracking, expenses | Project costing, Billing |
| **Asset Maintenance** | Maintenance costs | FA capitalization |
| **DMS** | Document storage | Invoice/receipt storage |

### 13.2 Integration Pattern

**All integrations via Event Bus**

```python
# Example: Sales Order → AR Invoice

# Sales Module emits event
event_bus.emit('sales.order.delivered', {
    'order_id': 'SO-001',
    'customer_id': 'CUST-001',
    'items': [...],
    'total': 10000
})

# AR Module listens
@event_bus.on('sales.order.delivered')
def create_invoice_from_sales_order(order_data):
    invoice = ARInvoice({
        'customer_id': order_data['customer_id'],
        'sales_order_id': order_data['order_id'],
        'items': order_data['items'],
        'total_amount': order_data['total']
    })
    invoice.insert()
    invoice.submit()
```

---

## 14. COMPLETE MODULE EXAMPLES

### 14.1 Accounting Module Structure

**Reference**: See [SARAISE module framework](../../../architecture/module-framework.md) for complete pattern

### 14.2 Vendor Model (Django ORM)

```python
# backend/src/modules/accounting/models.py

from django.db import models
from src.models.base import TenantBase

class Vendor(TenantBase):
    """Vendor master with tenant isolation"""

    class Meta:
        db_table = "accounting_vendors"
        indexes = [
            models.Index(fields=["tenant_id", "vendor_code"]),
        ]

    vendor_code = models.CharField(max_length=50, unique=True)
    vendor_name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255, blank=True)
    tax_id = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    currency_code = models.CharField(max_length=3, default="USD")
    payment_terms = models.CharField(max_length=100, blank=True)
    credit_limit = models.DecimalField(max_digits=20, decimal_places=2, null=True)
    status = models.CharField(
        max_length=20,
        choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive")],
        default="ACTIVE"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # CRITICAL: tenant_id inherited from TenantBase for row-level multitenancy
```

---

## 15. EVENT-DRIVEN ARCHITECTURE

### 15.1 Event Bus

**See [resource-modular-monolith-architecture.md](resource-modular-monolith-architecture.md) Section 4.1** for Event Bus implementation

### 15.2 Key Events

```python
# Financial Events Catalog

EVENTS = {
    # GL Events
    'gl.journal.posted': ['update_account_balances', 'audit_log'],
    'gl.period.closed': ['lock_transactions', 'notify_users'],

    # AP Events
    'ap.invoice.submitted': ['create_gl_journal', 'update_cash_forecast', 'record_tax'],
    'ap.payment.processed': ['update_vendor_balance', 'bank_reconciliation'],

    # AR Events
    'ar.invoice.posted': ['create_gl_journal', 'update_cash_forecast', 'send_email'],
    'ar.receipt.applied': ['update_customer_balance', 'bank_reconciliation'],

    # Budget Events
    'budget.exceeded': ['send_alert', 'require_approval'],

    # System Events
    'user.login': ['audit_log', 'session_tracking'],
    'data.changed': ['audit_log', 'version_history']
}
```

---

## 16. SECURITY & PERMISSIONS

### 16.1 RBAC Implementation

```python
# app/core/permissions.py

from typing import List, Dict
from enum import Enum

class Permission(Enum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    SUBMIT = "submit"
    CANCEL = "cancel"
    APPROVE = "approve"

class PermissionEngine:

    @staticmethod
    def check_permission(
        user_id: str,
        resource: str,
        action: Permission,
        doc_id: str = None
    ) -> bool:
        """Check if user has permission for action on resource"""

        # Get user roles
        user_roles = PermissionEngine._get_user_roles(user_id)

        # Get resource permissions
        permissions = PermissionEngine._get_resource_permissions(resource)

        # Check if any role has permission
        for role in user_roles:
            if role in permissions:
                role_perms = permissions[role]
                if action.value in role_perms and role_perms[action.value]:
                    # Additional checks
                    if PermissionEngine._check_row_level_security(user_id, resource, doc_id):
                        return True

        return False

    @staticmethod
    def _check_row_level_security(user_id: str, resource: str, doc_id: str) -> bool:
        """Row-level security: User can only access docs in their company/department"""
        # Implementation
        pass
```

### 16.2 SOD (Segregation of Duties)

```python
SOD_CONFLICTS = [
    # Creator != Approver
    {
        'resource_type': 'JournalEntry',
        'conflict': ['create', 'approve']
    },
    {
        'resource_type': 'APInvoice',
        'conflict': ['create', 'approve']
    },
    {
        'resource_type': 'Payment',
        'conflict': ['create', 'process']
    },
    # Reconciler != Cashier
    {
        'resource_type': 'BankReconciliation',
        'roles_conflict': ['Cash Manager', 'Reconciliation Manager']
    }
]
```

---

## 17. DEPLOYMENT GUIDE

### 17.1 Docker Setup

```dockerfile
# Dockerfile (backend)

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Copy application
COPY backend/src ./src
COPY backend/tests ./tests

# Run Django app
CMD ["python", "src/manage.py", "runserver", "0.0.0.0:8000"]
```

```yaml
# docker-compose.yml

version: '3.8'

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/saraise
      - REDIS_URL=redis://redis:6379/0
      - DEBUG=False
    depends_on:
      - db
      - redis
    command: >
      sh -c "python src/manage.py migrate &&
             python src/manage.py runserver 0.0.0.0:8000"

  db:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=saraise
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  frontend:
    build:
      context: ./frontend
    ports:
      - "5173:5173"
    depends_on:
      - backend
    environment:
      - VITE_API_URL=http://localhost:8000

volumes:
  postgres_data:
```

### 17.2 Quick Start

```bash
# Clone repository
git clone <repo-url>
cd saraise

# Install backend dependencies
cd backend
pip install -e ".[dev]"

# Install frontend dependencies
cd ../frontend
npm ci

# Run migrations
cd ../backend
python src/manage.py migrate

# Create superuser
python src/manage.py createsuperuser

# Start development servers
# Terminal 1: Backend
python src/manage.py runserver 0.0.0.0:8000

# Terminal 2: Frontend
cd ../frontend
npm run dev

# Access application
# Frontend: http://localhost:5173
# API Docs: http://localhost:8000/api/schema/
# Django Admin: http://localhost:8000/admin/
```

---

## 📚 ADDITIONAL DOCUMENTS

For detailed information, refer to:

1. **[accounting-module-design.md](accounting-module-design.md)** - Original comprehensive design (all features, 500+ pages catalogued)
2. **[accounting-database-schema.md](accounting-database-schema.md)** - Complete database schema (50+ tables with DDL)
3. **[resource-modular-monolith-architecture.md](resource-modular-monolith-architecture.md)** - Detailed framework implementation

---

## 🎯 DEVELOPMENT ROADMAP

### Phase 1: MVP (Months 1-6)
- ✅ Core GL (COA, Journals, Periods)
- ✅ AP (Vendors, Invoices, Payments)
- ✅ AR (Customers, Invoices, Receipts)
- ✅ Cash Management (Bank accounts, Reconciliation)
- ✅ Basic Reporting (Trial Balance, P&L, Balance Sheet)
- ✅ User Management & RBAC

### Phase 2: Enterprise Features (Months 7-12)
- ✅ Fixed Assets with depreciation
- ✅ Multi-GAAP (US GAAP + IFRS)
- ✅ Tax Management (GST India, VAT GCC)
- ✅ E-invoicing (India IRP, Saudi ZATCA)
- ✅ Project Accounting
- ✅ Budgeting & Forecasting
- ✅ AI/ML (OCR, Auto-matching)

### Phase 3: Advanced (Months 13-18)
- ✅ Multi-entity Consolidation
- ✅ Revenue Recognition (ASC 606/IFRS 15)
- ✅ Lease Accounting (ASC 842/IFRS 16)
- ✅ Advanced Analytics & BI
- ✅ Mobile Apps
- ✅ White-label SaaS

---

**END OF DOCUMENTATION**

*Last Updated: 2026-01-03*
*Version: 2.0 (SARAISE-aligned)*
*Architecture: Django REST Framework + Modular Monolith with Row-Level Multitenancy*
*Reference*: [SARAISE Module Framework](../../../architecture/module-framework.md) | [Session Management](../../../architecture/authentication-and-session-management-spec.md) | [Policy Engine](../../../architecture/policy-engine-spec.md)
