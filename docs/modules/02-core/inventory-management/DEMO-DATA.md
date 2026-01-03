# Inventory Management Module - Demo Data

## Overview

This document describes the demo data structure for the Inventory Management module. Demo data provides realistic examples of items, categories, warehouses, stock entries, and stock balances.

## Demo Data Structure

### Item Categories

**Count:** 5-10 demo categories

**Sample Data:**
- Electronics
- Office Supplies
- Raw Materials
- Finished Goods
- Consumables

### Items

**Count:** 30-50 demo items

**Sample Data:**
- Various products with different types
- Items with variants (size, color, etc.)
- Items with attributes
- Different pricing tiers

**Fields:**
- Item name, code, SKU
- Category, type
- Description, images
- Pricing information
- Stock settings

### Warehouses

**Count:** 3-5 demo warehouses

**Sample Data:**
- Main Warehouse (HQ)
- Regional Warehouse (North)
- Regional Warehouse (South)
- Distribution Center

**Fields:**
- Warehouse name, code
- Address, manager
- Storage locations
- Is active

### Stock Entries

**Count:** 20-30 demo stock entries

**Sample Data:**
- Receipts (purchases)
- Deliveries (sales)
- Transfers (warehouse to warehouse)
- Adjustments (inventory corrections)

**Fields:**
- Entry type, date
- Warehouse, reference
- Stock entry lines (items, quantities)
- Status

### Stock Balances

**Count:** 50-100 demo stock balances

**Sample Data:**
- Current stock levels per item per warehouse
- Various quantities (some low stock, some high)
- Different valuation methods

**Fields:**
- Item, warehouse
- Quantity, reserved quantity
- Valuation, cost
- Last updated

### Batches & Serial Numbers

**Count:** 10-20 demo batches

**Sample Data:**
- Batch-tracked items
- Serial number tracked items
- Expiry dates for perishables

## Relationships

- Items → Categories
- Items → Stock Entries (movements)
- Items → Stock Balances (current levels)
- Warehouses → Stock Entries
- Warehouses → Stock Balances
- Items → Batches/Serial Numbers

## Data Seeding Script

The demo data seeding script should:

1. Create Item Categories
2. Create Items (with variants and attributes)
3. Create Warehouses
4. Create Stock Entries (receipts, deliveries, transfers)
5. Create Stock Balances (current levels)
6. Create Batches and Serial Numbers (if applicable)

## Integration

Add to `seed_demo_tenant.py`:
```python
from backend.scripts.seed_inventory_demo_data import seed_inventory_demo_data

async def seed_demo_tenant():
    # ... existing code ...
    await seed_inventory_demo_data(session, tenant.id, demo_user.id)
```
