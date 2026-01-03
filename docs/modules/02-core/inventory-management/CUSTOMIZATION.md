# Inventory Management Module - Customization Guide

**Module**: `inventory`
**Category**: Core Business
**Version**: 1.0.0

---

## Overview

This guide documents all customization points available in the Inventory Management module. Use these customization capabilities to extend inventory management, customize stock movements, automate reorder points, and integrate with external inventory systems.

---

## Customization Points

### 1. Item Model

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_delete`, `after_delete`

**Use Cases**:
- Auto-generate item codes
- Validate item data
- Calculate item costs
- Sync items to external systems

**Example Server Script**:
```python
# Auto-generate item code
def before_insert(doc, method):
    """Generate item code if not provided"""
    if not doc.item_code:
        # Generate: ITM-XXX
        last_item = frappe.db.get_value(
            "Item",
            {"item_code": ["like", "ITM-%"]},
            "item_code",
            order_by="item_code desc"
        )
        seq = int(last_item.split("-")[-1]) + 1 if last_item else 1
        doc.item_code = f"ITM-{seq:05d}"
```

### 2. Stock Entry Resource

**Available Events**: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_submit`, `after_submit`

**Use Cases**:
- Validate stock availability
- Update stock balances
- Calculate stock valuation
- Trigger reorder alerts

### 3. Stock Balance Resource

**Available Events**: `before_update`, `after_update`

**Use Cases**:
- Validate stock levels
- Trigger low stock alerts
- Calculate reorder points

---

## Custom API Endpoints

### Example: Stock Reorder Calculator

```python
# API Script: Calculate reorder points
# Endpoint: POST /api/v1/customization/custom-endpoints/inventory_reorder_calc

@frappe.whitelist(allow_guest=False)
def calculate_reorder_points(item_ids=None):
    """Calculate reorder points for items"""
    # Implementation for reorder point calculation
    return {"reorder_points": {...}}
```

---

## Webhooks

### Available Events

| Event Type | Description |
|------------|-------------|
| `inventory.item.created` | Item created |
| `inventory.stock_entry.created` | Stock entry created |
| `inventory.stock_low` | Stock level below threshold |
| `inventory.stock_received` | Stock received |

---

## AI-Powered Code Generation

Ask Amani can generate customizations:
- "Create a script that auto-calculates reorder points"
- "Generate a webhook that syncs inventory to Shopify"
- "Create an API endpoint to generate stock reports"

---

## Best Practices

1. **Accuracy**: Ensure stock levels are accurate
2. **Real-time Updates**: Update stock balances in real-time
3. **Validation**: Validate stock movements before processing
4. **Audit Trail**: Maintain audit logs for stock transactions
5. **Performance**: Optimize stock queries for large inventories
