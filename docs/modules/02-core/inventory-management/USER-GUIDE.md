<!-- SPDX-License-Identifier: Apache-2.0 -->
# Inventory Module User Guide

## Table of Contents

1. [Getting Started](#getting-started)
2. [Item Management](#item-management)
3. [Warehouse Operations](#warehouse-operations)
4. [Stock Management](#stock-management)
5. [Mobile Scanning](#mobile-scanning)
6. [Reports & Analytics](#reports--analytics)
7. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Prerequisites

- Access to SARAISE platform
- Appropriate permissions (tenant_user or tenant_admin)
- Mobile device with camera (for mobile scanning)

### First Steps

1. **Create Warehouses**
   - Navigate to Inventory → Warehouses
   - Click "Create Warehouse"
   - Enter warehouse code, name, and address
   - Set warehouse type (Distribution Center, Retail Store, etc.)

2. **Create Storage Locations**
   - Navigate to Inventory → Warehouses → [Select Warehouse] → Locations
   - Create zones, aisles, racks, and bins
   - Example: Zone-A → Aisle-3 → Rack-5 → Bin-B2

3. **Create Items**
   - Navigate to Inventory → Items
   - Click "Create Item"
   - Enter item code, name, and description
   - Configure tracking options (batch, serial)
   - Set reorder levels

---

## Item Management

### Creating Items

1. Go to **Inventory → Items**
2. Click **"Create Item"**
3. Fill in required fields:
   - **Item Code**: Unique identifier (e.g., "LAPTOP-001")
   - **Item Name**: Display name
   - **Unit of Measure**: Pcs, Kg, L, etc.
   - **Item Group**: Category (Electronics, Raw Materials, etc.)
4. Configure tracking:
   - **Has Batch No**: Enable for items with batch tracking
   - **Has Serial No**: Enable for serialized items
5. Set reorder parameters:
   - **Reorder Level**: Minimum stock level
   - **Reorder Qty**: Quantity to order when below reorder level
6. Click **"Save"**

### Managing Item Barcodes

1. Go to **Inventory → Items → [Select Item] → Barcodes**
2. Click **"Add Barcode"**
3. Enter barcode value or scan with barcode scanner
4. Select barcode type (UPC-A, EAN-13, Code 128, QR Code, etc.)
5. Mark as primary if this is the main barcode
6. Click **"Save"**

### Bulk Barcode Generation

1. Go to **Inventory → Barcodes**
2. Select multiple items
3. Click **"Generate Barcodes"**
4. Choose barcode format
5. System generates barcodes automatically

---

## Warehouse Operations

### Receiving Goods (GRN)

1. **Create GRN**
   - Navigate to **Inventory → Receiving → Create GRN**
   - Select warehouse
   - Link to purchase order (optional)
   - Enter supplier information

2. **Add Items**
   - Click **"Add Item"**
   - Select item from list or scan barcode
   - Enter received quantity
   - Enter batch number (if applicable)
   - Scan serial numbers (if applicable)
   - Select storage location

3. **Post GRN**
   - Review all items
   - Click **"Post GRN"**
   - System creates put-away tasks automatically

### Put-Away Operations

1. **View Put-Away Tasks**
   - Navigate to **Inventory → Put-Away Tasks**
   - Filter by warehouse and status

2. **Start Put-Away**
   - Click on a task to start
   - Scan item barcode to confirm
   - System suggests optimal location
   - Scan location barcode to confirm put-away
   - Click **"Complete"**

3. **Mobile Put-Away**
   - Open mobile app
   - Navigate to Put-Away
   - Scan item barcode
   - Scan suggested location
   - Confirm put-away

### Picking Operations

1. **Create Pick List**
   - Navigate to **Inventory → Pick Lists → Create**
   - Select warehouse
   - Choose picking strategy:
     - **Wave Picking**: Group multiple orders
     - **Batch Picking**: Pick multiple orders simultaneously
     - **Zone Picking**: Pick by warehouse zone
   - Select sales orders
   - Click **"Generate Pick List"**

2. **Execute Picking**
   - Open pick list
   - Navigate to first pick location
   - Scan item barcode
   - Scan location barcode
   - Enter picked quantity
   - Scan serial numbers (if applicable)
   - Mark task as complete

3. **Complete Pick List**
   - Review all picked items
   - Click **"Complete Pick List"**
   - System creates packing tasks

### Packing Operations

1. **View Packing Tasks**
   - Navigate to **Inventory → Packing Tasks**
   - Filter by warehouse and status

2. **Pack Items**
   - Open packing task
   - Scan items into package
   - Select package size
   - Weigh package
   - Print shipping label
   - Click **"Complete Packing"**

### Shipping Operations

1. **Create Shipping Task**
   - Navigate to **Inventory → Shipping Tasks**
   - Link to packing task
   - Enter shipping address
   - Select carrier

2. **Get Shipping Rates**
   - Click **"Get Rates"**
   - System fetches rates from carrier APIs
   - Select preferred rate

3. **Ship Package**
   - Enter tracking number
   - Click **"Ship"**
   - System updates order status

---

## Stock Management

### Viewing Stock Levels

1. **Stock Balance**
   - Navigate to **Inventory → Stock → Stock Balance**
   - Filter by warehouse, item, or category
   - View:
     - On Hand: Physical stock
     - Allocated: Reserved for orders
     - Available: On Hand - Allocated
     - On Order: On purchase orders
     - Projected: On Hand + On Order - Allocated

2. **Stock Ledger**
   - Navigate to **Inventory → Stock → Stock Ledger**
   - View all stock transactions
   - Filter by date range, item, warehouse
   - Export to CSV/Excel

### Stock Transfers

1. **Create Transfer**
   - Navigate to **Inventory → Stock Transfers → Create**
   - Select source warehouse
   - Select destination warehouse
   - Add items to transfer
   - Enter quantities
   - Click **"Create Transfer"**

2. **Ship Transfer**
   - Open transfer
   - Click **"Ship"**
   - Enter carrier and tracking number
   - Click **"Confirm Shipment"**

3. **Receive Transfer**
   - Navigate to destination warehouse
   - Open transfer
   - Click **"Receive"**
   - Verify received quantities
   - Click **"Confirm Receipt"**

### Stock Adjustments

1. **Create Adjustment**
   - Navigate to **Inventory → Stock → Stock Adjustments**
   - Click **"Create Adjustment"**
   - Select warehouse
   - Enter adjustment reason
   - Add items and adjusted quantities
   - Click **"Submit"**

2. **Approve Adjustment**
   - Manager reviews adjustment
   - Clicks **"Approve"**
   - System posts adjustment to stock

---

## Mobile Scanning

### Setting Up Mobile Scanning

1. **Enable Camera Access**
   - Open mobile app
   - Grant camera permissions when prompted

2. **Configure Scanner**
   - Go to Settings → Mobile Scanning
   - Enable offline mode (optional)
   - Set default warehouse
   - Configure operation types

### Batch Scanning

1. **Start Batch Scan**
   - Navigate to **Inventory → Mobile Scanning**
   - Select operation type (Scan, Receive, Issue, Transfer)
   - Select warehouse

2. **Scan Items**
   - Point camera at barcode
   - System automatically recognizes barcode
   - Enter quantity (if needed)
   - Enter batch/serial numbers (if required)
   - Click **"Add Scan"**

3. **Process Batch**
   - Review all scanned items
   - Click **"Process Batch Scan"**
   - System validates and processes all scans

### Offline Scanning

1. **Save for Offline**
   - Scan items as usual
   - Click **"Save for Offline"**
   - Scans are stored locally

2. **Sync When Online**
   - When connection is restored
   - Click **"Sync Now"**
   - System syncs all offline scans
   - Resolve any conflicts if needed

### Conflict Resolution

1. **View Conflicts**
   - If conflicts occur during sync
   - System shows conflict dialog
   - Review each conflict

2. **Resolve Conflict**
   - Select conflict to resolve
   - Choose resolution strategy:
     - **Use Server Version**: Keep server data
     - **Use Client Version**: Keep local data
     - **Merge Both**: Combine data
   - Click **"Resolve"**

---

## Reports & Analytics

### Stock Reports

1. **Stock Summary**
   - Navigate to **Inventory → Reports → Stock Summary**
   - Filter by warehouse, category, date
   - View stock levels and values
   - Export to Excel

2. **Aging Report**
   - Navigate to **Inventory → Reports → Aging Report**
   - View inventory age by bucket (0-30, 31-60, 61-90, 90+ days)
   - Identify slow-moving items
   - Export report

3. **Stock Projection**
   - Navigate to **Inventory → Reports → Stock Projection**
   - Select warehouse and projection period
   - View projected stock levels
   - Includes inbound and outbound projections

### Demand Forecasting

1. **Create Forecast**
   - Navigate to **Inventory → Forecasting → Create Forecast**
   - Select item and warehouse
   - Choose forecast period (30, 60, 90 days)
   - Select algorithm (ARIMA, Prophet, ML, LSTM)
   - Click **"Run Forecast"**

2. **View Forecast Results**
   - Open forecast
   - View forecasted demand by date
   - Check confidence intervals
   - Review forecast accuracy (MAPE)

3. **Update Forecast Accuracy**
   - After actual sales occur
   - Navigate to **Inventory → Forecasting → [Select Forecast] → Update Accuracy**
   - Enter actual quantities
   - System updates accuracy metrics

### ABC Analysis

1. **Run ABC Analysis**
   - Navigate to **Inventory → ABC Analysis**
   - Select warehouse (optional)
   - Click **"Run Analysis"**
   - System categorizes items:
     - **Category A**: High value (20% items, 80% value)
     - **Category B**: Medium value (30% items, 15% value)
     - **Category C**: Low value (50% items, 5% value)

2. **Update Item Classifications**
   - Review analysis results
   - Click **"Update All Items"**
   - System updates item ABC classifications

### Reorder Reports

1. **View Reorder Report**
   - Navigate to **Inventory → Reports → Reorder Report**
   - View items below reorder point
   - See recommended order quantities
   - Filter by warehouse

2. **Create Purchase Orders**
   - Select items from reorder report
   - Click **"Create Purchase Order"**
   - System creates PO with recommended quantities

---

## Troubleshooting

### Common Issues

#### Barcode Not Found

**Problem**: Scanner cannot find barcode in system

**Solutions**:
1. Verify barcode is assigned to item
2. Check barcode value is correct
3. Try manual entry instead of scanning
4. Contact admin to add barcode

#### Insufficient Stock

**Problem**: Cannot issue stock due to insufficient quantity

**Solutions**:
1. Check stock balance for item
2. Verify warehouse selection
3. Check for reserved stock
4. Create stock receipt if needed

#### Sync Conflicts

**Problem**: Conflicts when syncing offline scans

**Solutions**:
1. Review conflict details
2. Choose appropriate resolution strategy
3. Use server version for critical data
4. Contact support if unsure

#### Slow Performance

**Problem**: Reports or lists load slowly

**Solutions**:
1. Use filters to reduce data
2. Use pagination (limit results)
3. Export large reports instead of viewing
4. Contact support if issue persists

### Getting Help

- **Documentation**: https://docs.saraise.com/inventory
- **Support Email**: support@saraise.com
- **Knowledge Base**: https://help.saraise.com
- **Video Tutorials**: https://learn.saraise.com/inventory

---

## Best Practices

1. **Regular Cycle Counts**
   - Perform cycle counts regularly
   - Focus on high-value items (Category A)
   - Use ABC-based cycle counting strategy

2. **Maintain Accurate Data**
   - Update item information promptly
   - Keep barcodes up to date
   - Verify stock levels regularly

3. **Use Mobile Scanning**
   - Use mobile app for warehouse operations
   - Scan barcodes instead of manual entry
   - Sync offline scans regularly

4. **Monitor Stock Levels**
   - Review reorder reports weekly
   - Set appropriate reorder points
   - Use demand forecasts for planning

5. **Optimize Warehouse Operations**
   - Use put-away strategies (FIFO, FEFO)
   - Optimize pick routes
   - Group orders for batch picking

---

## Glossary

- **GRN**: Goods Receipt Note - Document for receiving goods
- **Put-Away**: Process of storing received goods in warehouse locations
- **Pick List**: List of items to pick for orders
- **Cycle Count**: Physical inventory count
- **ABC Analysis**: Classification of items by value
- **FEFO**: First Expiry, First Out - Picking strategy for batches
- **FIFO**: First In, First Out - Inventory valuation/picking method
- **MAPE**: Mean Absolute Percentage Error - Forecast accuracy metric
- **ROP**: Reorder Point - Stock level that triggers reordering
- **EOQ**: Economic Order Quantity - Optimal order quantity

---

**Last Updated**: 2025-11-16
**Version**: 1.0.0
