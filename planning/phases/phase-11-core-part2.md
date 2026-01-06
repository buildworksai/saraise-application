# Phase 11: Core Modules Part 2 — Operations

**Duration:** 5 weeks (Weeks 21-25)  
**Modules:** Sales Management, Purchase Management, Inventory Management  
**Status:** ⏸️ BLOCKED (Awaiting Phase 10)  
**Prerequisites:** Phase 10 complete (CRM, Accounting operational)

---

## Phase Objectives

Implement core operational modules that handle the sales-to-cash and procure-to-pay cycles.

### Success Criteria
- [ ] 3 modules operational (backend + frontend + tests)
- [ ] ≥90% test coverage per module
- [ ] GL integration verified for all transactions
- [ ] Inventory valuation accurate

---

## Week 21-22: Sales Management Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `sales_management` |
| Type | Core |
| Priority | P1 |
| Dependencies | CRM, Accounting, Inventory |
| Spec Location | `docs/modules/02-core/sales-management/` |
| Timeline | 7-10 days |

### Key Entities

```python
# Sales entities
- SalesOrder (customer_id, order_number, date, status, total, tenant_id)
- SalesOrderLine (order_id, product_id, quantity, unit_price, discount)
- Quotation (customer_id, quote_number, valid_until, status, tenant_id)
- QuotationLine (quotation_id, product_id, quantity, unit_price)
- DeliveryNote (order_id, delivery_number, date, status, tenant_id)
- DeliveryNoteLine (delivery_id, product_id, quantity_delivered)
```

### Key Implementation: Order-to-Cash Flow

```python
# backend/src/modules/sales_management/services.py

class SalesOrderService:
    """Order-to-cash business logic."""

    def confirm_order(
        self,
        order_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> SalesOrder:
        """
        Confirm sales order:
        1. Reserve inventory
        2. Update order status
        3. Trigger workflow
        """

        order = SalesOrder.objects.get(
            id=order_id,
            tenant_id=tenant_id
        )

        if order.status != 'draft':
            raise ValidationError(f"Cannot confirm order with status: {order.status}")

        with transaction.atomic():
            # Reserve inventory for each line
            for line in order.lines.all():
                InventoryService().reserve_stock(
                    product_id=line.product_id,
                    quantity=line.quantity,
                    tenant_id=tenant_id,
                    reference_type='sales_order',
                    reference_id=order.id
                )

            order.status = 'confirmed'
            order.confirmed_at = timezone.now()
            order.confirmed_by = user_id
            order.save()

        # Trigger workflow
        WorkflowEngine().trigger_event(
            event_type='sales.order.confirmed',
            tenant_id=tenant_id,
            payload={'order_id': str(order.id)}
        )

        return order

    def create_invoice_from_order(
        self,
        order_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> Invoice:
        """Create invoice from confirmed sales order."""

        order = SalesOrder.objects.get(
            id=order_id,
            tenant_id=tenant_id
        )

        if order.status not in ['confirmed', 'delivered']:
            raise ValidationError("Order must be confirmed or delivered")

        # Create invoice
        invoice = Invoice.objects.create(
            tenant_id=tenant_id,
            customer_id=order.customer_id,
            invoice_number=self._generate_invoice_number(tenant_id),
            date=timezone.now().date(),
            due_date=self._calculate_due_date(order.customer),
            sales_order=order,
            created_by=user_id
        )

        # Copy lines
        for order_line in order.lines.all():
            InvoiceLine.objects.create(
                invoice=invoice,
                description=order_line.product.name,
                quantity=order_line.quantity,
                unit_price=order_line.unit_price,
                tax_rate=order_line.tax_rate
            )

        # Link back to order
        order.invoice = invoice
        order.status = 'invoiced'
        order.save()

        return invoice
```

---

## Week 22-24: Purchase Management Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `purchase_management` |
| Type | Core |
| Priority | P1 |
| Dependencies | Accounting, Inventory |
| Spec Location | `docs/modules/02-core/purchase-management/` |
| Timeline | 7-10 days |

### Key Entities

```python
# Purchase entities
- PurchaseRequisition (requester_id, date, status, tenant_id)
- PurchaseRequisitionLine (requisition_id, product_id, quantity, required_date)
- RequestForQuote (requisition_id, vendor_ids, deadline, tenant_id)
- VendorQuote (rfq_id, vendor_id, total, valid_until)
- PurchaseOrder (vendor_id, order_number, date, status, tenant_id)
- PurchaseOrderLine (order_id, product_id, quantity, unit_price)
- GoodsReceipt (order_id, receipt_number, date, tenant_id)
- GoodsReceiptLine (receipt_id, product_id, quantity_received, quality_status)
```

### Key Implementation: Procure-to-Pay Flow

```python
# backend/src/modules/purchase_management/services.py

class PurchaseOrderService:
    """Procure-to-pay business logic."""

    def receive_goods(
        self,
        order_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        receipt_lines: list[dict]
    ) -> GoodsReceipt:
        """
        Receive goods against purchase order:
        1. Create goods receipt
        2. Update inventory
        3. Post to GL (inventory asset)
        """

        order = PurchaseOrder.objects.get(
            id=order_id,
            tenant_id=tenant_id
        )

        if order.status not in ['confirmed', 'partial']:
            raise ValidationError(f"Cannot receive against order with status: {order.status}")

        with transaction.atomic():
            receipt = GoodsReceipt.objects.create(
                tenant_id=tenant_id,
                purchase_order=order,
                receipt_number=self._generate_receipt_number(tenant_id),
                date=timezone.now().date(),
                created_by=user_id
            )

            for line_data in receipt_lines:
                order_line = PurchaseOrderLine.objects.get(
                    id=line_data['order_line_id'],
                    order__tenant_id=tenant_id  # TENANT ISOLATION
                )

                GoodsReceiptLine.objects.create(
                    receipt=receipt,
                    order_line=order_line,
                    product_id=order_line.product_id,
                    quantity_received=line_data['quantity'],
                    quality_status=line_data.get('quality_status', 'accepted')
                )

                # Update inventory
                if line_data.get('quality_status', 'accepted') == 'accepted':
                    InventoryService().add_stock(
                        product_id=order_line.product_id,
                        quantity=line_data['quantity'],
                        tenant_id=tenant_id,
                        unit_cost=order_line.unit_price,
                        reference_type='goods_receipt',
                        reference_id=receipt.id
                    )

            # Update order status
            self._update_order_status(order)

            # Post to GL
            self._post_goods_receipt_to_gl(receipt, tenant_id, user_id)

        return receipt

    def _post_goods_receipt_to_gl(
        self,
        receipt: GoodsReceipt,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID
    ):
        """
        Post goods receipt to GL.

        Journal Entry:
        - Debit: Inventory Asset
        - Credit: Goods Received Not Invoiced (GRNI)
        """

        inventory_account = self._get_account(tenant_id, 'inventory')
        grni_account = self._get_account(tenant_id, 'grni')

        total = sum(
            line.quantity_received * line.order_line.unit_price
            for line in receipt.lines.all()
        )

        JournalEntryService().create_journal_entry(
            tenant_id=tenant_id,
            user_id=user_id,
            date=receipt.date,
            description=f"Goods Receipt {receipt.receipt_number}",
            lines=[
                {'account_id': inventory_account.id, 'debit': total, 'credit': 0},
                {'account_id': grni_account.id, 'debit': 0, 'credit': total},
            ]
        )
```

---

## Week 24-25: Inventory Management Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `inventory_management` |
| Type | Core |
| Priority | P0 (Customer-Promised) |
| Dependencies | Accounting |
| Spec Location | `docs/modules/02-core/inventory-management/` |
| Timeline | 7-10 days |
| Risk | HIGH (Valuation accuracy critical) |

### Key Entities

```python
# Inventory entities
- Product (sku, name, category, type, costing_method, tenant_id)
- Warehouse (code, name, address, tenant_id)
- Location (warehouse_id, code, name, type)
- StockLevel (product_id, location_id, quantity, reserved, tenant_id)
- StockMovement (product_id, from_location, to_location, quantity, tenant_id)
- StockValuation (product_id, date, quantity, unit_cost, total_value, tenant_id)
- InventoryAdjustment (location_id, date, reason, status, tenant_id)
- BatchLot (product_id, batch_number, expiry_date, quantity, tenant_id)
```

### Key Implementation: Inventory Valuation

```python
# backend/src/modules/inventory_management/services.py

class InventoryService:
    """Inventory management with valuation."""

    COSTING_METHODS = ['fifo', 'lifo', 'weighted_average', 'standard']

    def add_stock(
        self,
        product_id: uuid.UUID,
        quantity: Decimal,
        tenant_id: uuid.UUID,
        unit_cost: Decimal,
        location_id: uuid.UUID = None,
        reference_type: str = None,
        reference_id: uuid.UUID = None
    ) -> StockMovement:
        """
        Add stock and update valuation.
        """

        product = Product.objects.get(
            id=product_id,
            tenant_id=tenant_id
        )

        location = location_id or self._get_default_location(tenant_id)

        with transaction.atomic():
            # Update stock level
            stock_level, _ = StockLevel.objects.get_or_create(
                product_id=product_id,
                location_id=location,
                tenant_id=tenant_id,
                defaults={'quantity': 0, 'reserved': 0}
            )
            stock_level.quantity += quantity
            stock_level.save()

            # Create movement record
            movement = StockMovement.objects.create(
                tenant_id=tenant_id,
                product_id=product_id,
                from_location=None,
                to_location=location,
                quantity=quantity,
                unit_cost=unit_cost,
                movement_type='receipt',
                reference_type=reference_type,
                reference_id=reference_id
            )

            # Update valuation based on costing method
            self._update_valuation(product, quantity, unit_cost, tenant_id)

        return movement

    def _update_valuation(
        self,
        product: Product,
        quantity: Decimal,
        unit_cost: Decimal,
        tenant_id: uuid.UUID
    ):
        """Update inventory valuation based on costing method."""

        if product.costing_method == 'weighted_average':
            self._update_weighted_average(product, quantity, unit_cost, tenant_id)
        elif product.costing_method == 'fifo':
            self._add_fifo_layer(product, quantity, unit_cost, tenant_id)
        elif product.costing_method == 'standard':
            # Standard cost doesn't change with receipts
            pass

    def _update_weighted_average(
        self,
        product: Product,
        quantity: Decimal,
        unit_cost: Decimal,
        tenant_id: uuid.UUID
    ):
        """Calculate weighted average cost."""

        valuation = StockValuation.objects.filter(
            product_id=product.id,
            tenant_id=tenant_id
        ).order_by('-date').first()

        if valuation:
            existing_value = valuation.quantity * valuation.unit_cost
            new_value = quantity * unit_cost
            total_quantity = valuation.quantity + quantity
            new_unit_cost = (existing_value + new_value) / total_quantity
        else:
            total_quantity = quantity
            new_unit_cost = unit_cost

        StockValuation.objects.create(
            tenant_id=tenant_id,
            product_id=product.id,
            date=timezone.now().date(),
            quantity=total_quantity,
            unit_cost=new_unit_cost,
            total_value=total_quantity * new_unit_cost
        )

    def get_stock_value(
        self,
        tenant_id: uuid.UUID,
        as_of_date: date = None
    ) -> dict:
        """Get total inventory value for tenant."""

        as_of_date = as_of_date or timezone.now().date()

        # Get latest valuation for each product
        valuations = StockValuation.objects.filter(
            tenant_id=tenant_id,
            date__lte=as_of_date
        ).values('product_id').annotate(
            latest_date=Max('date')
        )

        total_value = Decimal('0')

        for v in valuations:
            valuation = StockValuation.objects.get(
                product_id=v['product_id'],
                date=v['latest_date'],
                tenant_id=tenant_id
            )
            total_value += valuation.total_value

        return {
            'total_value': total_value,
            'as_of_date': as_of_date,
            'product_count': len(valuations)
        }
```

---

## Phase Completion Criteria

### Mandatory Checkpoints

- [ ] Sales module operational (quotes, orders, deliveries)
- [ ] Purchase module operational (requisitions, POs, receipts)
- [ ] Inventory module operational (stock, movements, valuation)
- [ ] ≥90% test coverage per module
- [ ] GL integration verified for all transactions
- [ ] Inventory valuation accurate (reconciles with GL)

### Integration Tests

```bash
# Full order-to-cash cycle
pytest tests/integration/test_order_to_cash.py -v

# Full procure-to-pay cycle
pytest tests/integration/test_procure_to_pay.py -v

# Inventory valuation reconciliation
pytest tests/integration/test_inventory_gl_reconciliation.py -v
```

---

## Document Status

**Status:** BLOCKED (Awaiting Phase 10)  
**Last Updated:** January 5, 2026  
**Next Phase:** Phase 12 (HR, Projects, BI)

---

