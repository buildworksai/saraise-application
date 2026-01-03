# Technical Specifications - Purchase Management

**Module ID:** `purchase`
**Version:** 1.0.0
**Last Updated:** 2025-12-11

## Database Schema

### Core Tables

#### `purchase_orders`
```sql
CREATE TABLE purchase_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    po_number VARCHAR(50) NOT NULL,
    supplier_id UUID NOT NULL REFERENCES suppliers(id),
    order_date DATE NOT NULL,
    expected_delivery_date DATE,
    status VARCHAR(20) DEFAULT 'draft', -- 'draft', 'submitted', 'approved', 'received', 'cancelled'
    total_amount DECIMAL(15,2),
    currency VARCHAR(3) DEFAULT 'USD',
    payment_terms VARCHAR(50),
    shipping_address JSONB,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMP,
    INDEX idx_po_tenant (tenant_id),
    INDEX idx_po_number (tenant_id, po_number),
    INDEX idx_po_supplier (supplier_id),
    INDEX idx_po_status (status),
    UNIQUE (tenant_id, po_number)
);
```

#### `purchase_order_items`
```sql
CREATE TABLE purchase_order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    po_id UUID NOT NULL REFERENCES purchase_orders(id),
    product_id UUID REFERENCES products(id),
    description VARCHAR(200),
    quantity DECIMAL(15,4) NOT NULL,
    unit_price DECIMAL(15,2) NOT NULL,
    tax_amount DECIMAL(15,2) DEFAULT 0,
    total_amount DECIMAL(15,2) NOT NULL,
    received_quantity DECIMAL(15,4) DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_po_item_tenant (tenant_id),
    INDEX idx_po_item_po (po_id),
    INDEX idx_po_item_product (product_id)
);
```

## API Architecture

### REST Endpoints
- `POST /api/v1/purchase/orders` - Create purchase order
- `GET /api/v1/purchase/orders` - List purchase orders
- `PUT /api/v1/purchase/orders/{id}` - Update purchase order
- `POST /api/v1/purchase/orders/{id}/approve` - Approve PO
- `POST /api/v1/purchase/orders/{id}/receive` - Receive goods

### GraphQL Schema
```graphql
type PurchaseOrder {
  id: ID!
  poNumber: String!
  supplier: Supplier!
  orderDate: Date!
  status: POStatus!
  totalAmount: Decimal!
  items: [PurchaseOrderItem!]!
}

type PurchaseOrderItem {
  id: ID!
  product: Product
  quantity: Decimal!
  unitPrice: Decimal!
  totalAmount: Decimal!
  receivedQuantity: Decimal!
}
```

## Data Models
- **PO Lifecycle**: Draft → Approval → Submission → Receipt → Payment
- **Three-Way Matching**: PO vs Receipt vs Invoice
- **Approval Workflows**: Multi-level approval based on amount
- **Supplier Performance**: Track on-time delivery, quality

## Integration Points
- **Inventory**: Update stock on goods receipt
- **Accounting**: Create AP entries on invoice receipt
- **Supplier Portal**: Suppliers can view and acknowledge POs

## Performance Targets
- PO creation: <200ms (P95)
- PO approval: <100ms (P95)
- Goods receipt: <500ms (P95)

## Security
- **RBAC**: `purchase.po.create`, `purchase.po.approve`
- **SoD**: Separate roles for PO creation and approval
- **RLP**: Row-level filtering by tenant_id

---
**Related Documentation:** [API](./API.md) | [User Guide](./USER-GUIDE.md) | [Agent Config](./AGENT-CONFIGURATION.md)
