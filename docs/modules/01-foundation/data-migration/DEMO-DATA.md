# Demo Data for Data Migration Module

<!-- SPDX-License-Identifier: Apache-2.0 -->

This document describes the demo data available for the Data Migration module.

## Demo Tenant

The demo data is created for the Demo Tenant:
- **Email**: `demo@saraise.com`
- **Password**: `DemoTenant@2025`

## Demo Data Structure

### Migration Templates

1. **Customer CSV Import Template**
   - Resource: Customer
   - Format: CSV
   - Required fields: customer_name, email
   - Optional fields: phone, address_line1, city, country

2. **Contact CSV Import Template**
   - Resource: Contact
   - Format: CSV
   - Required fields: first_name, last_name, email
   - Optional fields: phone, customer_id

### Sample Migration Jobs

1. **Customer Data Import - Demo**
   - Status: Completed
   - Total rows: 100
   - Success: 95
   - Errors: 5
   - Source: CSV file

2. **Contact Data Import - Demo**
   - Status: In Progress
   - Total rows: 50
   - Processed: 30
   - Success: 28
   - Errors: 2
   - Source: CSV file

## Running the Demo Data Seeder

```bash
python backend/scripts/seed_data_migration_demo.py
```

## Resetting Demo Data

To reset demo data, delete existing migrations and templates for the Demo Tenant, then run the seeder again.

## Demo Scenarios

### Scenario 1: Simple CSV Import
1. Use "Customer CSV Import" template
2. Upload CSV file with customer data
3. Review field mappings
4. Validate data
5. Execute migration

### Scenario 2: Migration with Validation
1. Create new migration for Contact Resource
2. Upload CSV file
3. Enable MDM validation
4. Review validation results
5. Fix errors
6. Execute migration

### Scenario 3: Regulated Data Migration
1. Create migration for regulated data
2. Enable QMS compliance
3. Create change control
4. Get approvals
5. Execute migration with full audit trail
