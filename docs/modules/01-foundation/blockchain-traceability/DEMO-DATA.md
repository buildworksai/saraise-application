# Demo Data for Blockchain Traceability Module

<!-- SPDX-License-Identifier: Apache-2.0 -->

This document describes the demo data available for the Blockchain Traceability module.

## Demo Tenant

The demo data is created for the Demo Tenant:
- **Domain**: `aiagentsorg.com`
- **Admin Email**: `admin@aiagentsorg.com`

## Demo Data Structure

### Blockchain Network

1. **Demo Simulated Network**
   - Network Type: `simulated`
   - Status: Active
   - Description: Simulated network for demo traceability
   - RPC URL: None (simulated)
   - Chain ID: None (simulated)

### Traceability Events

The demo includes traceability events for product `DEMO-PRODUCT-001`:

1. **Manufactured Event**
   - Event Type: `manufactured`
   - Location: Factory A
   - Timestamp: 10 days ago
   - Metadata: `{"batch": "BATCH-001", "line": "LINE-01"}`
   - Blockchain Transaction Hash: Generated hex hash
   - Blockchain Block Number: 1001
   - Verification Status: `verified`

2. **Shipped Event**
   - Event Type: `shipped`
   - Location: Distribution Center
   - Timestamp: 7 days ago
   - Metadata: `{"carrier": "Demo Logistics"}`
   - Blockchain Transaction Hash: Generated hex hash
   - Blockchain Block Number: 1005
   - Verification Status: `verified`

3. **Received Event**
   - Event Type: `received`
   - Location: Retail Store
   - Timestamp: 3 days ago
   - Metadata: `{"store_id": "STORE-001"}`
   - Blockchain Transaction Hash: Generated hex hash
   - Blockchain Block Number: 1010
   - Verification Status: `verified`

### Product Authenticity Record

1. **Authenticity Record for DEMO-PRODUCT-001**
   - Product ID: `DEMO-PRODUCT-001`
   - Authenticity Token: Generated hex token
   - Is Authentic: `true`
   - Verification Count: `0`
   - Blockchain Record ID: `AUTH-{hex}`

### Compliance Records

1. **Temperature Check Compliance**
   - Reference ID: `DEMO-PRODUCT-001`
   - Compliance Type: `temperature_check`
   - Status: `pass`
   - Details: `{"min_temp": 2, "max_temp": 8, "unit": "C"}`
   - Blockchain Proof: `PROOF-{hex}`

2. **Quality Audit Compliance**
   - Reference ID: `DEMO-PRODUCT-001`
   - Compliance Type: `quality_audit`
   - Status: `pass`
   - Details: `{"inspector": "QA-1", "score": 98}`
   - Blockchain Proof: `PROOF-{hex}`

## Running the Demo Data Seeder

```bash
python backend/scripts/seed_blockchain_traceability_demo.py
```

## Resetting Demo Data

To reset demo data, delete existing blockchain traceability records for the Demo Tenant, then run the seeder again.

## Demo Scenarios

### Scenario 1: Trace Product Origin
1. Navigate to Blockchain Traceability → Assets
2. Search for `DEMO-PRODUCT-001`
3. View the asset detail page
4. Review the complete traceability chain:
   - Manufactured at Factory A (10 days ago)
   - Shipped from Distribution Center (7 days ago)
   - Received at Retail Store (3 days ago)
5. Verify blockchain transaction hashes for each event

### Scenario 2: Verify Product Authenticity
1. Navigate to Blockchain Traceability → Authenticity Verification
2. Enter product ID: `DEMO-PRODUCT-001`
3. Enter authenticity token from the authenticity record
4. Verify authenticity status
5. Review blockchain proof

### Scenario 3: Compliance Audit
1. Navigate to Blockchain Traceability → Compliance Audit
2. Select product: `DEMO-PRODUCT-001`
3. Review compliance records:
   - Temperature check (passed)
   - Quality audit (passed)
4. Generate compliance audit report
5. Verify blockchain proofs for each compliance record

### Scenario 4: View Traceability Events
1. Navigate to Blockchain Traceability → Events
2. Filter by product ID: `DEMO-PRODUCT-001`
3. Review event timeline:
   - Manufactured → Shipped → Received
4. View blockchain transaction details for each event
5. Verify event metadata and actor information

### Scenario 5: Manage Blockchain Networks
1. Navigate to Blockchain Traceability → Networks (tenant admin only)
2. View existing "Demo Simulated Network"
3. Review network configuration
4. Test network connectivity (if RPC URL configured)

## Data Relationships

- **TraceabilityAsset** → Links to inventory items via `product_id` and `batch_id`
- **TraceabilityEvent** → References `TraceabilityAsset` via `product_id`
- **ProductAuthenticity** → References `TraceabilityAsset` via `product_id`
- **ComplianceRecord** → References `TraceabilityAsset` via `reference_id`
- **BlockchainNetwork** → Used by all blockchain operations

## Notes

- All blockchain transaction hashes and proofs are simulated for demo purposes
- The demo network is a simulated blockchain (no actual blockchain connection)
- Real blockchain integration would require actual RPC endpoints and network configuration
- All timestamps are relative to the current time when the seeder runs
