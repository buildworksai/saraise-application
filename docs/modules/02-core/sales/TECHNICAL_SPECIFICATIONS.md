# Technical Specifications - Sales Management

**Module ID:** `sales`
**Version:** 1.0.0
**Last Updated:** 2025-12-11

## Database Schema

### Core Tables

#### `sales_orders`
```sql
CREATE TABLE sales_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    so_number VARCHAR(50) NOT NULL,
    customer_id UUID NOT NULL REFERENCES customers(id),
    order_date DATE NOT NULL,
    delivery_date DATE,
    status VARCHAR(20) DEFAULT 'draft', -- 'draft', 'confirmed', 'shipped', 'delivered', 'cancelled'
    total_amount DECIMAL(15,2),
    currency VARCHAR(3) DEFAULT 'USD',
    payment_terms VARCHAR(50),
    shipping_address JSONB,
    billing_address JSONB,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    INDEX idx_so_tenant (tenant_id),
    INDEX idx_so_number (tenant_id, so_number),
    INDEX idx_so_customer (customer_id),
    INDEX idx_so_status (status),
    UNIQUE (tenant_id, so_number)
);
```

#### `sales_order_items`
```sql
CREATE TABLE sales_order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    so_id UUID NOT NULL REFERENCES sales_orders(id),
    product_id UUID REFERENCES products(id),
    description VARCHAR(200),
    quantity DECIMAL(15,4) NOT NULL,
    unit_price DECIMAL(15,2) NOT NULL,
    discount_percent DECIMAL(5,2) DEFAULT 0,
    tax_amount DECIMAL(15,2) DEFAULT 0,
    total_amount DECIMAL(15,2) NOT NULL,
    shipped_quantity DECIMAL(15,4) DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_so_item_tenant (tenant_id),
    INDEX idx_so_item_so (so_id),
    INDEX idx_so_item_product (product_id)
);
```

## API Architecture

### REST Endpoints
- `POST /api/v1/sales/orders` - Create sales order
- `GET /api/v1/sales/orders` - List sales orders
- `PUT /api/v1/sales/orders/{id}` - Update sales order
- `POST /api/v1/sales/orders/{id}/confirm` - Confirm order
- `POST /api/v1/sales/orders/{id}/ship` - Ship order
- `GET /api/v1/sales/analytics/revenue` - Revenue analytics

### GraphQL Schema
```graphql
type SalesOrder {
  id: ID!
  soNumber: String!
  customer: Customer!
  orderDate: Date!
  status: SOStatus!
  totalAmount: Decimal!
  items: [SalesOrderItem!]!
}

type SalesOrderItem {
  id: ID!
  product: Product
  quantity: Decimal!
  unitPrice: Decimal!
  discountPercent: Decimal
  totalAmount: Decimal!
  shippedQuantity: Decimal!
}
```

## Data Models
- **Sales Cycle**: Quote → Order → Fulfillment → Invoice → Payment
- **Inventory Reservation**: Reserve stock on order confirmation
- **Pricing**: Customer-specific pricing, volume discounts, promotions
- **Sales Analytics**: Revenue trends, top customers, product performance

## Integration Points
- **CRM**: Customer data and opportunities
- **Inventory**: Stock availability and reservation
- **Accounting**: Revenue recognition and AR
- **Shipping**: Integration with carriers

## Performance Targets
- Order creation: <200ms (P95)
- Order confirmation: <300ms (P95)
- Revenue analytics: <1 second (P95)

## Security
- **RBAC**: `sales.order.create`, `sales.order.approve`, `sales.analytics.view`
- **ABAC**: Territory-based access (sales reps can only see their territory)
- **RLP**: Row-level filtering by tenant_id and sales_rep_id

---
**Related Documentation:** [API](./API.md) | [User Guide](./USER-GUIDE.md) | [Agent Config](./AGENT-CONFIGURATION.md)
