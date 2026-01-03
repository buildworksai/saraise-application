# Gap Analysis & Implementation Plan: Accounting Module

## 1. Executive Summary

This document outlines the gaps between the currently implemented `backend/src/modules/accounting/models.py` and the comprehensive design specification in `accounting-module-design.md`. The goal is to achieve 100% feature parity with strict code compliance.

## 2. Current Implementation Status

### ✅ Implemented Features (Foundations)
*   **Chart of Accounts**: `AccountingAccount` supports hierarchy, types, multi-currency.
*   **General Ledger**: `JournalEntry`, `JournalEntryItem` with double-entry enforcement support.
*   **AP/AR Core**: `Invoice` (Sales & Purchase), `InvoiceItem`, `Payment`, `PaymentAllocation`.
*   **Tax**: `Tax`, `TaxExemption`, `TaxReturn` (VAT/GST support scaffolding).
*   **Fixed Assets**: `FixedAsset`, `AssetCategory`, `AssetDepreciationSchedule`.
*   **Period Management**: `GLPeriod`.
*   **Multi-Book**: `GLLedger`.
*   **Reporting**: `FinancialReport`.

### ❌ Missing / Incomplete Features

#### A. Advanced General Ledger
*   **Consolidation**: No models for `ConsolidationGroup`, `EliminationEntry`, `CurrencyTranslationAdjustment`.
*   **Allocations**: No mechanism for complex GL allocations (Step-down, etc.).

#### B. Accounts Payable (AP) Enhancements
*   **Vendor Management**: `AccountingSupplier` exists but overlaps with `Purchase.Supplier`.
    *   *Holistic Fix*: deprecate `AccountingSupplier` and use `Purchase.Supplier` as the master, or sync them.
*   **Invoice Processing**: `modules/accounting/models.py` has a generic `Invoice` model, but `modules/purchase/models.py` has a robust `PurchaseInvoice` with 3-way matching.
    *   *Holistic Fix*: Use `PurchaseInvoice` for all PO-based AP. Use Accounting's generic `Invoice` only for direct GL bills or rename to `SalesInvoice` for AR.
*   **Payment Processing**: Missing `PaymentBatch`, `CheckRegister`, `ElectronicPaymentFile` (ACH/SEPA/NACHA).

#### C. Accounts Receivable (AR) Enhancements
*   **Sales Functionality**: `Invoice` model in accounting acts as the Sales Invoice currently.
*   **Dunning**: No `DunningLevel`, `DunningRun`, `DunningLetter` models.
*   **Revenue Recognition**: Missing `RevRecSchedule`, `PerformanceObligation` (ASC 606).

#### D. Cash Management
*   **Bank Integration**: Missing `BankAccount`, `BankStatement`, `BankStatementLine`.
*   **Reconciliation**: Missing `BankReconciliation`, `ReconciliationRule` (for auto-match).
*   **Cash Forecasting**: No models for cash flow forecast scenarios.

#### E. Inventory Accounting (Integration)
*   *Observation*: `modules/inventory` handles `StockLedgerEntry` and `StockValuation`.
*   **Gap**: Accounting module needs an **Integration Service** to listen to `StockLedgerEntry` and post GL entries (Perpetual Inventory).
    *   Debit Inventory Asset / Credit Suspense (for receipts)
    *   Debit COGS / Credit Inventory Asset (for shipments)

#### F. Cost Accounting
*   **Cost Centers**: `CostCenter` model is missing.
*   **Allocations**: `CostAllocationRule`.

#### G. Budgeting
*   **Budgeting Models**: `Budget`, `BudgetVersion`, `BudgetLine` are missing.

#### H. Intercompany
*   **IC Transactions**: `IntercompanyTransaction`, `IntercompanyRelationship`.

## 3. Implementation Plan

### Phase 1: Core Data Structures (Missing Accounting Domains)
Focus on entities that *strictly* belong to Accounting and do not overlap with other modules.

1.  **Bank & Cash Management Models**: `BankAccount`, `BankStatement`, `BankReconciliation`.
2.  **Budgeting Models**: `Budget`, `BudgetVersion`, `BudgetLine`.
3.  **Cost Accounting Models**: `CostCenter`, `CostAllocationRule`.
4.  **Advanced AR Models**: `DunningLevel`, `RevRecSchedule`.

### Phase 2: Holistic ERP Integration (The "Glue")
Instead of duplicating purchase/inventory logic, we implement **Accounting Event Handlers**.

1.  **Inventory Integration**:
    *   Create `InventoryGlPoster` service.
    *   Triggers: `StockLedgerEntry` creation.
    *   Action: Create `JournalEntry` (Type: SYSTEM).
2.  **Purchase Integration**:
    *   Create `PurchaseGlPoster` service.
    *   Triggers: `GoodsReceiptNote` (Accrual), `PurchaseInvoice` (AP).
    *   Action: Create `JournalEntry`.
3.  **Unified Entity Management**:
    *   Ensure `AccountingSupplier` reads from `Purchase.Supplier`.


## 4. Immediate Action Items
*   Update `models.py` to include missing entities.
*   Validate relationships and strict foreign keys (Tenant ID on EVERYTHING).
