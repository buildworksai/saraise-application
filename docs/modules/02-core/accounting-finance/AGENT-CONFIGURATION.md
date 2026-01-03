# Accounting & Finance Module - AI Agent Configuration

## Overview

The Accounting & Finance module exposes AI agents for intelligent invoice classification and expense analysis. These agents are automatically discovered by Ask Amani and can be invoked through the SARAISE AI Assistant interface.

## Registered AI Agents

### 1. Invoice Classification Agent (`invoice_classification_agent`)

**Description:** AI agent for classifying and categorizing invoices

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.3
- **Max Tokens:** 1000

**Use Cases:**
- Automatically categorize invoices by expense type
- Extract key information from invoice documents
- Match invoices to purchase orders
- Identify duplicate invoices
- Classify invoices for tax purposes

**Integration Points:**
- Invoice processing workflows
- Accounts payable automation
- Tax reporting
- Financial reconciliation

**Ask Amani Entry Points:**
- "Classify this invoice"
- "What category should this invoice be in?"
- "Extract information from this invoice"

### 2. Expense Analysis Agent (`expense_analysis_agent`)

**Description:** AI agent for analyzing and categorizing expenses

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.2
- **Max Tokens:** 800

**Use Cases:**
- Analyze expense patterns
- Categorize expenses automatically
- Detect anomalies in expense reports
- Generate expense insights
- Identify cost optimization opportunities

**Integration Points:**
- Expense reporting workflows
- Budget analysis
- Cost center allocation
- Financial forecasting

**Ask Amani Entry Points:**
- "Analyze expenses for this month"
- "What are the top expense categories?"
- "Detect any unusual expenses"
- "Generate expense insights"

### 3. Tax Advisory Agent (`tax_advisory_agent`)

**Description:** AI agent for tax calculation guidance and multi-jurisdiction tax compliance

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.1 (low for accuracy)
- **Max Tokens:** 1200

**Use Cases:**
- Calculate taxes for multi-jurisdiction invoices
- Provide tax compliance guidance
- Recommend optimal tax strategies
- Validate tax rates and jurisdictions
- Generate tax reports and summaries

**Integration Points:**
- Tax Engine (TaxService, InternalTaxProvider)
- Invoice processing
- Multi-currency transactions
- Cross-border compliance

**Ask Amani Entry Points:**
- "Calculate tax for this invoice in California"
- "What tax rate should I use for this customer?"
- "How do I handle multi-jurisdiction tax?"
- "Explain tax compliance for cross-border sales"

### 4. AR/AP Aging Analyst (`ar_ap_aging_analyst`)

**Description:** AI agent for analyzing aging reports and providing collection/payment insights

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.3
- **Max Tokens:** 1000

**Use Cases:**
- Analyze accounts receivable aging
- Identify overdue invoices
- Recommend collection strategies
- Analyze accounts payable aging
- Prioritize payment schedules
- Generate aging insights and trends

**Integration Points:**
- Reporting Service (ReportingService)
- AR/AP Aging Materialized Views
- Invoice and Payment services
- Cash flow forecasting

**Ask Amani Entry Points:**
- "Show me aging analysis for overdue invoices"
- "Which customers have the highest overdue amounts?"
- "Analyze my AR aging for Q4"
- "What's my AP aging looking like?"
- "Recommend collection priorities"

### 5. Credit/Refund Advisor (`credit_refund_advisor`)

**Description:** AI agent for credit note and refund workflow guidance

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.2
- **Max Tokens:** 900

**Use Cases:**
- Guide credit note creation
- Recommend credit note application
- Process refund workflows
- Validate credit/refund eligibility
- Track credit note utilization
- Generate refund reports

**Integration Points:**
- Payment Service (refund_payment, apply_credit_note)
- Invoice Service (Credit Note creation)
- Customer service workflows
- Financial reconciliation

**Ask Amani Entry Points:**
- "How do I create a credit note?"
- "Apply this credit note to invoice INV-001"
- "Process a refund for payment PAY-123"
- "Show me unused credit notes for customer X"
- "What's the refund policy for this invoice?"

## Workflows

### 1. Invoice to Payment Workflow (`invoice_to_payment`)

**Description:** Process invoice payment workflow

**Steps:**
1. Data Ingestion: Extract invoice data
2. Validation: Verify amount and customer requirements
3. Payment Processing: Automatic payment method
4. Data Output: Create payment record

**AI Agent Integration:**
- Uses `invoice_classification_agent` for invoice categorization
- Automatically triggers on invoice creation

### 2. Journal Entry Approval Workflow (`journal_entry_approval`)

**Description:** Journal entry approval workflow

**Steps:**
1. Data Ingestion: Extract journal entry data
2. Validation: Verify balanced entries and approver
3. Approval Workflow: Two-level approval process
4. Data Output: Create approved journal entry

**AI Agent Integration:**
- Uses `expense_analysis_agent` for expense validation
- Automatically triggers on journal entry creation

### 3. Tax Calculation Workflow (`tax_calculation_workflow`)

**Description:** Automated tax calculation using Tax Engine for multi-jurisdiction compliance

**Steps:**
1. Data Ingestion: Extract invoice data
2. Tax Calculation: Apply Tax Engine with jurisdiction detection
3. Validation: Verify tax rates and jurisdiction validity
4. Data Output: Update invoice with calculated tax

**AI Agent Integration:**
- Uses `tax_advisory_agent` for tax guidance
- Integrates with TaxEngine and InternalTaxProvider
- Supports multi-jurisdiction tax calculation

**Ask Amani Triggers:**
- "Calculate tax for this invoice"
- "Apply tax to invoice INV-001"

### 4. Aging Report Generation Workflow (`aging_report_generation`)

**Description:** Scheduled aging report refresh and analysis for AR/AP management

**Steps:**
1. Data Ingestion: Extract invoice and payment data
2. Aging Calculation: Calculate aging buckets (current, 1-30, 31-60, 61-90, 90+)
3. Materialized View Refresh: Update AR/AP aging views
4. Data Output: Generate aging reports

**AI Agent Integration:**
- Uses `ar_ap_aging_analyst` for insights
- Refreshes materialized views (ar_aging_invoice_view, ap_aging_bill_view)
- Scheduled execution (daily/weekly)

**Ask Amani Triggers:**
- "Refresh aging reports"
- "Generate AR aging analysis"

### 5. Credit Note Application Workflow (`credit_note_application`)

**Description:** Credit note to invoice application workflow with validation

**Steps:**
1. Data Ingestion: Extract credit note data
2. Validation: Verify customer match, currency match, amount validity
3. Credit Application: Apply credit note to invoice
4. Data Output: Create payment record

**AI Agent Integration:**
- Uses `credit_refund_advisor` for guidance
- Integrates with PaymentService.apply_credit_note()
- Validates credit note eligibility

**Ask Amani Triggers:**
- "Apply credit note CN-001 to invoice INV-123"
- "Use this credit note for payment"

## Ask Amani Integration

All Accounting AI agents are automatically discoverable by Ask Amani through the module registry. Users can interact with these agents through natural language queries:

**Example Queries:**
- "Classify this invoice for Acme Corp"
- "Analyze expenses for Q4"
- "What are the top expense categories this month?"
- "Detect any unusual expenses in the last 30 days"
- **"Calculate tax for this multi-state invoice"**
- **"Show me AR aging for customers over 60 days"**
- **"How do I apply a credit note to an invoice?"**
- **"Process a refund for payment PAY-456"**

## Phase 2 Features Integration

### Tax Engine
- **Service**: `TaxService`, `TaxEngine`, `InternalTaxProvider`
- **Agent**: `tax_advisory_agent`
- **Workflow**: `tax_calculation_workflow`
- **Natural Language**: "Calculate tax for invoice in [jurisdiction]"

### Aging Reports
- **Service**: `ReportingService`
- **Models**: `ARAgingReport`, `APAgingReport`
- **Agent**: `ar_ap_aging_analyst`
- **Workflow**: `aging_report_generation`
- **Natural Language**: "Show aging analysis for [AR/AP]"

### Credit/Refund
- **Service**: `PaymentService.refund_payment()`, `PaymentService.apply_credit_note()`
- **Agent**: `credit_refund_advisor`
- **Workflow**: `credit_note_application`
- **Natural Language**: "Apply credit note [CN-XXX] to invoice [INV-XXX]"

## Configuration

AI agents are configured in `MODULE_MANIFEST` in `backend/src/modules/accounting/__init__.py`. To modify agent configurations:

1. Update the `ai_agents` array in `MODULE_MANIFEST`
2. Restart the application to reload module configuration
3. Ask Amani will automatically discover the updated agents

## Customization

AI agents can be customized through:
- Server Scripts: Modify agent behavior programmatically
- Client Scripts: Customize agent UI interactions
- Webhooks: Integrate with external accounting systems
- Custom API Endpoints: Expose agent functionality via REST APIs

See `CUSTOMIZATION.md` for detailed customization options.
