<!-- SPDX-License-Identifier: Apache-2.0 -->
# Inventory & Warehouse Management Module

**Module Code**: `inventory`
**Category**: Core Business
**Priority**: Critical - Supply Chain Management
**Version**: 1.0.0
**Status**: Implementation Complete

---

## Executive Summary

The Inventory & Warehouse Management module provides comprehensive **inventory control** from stock tracking to warehouse operations, batch/serial management, and real-time inventory visibility. Powered by AI agents, this module automates reordering, demand forecasting, warehouse optimization, and inventory reconciliation—delivering a world-class inventory management experience that rivals SAP Extended Warehouse Management, Oracle NetSuite WMS, Microsoft Dynamics 365 Supply Chain, and Odoo Inventory.

### Vision

**"Every item, in every location, tracked in real-time with AI-powered optimization for zero stockouts and minimal carrying costs."**

---

## World-Class Features

### 1. Multi-Warehouse Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Warehouse Hierarchy**:
```python
warehouse_structure = {
    "warehouse": "Physical location (DC, Store, Plant)",
    "zones": "Sections within warehouse (Receiving, Storage, Picking, Shipping)",
    "aisles": "Rows of storage locations",
    "racks": "Shelving units",
    "bins": "Individual storage locations",
    "example": "WH-01 → Zone-A → Aisle-3 → Rack-5 → Bin-B2"
}
```

**Warehouse Types**:
```python
warehouse_types = {
    "distribution_center": "Central DC for distribution",
    "retail_store": "Retail store with inventory",
    "manufacturing_plant": "Production facility",
    "warehouse_3pl": "Third-party logistics warehouse",
    "transit_warehouse": "Cross-dock facility",
    "consignment": "Customer-owned inventory at your location"
}
```

**Warehouse Features**:
```python
warehouse_capabilities = {
    "location_tracking": "Track stock by bin location",
    "zone_management": "Organize by zones (cold storage, hazmat)",
    "capacity_planning": "Track utilized vs. available capacity",
    "put_away_strategy": "FIFO, FEFO, fixed bin, dynamic",
    "picking_strategy": "Zone picking, batch picking, wave picking",
    "cycle_counting": "Continuous inventory accuracy checks",
    "barcode_scanning": "Mobile scanning for all operations"
}
```

### 2. Stock Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Stock Ledger**:
```python
stock_transactions = {
    "goods_receipt": "Purchase order receipt",
    "goods_issue": "Sales order fulfillment",
    "stock_transfer": "Between warehouses",
    "stock_adjustment": "Manual adjustments",
    "manufacturing": "Consumption & production",
    "return": "Sales/purchase returns",
    "scrap": "Write-off damaged goods",
    "stock_reclassification": "Change item classification"
}
```

**Real-Time Stock Levels**:
```python
stock_view = {
    "on_hand": "Physical stock in warehouse",
    "available": "On-hand - allocated",
    "allocated": "Reserved for sales orders",
    "ordered": "On purchase orders",
    "in_transit": "Between warehouses",
    "projected": "On-hand + ordered - allocated",
    "safety_stock": "Minimum required level",
    "reorder_point": "Trigger for replenishment"
}
```

**Stock Valuation Methods**:
```python
valuation_methods = {
    "fifo": "First In, First Out",
    "lifo": "Last In, First Out (US GAAP)",
    "weighted_average": "Moving average cost",
    "standard_cost": "Predetermined cost",
    "actual_cost": "Actual purchase cost",
    "specific_identification": "Serial number tracking"
}
```

**ABC Analysis**:
```
Category A (High Value - 20% items, 80% value):
  - Tight inventory control
  - Frequent cycle counts
  - Accurate demand forecasting

Category B (Medium Value - 30% items, 15% value):
  - Moderate controls
  - Periodic reviews

Category C (Low Value - 50% items, 5% value):
  - Simple controls
  - Min/max reordering
```

### 3. Batch & Serial Number Tracking
**Status**: Must-Have | **Competitive Parity**: Advanced

**Batch Tracking**:
```python
batch_management = {
    "batch_creation": {
        "auto_generate": "Auto batch number on receipt",
        "manual_entry": "Manual batch entry",
        "supplier_batch": "Use supplier's batch number"
    },
    "batch_attributes": {
        "manufacturing_date": "Production date",
        "expiry_date": "Expiration date",
        "supplier_batch": "Supplier's batch number",
        "batch_size": "Quantity in batch",
        "qc_status": "Passed, failed, in-progress"
    },
    "batch_traceability": {
        "forward": "Where did this batch go? (customers)",
        "backward": "Where did this batch come from? (supplier)",
        "recall": "Identify affected customers for recall"
    }
}
```

**Serial Number Tracking**:
```python
serial_management = {
    "use_cases": [
        "Electronics (laptops, phones)",
        "Appliances (refrigerators, washing machines)",
        "Equipment (tools, machinery)",
        "Medical devices",
        "Automobiles"
    ],
    "operations": {
        "receipt": "Scan serials on PO receipt",
        "storage": "Track serial by bin location",
        "sales": "Scan serials on delivery",
        "warranty": "Track warranty by serial",
        "service": "Service history by serial"
    },
    "serial_attributes": {
        "serial_number": "Unique identifier",
        "manufacturer": "Manufacturer name",
        "model": "Model number",
        "warranty_start": "Warranty start date",
        "warranty_end": "Warranty end date",
        "current_location": "Warehouse/customer",
        "current_status": "In stock, sold, in service, scrapped"
    }
}
```

**FEFO (First Expiry, First Out)**:
```python
fefo_logic = {
    "industries": ["Food & beverage", "Pharmaceuticals", "Cosmetics"],
    "picking_rule": "Pick batches with earliest expiry first",
    "expiry_alerts": {
        "90_days": "Warning - approaching expiry",
        "30_days": "Urgent - mark for clearance",
        "expired": "Block from sales, quarantine"
    }
}
```

### 4. Inventory Replenishment
**Status**: Must-Have | **Competitive Advantage**: AI-Powered

**Reorder Strategies**:
```python
reorder_methods = {
    "reorder_point": {
        "formula": "ROP = (Daily Usage × Lead Time) + Safety Stock",
        "example": "ROP = (100 units/day × 10 days) + 200 = 1,200 units",
        "trigger": "When stock falls below ROP, create PO"
    },
    "min_max": {
        "min": "Minimum stock level (reorder point)",
        "max": "Maximum stock level (target)",
        "order_qty": "Max - current stock"
    },
    "periodic_review": {
        "frequency": "Weekly, monthly review",
        "order_qty": "Target stock - current stock - ordered"
    },
    "kanban": {
        "trigger": "Visual signal (empty bin)",
        "order_qty": "Fixed quantity per kanban"
    }
}
```

**AI-Powered Demand Forecasting**:
```python
ai_forecasting = {
    "inputs": [
        "Historical sales data (12-24 months)",
        "Seasonality patterns",
        "Promotions and campaigns",
        "Market trends",
        "External factors (weather, holidays)"
    ],
    "algorithms": {
        "time_series": "ARIMA, Prophet",
        "machine_learning": "Random Forest, XGBoost",
        "deep_learning": "LSTM neural networks"
    },
    "output": {
        "daily_forecast": "Next 90 days",
        "confidence_interval": "95% confidence range",
        "accuracy": "±10% MAPE (Mean Absolute Percentage Error)"
    },
    "actions": {
        "auto_po": "Auto-generate purchase requisitions",
        "transfer_suggestions": "Move stock between warehouses",
        "slow_moving_alerts": "Flag slow-moving items"
    }
}
```

**Economic Order Quantity (EOQ)**:
```python
eoq_calculation = {
    "formula": "EOQ = √((2 × D × S) / H)",
    "where": {
        "D": "Annual demand",
        "S": "Ordering cost per order",
        "H": "Holding cost per unit per year"
    },
    "example": {
        "D": 10000,
        "S": 50,
        "H": 2,
        "EOQ": 707  # √((2 × 10000 × 50) / 2) ≈ 707 units
    }
}
```

### 5. Warehouse Operations
**Status**: Must-Have | **Competitive Parity**: Advanced

**Inbound Operations**:
```python
inbound_process = {
    "1_receiving": {
        "scan_po": "Scan PO barcode",
        "verify_qty": "Verify quantity received",
        "quality_check": "QC inspection",
        "create_grn": "Goods Receipt Note",
        "print_labels": "Print bin labels"
    },
    "2_put_away": {
        "strategy": "FIFO, FEFO, fixed bin, nearest bin",
        "task_creation": "Auto-create put-away tasks",
        "bin_suggestion": "Suggest optimal bin location",
        "scan_confirmation": "Scan bin to confirm put-away"
    }
}
```

**Outbound Operations**:
```python
outbound_process = {
    "1_pick_list": {
        "wave_picking": "Group orders into waves",
        "batch_picking": "Pick multiple orders simultaneously",
        "zone_picking": "Each picker handles specific zone",
        "pick_optimization": "Optimize pick route"
    },
    "2_picking": {
        "pick_task": "Mobile app shows pick tasks",
        "scan_item": "Scan item barcode",
        "scan_bin": "Scan bin location",
        "verify_qty": "Confirm quantity picked",
        "mark_complete": "Mark task complete"
    },
    "3_packing": {
        "packing_station": "Dedicated packing area",
        "scan_items": "Scan items into shipment",
        "packaging": "Select box size",
        "weight_capture": "Weigh package",
        "print_label": "Print shipping label"
    },
    "4_shipping": {
        "scan_shipment": "Scan shipment barcode",
        "load_truck": "Load onto vehicle",
        "create_manifest": "Shipping manifest",
        "mark_dispatched": "Update status to shipped"
    }
}
```

**Cycle Counting**:
```python
cycle_counting = {
    "methods": {
        "abc_based": "Count A items weekly, B monthly, C quarterly",
        "random_sampling": "Random selection daily",
        "location_based": "Count specific locations",
        "negative_stock": "Count items showing negative stock"
    },
    "process": {
        "create_count_task": "System generates count task",
        "assign_counter": "Assign to warehouse staff",
        "perform_count": "Physical count with mobile app",
        "variance_check": "Compare physical vs. system",
        "adjustment": "Create stock adjustment if variance",
        "approval": "Manager approval for adjustments"
    },
    "kpis": {
        "accuracy": "Target: 98%+ accuracy",
        "frequency": "Count all items at least annually"
    }
}
```

### 6. Inventory Transfers
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Transfer Types**:
```python
transfer_types = {
    "warehouse_to_warehouse": {
        "use_case": "Replenish retail store from DC",
        "workflow": "Create transfer → Pick → Pack → Ship → Receive",
        "in_transit": "Track goods in transit",
        "landed_cost": "Allocate freight to transferred items"
    },
    "location_to_location": {
        "use_case": "Move within same warehouse",
        "workflow": "Create transfer → Move → Confirm",
        "instant": "No in-transit status"
    },
    "bulk_transfer": {
        "use_case": "Move multiple items",
        "workflow": "Upload CSV → Validate → Execute"
    }
}
```

**In-Transit Tracking**:
```python
in_transit_features = {
    "status_tracking": [
        "Created",
        "Picked",
        "Packed",
        "Shipped",
        "In Transit",
        "Delivered",
        "Received"
    ],
    "documents": [
        "Transfer order",
        "Packing list",
        "Shipping manifest",
        "Goods receipt note"
    ],
    "integrations": [
        "FedEx tracking",
        "UPS tracking",
        "USPS tracking",
        "Custom courier API"
    ]
}
```

### 7. Kitting & Bundling
**Status**: Should-Have | **Competitive Parity**: Advanced

**Product Kitting**:
```python
kitting = {
    "definition": "Combine multiple items into single SKU",
    "examples": {
        "computer_kit": {
            "sku": "KIT-LAPTOP-001",
            "components": [
                {"item": "Laptop", "qty": 1},
                {"item": "Mouse", "qty": 1},
                {"item": "Laptop Bag", "qty": 1},
                {"item": "Charger", "qty": 1}
            ]
        },
        "meal_kit": {
            "sku": "MEAL-PASTA-001",
            "components": [
                {"item": "Pasta", "qty": 1},
                {"item": "Sauce", "qty": 1},
                {"item": "Cheese", "qty": 1},
                {"item": "Spices", "qty": 1}
            ]
        }
    },
    "operations": {
        "assembly": "Assemble kit from components",
        "disassembly": "Break kit into components",
        "stock_tracking": "Track kit stock separately",
        "costing": "Sum of component costs"
    }
}
```

**Dynamic Bundling**:
```python
dynamic_bundling = {
    "definition": "Create bundles at time of sale",
    "use_case": "Buy 2 shirts, get 1 tie free",
    "pricing": "Bundle pricing vs. component pricing",
    "stock_impact": "Deduct individual items, not bundle"
}
```

### 8. Quality Control
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**QC Inspection Points**:
```python
qc_checkpoints = {
    "inbound_inspection": {
        "trigger": "Goods receipt",
        "checks": ["Quantity", "Condition", "Specifications"],
        "outcomes": ["Accept", "Reject", "Partial Accept"],
        "quarantine": "Hold stock until QC passed"
    },
    "in_process_inspection": {
        "trigger": "During manufacturing",
        "checks": ["Work in progress quality"],
        "outcomes": ["Continue", "Rework", "Scrap"]
    },
    "outbound_inspection": {
        "trigger": "Before shipping",
        "checks": ["Order accuracy", "Packaging quality"],
        "outcomes": ["Ship", "Repack", "Hold"]
    }
}
```

**QC Templates**:
```python
qc_template = {
    "template_name": "Electronics Incoming Inspection",
    "inspection_points": [
        {
            "parameter": "Physical Damage",
            "method": "Visual",
            "acceptance": "No damage",
            "mandatory": True
        },
        {
            "parameter": "Functionality Test",
            "method": "Power On Test",
            "acceptance": "Powers on successfully",
            "mandatory": True
        },
        {
            "parameter": "Serial Number",
            "method": "Scan",
            "acceptance": "Valid serial",
            "mandatory": True
        }
    ]
}
```

### 9. Inventory Valuation & Costing
**Status**: Must-Have | **Competitive Parity**: Advanced

**Stock Valuation Report**:
```
Inventory Valuation - November 30, 2025

Item            Qty     Avg Cost    Total Value
------------------------------------------------
Laptop A        100     $800.00     $80,000.00
Mouse B         500     $15.00      $7,500.00
Keyboard C      300     $25.00      $7,500.00
------------------------------------------------
Total                               $95,000.00
```

**Landed Cost**:
```python
landed_cost = {
    "components": {
        "product_cost": "Purchase price from supplier",
        "freight": "Shipping cost",
        "customs_duty": "Import duty",
        "insurance": "Cargo insurance",
        "handling": "Warehouse handling fees"
    },
    "allocation": {
        "by_weight": "Freight allocated by item weight",
        "by_value": "Duty allocated by item value",
        "by_quantity": "Handling by item count"
    },
    "example": {
        "product_cost": 1000.00,
        "freight": 100.00,
        "duty": 50.00,
        "total_landed_cost": 1150.00
    }
}
```

**Standard Costing vs. Actual Costing**:
```python
costing_methods = {
    "standard_cost": {
        "definition": "Predetermined cost set annually",
        "pros": "Simpler, cost variance analysis",
        "cons": "May not reflect actual cost",
        "use_case": "Manufacturing, budgeting"
    },
    "actual_cost": {
        "definition": "Actual purchase/production cost",
        "pros": "Accurate cost",
        "cons": "More complex, cost fluctuations",
        "use_case": "Trading, retail"
    }
}
```

### 10. Barcode & RFID
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Barcode Support**:
```python
barcode_formats = {
    "1d_barcodes": [
        "UPC-A (retail)",
        "EAN-13 (international)",
        "Code 128 (logistics)",
        "Code 39 (industrial)"
    ],
    "2d_barcodes": [
        "QR Code",
        "Data Matrix",
        "PDF417"
    ],
    "gs1_standards": {
        "gtin": "Global Trade Item Number",
        "sscc": "Serial Shipping Container Code",
        "batch": "Batch/lot number",
        "expiry": "Expiration date"
    }
}
```

**Mobile Scanning**:
```python
mobile_app_features = {
    "operations": [
        "Goods receipt",
        "Put-away",
        "Picking",
        "Cycle counting",
        "Stock transfer",
        "Stock adjustment"
    ],
    "scanning": {
        "camera": "Use phone camera",
        "bluetooth_scanner": "Pair Bluetooth scanner",
        "offline_mode": "Work offline, sync later"
    },
    "validation": {
        "real_time": "Validate against system",
        "alerts": "Audio/visual alerts for errors",
        "confirmation": "Confirm actions"
    }
}
```

**RFID Tracking**:
```python
rfid_features = {
    "use_cases": [
        "High-value items (jewelry, electronics)",
        "Apparel (retail stores)",
        "Assets (tools, equipment)",
        "Pallets (warehouse automation)"
    ],
    "advantages": {
        "bulk_scanning": "Scan 100+ items simultaneously",
        "no_line_of_sight": "Read through boxes",
        "automated_tracking": "Auto-track movement through portals",
        "accuracy": "99.9%+ inventory accuracy"
    },
    "operations": {
        "tagging": "Attach RFID tags to items",
        "portal_reading": "Auto-read at dock doors",
        "handheld_reading": "Mobile RFID readers",
        "inventory_count": "Instant inventory count"
    }
}
```

### 11. Returns Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Return Types**:
```python
return_types = {
    "sales_return": {
        "trigger": "Customer returns product",
        "workflow": "Create return → Receive → QC → Restock/Scrap",
        "credit_note": "Issue credit to customer",
        "restocking_fee": "Optional fee for returns"
    },
    "purchase_return": {
        "trigger": "Return to supplier",
        "workflow": "Create return → Ship → Supplier receives → Credit",
        "debit_note": "Debit note to supplier"
    },
    "warranty_return": {
        "trigger": "Defective product under warranty",
        "workflow": "RMA → Receive → Test → Replace/Repair",
        "claim": "Submit warranty claim to manufacturer"
    }
}
```

**RMA (Return Merchandise Authorization)**:
```python
rma_process = {
    "1_request": "Customer requests return online",
    "2_approval": "Validate reason, approve RMA",
    "3_rma_number": "Generate RMA number",
    "4_shipping_label": "Email return shipping label",
    "5_receive": "Receive returned item",
    "6_inspection": "QC inspection",
    "7_disposition": {
        "restock": "Add back to inventory",
        "repair": "Send for repair",
        "scrap": "Write off as loss",
        "return_to_vendor": "Return to supplier"
    },
    "8_refund": "Process refund or replacement"
}
```

### 12. Inventory Reports & Analytics
**Status**: Must-Have | **Competitive Parity**: Advanced

**Standard Reports**:
```python
inventory_reports = {
    "stock_summary": "Stock by item, warehouse, category",
    "stock_ledger": "All stock transactions",
    "stock_valuation": "Value of inventory",
    "aging_report": "Age of inventory",
    "abc_analysis": "A/B/C classification",
    "slow_moving": "Items with low turnover",
    "fast_moving": "Items with high turnover",
    "dead_stock": "Zero movement in 6+ months",
    "stock_projection": "Projected stock levels",
    "reorder_report": "Items below reorder point",
    "batch_expiry": "Batches nearing expiry",
    "serial_tracking": "Serial number trace report"
}
```

**Key Metrics**:
```python
inventory_kpis = {
    "inventory_turnover": {
        "formula": "COGS / Average Inventory",
        "target": "Industry-dependent (4-12x annually)",
        "interpretation": "Higher = better inventory management"
    },
    "days_inventory_outstanding": {
        "formula": "365 / Inventory Turnover",
        "target": "30-90 days",
        "interpretation": "Lower = faster moving inventory"
    },
    "stockout_rate": {
        "formula": "# of stockouts / total orders × 100",
        "target": "< 2%",
        "interpretation": "Lower = better availability"
    },
    "inventory_accuracy": {
        "formula": "Matching records / total records × 100",
        "target": "> 98%",
        "interpretation": "Higher = better record accuracy"
    },
    "carrying_cost": {
        "formula": "Total holding cost / average inventory value",
        "typical": "15-25% of inventory value annually",
        "components": ["Storage", "Insurance", "Obsolescence", "Capital cost"]
    },
    "fill_rate": {
        "formula": "Orders fulfilled completely / total orders × 100",
        "target": "> 95%",
        "interpretation": "Higher = better customer service"
    }
}
```

**AI Analytics**:
```python
ai_analytics = {
    "demand_forecasting": "Predict future demand",
    "stockout_prediction": "Predict potential stockouts",
    "optimal_stock_levels": "Recommend safety stock & reorder points",
    "slow_moving_detection": "Identify items becoming slow movers",
    "pricing_optimization": "Suggest markdowns for old stock",
    "warehouse_optimization": "Suggest better bin assignments",
    "supplier_performance": "Analyze lead time accuracy"
}
```

---

## AI Agent Integration

### Inventory AI Agents

**1. Demand Forecasting Agent**
```python
agent_capabilities = {
    "forecast_demand": "Predict demand for next 90 days using ML",
    "seasonality_detection": "Identify seasonal patterns",
    "trend_analysis": "Detect upward/downward trends",
    "promotion_impact": "Model impact of promotions",
    "new_product_forecast": "Forecast for new product launches",
    "accuracy_tracking": "Track forecast vs. actual, improve model"
}
```

**2. Replenishment Agent**
```python
agent_capabilities = {
    "auto_po_creation": "Auto-create POs when stock below ROP",
    "optimal_order_qty": "Calculate EOQ considering constraints",
    "supplier_selection": "Choose best supplier (price, lead time, quality)",
    "transfer_suggestions": "Suggest inter-warehouse transfers",
    "safety_stock_optimization": "Adjust safety stock based on variability",
    "lead_time_tracking": "Learn actual lead times, adjust forecasts"
}
```

**3. Warehouse Optimization Agent**
```python
agent_capabilities = {
    "slotting_optimization": "Place fast movers near packing area",
    "pick_path_optimization": "Optimize picker routes",
    "wave_planning": "Group orders into efficient picking waves",
    "labor_planning": "Predict staffing needs by hour",
    "space_utilization": "Maximize warehouse space usage",
    "cross_docking": "Identify cross-dock opportunities"
}
```

**4. Quality Control Agent**
```python
agent_capabilities = {
    "defect_prediction": "Predict quality issues by supplier/batch",
    "image_recognition": "AI-powered visual quality inspection",
    "anomaly_detection": "Flag unusual patterns (sudden defects)",
    "supplier_scoring": "Score suppliers based on QC pass rate",
    "automated_disposition": "Auto-decide accept/reject based on rules",
    "root_cause_analysis": "Analyze quality issues for patterns"
}
```

**5. Inventory Accuracy Agent**
```python
agent_capabilities = {
    "discrepancy_detection": "Flag unusual stock movements",
    "cycle_count_prioritization": "Prioritize which items to count",
    "shrinkage_prediction": "Predict high-shrinkage items/locations",
    "auto_reconciliation": "Auto-adjust minor variances",
    "fraud_detection": "Detect potential theft or fraud patterns",
    "accuracy_scoring": "Score accuracy by warehouse/zone/picker"
}
```

---

## Database Schema

```sql
-- Warehouses
CREATE TABLE warehouses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Warehouse Info
    warehouse_code VARCHAR(50) NOT NULL,
    warehouse_name VARCHAR(255) NOT NULL,
    warehouse_type VARCHAR(50), -- dc, retail, plant, 3pl, transit

    -- Address
    address_line1 VARCHAR(255),
    address_line2 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(100),
    postal_code VARCHAR(20),
    country VARCHAR(100),

    -- Contact
    contact_person VARCHAR(255),
    phone VARCHAR(50),
    email VARCHAR(255),

    -- Settings
    is_default BOOLEAN DEFAULT false,
    active BOOLEAN DEFAULT true,

    -- Capacity
    total_capacity_sqft DECIMAL(12, 2),
    used_capacity_sqft DECIMAL(12, 2),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, warehouse_code),
    INDEX idx_tenant (tenant_id)
);

-- Storage Locations (Bins)
CREATE TABLE storage_locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    warehouse_id UUID REFERENCES warehouses(id),

    -- Location Hierarchy
    location_code VARCHAR(100) NOT NULL, -- A-1-3-B2
    zone VARCHAR(50), -- Receiving, Storage, Picking, Shipping
    aisle VARCHAR(50),
    rack VARCHAR(50),
    bin VARCHAR(50),

    -- Properties
    location_type VARCHAR(50), -- pallet, shelf, floor
    capacity_units DECIMAL(12, 2),
    capacity_weight_kg DECIMAL(12, 2),
    capacity_volume_cbm DECIMAL(12, 2),

    -- Current Usage
    occupied BOOLEAN DEFAULT false,
    current_item_id UUID REFERENCES items(id),

    -- Special Handling
    temperature_controlled BOOLEAN DEFAULT false,
    hazmat_approved BOOLEAN DEFAULT false,

    active BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, warehouse_id, location_code),
    INDEX idx_warehouse (warehouse_id),
    INDEX idx_zone (warehouse_id, zone)
);

-- Items (Products/SKUs)
CREATE TABLE items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Item Identification
    item_code VARCHAR(100) NOT NULL,
    item_name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Classification
    item_group VARCHAR(100),
    category VARCHAR(100),
    brand VARCHAR(100),

    -- Barcodes
    barcode VARCHAR(100),
    upc VARCHAR(50),
    ean VARCHAR(50),
    sku VARCHAR(100),

    -- Tracking
    has_batch_no BOOLEAN DEFAULT false,
    has_serial_no BOOLEAN DEFAULT false,
    has_expiry_date BOOLEAN DEFAULT false,

    -- Inventory Settings
    default_warehouse_id UUID REFERENCES warehouses(id),
    is_stock_item BOOLEAN DEFAULT true,
    valuation_method VARCHAR(50) DEFAULT 'fifo', -- fifo, lifo, moving_avg, standard

    -- Reorder Settings
    reorder_point DECIMAL(12, 2),
    reorder_qty DECIMAL(12, 2),
    min_order_qty DECIMAL(12, 2),
    max_order_qty DECIMAL(12, 2),
    safety_stock DECIMAL(12, 2),
    lead_time_days INTEGER,

    -- Unit of Measure
    stock_uom VARCHAR(50), -- EA, KG, LB, BOX
    purchase_uom VARCHAR(50),
    sales_uom VARCHAR(50),

    -- Dimensions
    weight_kg DECIMAL(10, 2),
    length_cm DECIMAL(10, 2),
    width_cm DECIMAL(10, 2),
    height_cm DECIMAL(10, 2),

    -- Costing
    standard_cost DECIMAL(15, 2),
    last_purchase_cost DECIMAL(15, 2),
    average_cost DECIMAL(15, 2),

    -- Status
    active BOOLEAN DEFAULT true,
    is_fixed_asset BOOLEAN DEFAULT false,

    -- ABC Classification
    abc_classification VARCHAR(1), -- A, B, C

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, item_code),
    INDEX idx_tenant (tenant_id),
    INDEX idx_barcode (barcode),
    INDEX idx_category (category)
);

-- Stock Ledger (All stock transactions)
CREATE TABLE stock_ledger_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Transaction Info
    posting_date DATE NOT NULL,
    posting_time TIME NOT NULL,

    -- Item & Warehouse
    item_id UUID REFERENCES items(id) NOT NULL,
    warehouse_id UUID REFERENCES warehouses(id) NOT NULL,
    location_id UUID REFERENCES storage_locations(id),

    -- Batch/Serial
    batch_no VARCHAR(100),
    serial_no VARCHAR(100),

    -- Quantity & Valuation
    actual_qty DECIMAL(15, 4) NOT NULL, -- Positive for IN, Negative for OUT
    qty_after_transaction DECIMAL(15, 4) NOT NULL,

    stock_value DECIMAL(15, 2),
    stock_value_difference DECIMAL(15, 2),
    valuation_rate DECIMAL(15, 4),

    -- Transaction Type
    voucher_type VARCHAR(50) NOT NULL, -- purchase_receipt, delivery_note, stock_entry, etc.
    voucher_no VARCHAR(100) NOT NULL,
    voucher_detail_no VARCHAR(100),

    -- Company & Project
    company_id UUID,
    project_id UUID REFERENCES projects(id),

    -- Cost Centers
    cost_center_id UUID REFERENCES cost_centers(id),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_item_warehouse (item_id, warehouse_id),
    INDEX idx_voucher (voucher_type, voucher_no),
    INDEX idx_posting_date (posting_date),
    INDEX idx_batch (batch_no),
    INDEX idx_serial (serial_no)
);

-- Current Stock Balance (Materialized View / Fast Query Table)
CREATE TABLE stock_balance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Item & Warehouse
    item_id UUID REFERENCES items(id) NOT NULL,
    warehouse_id UUID REFERENCES warehouses(id) NOT NULL,
    location_id UUID REFERENCES storage_locations(id),

    -- Batch/Serial
    batch_no VARCHAR(100),
    serial_no VARCHAR(100),

    -- Quantities
    qty_on_hand DECIMAL(15, 4) DEFAULT 0,
    qty_allocated DECIMAL(15, 4) DEFAULT 0, -- Reserved for sales orders
    qty_available DECIMAL(15, 4) DEFAULT 0, -- on_hand - allocated
    qty_on_order DECIMAL(15, 4) DEFAULT 0, -- On purchase orders
    qty_in_transit DECIMAL(15, 4) DEFAULT 0,
    qty_projected DECIMAL(15, 4) DEFAULT 0, -- on_hand + on_order - allocated

    -- Valuation
    stock_value DECIMAL(15, 2),
    valuation_rate DECIMAL(15, 4),

    last_updated TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, item_id, warehouse_id, location_id, batch_no, serial_no),
    INDEX idx_item (item_id),
    INDEX idx_warehouse (warehouse_id),
    INDEX idx_item_warehouse (item_id, warehouse_id)
);

-- Batch Numbers
CREATE TABLE batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    batch_no VARCHAR(100) NOT NULL,
    item_id UUID REFERENCES items(id) NOT NULL,

    -- Dates
    manufacturing_date DATE,
    expiry_date DATE,

    -- Supplier Info
    supplier_id UUID REFERENCES suppliers(id),
    supplier_batch_no VARCHAR(100),

    -- Quantity
    batch_qty DECIMAL(15, 4),
    qty_remaining DECIMAL(15, 4),

    -- Quality Control
    qc_status VARCHAR(50) DEFAULT 'pending', -- pending, passed, failed, in_progress
    qc_tested_on DATE,
    qc_tested_by UUID REFERENCES users(id),

    -- Status
    status VARCHAR(50) DEFAULT 'active', -- active, expired, recalled, exhausted

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, batch_no, item_id),
    INDEX idx_item (item_id),
    INDEX idx_expiry (expiry_date),
    INDEX idx_supplier (supplier_id)
);

-- Serial Numbers
CREATE TABLE serial_numbers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    serial_no VARCHAR(100) NOT NULL,
    item_id UUID REFERENCES items(id) NOT NULL,

    -- Current Location
    warehouse_id UUID REFERENCES warehouses(id),
    location_id UUID REFERENCES storage_locations(id),

    -- Status
    status VARCHAR(50) DEFAULT 'in_stock', -- in_stock, sold, in_service, scrapped

    -- Supplier/Manufacturer Info
    supplier_id UUID REFERENCES suppliers(id),
    manufacturer VARCHAR(255),
    model_no VARCHAR(100),

    -- Purchase Info
    purchase_document_no VARCHAR(100),
    purchase_date DATE,
    purchase_rate DECIMAL(15, 2),

    -- Sales Info
    sales_document_no VARCHAR(100),
    sales_date DATE,
    customer_id UUID REFERENCES customers(id),

    -- Warranty
    warranty_start_date DATE,
    warranty_end_date DATE,
    warranty_period_days INTEGER,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, serial_no),
    INDEX idx_item (item_id),
    INDEX idx_status (status),
    INDEX idx_warehouse (warehouse_id)
);

-- Stock Transfers
CREATE TABLE stock_transfers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Transfer Info
    transfer_no VARCHAR(100) NOT NULL,
    transfer_date DATE NOT NULL,

    -- From/To
    from_warehouse_id UUID REFERENCES warehouses(id) NOT NULL,
    to_warehouse_id UUID REFERENCES warehouses(id) NOT NULL,

    -- Purpose
    purpose VARCHAR(50), -- replenishment, relocation, customer_order

    -- Status
    status VARCHAR(50) DEFAULT 'draft', -- draft, in_transit, received, cancelled

    -- Shipping Info
    carrier VARCHAR(255),
    tracking_number VARCHAR(255),
    shipped_at TIMESTAMPTZ,
    expected_delivery_date DATE,
    received_at TIMESTAMPTZ,

    -- Approval
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,

    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, transfer_no),
    INDEX idx_from_warehouse (from_warehouse_id),
    INDEX idx_to_warehouse (to_warehouse_id),
    INDEX idx_status (status)
);

-- Stock Transfer Items
CREATE TABLE stock_transfer_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_transfer_id UUID REFERENCES stock_transfers(id) ON DELETE CASCADE,

    item_id UUID REFERENCES items(id) NOT NULL,

    -- Quantity
    qty DECIMAL(15, 4) NOT NULL,
    uom VARCHAR(50),

    -- Batch/Serial
    batch_no VARCHAR(100),
    serial_no VARCHAR(100),

    -- From/To Locations
    from_location_id UUID REFERENCES storage_locations(id),
    to_location_id UUID REFERENCES storage_locations(id),

    -- Costing
    valuation_rate DECIMAL(15, 4),
    amount DECIMAL(15, 2),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_transfer (stock_transfer_id),
    INDEX idx_item (item_id)
);

-- Stock Adjustments
CREATE TABLE stock_adjustments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Adjustment Info
    adjustment_no VARCHAR(100) NOT NULL,
    adjustment_date DATE NOT NULL,

    -- Warehouse
    warehouse_id UUID REFERENCES warehouses(id) NOT NULL,

    -- Reason
    adjustment_type VARCHAR(50), -- damaged, lost, found, cycle_count, other
    reason TEXT,

    -- Status
    status VARCHAR(50) DEFAULT 'draft', -- draft, submitted, approved, posted

    -- Approval
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,

    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, adjustment_no),
    INDEX idx_warehouse (warehouse_id),
    INDEX idx_date (adjustment_date)
);

-- Stock Adjustment Items
CREATE TABLE stock_adjustment_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_adjustment_id UUID REFERENCES stock_adjustments(id) ON DELETE CASCADE,

    item_id UUID REFERENCES items(id) NOT NULL,
    location_id UUID REFERENCES storage_locations(id),

    -- Batch/Serial
    batch_no VARCHAR(100),
    serial_no VARCHAR(100),

    -- Quantity
    current_qty DECIMAL(15, 4),
    adjusted_qty DECIMAL(15, 4),
    difference_qty DECIMAL(15, 4), -- adjusted - current

    -- Valuation
    valuation_rate DECIMAL(15, 4),
    amount DECIMAL(15, 2),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_adjustment (stock_adjustment_id),
    INDEX idx_item (item_id)
);

-- Cycle Counts
CREATE TABLE cycle_counts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Count Info
    count_no VARCHAR(100) NOT NULL,
    count_date DATE NOT NULL,

    -- Warehouse/Location
    warehouse_id UUID REFERENCES warehouses(id) NOT NULL,
    location_id UUID REFERENCES storage_locations(id),

    -- Count Scope
    count_type VARCHAR(50), -- full, abc, random, location, item_specific

    -- Assignment
    assigned_to UUID REFERENCES users(id),

    -- Status
    status VARCHAR(50) DEFAULT 'scheduled', -- scheduled, in_progress, completed, cancelled

    -- Results
    items_counted INTEGER,
    items_matched INTEGER,
    items_variance INTEGER,
    accuracy_percentage DECIMAL(5, 2),

    completed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, count_no),
    INDEX idx_warehouse (warehouse_id),
    INDEX idx_status (status)
);

-- Cycle Count Items
CREATE TABLE cycle_count_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cycle_count_id UUID REFERENCES cycle_counts(id) ON DELETE CASCADE,

    item_id UUID REFERENCES items(id) NOT NULL,
    location_id UUID REFERENCES storage_locations(id),

    -- Batch/Serial
    batch_no VARCHAR(100),
    serial_no VARCHAR(100),

    -- Expected vs. Actual
    system_qty DECIMAL(15, 4),
    counted_qty DECIMAL(15, 4),
    variance_qty DECIMAL(15, 4), -- counted - system

    -- Status
    match_status VARCHAR(50), -- match, variance, missing, extra

    -- Adjustment
    adjustment_created BOOLEAN DEFAULT false,
    stock_adjustment_id UUID REFERENCES stock_adjustments(id),

    counted_by UUID REFERENCES users(id),
    counted_at TIMESTAMPTZ,

    INDEX idx_cycle_count (cycle_count_id),
    INDEX idx_item (item_id)
);

-- Kitting/Bundle BOMs
CREATE TABLE item_boms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Parent Item (Kit)
    item_id UUID REFERENCES items(id) NOT NULL,

    bom_name VARCHAR(255),
    is_active BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_item (item_id)
);

-- BOM Items (Components)
CREATE TABLE item_bom_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_bom_id UUID REFERENCES item_boms(id) ON DELETE CASCADE,

    -- Component Item
    component_item_id UUID REFERENCES items(id) NOT NULL,

    qty DECIMAL(15, 4) NOT NULL,
    uom VARCHAR(50),

    INDEX idx_bom (item_bom_id),
    INDEX idx_component (component_item_id)
);

-- Quality Inspections
CREATE TABLE quality_inspections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    -- Inspection Info
    inspection_no VARCHAR(100) NOT NULL,
    inspection_date DATE NOT NULL,

    -- Inspection Type
    inspection_type VARCHAR(50), -- inbound, outbound, in_process

    -- Reference Document
    reference_type VARCHAR(50), -- purchase_receipt, delivery_note, work_order
    reference_no VARCHAR(100),

    -- Item & Batch
    item_id UUID REFERENCES items(id) NOT NULL,
    batch_no VARCHAR(100),

    -- Quantity
    sample_size DECIMAL(15, 4),
    inspected_qty DECIMAL(15, 4),

    -- Result
    status VARCHAR(50) DEFAULT 'pending', -- pending, in_progress, passed, failed, partial

    inspector_id UUID REFERENCES users(id),
    inspected_at TIMESTAMPTZ,

    -- Remarks
    remarks TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, inspection_no),
    INDEX idx_item (item_id),
    INDEX idx_reference (reference_type, reference_no)
);

-- Reorder Recommendations (AI-generated)
CREATE TABLE reorder_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),

    item_id UUID REFERENCES items(id) NOT NULL,
    warehouse_id UUID REFERENCES warehouses(id) NOT NULL,

    -- Current State
    current_stock DECIMAL(15, 4),
    allocated_stock DECIMAL(15, 4),
    available_stock DECIMAL(15, 4),
    on_order DECIMAL(15, 4),

    -- Forecast
    forecasted_demand_30d DECIMAL(15, 4),
    forecasted_demand_60d DECIMAL(15, 4),
    forecasted_demand_90d DECIMAL(15, 4),

    -- Recommendation
    recommended_order_qty DECIMAL(15, 4),
    recommended_order_date DATE,

    -- Reasoning
    reason TEXT, -- e.g., "Stock will run out in 12 days based on forecast"
    urgency VARCHAR(50), -- low, medium, high, critical

    -- AI Confidence
    confidence_score DECIMAL(5, 2), -- 0-100

    -- Status
    status VARCHAR(50) DEFAULT 'pending', -- pending, po_created, dismissed

    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,

    INDEX idx_item_warehouse (item_id, warehouse_id),
    INDEX idx_urgency (urgency),
    INDEX idx_status (status)
);
```

---

## API Specification

### Stock Management APIs

```python
# Get Stock Balance
GET /api/v1/inventory/stock-balance
Query Params: ?item_id=uuid&warehouse_id=uuid
Response: {
    "item_id": "uuid",
    "warehouse_id": "uuid",
    "qty_on_hand": 500.00,
    "qty_allocated": 150.00,
    "qty_available": 350.00,
    "qty_on_order": 200.00,
    "qty_projected": 550.00,
    "stock_value": 25000.00
}

# Get Stock Ledger
GET /api/v1/inventory/stock-ledger
Query Params: ?item_id=uuid&from_date=2025-11-01&to_date=2025-11-30
Response: {
    "entries": [
        {
            "posting_date": "2025-11-10",
            "voucher_type": "purchase_receipt",
            "voucher_no": "PR-001",
            "actual_qty": 100.00,
            "qty_after_transaction": 500.00,
            "valuation_rate": 50.00,
            "stock_value_difference": 5000.00
        }
    ]
}

# Create Stock Entry (Manual Adjustment)
POST /api/v1/inventory/stock-entries
Request: {
    "entry_type": "material_receipt",
    "warehouse_id": "uuid",
    "posting_date": "2025-11-10",
    "items": [
        {
            "item_id": "uuid",
            "qty": 100.00,
            "location_id": "uuid",
            "batch_no": "BATCH-001",
            "valuation_rate": 50.00
        }
    ]
}
```

### Warehouse Operations APIs

```python
# Create Pick List
POST /api/v1/inventory/pick-lists
Request: {
    "warehouse_id": "uuid",
    "picking_strategy": "zone", # zone, batch, wave
    "sales_orders": ["uuid1", "uuid2"]
}
Response: {
    "pick_list_id": "uuid",
    "tasks": [
        {
            "item_id": "uuid",
            "item_name": "Laptop",
            "qty": 5,
            "from_location": "A-1-3-B2",
            "batch_no": "BATCH-001",
            "serial_nos": ["SN001", "SN002", "SN003", "SN004", "SN005"]
        }
    ]
}

# Complete Pick Task
POST /api/v1/inventory/pick-lists/{id}/complete
Request: {
    "tasks": [
        {
            "task_id": "uuid",
            "qty_picked": 5,
            "scanned_serials": ["SN001", "SN002", "SN003", "SN004", "SN005"]
        }
    ]
}

# Create Put-Away Task
POST /api/v1/inventory/put-away-tasks
Request: {
    "goods_receipt_id": "uuid",
    "items": [
        {
            "item_id": "uuid",
            "qty": 100,
            "suggested_location_id": "uuid"
        }
    ]
}
```

### Stock Transfer APIs

```python
# Create Stock Transfer
POST /api/v1/inventory/stock-transfers
Request: {
    "from_warehouse_id": "uuid",
    "to_warehouse_id": "uuid",
    "transfer_date": "2025-11-10",
    "items": [
        {
            "item_id": "uuid",
            "qty": 50,
            "batch_no": "BATCH-001"
        }
    ]
}

# Ship Transfer
POST /api/v1/inventory/stock-transfers/{id}/ship
Request: {
    "carrier": "FedEx",
    "tracking_number": "1234567890",
    "expected_delivery_date": "2025-11-15"
}

# Receive Transfer
POST /api/v1/inventory/stock-transfers/{id}/receive
Request: {
    "items": [
        {
            "item_id": "uuid",
            "qty_received": 50,
            "to_location_id": "uuid"
        }
    ]
}
```

### Batch & Serial APIs

```python
# Create Batch
POST /api/v1/inventory/batches
Request: {
    "batch_no": "BATCH-20251110-001",
    "item_id": "uuid",
    "manufacturing_date": "2025-11-01",
    "expiry_date": "2026-11-01",
    "supplier_id": "uuid",
    "batch_qty": 1000
}

# Get Batches Expiring Soon
GET /api/v1/inventory/batches/expiring
Query Params: ?days=30
Response: {
    "batches": [
        {
            "batch_no": "BATCH-001",
            "item_name": "Milk",
            "expiry_date": "2025-12-01",
            "days_to_expiry": 21,
            "qty_remaining": 50,
            "warehouse": "Store #1"
        }
    ]
}

# Serial Number Trace
GET /api/v1/inventory/serial-numbers/{serial_no}/trace
Response: {
    "serial_no": "SN123456",
    "item_name": "Laptop XYZ",
    "current_status": "sold",
    "current_location": "Customer ABC",
    "history": [
        {
            "date": "2025-10-01",
            "event": "Purchased",
            "supplier": "Tech Supplier Inc"
        },
        {
            "date": "2025-10-05",
            "event": "Received",
            "warehouse": "DC-01",
            "location": "A-1-3-B2"
        },
        {
            "date": "2025-11-01",
            "event": "Sold",
            "customer": "ABC Corp",
            "invoice": "INV-2025-1234"
        }
    ]
}
```

### Cycle Count APIs

```python
# Create Cycle Count
POST /api/v1/inventory/cycle-counts
Request: {
    "warehouse_id": "uuid",
    "count_type": "abc",
    "count_date": "2025-11-10",
    "assigned_to": "uuid"
}

# Submit Count
POST /api/v1/inventory/cycle-counts/{id}/submit-count
Request: {
    "items": [
        {
            "item_id": "uuid",
            "location_id": "uuid",
            "batch_no": "BATCH-001",
            "counted_qty": 95
        }
    ]
}

# Create Adjustment from Variance
POST /api/v1/inventory/cycle-counts/{id}/create-adjustment
```

### AI & Analytics APIs

```python
# Get Demand Forecast
GET /api/v1/inventory/ai/demand-forecast/{item_id}
Query Params: ?warehouse_id=uuid&days=90
Response: {
    "item_id": "uuid",
    "warehouse_id": "uuid",
    "forecast_period": "90 days",
    "forecast": [
        {
            "date": "2025-11-11",
            "predicted_demand": 15.2,
            "confidence_interval": {
                "lower": 12.0,
                "upper": 18.5
            }
        }
    ],
    "total_forecasted_demand": 1350,
    "model_accuracy_mape": 8.5,
    "recommended_order_qty": 200
}

# Get Reorder Recommendations
GET /api/v1/inventory/ai/reorder-recommendations
Query Params: ?urgency=high&warehouse_id=uuid
Response: {
    "recommendations": [
        {
            "id": "uuid",
            "item_name": "Widget A",
            "warehouse": "DC-01",
            "current_stock": 50,
            "forecasted_demand_30d": 200,
            "recommended_order_qty": 250,
            "urgency": "high",
            "reason": "Stock will run out in 7 days",
            "confidence": 92.5
        }
    ]
}

# ABC Analysis
GET /api/v1/inventory/analytics/abc-analysis
Response: {
    "category_a": {
        "item_count": 200,
        "percentage_items": 20,
        "total_value": 800000,
        "percentage_value": 80
    },
    "category_b": {
        "item_count": 300,
        "percentage_items": 30,
        "total_value": 150000,
        "percentage_value": 15
    },
    "category_c": {
        "item_count": 500,
        "percentage_items": 50,
        "total_value": 50000,
        "percentage_value": 5
    }
}

# Inventory Turnover Report
GET /api/v1/inventory/analytics/turnover
Query Params: ?from_date=2025-01-01&to_date=2025-11-10
Response: {
    "items": [
        {
            "item_name": "Laptop A",
            "cogs": 800000,
            "average_inventory": 100000,
            "turnover_ratio": 8.0,
            "days_inventory": 45.6,
            "classification": "fast_moving"
        }
    ]
}
```

### Reports APIs

```python
# Stock Summary Report
GET /api/v1/inventory/reports/stock-summary
Query Params: ?warehouse_id=uuid&category=Electronics

# Aging Report
GET /api/v1/inventory/reports/aging
Response: {
    "items": [
        {
            "item_name": "Old Model Phone",
            "qty": 50,
            "age_days": 365,
            "value": 15000,
            "aging_bucket": "over_360_days"
        }
    ]
}

# Stock Valuation
GET /api/v1/inventory/reports/valuation
Query Params: ?as_of=2025-11-10
Response: {
    "total_value": 1250000.00,
    "by_warehouse": [...],
    "by_category": [...]
}
```

---

## Security Considerations

### Access Controls

```python
inventory_permissions = {
    "inventory.items.view": "View items",
    "inventory.items.create": "Create items",
    "inventory.items.edit": "Edit items",

    "inventory.stock.view": "View stock levels",
    "inventory.stock.transfer": "Create stock transfers",
    "inventory.stock.adjust": "Create stock adjustments",

    "inventory.warehouse.view": "View warehouses",
    "inventory.warehouse.manage": "Manage warehouse settings",

    "inventory.picking.view": "View pick lists",
    "inventory.picking.execute": "Execute picking tasks",

    "inventory.cycle_count.view": "View cycle counts",
    "inventory.cycle_count.perform": "Perform cycle counts",
    "inventory.cycle_count.approve": "Approve adjustments from cycle counts",

    "inventory.reports.view": "View inventory reports",
    "inventory.reports.export": "Export reports",

    "inventory.batch_serial.view": "View batch/serial tracking",
    "inventory.batch_serial.trace": "Perform trace operations"
}
```

### Audit Trail

```python
audit_events = {
    "stock_entry_created": "Who, when, transaction details",
    "stock_adjusted": "Who adjusted, reason, before/after qty",
    "cycle_count_performed": "Counter, variances, adjustments",
    "batch_created": "Batch details, created by",
    "serial_sold": "Serial number, customer, invoice",
    "item_modified": "Field changes, modified by",
    "transfer_shipped": "Transfer details, shipped by",
    "transfer_received": "Received by, received qty"
}
```

### Physical Security Integration

```python
security_features = {
    "restricted_areas": "Access control for high-value zones",
    "video_surveillance": "CCTV integration for warehouse areas",
    "access_logging": "Log all bin access events",
    "shrinkage_alerts": "Alert on unusual stock variances",
    "dual_custody": "Require two people for high-value transactions"
}
```

---

## Implementation Roadmap

### Phase 1: Core Inventory (Month 1-2)
- [ ] Item master data management
- [ ] Warehouses and storage locations
- [ ] Stock ledger and balance tracking
- [ ] Basic stock transactions (receipt, issue, transfer)
- [ ] Stock valuation (FIFO, moving average)

### Phase 2: Warehouse Operations (Month 3)
- [ ] Goods receipt and put-away
- [ ] Pick list generation
- [ ] Packing and shipping
- [ ] Barcode scanning mobile app
- [ ] Bin location tracking

### Phase 3: Batch & Serial Tracking (Month 4)
- [ ] Batch number management
- [ ] Serial number tracking
- [ ] FEFO picking for batches
- [ ] Expiry date tracking
- [ ] Forward/backward traceability

### Phase 4: Replenishment & Planning (Month 5)
- [ ] Reorder point automation
- [ ] AI demand forecasting
- [ ] Auto PO generation
- [ ] Safety stock calculation
- [ ] ABC classification

### Phase 5: Advanced Features (Month 6)
- [ ] Cycle counting
- [ ] Quality inspections
- [ ] Kitting and bundling
- [ ] Multi-UOM conversions
- [ ] Landed cost allocation

### Phase 6: AI & Optimization (Month 7)
- [ ] AI warehouse optimization (slotting)
- [ ] Predictive stockout alerts
- [ ] Automated replenishment
- [ ] RFID integration
- [ ] Advanced analytics dashboards

---

## Competitive Analysis

| Feature | SARAISE | SAP EWM | Oracle NetSuite WMS | Microsoft D365 SCM | Odoo Inventory |
|---------|---------|---------|---------------------|-------------------|----------------|
| **Multi-Warehouse** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Batch Tracking** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Serial Tracking** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Bin Location** | ✓ | ✓ | ✓ | ✓ | ✓ Limited |
| **AI Demand Forecast** | ✓ ML-powered | ✓ | ✓ Add-on | ✓ Copilot | ✗ |
| **Auto Replenishment** | ✓ AI-driven | ✓ | ✓ | ✓ | ✓ Basic |
| **Mobile WMS** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **RFID Support** | ✓ | ✓ | ✓ | ✓ | ✗ |
| **Cycle Counting** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Wave Picking** | ✓ | ✓ | ✓ | ✓ | ✗ |
| **Quality Management** | ✓ | ✓ | ✓ Add-on | ✓ | ✓ Basic |
| **Real-time Visibility** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Pricing** | $$ | $$$$ | $$$ | $$$ | $ |

**Verdict**: Matches SAP/Oracle/Microsoft on core WMS features with superior AI forecasting at significantly lower cost.

---

## Success Metrics

- **Inventory Accuracy**: > 98% (cycle count accuracy)
- **Stockout Rate**: < 2% (items out of stock when ordered)
- **Inventory Turnover**: Improve by 25% (faster inventory movement)
- **Carrying Cost**: Reduce by 15% (lower holding costs)
- **Order Fulfillment Time**: < 24 hours (from order to ship)
- **Pick Accuracy**: > 99.5% (correct items picked)
- **Forecast Accuracy**: MAPE < 10% (demand forecast accuracy)
- **Warehouse Space Utilization**: > 85% (effective space usage)
- **Cycle Count Frequency**: 100% of items counted annually
- **Days Inventory Outstanding**: Reduce by 20%
- **ROI**: 4x return in year 1 (reduced stockouts + lower carrying costs)

---

**Document Control**:
- **Author**: SARAISE Architecture Team
- **Last Updated**: 2025-11-10
- **Status**: Planning - Ready for Implementation
