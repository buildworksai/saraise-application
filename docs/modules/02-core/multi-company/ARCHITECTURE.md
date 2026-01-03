<!-- SPDX-License-Identifier: Apache-2.0 -->
# Multi-Company & Holding Company Module - - Architecture

**Version:** 1.0.0
**Last Updated:** 2025-12-02
**Status:** Architecture Design
**Merged from:** MULTI-COMPANY-DESIGN.md and MULTI-COMPANY-DESIGN-PART2.md

---

## Table of Contents

- [1. Executive Summary](#1-executive-summary)
  - [1.1 Vision Statement](#11-vision-statement)
  - [1.2 Market Research & Competitive Analysis](#12-market-research--competitive-analysis)
  - [1.3 User Personas](#13-user-personas)
  - [1.4 Jobs-to-be-Done (JTBD)](#14-jobs-to-be-done-jtbd)
  - [1.5 Measurable Outcomes](#15-measurable-outcomes)
- [2. Architecture & Technical Design](#2-architecture--technical-design)
  - [2.1 Module Architecture](#21-module-architecture)
  - [2.2 Integration Points](#22-integration-points)
  - [2.3 API Design](#23-api-design)
  - [2.4 Data Models](#24-data-models)
- [3. UX/UI Design](#3-uxui-design)
  - [3.1 User Flows](#31-user-flows)
  - [3.2 Component Inventory](#32-component-inventory)
  - [3.3 Visual Design Specifications](#33-visual-design-specifications)
- [4. Security & Compliance](#4-security--compliance)
  - [4.1 Entity-Level Access Control](#41-entity-level-access-control)
  - [4.2 Audit Requirements](#42-audit-requirements)
- [5. Performance & Scalability](#5-performance--scalability)
  - [5.1 Performance Targets](#51-performance-targets)
  - [5.2 Scalability Requirements](#52-scalability-requirements)
  - [5.3 Optimization Strategies](#53-optimization-strategies)
- [6. Testing Strategy](#6-testing-strategy)
- [7. AI-Powered Features](#7-ai-powered-features)
  - [7.1 AI Consolidation Assistant](#71-ai-consolidation-assistant)
  - [7.2 AI Transfer Pricing Optimizer](#72-ai-transfer-pricing-optimizer)
  - [7.3 AI FX Forecasting](#73-ai-fx-forecasting)
  - [7.4 AI Compliance Monitor](#74-ai-compliance-monitor)
- [8. Implementation Roadmap](#8-implementation-roadmap)
  - [8.1 Phase 1: Multi-Entity Foundation (Month 1-2)](#81-phase-1-multi-entity-foundation-month-1-2)
  - [8.2 Phase 2: Inter-Company Transactions (Month 3-4)](#82-phase-2-inter-company-transactions-month-3-4)
  - [8.3 Phase 3: Consolidation Engine (Month 5-7)](#83-phase-3-consolidation-engine-month-5-7)
  - [8.4 Phase 4: Advanced Features (Month 8-9)](#84-phase-4-advanced-features-month-8-9)
  - [8.5 Phase 5: Global Compliance (Month 10-11)](#85-phase-5-global-compliance-month-10-11)
  - [8.6 Phase 6: AI & Optimization (Month 12)](#86-phase-6-ai--optimization-month-12)
- [9. Acceptance Criteria](#9-acceptance-criteria)
  - [9.1 Functional Acceptance Criteria](#91-functional-acceptance-criteria)
  - [9.2 Performance Acceptance Criteria](#92-performance-acceptance-criteria)
  - [9.3 Security Acceptance Criteria](#93-security-acceptance-criteria)
  - [9.4 Compliance Acceptance Criteria](#94-compliance-acceptance-criteria)
- [10. Success Metrics](#10-success-metrics)
  - [10.1 Business Metrics](#101-business-metrics)
  - [10.2 User Metrics](#102-user-metrics)
  - [10.3 Technical Metrics](#103-technical-metrics)
- [11. Risk Mitigation](#11-risk-mitigation)
  - [11.1 Technical Risks](#111-technical-risks)
  - [11.2 Compliance Risks](#112-compliance-risks)
  - [11.3 Business Risks](#113-business-risks)
- [12. Dependencies & Integration](#12-dependencies--integration)
  - [12.1 Core Dependencies](#121-core-dependencies)
  - [12.2 Module Integrations](#122-module-integrations)
  - [12.3 External Integrations](#123-external-integrations)
- [13. Documentation Requirements](#13-documentation-requirements)
  - [13.1 User Documentation](#131-user-documentation)
  - [13.2 Technical Documentation](#132-technical-documentation)
  - [13.3 Compliance Documentation](#133-compliance-documentation)
- [14. Future Enhancements](#14-future-enhancements)
  - [14.1 Planned Enhancements (Q2 2025)](#141-planned-enhancements-q2-2025)
  - [14.2 Future Considerations (Q3-Q4 2025)](#142-future-considerations-q3-q4-2025)

---

**Module Code**: `multi_company`
**Category**: Advanced Features
**Priority**: Critical - Enterprise Growth
**Version**: 1.0.0
**Status**: Design Phase

---

## 1. Executive Summary

### 1.1 Vision Statement

**"One platform for your entire corporate group - manage multiple companies, countries, and currencies with enterprise-grade consolidation and compliance."**

The Multi-Company & Holding Company module enables enterprises to manage multiple legal entities, subsidiaries, and business units within a single SARAISE instance. This module provides the foundation for enterprise growth, enabling organizations to scale from single-entity operations to complex multi-national corporate structures.

### 1.2 Market Research & Competitive Analysis

**Market Opportunity**:
- **Target Market**: Mid-market to enterprise companies (500+ employees, $50M+ revenue)
- **Market Size**: $12B+ global ERP market, multi-company features are table stakes for enterprise
- **Growth Drivers**: Globalization, M&A activity, regulatory compliance requirements

**Competitive Landscape**:

| Feature | SARAISE | SAP S/4HANA | Oracle ERP Cloud | NetSuite OneWorld | Microsoft D365 |
|---------|---------|-------------|------------------|-------------------|----------------|
| **Multi-Entity** | Unlimited | Unlimited | Unlimited | Unlimited | Unlimited |
| **Consolidation** | ✓ Advanced | ✓ Advanced | ✓ Advanced | ✓ | ✓ |
| **IC Automation** | ✓ Full | ✓ | ✓ | ✓ Limited | ✓ |
| **Transfer Pricing** | ✓ Advanced | ✓ (add-on) | ✓ (add-on) | ✗ | Partial |
| **Multi-GAAP** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Multi-Currency** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Global Tax** | ✓ 150+ countries | ✓ | ✓ | ✓ | ✓ |
| **AI Features** | ✓ Native | Partial | Partial | ✗ | Partial |
| **Ease of Use** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Pricing** | $$ | $$$$ | $$$$ | $$$ | $$$ |

**Competitive Advantage**:
- **Native AI Integration**: AI-powered consolidation assistance, transfer pricing optimization, FX forecasting
- **Superior UX**: Intuitive interface vs. complex enterprise ERP systems
- **Cost Efficiency**: Enterprise-grade features at 1/3 the cost of SAP/Oracle
- **Modern Architecture**: Cloud-native, API-first, extensible platform

**Key Differentiators**:
1. **Automated IC Processing**: 95% automation vs. 60-70% in competitors
2. **AI-Powered Consolidation**: Reduces consolidation time by 50%
3. **Transfer Pricing Compliance**: Built-in TP engine vs. expensive add-ons
4. **Unified Platform**: Single instance for all entities vs. multiple instances

### 1.3 User Personas

**Primary Personas**:

1. **Group CFO** (Executive)
   - **Goals**: Consolidated financial visibility, compliance, strategic planning
   - **Pain Points**: Manual consolidation, lack of real-time visibility, compliance risks
   - **Jobs-to-be-Done**: Review consolidated financials, approve budgets, ensure compliance
   - **Success Metrics**: Consolidation time <4 hours, 100% compliance, real-time dashboards

2. **Group Finance Manager** (Manager)
   - **Goals**: Run consolidation, manage IC transactions, prepare reports
   - **Pain Points**: Complex Excel-based consolidation, IC reconciliation, currency translation
   - **Jobs-to-be-Done**: Execute monthly consolidation, reconcile IC balances, generate reports
   - **Success Metrics**: 95% IC auto-reconciliation, <4 hour consolidation, zero errors

3. **Entity Controller** (Manager)
   - **Goals**: Manage entity books, ensure local compliance, submit to group
   - **Pain Points**: Dual reporting (local + group), complex entity setup, data entry
   - **Jobs-to-be-Done**: Close entity books, prepare local reports, submit to consolidation
   - **Success Metrics**: On-time submission, zero local compliance issues, accurate data

4. **Tax Manager** (Specialist)
   - **Goals**: Ensure transfer pricing compliance, manage tax reporting, minimize tax risk
   - **Pain Points**: Complex TP documentation, manual calculations, compliance tracking
   - **Jobs-to-be-Done**: Set TP rules, review TP compliance, prepare tax reports
   - **Success Metrics**: 100% TP compliance, automated documentation, zero audit findings

5. **Group Auditor** (External)
   - **Goals**: Audit consolidated financials, verify eliminations, test controls
   - **Pain Points**: Limited access, complex data extraction, manual testing
   - **Jobs-to-be-Done**: Access consolidated data, verify eliminations, test controls
   - **Success Metrics**: Complete audit trail, easy data access, efficient audit process

### 1.4 Jobs-to-be-Done (JTBD)

**Core Jobs**:

1. **"As a Group CFO, I need consolidated financial visibility across all entities so I can make strategic decisions with complete information."**
   - **Outcome**: Real-time consolidated dashboards, drill-down capability, variance analysis

2. **"As a Group Finance Manager, I need to consolidate multiple entities efficiently so I can close the books quickly and accurately."**
   - **Outcome**: Automated consolidation, <4 hour close, zero manual errors

3. **"As an Entity Controller, I need to maintain separate books for my entity while contributing to group consolidation so I can meet both local and group requirements."**
   - **Outcome**: Separate entity books, seamless group submission, dual reporting

4. **"As a Tax Manager, I need to ensure transfer pricing compliance across all IC transactions so I can avoid tax penalties and audits."**
   - **Outcome**: Automated TP calculations, compliance documentation, risk alerts

5. **"As an IC Coordinator, I need to process inter-company transactions efficiently so I can maintain accurate IC balances and avoid reconciliation issues."**
   - **Outcome**: Automated IC processing, 95% auto-reconciliation, workflow approvals

### 1.5 Measurable Outcomes

**Business Outcomes**:
- **Consolidation Efficiency**: 60% reduction in consolidation effort (from days to <4 hours)
- **IC Automation**: 95% IC transactions auto-matched and reconciled
- **Compliance**: 100% compliance in all operating jurisdictions
- **Cost Savings**: $200K+ annual savings vs. manual/Excel consolidation
- **Scalability**: Support 100+ legal entities in single instance

**User Outcomes**:
- **Time Savings**: Finance team saves 20+ hours/month on consolidation
- **Accuracy**: Zero consolidation errors vs. 5-10 errors/month manual
- **Visibility**: Real-time consolidated dashboards vs. monthly reports
- **Compliance**: Automated TP compliance vs. manual documentation

**Technical Outcomes**:
- **Performance**: Consolidation runs in <4 hours for 50 entities
- **Reliability**: 99.9% uptime, zero data loss
- **Scalability**: Support 100+ entities, 1M+ transactions/month
- **Integration**: Seamless integration with all SARAISE modules

---

## 2. Architecture & Technical Design

### 2.1 Module Architecture

**Architecture Principles**:
- **Entity Isolation**: Complete data isolation between legal entities
- **Shared Services**: Common services (consolidation, IC processing) at group level
- **Hierarchical Structure**: Support unlimited hierarchy depth
- **Multi-Currency**: Native multi-currency support with FX translation
- **Audit Trail**: Comprehensive audit trail for all multi-company operations

**Module Structure**:
```
backend/src/modules/multi_company/
├── __init__.py                    # Module manifest
├── models.py                      # Legal entities, IC transactions, consolidation
├── serializers.py            # DRF serializers
├── services/
│   ├── entity_service.py          # Legal entity management
│   ├── ic_transaction_service.py  # Inter-company transaction processing
│   ├── consolidation_service.py  # Consolidation engine
│   ├── transfer_pricing_service.py # Transfer pricing engine
│   └── currency_translation_service.py # FX translation
├── routes.py                      # API endpoints
├── permissions.py                 # Entity-level permissions
└── tests/
    ├── test_entities.py
    ├── test_ic_transactions.py
    ├── test_consolidation.py
    └── test_transfer_pricing.py
```

**Database Schema Overview**:
- `legal_entities`: Legal entity master data
- `intercompany_transactions`: IC transaction records
- `consolidation_periods`: Consolidation period management
- `consolidation_eliminations`: Elimination entries
- `currency_translations`: FX translation history
- `entity_access`: Entity-level access control
- `transfer_pricing_rules`: TP rules and methods

### 2.2 Integration Points

**Core Module Dependencies**:
- `base`: Core platform functionality
- `auth`: Authentication and authorization
- `metadata`: Dynamic Resource system
- `billing`: Subscription and billing management
- `tenant_management`: Tenant-level operations

**Module Integrations**:
- **Accounting**: Multi-entity general ledger, separate books per entity
- **Inventory**: IC inventory transfers, cross-entity stock movements
- **Sales**: IC sales orders, cross-entity invoicing
- **Purchase**: IC purchase orders, cross-entity procurement
- **Billing**: Entity-level billing, consolidated invoicing
- **Reporting**: Consolidated reporting, entity-level reports

**External Integrations**:
- **FX Rate Providers**: Real-time currency exchange rates
- **Tax Engines**: Country-specific tax calculation engines
- **E-Invoicing**: Government e-invoicing portals (Italy, Mexico, Brazil)
- **Regulatory Reporting**: Statutory filing systems

### 2.3 API Design

**Core API Endpoints**:

```python
# Legal Entities
POST   /api/v1/multi-company/entities/              # Create legal entity
GET    /api/v1/multi-company/entities/              # List legal entities
GET    /api/v1/multi-company/entities/{id}          # Get entity details
PUT    /api/v1/multi-company/entities/{id}          # Update entity
DELETE /api/v1/multi-company/entities/{id}          # Deactivate entity
GET    /api/v1/multi-company/entities/tree          # Get org hierarchy tree
GET    /api/v1/multi-company/entities/{id}/hierarchy # Get entity hierarchy

# Inter-Company Transactions
POST   /api/v1/multi-company/ic-transactions/       # Create IC transaction
GET    /api/v1/multi-company/ic-transactions/       # List IC transactions
GET    /api/v1/multi-company/ic-transactions/{id}    # Get IC transaction
PUT    /api/v1/multi-company/ic-transactions/{id}   # Update IC transaction
POST   /api/v1/multi-company/ic-transactions/{id}/approve  # Approve IC transaction
POST   /api/v1/multi-company/ic-transactions/{id}/post     # Post IC transaction
GET    /api/v1/multi-company/ic-reconciliation       # IC reconciliation report
POST   /api/v1/multi-company/ic-reconciliation/match # Auto-match IC transactions

# Consolidation
POST   /api/v1/multi-company/consolidation/periods/ # Create consolidation period
GET    /api/v1/multi-company/consolidation/periods/  # List consolidation periods
POST   /api/v1/multi-company/consolidation/run      # Run consolidation
GET    /api/v1/multi-company/consolidation/eliminations  # Get elimination entries
POST   /api/v1/multi-company/consolidation/translate     # Translate foreign entities
GET    /api/v1/multi-company/consolidation/reports       # Consolidated reports
GET    /api/v1/multi-company/consolidation/status        # Consolidation status

# Transfer Pricing
POST   /api/v1/multi-company/transfer-pricing/rules/     # Create TP rule
GET    /api/v1/multi-company/transfer-pricing/rules/     # List TP rules
PUT    /api/v1/multi-company/transfer-pricing/rules/{id} # Update TP rule
POST   /api/v1/multi-company/transfer-pricing/calculate  # Calculate TP price
GET    /api/v1/multi-company/transfer-pricing/report     # TP compliance report
GET    /api/v1/multi-company/transfer-pricing/benchmark  # TP benchmarking

# Access Control
POST   /api/v1/multi-company/access/grant           # Grant entity access
DELETE /api/v1/multi-company/access/revoke          # Revoke entity access
GET    /api/v1/multi-company/access/my-entities     # Get my accessible entities
GET    /api/v1/multi-company/access/audit-log       # Access audit log
```

**API Request/Response Examples**:

```python
# Create Legal Entity
POST /api/v1/multi-company/entities/
{
  "entity_code": "UK01",
  "legal_name": "Acme UK Ltd.",
  "trading_name": "Acme UK",
  "registration_number": "12345678",
  "tax_id": "GB123456789",
  "jurisdiction": "United Kingdom",
  "parent_entity_id": "parent-uuid",
  "ownership_percentage": 100.00,
  "functional_currency": "GBP",
  "accounting_standard": "IFRS",
  "fiscal_year_end": "12-31"
}

# Create IC Transaction
POST /api/v1/multi-company/ic-transactions/
{
  "transaction_type": "sale",
  "transaction_date": "2025-01-15",
  "from_entity_id": "manufacturing-uuid",
  "to_entity_id": "sales-uuid",
  "amount": 5000.00,
  "currency": "USD",
  "transfer_pricing_method": "cost_plus",
  "markup_percentage": 20.00,
  "source_document_type": "sales_order",
  "source_document_id": "so-uuid"
}
```

### 2.4 Data Models

**Core Models**:

```python
# Legal Entity Model
class LegalEntity(Base):
    __tablename__ = "legal_entities"

    id: Mapped[str]
    tenant_id: Mapped[str]
    entity_code: Mapped[str]  # Unique code (e.g., "US01", "UK01")
    legal_name: Mapped[str]
    trading_name: Mapped[Optional[str]]
    registration_number: Mapped[Optional[str]]
    tax_id: Mapped[Optional[str]]
    jurisdiction: Mapped[str]  # Country/State
    parent_entity_id: Mapped[Optional[str]]
    ownership_percentage: Mapped[Optional[Decimal]]
    consolidation_method: Mapped[str]  # full, proportional, equity, cost
    functional_currency: Mapped[str]
    accounting_standard: Mapped[str]  # IFRS, US_GAAP, LOCAL_GAAP
    fiscal_year_end: Mapped[str]  # MM-DD
    status: Mapped[str]  # active, inactive, dissolved

# Inter-Company Transaction Model
class InterCompanyTransaction(Base):
    __tablename__ = "intercompany_transactions"

    id: Mapped[str]
    tenant_id: Mapped[str]
    ic_transaction_id: Mapped[str]  # Unique IC transaction ID
    transaction_type: Mapped[str]  # sale, loan, service, royalty, dividend
    transaction_date: Mapped[date]
    from_entity_id: Mapped[str]
    to_entity_id: Mapped[str]
    amount: Mapped[Decimal]
    currency: Mapped[str]
    transfer_pricing_method: Mapped[Optional[str]]
    markup_percentage: Mapped[Optional[Decimal]]
    status: Mapped[str]  # draft, approved, posted, reconciled
    reconciled: Mapped[bool]

# Consolidation Period Model
class ConsolidationPeriod(Base):
    __tablename__ = "consolidation_periods"

    id: Mapped[str]
    tenant_id: Mapped[str]
    period_name: Mapped[str]  # e.g., "2025 Q4"
    period_type: Mapped[str]  # monthly, quarterly, annual
    start_date: Mapped[date]
    end_date: Mapped[date]
    consolidation_currency: Mapped[str]
    consolidation_standard: Mapped[str]  # IFRS, US_GAAP
    status: Mapped[str]  # open, locked, consolidated
```

---

## 3. UX/UI Design

### 3.1 User Flows

**Flow 1: Entity Setup & Hierarchy Management**

```
┌─────────────────────────────────────────────────────────────┐
│  Entity Setup Flow                                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Group Admin navigates to Multi-Company → Entities      │
│     ┌───────────────────────────────────────────────────┐  │
│     │ [Entities List View]                              │  │
│     │ - Entity Code | Name | Currency | Status         │  │
│     │ [Create Entity] button                           │  │
│     └───────────────────────────────────────────────────┘  │
│                        ↓                                    │
│  2. Create Entity Form                                     │
│     ┌───────────────────────────────────────────────────┐  │
│     │ Entity Details:                                  │  │
│     │ - Entity Code: [UK01____]                       │  │
│     │ - Legal Name: [Acme UK Ltd.]                     │  │
│     │ - Trading Name: [Acme UK]                        │  │
│     │ - Parent Entity: [Select...] (optional)           │  │
│     │ - Ownership %: [100.00]                          │  │
│     │ - Jurisdiction: [United Kingdom ▼]               │  │
│     │ - Currency: [GBP ▼]                              │  │
│     │ - Accounting Standard: [IFRS ▼]                  │  │
│     │ [Save] [Cancel]                                   │  │
│     └───────────────────────────────────────────────────┘  │
│                        ↓                                    │
│  3. Entity Created → View Hierarchy                        │
│     ┌───────────────────────────────────────────────────┐  │
│     │ [Organization Chart View]                         │  │
│     │     Acme Holdings Inc.                           │  │
│     │           │                                        │  │
│     │    ┌──────┴──────┐                                │  │
│     │    │             │                                │  │
│     │ Acme UK    Acme US                                │  │
│     │ (100%)     (100%)                                 │  │
│     └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Flow 2: Inter-Company Transaction Processing**

```
┌─────────────────────────────────────────────────────────────┐
│  IC Transaction Flow                                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Entity User creates IC Sales Order                      │
│     ┌───────────────────────────────────────────────────┐  │
│     │ IC Sales Order:                                    │  │
│     │ - From Entity: [Acme Manufacturing]               │  │
│     │ - To Entity: [Acme Sales]                         │  │
│     │ - Product: [Widget A]                             │  │
│     │ - Quantity: [100]                                 │  │
│     │ - IC Price: [$50.00] (auto-calculated)            │  │
│     │ - TP Method: [Cost Plus - 20%]                    │  │
│     │ [Create IC Transaction]                            │  │
│     └───────────────────────────────────────────────────┘  │
│                        ↓                                    │
│  2. System creates mirrored IC Purchase Order              │
│     (Automated - notification sent to Acme Sales)          │
│                        ↓                                    │
│  3. Acme Sales approves IC PO                               │
│     ┌───────────────────────────────────────────────────┐  │
│     │ [Pending IC Transactions]                          │  │
│     │ IC PO #IC-2025-001 from Acme Manufacturing         │  │
│     │ Amount: $5,000.00                                  │  │
│     │ [Approve] [Reject] [Request Changes]              │  │
│     └───────────────────────────────────────────────────┘  │
│                        ↓                                    │
│  4. Both sides posted automatically                        │
│     Manufacturing: Dr. IC AR $5,000, Cr. IC Sales $5,000  │
│     Sales: Dr. Inventory $5,000, Cr. IC AP $5,000         │
│                        ↓                                    │
│  5. Auto-reconciliation                                    │
│     [IC Reconciliation Dashboard]                          │
│     Status: ✓ Matched | Balance: $0.00                    │
└─────────────────────────────────────────────────────────────┘
```

**Flow 3: Consolidation Process**

```
┌─────────────────────────────────────────────────────────────┐
│  Consolidation Flow                                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Group Finance creates consolidation period              │
│     ┌───────────────────────────────────────────────────┐  │
│     │ Period: [2025 Q4]                                 │  │
│     │ Start: [2025-10-01] End: [2025-12-31]            │  │
│     │ Currency: [USD] Standard: [IFRS]                  │  │
│     │ [Create Period]                                   │  │
│     └───────────────────────────────────────────────────┘  │
│                        ↓                                    │
│  2. Entities close books and submit                        │
│     [Entity Status Dashboard]                               │
│     ✓ Acme US - Closed                                     │
│     ✓ Acme UK - Closed                                     │
│     ⏳ Acme DE - In Progress                                │
│                        ↓                                    │
│  3. Run consolidation                                       │
│     ┌───────────────────────────────────────────────────┐  │
│     │ [Consolidation Wizard]                              │  │
│     │ Step 1: Select entities [✓]                        │  │
│     │ Step 2: Currency translation [✓]                   │  │
│     │ Step 3: IC reconciliation [✓]                      │  │
│     │ Step 4: Generate eliminations [✓]                  │  │
│     │ Step 5: Calculate minority interest [✓]             │  │
│     │ [Run Consolidation]                                │  │
│     └───────────────────────────────────────────────────┘  │
│                        ↓                                    │
│  4. Review elimination entries                              │
│     [Elimination Entries]                                  │
│     - IC Revenue/Expense: $5,000,000                       │
│     - IC Profit in Inventory: $500,000                     │
│     - IC AR/AP: $1,200,000                                  │
│     [Approve Eliminations]                                 │
│                        ↓                                    │
│  5. Generate consolidated reports                          │
│     [Consolidated Financial Statements]                    │
│     - Balance Sheet                                        │
│     - Income Statement                                     │
│     - Cash Flow Statement                                  │
│     - Segment Reporting                                    │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Component Inventory

**Core UI Components**:

1. **Entity Management**
   - `EntityList`: List view with filters, search, hierarchy toggle
   - `EntityForm`: Create/edit entity form with validation
   - `EntityHierarchyChart`: Interactive org chart visualization
   - `EntityDetails`: Entity detail view with tabs (Info, Books, Users, Reports)

2. **Inter-Company Transactions**
   - `ICTransactionList`: List with filters (entity, type, status, date range)
   - `ICTransactionForm`: Create/edit IC transaction with dual-entry preview
   - `ICReconciliationDashboard`: Real-time IC balance reconciliation
   - `ICTransactionApproval`: Approval workflow component

3. **Consolidation**
   - `ConsolidationWizard`: Step-by-step consolidation process
   - `ConsolidationPeriodList`: Period management with status indicators
   - `EliminationEntriesList`: Review and approve elimination entries
   - `ConsolidatedReports`: Financial statements and segment reports

4. **Transfer Pricing**
   - `TPRulesList`: List of TP rules with methods and rates
   - `TPRuleForm`: Create/edit TP rule with method selection
   - `TPCalculator`: Calculate IC price based on TP method
   - `TPComplianceReport`: TP compliance dashboard

5. **Access Control**
   - `EntityAccessList`: User access by entity
   - `EntityAccessGrant`: Grant/revoke entity access
   - `EntityContextSwitcher`: Switch between accessible entities

### 3.3 Visual Design Specifications

**Design System**:
- **Color Palette**: Use SARAISE brand colors (deepBlue, gold, teal, green)
- **Typography**: System fonts with clear hierarchy
- **Spacing**: 8px grid system
- **Components**: Radix UI primitives with custom styling

**Key Screens**:

1. **Entity Hierarchy Dashboard**
   - Interactive org chart (ReactFlow)
   - Color-coded by entity type (holding, subsidiary, division)
   - Click to drill down to entity details
   - Summary cards: Total entities, Active entities, Revenue, Employees

2. **IC Transaction Form**
   - Split-screen: From Entity | To Entity
   - Real-time TP calculation preview
   - Dual-entry accounting preview
   - Approval workflow status

3. **Consolidation Dashboard**
   - Progress indicators for each consolidation step
   - Entity status grid (closed, in progress, pending)
   - Elimination summary cards
   - Consolidated financial statements viewer

---

## 4. Security & Compliance

### 4.1 Entity-Level Access Control

**Access Control Model**:
- **Entity-Level Permissions**: Users granted access to specific entities
- **Cross-Entity Access**: Group roles can access multiple entities
- **Hierarchical Access**: Access to parent implies access to children (configurable)
- **Row-Level Security**: Automatic data filtering by entity

**Permission Types**:
- `view`: Read-only access to entity data
- `edit`: Modify entity data
- `approve`: Approve transactions (IC transactions, eliminations)
- `consolidate`: Run consolidation (group finance only)
- `admin`: Entity admin (manage users, settings)

**Special Roles**:
- `group_admin`: All entities, full permissions
- `group_finance`: All entities, financial data only
- `auditor`: All entities, read-only, time-limited
- `ic_coordinator`: Entities with IC transactions, IC permissions

### 4.2 Audit Requirements

**Audit Trail**:
- All entity creation/modification
- All IC transaction creation/approval/posting
- All consolidation runs and eliminations
- All TP rule changes
- All entity access grants/revocations
- All cross-entity data access

**Compliance Features**: SOX (internal controls, segregation of duties, audit trails), IFRS/US GAAP (multi-GAAP ledger, mapping, translation), BEPS (TP documentation, CbC Reporting), Pillar Two (ETR calculation, top-up tax), GDPR/CCPA (data privacy, localization).

---

## 5. Performance & Scalability

### 5.1 Performance Targets

- **Entity Creation**: < 200ms
- **IC Transaction Processing**: < 500ms (including dual-entry)
- **Consolidation Run**: < 4 hours for 50 entities
- **IC Reconciliation**: < 30 seconds for 1,000 transactions
- **Currency Translation**: < 5 minutes for 50 entities
- **Report Generation**: < 2 minutes for consolidated financials

### 5.2 Scalability Requirements

- **Entity Support**: 100+ legal entities in single instance
- **Transaction Volume**: 1M+ transactions/month per entity
- **IC Transactions**: 10,000+ IC transactions/month
- **Concurrent Users**: 500+ users across all entities
- **Data Retention**: 7+ years for audit compliance

### 5.3 Optimization Strategies

- **Database Partitioning**: Partition by entity and date
- **Materialized Views**: Pre-computed consolidated trial balances
- **Caching**: Redis caching for entity hierarchy, TP rules
- **Async Processing**: Background jobs for consolidation, translation

## 6. Testing Strategy

**Test Coverage**: 90%+ unit tests, integration tests for all APIs, E2E tests for critical flows, performance tests for consolidation, compliance tests for TP and multi-GAAP. **Critical Test Cases**: Entity hierarchy (5 levels, 50 entities), IC dual-entry accuracy, consolidation eliminations, currency translation, TP calculations, access control, audit trail. **Next**: See `MULTI-COMPANY-DESIGN-PART2.md` for AI features, implementation roadmap, and acceptance criteria.


---

**Module Code**: `multi_company`
**Category**: Advanced Features
**Version**: 1.0.0
**Status**: Design Phase

---

## 7. AI-Powered Features

### 7.1 AI Consolidation Assistant

**Capabilities**:
- **Auto-Detection**: Automatically detect IC transactions needing elimination
- **Smart Suggestions**: Suggest elimination entries based on transaction patterns
- **Error Detection**: Identify consolidation errors and inconsistencies
- **Predictive Adjustments**: Predict consolidation adjustments needed

**Implementation**:
```python
class AIConsolidationAssistant:
    async def detect_eliminations(
        self,
        consolidation_period_id: str
    ) -> List[EliminationSuggestion]:
        """AI-powered elimination detection"""
        # Analyze IC transactions
        # Identify patterns requiring elimination
        # Suggest elimination entries
        pass

    async def validate_consolidation(
        self,
        consolidation_id: str
    ) -> ConsolidationValidation:
        """Validate consolidation for errors"""
        # Check IC reconciliation
        # Verify elimination completeness
        # Validate currency translation
        # Flag inconsistencies
        pass
```

**User Experience**:
- AI suggestions appear in consolidation wizard
- One-click approval of AI-suggested eliminations
- Confidence scores for each suggestion
- Explanation of why elimination is needed

### 7.2 AI Transfer Pricing Optimizer

**Capabilities**:
- **Method Recommendation**: Recommend optimal TP methods per transaction type
- **Benchmarking**: AI-sourced comparable data for benchmarking
- **Risk Assessment**: Flag TP compliance risks automatically
- **Documentation**: Auto-generate TP documentation

**Implementation**:
```python
class AITransferPricingOptimizer:
    async def recommend_method(
        self,
        transaction_type: str,
        product_category: str,
        entity_pair: Tuple[str, str]
    ) -> TPRecommendation:
        """Recommend best TP method"""
        # Analyze transaction characteristics
        # Compare to industry benchmarks
        # Recommend method with justification
        pass

    async def assess_compliance_risk(
        self,
        ic_transaction_id: str
    ) -> ComplianceRisk:
        """Assess TP compliance risk"""
        # Check against TP rules
        # Compare to benchmarks
        # Flag high-risk transactions
        pass
```

**User Experience**:
- Real-time TP method recommendations during IC transaction creation
- Compliance risk indicators (green/yellow/red)
- Automated TP documentation generation
- Benchmarking dashboard with AI insights

### 7.3 AI FX Forecasting

**Capabilities**:
- **Rate Forecasting**: Forecast currency rates for planning
- **Translation Impact**: Predict translation adjustments
- **Hedging Recommendations**: Recommend hedging strategies
- **Consolidation Impact**: Estimate FX impact on consolidated results

**Implementation**:
```python
class AIFXForecaster:
    async def forecast_rates(
        self,
        currency_pair: str,
        horizon_days: int
    ) -> FXForecast:
        """Forecast currency exchange rates"""
        # Use ML models trained on historical data
        # Consider economic indicators
        # Provide confidence intervals
        pass

    async def estimate_translation_impact(
        self,
        entity_id: str,
        consolidation_period_id: str
    ) -> TranslationImpact:
        """Estimate FX translation impact"""
        # Forecast rates
        # Calculate translation adjustments
        # Estimate CTA impact
        pass
```

**User Experience**:
- FX forecast charts in consolidation dashboard
- Translation impact estimates before consolidation
- Hedging recommendations with risk analysis
- Real-time FX alerts for significant movements

### 7.4 AI Compliance Monitor

**Capabilities**:
- **Regulatory Monitoring**: Monitor regulatory changes in all jurisdictions
- **Compliance Alerts**: Alert to new compliance requirements
- **Risk Assessment**: Assess compliance risk by entity
- **Recommendations**: Recommend corrective actions

**Implementation**:
```python
class AIComplianceMonitor:
    async def monitor_regulations(
        self,
        jurisdictions: List[str]
    ) -> List[RegulatoryChange]:
        """Monitor regulatory changes"""
        # Web scraping for regulatory updates
        # NLP to extract relevant changes
        # Alert finance team
        pass

    async def assess_entity_compliance(
        self,
        entity_id: str
    ) -> ComplianceAssessment:
        """Assess entity compliance status"""
        # Check all compliance requirements
        # Identify gaps
        # Recommend actions
        pass
```

**User Experience**:
- Compliance dashboard with risk scores
- Real-time regulatory change alerts
- Compliance checklist per entity
- Action recommendations with priority

---

## 8. Implementation Roadmap

### 8.1 Phase 1: Multi-Entity Foundation (Month 1-2)

**Objectives**:
- Legal entity structure and hierarchy
- Multi-entity data model
- Entity-level permissions and access control
- Chart of accounts per entity
- Multi-currency support

**Deliverables**:
- Entity management UI
- Entity hierarchy visualization
- Entity-level access control
- Multi-currency transaction support
- Entity-specific chart of accounts

**Success Criteria**:
- Support 10 legal entities in single instance
- Entity data isolation working correctly
- Multi-currency transactions processed accurately
- Access control enforced at entity level

**Acceptance Tests**:
1. Create 10 entities with different currencies
2. Verify data isolation between entities
3. Test entity-level access control
4. Process multi-currency transactions
5. Verify entity hierarchy display

### 8.2 Phase 2: Inter-Company Transactions (Month 3-4)

**Objectives**:
- IC transaction framework
- Dual-entry IC processing
- IC reconciliation
- Basic transfer pricing
- IC workflow and approvals

**Deliverables**:
- IC transaction creation UI
- Automated dual-entry processing
- IC reconciliation dashboard
- Basic TP calculation (cost-plus method)
- IC approval workflow

**Success Criteria**:
- Process 100+ IC transactions/month
- 95% IC transactions auto-matched
- Dual-entry accuracy 100%
- IC reconciliation in <30 seconds

**Acceptance Tests**:
1. Create IC sale transaction
2. Verify dual-entry created automatically
3. Approve IC transaction from both sides
4. Run IC reconciliation
5. Verify 100% match rate

### 8.3 Phase 3: Consolidation Engine (Month 5-7)

**Objectives**:
- Consolidation framework
- Automatic elimination entries
- Currency translation
- Minority interest calculation
- Consolidated financial statements
- Segment reporting

**Deliverables**:
- Consolidation wizard
- Automated elimination engine
- Currency translation service
- Consolidated financial statements
- Segment reporting dashboard

**Success Criteria**:
- Monthly group consolidation in <4 hours
- 90% eliminations auto-generated
- Currency translation accuracy 100%
- Consolidated reports generated automatically

**Acceptance Tests**:
1. Create consolidation period
2. Run consolidation for 5 entities
3. Verify elimination entries generated
4. Verify currency translation accuracy
5. Generate consolidated financial statements

### 8.4 Phase 4: Advanced Features (Month 8-9)

**Objectives**:
- Advanced transfer pricing
- Multi-GAAP ledger
- Consolidated budgeting
- Inter-company netting
- Advanced eliminations

**Deliverables**:
- Advanced TP methods (CUP, resale price, TNMM, profit split)
- Multi-GAAP reporting
- Consolidated budgeting module
- IC netting service
- Advanced elimination rules

**Success Criteria**:
- Full TP compliance (all methods)
- Dual GAAP reporting (local + group)
- Consolidated budgets generated
- IC netting reduces transactions by 30%

**Acceptance Tests**:
1. Configure TP rules for all methods
2. Generate TP compliance reports
3. Report in both local and group GAAP
4. Create consolidated budget
5. Run IC netting process

### 8.5 Phase 5: Global Compliance (Month 10-11)

**Objectives**:
- Country-specific localization (10 countries)
- VAT/GST engines
- E-invoicing
- Statutory reporting
- CbC Reporting (BEPS)

**Deliverables**:
- Localization for 10 countries
- VAT/GST calculation engines
- E-invoicing integration (Italy, Mexico, Brazil)
- Statutory report templates
- CbC Reporting module

**Success Criteria**:
- Compliant in 10 countries
- VAT/GST calculated correctly
- E-invoices generated and submitted
- Statutory reports filed electronically
- CbC reports generated

**Acceptance Tests**:
1. Configure localization for 10 countries
2. Calculate VAT/GST for test transactions
3. Generate and submit e-invoices
4. Generate statutory reports
5. Generate CbC reports

### 8.6 Phase 6: AI & Optimization (Month 12)

**Objectives**:
- AI consolidation assistant
- AI transfer pricing optimizer
- FX forecasting
- Compliance monitoring
- Performance optimization

**Deliverables**:
- AI consolidation assistant
- AI TP optimizer
- FX forecasting service
- Compliance monitoring dashboard
- Performance optimizations

**Success Criteria**:
- 50% reduction in consolidation effort
- TP compliance risk reduced by 40%
- FX forecasts within 5% accuracy
- Compliance alerts within 24 hours
- Consolidation time <2 hours

**Acceptance Tests**:
1. Use AI assistant for consolidation
2. Verify TP recommendations
3. Test FX forecasting accuracy
4. Verify compliance alerts
5. Measure performance improvements

---

## 9. Acceptance Criteria

### 9.1 Functional Acceptance Criteria

**Entity Management**:
- ✅ Create legal entity with all required fields
- ✅ Support unlimited hierarchy depth
- ✅ Display entity hierarchy in interactive org chart
- ✅ Update entity details without data loss
- ✅ Deactivate entity (soft delete)

**Inter-Company Transactions**:
- ✅ Create IC transaction with dual-entry preview
- ✅ Automatically create mirrored transaction
- ✅ Approve IC transaction from both entities
- ✅ Auto-match IC transactions in reconciliation
- ✅ Generate IC reconciliation report

**Consolidation**:
- ✅ Create consolidation period
- ✅ Run consolidation for multiple entities
- ✅ Generate automatic elimination entries
- ✅ Translate foreign currency entities
- ✅ Calculate minority interest
- ✅ Generate consolidated financial statements

**Transfer Pricing**:
- ✅ Configure TP rules for all methods
- ✅ Calculate IC price based on TP method
- ✅ Generate TP compliance reports
- ✅ Benchmark against comparables
- ✅ Auto-generate TP documentation

### 9.2 Performance Acceptance Criteria

- ✅ Entity creation: < 200ms
- ✅ IC transaction processing: < 500ms
- ✅ Consolidation run: < 4 hours for 50 entities
- ✅ IC reconciliation: < 30 seconds for 1,000 transactions
- ✅ Currency translation: < 5 minutes for 50 entities
- ✅ Report generation: < 2 minutes for consolidated financials

### 9.3 Security Acceptance Criteria

- ✅ Entity data isolation enforced
- ✅ Entity-level access control working
- ✅ Cross-entity access logged
- ✅ Audit trail complete for all operations
- ✅ RBAC permissions enforced

### 9.4 Compliance Acceptance Criteria

- ✅ SOX compliance features working
- ✅ Multi-GAAP reporting accurate
- ✅ TP compliance documentation complete
- ✅ Statutory reports generated correctly
- ✅ CbC reports formatted correctly

---

## 10. Success Metrics

### 10.1 Business Metrics

- **Consolidation Efficiency**: 60% reduction in consolidation effort
- **IC Automation**: 95% IC transactions auto-matched and reconciled
- **Compliance**: 100% compliance in all operating jurisdictions
- **Cost Savings**: $200K+ annual savings vs. manual/Excel consolidation
- **Scalability**: Support 100+ legal entities in single instance

### 10.2 User Metrics

- **Time Savings**: Finance team saves 20+ hours/month on consolidation
- **Accuracy**: Zero consolidation errors vs. 5-10 errors/month manual
- **Visibility**: Real-time consolidated dashboards vs. monthly reports
- **Compliance**: Automated TP compliance vs. manual documentation
- **User Satisfaction**: Finance team rates 4.5+/5 for multi-company features

### 10.3 Technical Metrics

- **Performance**: Consolidation runs in <4 hours for 50 entities
- **Reliability**: 99.9% uptime, zero data loss
- **Scalability**: Support 100+ entities, 1M+ transactions/month
- **Integration**: Seamless integration with all SARAISE modules
- **Test Coverage**: 90%+ test coverage for all services

---

## 11. Risk Mitigation

### 11.1 Technical Risks

**Risk**: Consolidation performance degrades with entity count
- **Mitigation**: Database partitioning, materialized views, async processing
- **Monitoring**: Performance metrics, load testing

**Risk**: Currency translation accuracy issues
- **Mitigation**: Comprehensive testing, rate validation, audit trail
- **Monitoring**: Translation variance analysis, reconciliation reports

**Risk**: IC reconciliation complexity
- **Mitigation**: Automated matching algorithms, manual override capability
- **Monitoring**: Reconciliation success rate, unmatched transaction alerts

### 11.2 Compliance Risks

**Risk**: TP compliance violations
- **Mitigation**: Built-in TP engine, compliance checks, documentation
- **Monitoring**: TP risk dashboard, compliance reports

**Risk**: Regulatory changes not captured
- **Mitigation**: AI compliance monitoring, regulatory update alerts
- **Monitoring**: Compliance risk scores, regulatory change log

**Risk**: Data privacy violations
- **Mitigation**: Entity data isolation, access controls, audit logging
- **Monitoring**: Access audit logs, data residency compliance

### 11.3 Business Risks

**Risk**: User adoption challenges
- **Mitigation**: Intuitive UI, comprehensive training, excellent documentation
- **Monitoring**: User satisfaction surveys, feature usage analytics

**Risk**: Integration complexity
- **Mitigation**: Well-defined APIs, integration guides, support
- **Monitoring**: Integration success rate, API usage metrics

---

## 12. Dependencies & Integration

### 12.1 Core Dependencies

- **base**: Core platform functionality
- **auth**: Authentication and authorization
- **metadata**: Dynamic Resource system
- **billing**: Subscription and billing management
- **tenant_management**: Tenant-level operations

### 12.2 Module Integrations

- **Accounting**: Multi-entity general ledger, separate books per entity
- **Inventory**: IC inventory transfers, cross-entity stock movements
- **Sales**: IC sales orders, cross-entity invoicing
- **Purchase**: IC purchase orders, cross-entity procurement
- **Billing**: Entity-level billing, consolidated invoicing
- **Reporting**: Consolidated reporting, entity-level reports

### 12.3 External Integrations

- **FX Rate Providers**: Real-time currency exchange rates (XE, OANDA)
- **Tax Engines**: Country-specific tax calculation engines
- **E-Invoicing**: Government e-invoicing portals (Italy, Mexico, Brazil)
- **Regulatory Reporting**: Statutory filing systems

---

## 13. Documentation Requirements

### 13.1 User Documentation

- **Entity Setup Guide**: Step-by-step entity creation and configuration
- **IC Transaction Guide**: How to create and process IC transactions
- **Consolidation Guide**: Complete consolidation process walkthrough
- **TP Compliance Guide**: Transfer pricing setup and compliance
- **Access Control Guide**: Entity-level permissions and access management

### 13.2 Technical Documentation

- **API Documentation**: Complete API reference with examples
- **Database Schema**: Entity-relationship diagrams, table definitions
- **Integration Guide**: How to integrate with other modules
- **Deployment Guide**: Multi-company deployment considerations
- **Performance Tuning**: Optimization strategies and best practices

### 13.3 Compliance Documentation

- **SOX Compliance Guide**: SOX requirements and SARAISE features
- **TP Compliance Guide**: Transfer pricing compliance and documentation
- **Multi-GAAP Guide**: Multi-GAAP reporting setup and configuration
- **Statutory Reporting Guide**: Country-specific statutory reporting

---

## 14. Future Enhancements

### 14.1 Planned Enhancements (Q2 2025)

- **Advanced Consolidation**: Proportional consolidation, equity method automation
- **IC Netting**: Automated inter-company netting service
- **Cash Pooling**: Group cash pooling and sweep account management
- **Advanced TP**: Profit split method, advanced benchmarking

### 14.2 Future Considerations (Q3-Q4 2025)

- **Multi-Entity Workflows**: Workflows spanning multiple entities
- **Entity Analytics**: Advanced analytics across entities
- **M&A Support**: Merger and acquisition transaction support
- **Divestiture Support**: Entity divestiture and spin-off support

---

**Document Control**:
- **Author**: SARAISE Enterprise Finance Team
- **Last Updated**: 2025-01-XX
- **Status**: Design Complete - Ready for Implementation
- **Next Review**: 2025-02-01
