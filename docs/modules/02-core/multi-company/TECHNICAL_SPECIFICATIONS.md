# Technical Specifications - Multi-Company & Holding Company

**Module ID:** `multi-company`
**Version:** 1.0.0
**Last Updated:** 2025-12-11

## Database Schema

### Core Tables

#### `companies`
Stores legal entities, subsidiaries, divisions, and branches within the corporate structure.

```sql
CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    parent_company_id UUID REFERENCES companies(id), -- NULL for holding company
    code VARCHAR(20) NOT NULL, -- Unique company code (e.g., "ACME-US", "ACME-UK")
    legal_name VARCHAR(255) NOT NULL,
    trading_name VARCHAR(255),
    company_type VARCHAR(50) NOT NULL, -- 'holding_company', 'subsidiary', 'division', 'branch', 'joint_venture', 'associate'

    -- Legal Registration
    registration_number VARCHAR(100),
    tax_id VARCHAR(100),
    jurisdiction VARCHAR(100), -- Country/state of incorporation
    incorporation_date DATE,
    legal_form VARCHAR(100), -- 'Corporation', 'LLC', 'Partnership', etc.

    -- Addresses
    registered_office_address JSONB,
    principal_place_address JSONB,
    tax_domicile VARCHAR(100),

    -- Financial Configuration
    fiscal_year_end VARCHAR(5), -- MM-DD format (e.g., "12-31")
    reporting_currency VARCHAR(3) NOT NULL, -- ISO 4217 currency code
    functional_currency VARCHAR(3) NOT NULL,
    accounting_standard VARCHAR(20), -- 'GAAP', 'IFRS', 'LOCAL_GAAP'

    -- Ownership
    ownership_percentage DECIMAL(5,2), -- % owned by parent (0-100)
    effective_ownership_percentage DECIMAL(5,2), -- Calculated cascading ownership
    voting_rights_percentage DECIMAL(5,2),
    consolidation_method VARCHAR(30), -- 'full', 'proportional', 'equity', 'cost'

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'inactive', 'dissolved'

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    updated_by UUID REFERENCES users(id),

    INDEX idx_companies_tenant (tenant_id),
    INDEX idx_companies_parent (parent_company_id),
    INDEX idx_companies_code (tenant_id, code),
    INDEX idx_companies_type (company_type),
    UNIQUE (tenant_id, code)
);
```

#### `company_hierarchies`
Materialized path for efficient hierarchy queries.

```sql
CREATE TABLE company_hierarchies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    company_id UUID NOT NULL REFERENCES companies(id),
    ancestor_id UUID NOT NULL REFERENCES companies(id),
    depth INTEGER NOT NULL, -- 0 for self, 1 for direct parent, etc.
    path VARCHAR(1000), -- Materialized path (e.g., "/root/parent/child")

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    INDEX idx_hierarchy_tenant (tenant_id),
    INDEX idx_hierarchy_company (company_id),
    INDEX idx_hierarchy_ancestor (ancestor_id),
    INDEX idx_hierarchy_path (path),
    UNIQUE (tenant_id, company_id, ancestor_id)
);
```

#### `intercompany_transactions`
Tracks all inter-company transactions for elimination and reconciliation.

```sql
CREATE TABLE intercompany_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    transaction_number VARCHAR(50) NOT NULL,
    transaction_type VARCHAR(50) NOT NULL, -- 'sales_purchase', 'loan', 'royalty', 'management_fee', 'dividend', 'capital_contribution'

    -- Parties
    from_company_id UUID NOT NULL REFERENCES companies(id),
    to_company_id UUID NOT NULL REFERENCES companies(id),

    -- Transaction Details
    transaction_date DATE NOT NULL,
    amount DECIMAL(20,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    description TEXT,

    -- Accounting
    from_company_journal_entry_id UUID, -- Link to journal entry in from_company
    to_company_journal_entry_id UUID, -- Link to journal entry in to_company

    -- Transfer Pricing
    transfer_pricing_method VARCHAR(50), -- 'cost_plus', 'resale_price', 'cup', 'tnmm', 'profit_split'
    transfer_pricing_markup_percentage DECIMAL(5,2),
    arms_length_price DECIMAL(20,2),
    transfer_pricing_documentation TEXT,

    -- Status
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'approved', 'posted', 'eliminated'
    from_company_status VARCHAR(20) DEFAULT 'pending',
    to_company_status VARCHAR(20) DEFAULT 'pending',

    -- Reconciliation
    is_reconciled BOOLEAN DEFAULT FALSE,
    reconciled_at TIMESTAMP,
    reconciled_by UUID REFERENCES users(id),

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    INDEX idx_ic_trans_tenant (tenant_id),
    INDEX idx_ic_trans_from (from_company_id),
    INDEX idx_ic_trans_to (to_company_id),
    INDEX idx_ic_trans_date (transaction_date),
    INDEX idx_ic_trans_status (status),
    INDEX idx_ic_trans_number (tenant_id, transaction_number),
    UNIQUE (tenant_id, transaction_number)
);
```

#### `consolidation_rules`
Defines rules for consolidation and elimination entries.

```sql
CREATE TABLE consolidation_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    rule_name VARCHAR(100) NOT NULL,
    rule_type VARCHAR(50) NOT NULL, -- 'elimination', 'adjustment', 'reclassification'

    -- Scope
    applies_to_company_ids UUID[], -- NULL = all companies
    applies_to_transaction_types VARCHAR(50)[],

    -- Rule Logic
    source_account_pattern VARCHAR(100), -- Account code pattern
    target_account_pattern VARCHAR(100),
    elimination_percentage DECIMAL(5,2) DEFAULT 100.00,

    -- Conditions
    conditions JSONB, -- Complex conditions in JSON format

    -- Execution
    execution_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    INDEX idx_consol_rules_tenant (tenant_id),
    INDEX idx_consol_rules_type (rule_type),
    INDEX idx_consol_rules_active (is_active)
);
```

#### `consolidation_periods`
Tracks consolidation runs for each period.

```sql
CREATE TABLE consolidation_periods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    period_start_date DATE NOT NULL,
    period_end_date DATE NOT NULL,
    consolidation_type VARCHAR(20) NOT NULL, -- 'monthly', 'quarterly', 'annual'

    -- Status
    status VARCHAR(20) DEFAULT 'draft', -- 'draft', 'in_progress', 'completed', 'final'
    version INTEGER DEFAULT 1,

    -- Consolidation Details
    consolidation_currency VARCHAR(3) NOT NULL,
    included_company_ids UUID[] NOT NULL,
    elimination_entries_count INTEGER DEFAULT 0,

    -- Results
    consolidated_revenue DECIMAL(20,2),
    consolidated_net_income DECIMAL(20,2),
    minority_interest DECIMAL(20,2),

    -- Timestamps
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    finalized_at TIMESTAMP,

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    INDEX idx_consol_period_tenant (tenant_id),
    INDEX idx_consol_period_dates (period_start_date, period_end_date),
    INDEX idx_consol_period_status (status)
);
```

#### `company_user_access`
Controls which users can access which companies.

```sql
CREATE TABLE company_user_access (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    user_id UUID NOT NULL REFERENCES users(id),
    company_id UUID NOT NULL REFERENCES companies(id),
    access_level VARCHAR(20) NOT NULL, -- 'read', 'write', 'admin'
    is_default_company BOOLEAN DEFAULT FALSE,

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    granted_by UUID REFERENCES users(id),

    INDEX idx_company_access_tenant (tenant_id),
    INDEX idx_company_access_user (user_id),
    INDEX idx_company_access_company (company_id),
    UNIQUE (tenant_id, user_id, company_id)
);
```

## API Architecture

### REST Endpoints

#### Company Management
- `POST /api/v1/companies` - Create new company
- `GET /api/v1/companies` - List all companies (with hierarchy)
- `GET /api/v1/companies/{id}` - Get company details
- `PUT /api/v1/companies/{id}` - Update company
- `DELETE /api/v1/companies/{id}` - Deactivate company
- `GET /api/v1/companies/{id}/hierarchy` - Get company hierarchy tree
- `POST /api/v1/companies/{id}/switch` - Switch active company context

#### Inter-Company Transactions
- `POST /api/v1/intercompany/transactions` - Create IC transaction
- `GET /api/v1/intercompany/transactions` - List IC transactions
- `GET /api/v1/intercompany/transactions/{id}` - Get IC transaction details
- `POST /api/v1/intercompany/transactions/{id}/approve` - Approve IC transaction
- `POST /api/v1/intercompany/transactions/{id}/post` - Post IC transaction to both companies
- `POST /api/v1/intercompany/reconcile` - Reconcile IC balances

#### Consolidation
- `POST /api/v1/consolidation/periods` - Create consolidation period
- `GET /api/v1/consolidation/periods` - List consolidation periods
- `POST /api/v1/consolidation/periods/{id}/execute` - Execute consolidation
- `GET /api/v1/consolidation/periods/{id}/report` - Get consolidated financial statements
- `POST /api/v1/consolidation/periods/{id}/finalize` - Finalize consolidation

### GraphQL Schema

```graphql
type Company {
  id: ID!
  code: String!
  legalName: String!
  tradingName: String
  companyType: CompanyType!
  parentCompany: Company
  subsidiaries: [Company!]!
  ownershipPercentage: Float
  effectiveOwnershipPercentage: Float
  reportingCurrency: String!
  functionalCurrency: String!
  consolidationMethod: ConsolidationMethod!
  isActive: Boolean!
}

type IntercompanyTransaction {
  id: ID!
  transactionNumber: String!
  transactionType: ICTransactionType!
  fromCompany: Company!
  toCompany: Company!
  amount: Decimal!
  currency: String!
  status: ICTransactionStatus!
  isReconciled: Boolean!
  transferPricingMethod: TransferPricingMethod
}

type ConsolidationPeriod {
  id: ID!
  periodStartDate: Date!
  periodEndDate: Date!
  consolidationType: ConsolidationType!
  status: ConsolidationStatus!
  consolidatedRevenue: Decimal
  consolidatedNetIncome: Decimal
  minorityInterest: Decimal
}

enum CompanyType {
  HOLDING_COMPANY
  SUBSIDIARY
  DIVISION
  BRANCH
  JOINT_VENTURE
  ASSOCIATE
}

enum ConsolidationMethod {
  FULL
  PROPORTIONAL
  EQUITY
  COST
}

enum ICTransactionType {
  SALES_PURCHASE
  LOAN
  ROYALTY
  MANAGEMENT_FEE
  DIVIDEND
  CAPITAL_CONTRIBUTION
}

type Query {
  companies(includeInactive: Boolean): [Company!]!
  companyHierarchy(rootCompanyId: ID): CompanyHierarchy!
  intercompanyTransactions(status: ICTransactionStatus): [IntercompanyTransaction!]!
  consolidationPeriods(year: Int): [ConsolidationPeriod!]!
}

type Mutation {
  createCompany(input: CreateCompanyInput!): Company!
  updateCompany(id: ID!, input: UpdateCompanyInput!): Company!
  createIntercompanyTransaction(input: CreateICTransactionInput!): IntercompanyTransaction!
  executeConsolidation(periodId: ID!): ConsolidationPeriod!
}
```

## Data Models

### Business Logic

#### Company Hierarchy Management
- **Unlimited Depth**: Support for complex multi-level hierarchies
- **Effective Ownership Calculation**: Cascading ownership percentage calculation
- **Circular Reference Prevention**: Validation to prevent circular ownership
- **Reorganization Support**: Easy restructuring without data loss

#### Inter-Company Transaction Processing
- **Dual Entry**: Automatic creation of mirrored transactions in both companies
- **Approval Workflow**: Multi-step approval process
- **Auto-Reconciliation**: Automatic matching of IC balances
- **Transfer Pricing**: Automated TP calculation and documentation

#### Consolidation Engine
- **Elimination Entries**: Automatic generation of consolidation eliminations
- **Currency Translation**: Multi-currency consolidation with CTA tracking
- **Minority Interest**: Automatic calculation of non-controlling interests
- **Segment Reporting**: Support for multi-dimensional segment reporting

## Integration Points

### Module Dependencies

#### Required Dependencies
- **Tenant Management**: Company-tenant relationships
- **Accounting**: Multi-company chart of accounts, journal entries
- **Auth**: Company-based access control
- **Metadata**: Entity definitions

#### Optional Dependencies
- **Billing**: Consolidated invoicing
- **All Business Modules**: Multi-company operations support

### Event Bus Integration

#### Published Events
- `company.created` - New company created
- `company.updated` - Company details updated
- `intercompany.transaction.created` - IC transaction created
- `intercompany.transaction.posted` - IC transaction posted
- `consolidation.started` - Consolidation process started
- `consolidation.completed` - Consolidation completed

#### Subscribed Events
- `accounting.journal_entry.posted` - Track IC journal entries
- `user.company.switched` - User switched active company

## Performance Considerations

### Optimization Strategies
- **Hierarchy Caching**: Redis cache for company hierarchy
- **Materialized Paths**: Pre-computed paths for efficient hierarchy queries
- **Batch Consolidation**: Process eliminations in batches
- **Indexed Queries**: All foreign keys and frequently queried fields indexed

### Performance Targets
- Company hierarchy retrieval: <50ms (P95)
- IC transaction creation: <150ms (P95)
- Consolidation execution: <5 seconds for 100 companies (P95)
- Company switching: <100ms (P95)

### Scalability
- Support 1,000+ companies per tenant
- Handle 100,000+ IC transactions per month
- Process consolidations for 500+ entities

## Security Implementation

### Authorization
- **RBAC**: `company.create`, `company.update`, `intercompany.process`, `consolidation.execute`
- **ABAC**: Company-based access control (users can only access assigned companies)
- **RLP**: Row-level filtering by company_id and tenant_id
- **SoD**: Separate roles for IC transaction creation and approval
- **JIT**: Temporary access for consolidation reviews

### Data Protection
- **Company Isolation**: Strict data isolation between companies
- **Cross-Company Access Control**: Explicit grants required
- **Audit Logging**: All company operations logged
- **Transfer Pricing Compliance**: TP documentation and audit trails

## Monitoring & Observability

### OpenTelemetry Tracing
- All company operations traced with `@trace_module_operation` decorator
- IC transaction processing traced end-to-end
- Consolidation process traced with detailed spans

### Key Metrics
- Active companies count (gauge)
- IC transactions per day (counter)
- Consolidation execution time (histogram)
- IC reconciliation rate (gauge)

### Alerts
- IC reconciliation mismatch > $10,000
- Consolidation execution time > 10 seconds
- Failed IC transaction rate > 5%

---

**Related Documentation:**
- [API Documentation](./API.md)
- [User Guide](./USER-GUIDE.md)
- [Agent Configuration](./AGENT-CONFIGURATION.md)
- [Detailed README](./README.md) - Comprehensive 1500+ line feature specification
