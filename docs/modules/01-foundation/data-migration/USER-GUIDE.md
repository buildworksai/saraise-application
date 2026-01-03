# Data Migration Framework User Guide

<!-- SPDX-License-Identifier: Apache-2.0 -->

## Getting Started

### Creating Your First Migration

1. Navigate to Data Migration module
2. Click "New Migration"
3. Enter migration name and select target Resource
4. Upload your data file (CSV, Excel, JSON)
5. Review AI-generated field mappings
6. Validate data
7. Execute migration

## Step-by-Step Guide

### Step 1: Create Migration

1. Click "New Migration" button
2. Fill in:
   - Migration Name
   - Target Resource
   - Source Type (CSV, Excel, JSON, etc.)
3. Click "Create"

### Step 2: Upload File

1. Click "Upload File" on the migration
2. Select your data file
3. File will be automatically analyzed
4. Review analysis results

### Step 3: Review Field Mappings

1. AI will automatically generate field mappings
2. Review each mapping:
   - Source Field
   - Target Field
   - Confidence Score
3. Adjust mappings as needed
4. Mark required fields

### Step 4: Validate Data

1. Click "Validate" button
2. Review validation results:
   - Errors (must fix)
   - Warnings (should review)
3. Fix errors in source data if needed
4. Re-validate until all errors resolved

### Step 5: Preview Data

1. Click "Preview" to see sample of transformed data
2. Review first 10-20 records
3. Verify data looks correct

### Step 6: Execute Migration

1. Click "Start Migration"
2. Monitor progress in real-time
3. Review results when complete

## Common Tasks

### Importing Customer Data

1. Create migration for "Customer" Resource
2. Upload CSV with customer data
3. Map fields:
   - customer_name → customer_name
   - email → email
   - phone → phone
4. Validate and execute

### Importing with Duplicate Detection

1. Enable duplicate detection in migration settings
2. Set duplicate threshold (default: 85%)
3. Review duplicate pairs before execution
4. Choose to skip or merge duplicates

### Using Migration Templates

1. Select a template from template library
2. Template provides:
   - Column definitions
   - Required fields
   - Sample data format
3. Follow template format for your file
4. Use template for faster setup

## Troubleshooting

### Common Errors

**Error: "Required field missing"**
- Solution: Ensure all required fields are mapped and have data

**Error: "Invalid data format"**
- Solution: Check data types match target field types

**Error: "Duplicate detected"**
- Solution: Review duplicates and decide to skip or merge

### Getting Help

- Check validation errors for specific issues
- Review migration logs for detailed error messages
- Contact support if issues persist
