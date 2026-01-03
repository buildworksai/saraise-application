# Technical Specifications - Fixed Assets

**Module ID:** `fixed-assets`
**Version:** 1.0.0
**Last Updated:** 2025-12-11

## Database Schema

### Core Tables

#### `fixed_assets`
```sql
CREATE TABLE fixed_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    asset_number VARCHAR(50) NOT NULL,
    asset_name VARCHAR(200) NOT NULL,
    asset_category VARCHAR(50), -- 'land', 'building', 'machinery', 'vehicle', 'furniture', 'it_equipment'
    acquisition_date DATE NOT NULL,
    acquisition_cost DECIMAL(15,2) NOT NULL,
    salvage_value DECIMAL(15,2) DEFAULT 0,
    useful_life_years INTEGER,
    depreciation_method VARCHAR(30), -- 'straight_line', 'declining_balance', 'units_of_production'
    accumulated_depreciation DECIMAL(15,2) DEFAULT 0,
    net_book_value DECIMAL(15,2),
    location VARCHAR(200),
    custodian_id UUID REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'disposed', 'fully_depreciated'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_fixed_asset_tenant (tenant_id),
    INDEX idx_fixed_asset_number (tenant_id, asset_number),
    INDEX idx_fixed_asset_category (asset_category),
    INDEX idx_fixed_asset_status (status),
    UNIQUE (tenant_id, asset_number)
);
```

#### `depreciation_schedules`
```sql
CREATE TABLE depreciation_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    asset_id UUID NOT NULL REFERENCES fixed_assets(id),
    period_date DATE NOT NULL,
    depreciation_amount DECIMAL(15,2) NOT NULL,
    accumulated_depreciation DECIMAL(15,2) NOT NULL,
    net_book_value DECIMAL(15,2) NOT NULL,
    is_posted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_depr_schedule_tenant (tenant_id),
    INDEX idx_depr_schedule_asset (asset_id),
    INDEX idx_depr_schedule_period (period_date),
    INDEX idx_depr_schedule_posted (is_posted)
);
```

## API Architecture

### REST Endpoints
- `POST /api/v1/fixed-assets` - Register fixed asset
- `GET /api/v1/fixed-assets` - List assets
- `PUT /api/v1/fixed-assets/{id}` - Update asset
- `POST /api/v1/fixed-assets/{id}/depreciate` - Calculate depreciation
- `GET /api/v1/fixed-assets/{id}/schedule` - Get depreciation schedule
- `POST /api/v1/fixed-assets/{id}/dispose` - Dispose asset

### GraphQL Schema
```graphql
type FixedAsset {
  id: ID!
  assetNumber: String!
  assetName: String!
  assetCategory: AssetCategory!
  acquisitionDate: Date!
  acquisitionCost: Decimal!
  depreciationMethod: DepreciationMethod!
  accumulatedDepreciation: Decimal!
  netBookValue: Decimal!
  status: AssetStatus!
  depreciationSchedule: [DepreciationEntry!]!
}

type DepreciationEntry {
  id: ID!
  periodDate: Date!
  depreciationAmount: Decimal!
  accumulatedDepreciation: Decimal!
  netBookValue: Decimal!
  isPosted: Boolean!
}

enum DepreciationMethod {
  STRAIGHT_LINE
  DECLINING_BALANCE
  UNITS_OF_PRODUCTION
}
```

## Data Models
- **Asset Lifecycle**: Acquisition → Depreciation → Disposal
- **Depreciation Calculation**: Automated monthly/annual depreciation
- **Asset Tracking**: Location, custodian, maintenance history
- **Disposal**: Sale, scrap, trade-in processing
- **Revaluation**: Asset revaluation for fair value accounting

## Integration Points
- **Accounting**: Automated journal entries for depreciation
- **Purchase**: Link to purchase orders for asset acquisition
- **Maintenance**: Integration with maintenance module

## Performance Targets
- Asset registration: <200ms (P95)
- Depreciation calculation: <1 second for 10,000 assets (P95)
- Schedule generation: <500ms (P95)

## Security
- **RBAC**: `fixed_assets.create`, `fixed_assets.depreciate`, `fixed_assets.dispose`
- **SoD**: Separate roles for asset registration and disposal
- **RLP**: Row-level filtering by tenant_id and department_id

---
**Related Documentation:** [API](./API.md) | [User Guide](./USER-GUIDE.md) | [Agent Config](./AGENT-CONFIGURATION.md)
