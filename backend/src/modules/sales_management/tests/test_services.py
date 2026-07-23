from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from src.modules.sales_management.models import SalesConfigurationVersion
from src.modules.sales_management.services import (
    ConcurrentModification,
    CustomerService,
    DeliveryNoteService,
    IdempotencyConflict,
    QuotationService,
    ResourceConflict,
    SalesConfigurationService,
    SalesOrderService,
)
from src.modules.sales_management.tests.conftest import customer, order_with_line, quote_payload, service_quote_payload

pytestmark = pytest.mark.django_db


def test_customer_service_crud_archive_and_tenant_isolation(actor_id, correlation_id):
    tenant, other = uuid.uuid4(), uuid.uuid4()
    row = CustomerService.create_customer(
        tenant,
        actor_id,
        correlation_id,
        "customer-create-1",
        {"tenant_id": other, "customer_code": "C-1", "customer_name": "Buyer"},
    )
    assert row.tenant_id == tenant
    assert CustomerService.create_customer(tenant, actor_id, correlation_id, "customer-create-1", {}) == row
    assert list(CustomerService.list_customers(tenant, {"search": "buyer"}, None, "customer_name")) == [row]
    with pytest.raises(LookupError):
        CustomerService.get_customer(other, row.pk)
    with pytest.raises(ConcurrentModification):
        CustomerService.update_customer(tenant, row.pk, actor_id, correlation_id, 99, {"customer_name": "No"})
    updated = CustomerService.update_customer(
        tenant, row.pk, actor_id, correlation_id, 1, {"customer_name": "Buyer updated"}
    )
    assert updated.customer_name == "Buyer updated" and updated.lock_version == 2
    archived = CustomerService.archive_customer(tenant, row.pk, actor_id, correlation_id, 2)
    assert archived.deleted_at is not None and not archived.is_active


def test_idempotency_key_conflict_is_explicit(actor_id, correlation_id):
    tenant = uuid.uuid4()
    CustomerService.create_customer(
        tenant, actor_id, correlation_id, "same-key", {"customer_code": "C-1", "customer_name": "One"}
    )
    with pytest.raises(IdempotencyConflict):
        QuotationService.create_quotation(tenant, actor_id, correlation_id, "same-key", {})


def test_quotation_preview_calculates_decimal_totals_from_configuration(actor_id):
    tenant = uuid.uuid4()
    buyer = customer(tenant)
    preview = QuotationService.preview_quotation(tenant, actor_id, quote_payload(buyer.pk))
    assert preview["subtotal_amount"] == Decimal("20.00")
    assert preview["discount_amount"] == Decimal("2.00")
    assert preview["tax_amount"] == Decimal("1.80")
    assert preview["total_amount"] == Decimal("19.80")
    with pytest.raises(ValidationError):
        QuotationService.preview_quotation(tenant, actor_id, {"lines": []})


def test_quotation_create_transition_convert_and_duplicate_prevention(actor_id, correlation_id):
    tenant = uuid.uuid4()
    buyer = customer(tenant)
    quote = QuotationService.create_quotation(
        tenant, actor_id, correlation_id, "q-create", service_quote_payload(buyer.pk)
    )
    assert quote.lines.count() == 1 and quote.quotation_number.startswith("QT-")
    quote = QuotationService.send(tenant, quote.pk, actor_id, correlation_id, "q-send")
    quote = QuotationService.accept(tenant, quote.pk, actor_id, correlation_id, "q-accept")
    order = QuotationService.convert_to_sales_order(tenant, quote.pk, actor_id, correlation_id, "q-convert")
    assert order.quotation_id == quote.pk and order.lines.count() == 1
    with pytest.raises(ResourceConflict):
        QuotationService.convert_to_sales_order(tenant, quote.pk, actor_id, correlation_id, "q-convert-2")


def test_configuration_preview_apply_export_import_and_rollback(actor_id, correlation_id):
    tenant = uuid.uuid4()
    current = SalesConfigurationService.get_current(tenant, "development")
    preview = SalesConfigurationService.preview_change(tenant, actor_id, "development", {"quotation_validity_days": 45})
    assert preview["valid"] and preview["diff"][0]["field"] == "quotation_validity_days"
    changed = SalesConfigurationService.apply_change(
        tenant,
        actor_id,
        correlation_id,
        "development",
        current.lock_version,
        {"quotation_validity_days": 45},
        "longer validity",
    )
    assert changed.version == 2 and SalesConfigurationVersion.objects.filter(configuration=changed).count() == 2
    document = SalesConfigurationService.export_configuration(tenant, "development")
    dry_run = SalesConfigurationService.import_configuration(
        tenant,
        actor_id,
        correlation_id,
        "development",
        changed.lock_version,
        document,
        True,
        "validate import",
    )
    assert dry_run["valid"]
    rolled = SalesConfigurationService.rollback(
        tenant,
        actor_id,
        correlation_id,
        "development",
        1,
        changed.lock_version,
        "restore default",
    )
    assert rolled.quotation_validity_days == 30 and rolled.version == 3


def test_order_confirmation_rejects_credit_limit(actor_id, correlation_id):
    tenant = uuid.uuid4()
    buyer = customer(tenant, credit_limit=Decimal("5.00"))
    data = {
        "order_date": date(2026, 1, 1),
        "customer_id": buyer.pk,
        "lines": [
            {
                "line_number": 1,
                "item_code": "I",
                "item_name": "Item",
                "quantity": Decimal("1"),
                "unit_price": Decimal("10"),
                "discount_percent": Decimal("0"),
                "tax_amount": Decimal("0"),
            }
        ],
    }
    order = SalesOrderService.create_order(tenant, actor_id, correlation_id, "o-create", data)
    with pytest.raises(ResourceConflict, match="credit limit"):
        SalesOrderService.confirm(tenant, order.pk, actor_id, correlation_id, "o-confirm")


def test_order_full_state_machine_and_delivery_precondition(actor_id, correlation_id):
    tenant = uuid.uuid4()
    buyer = customer(tenant)
    data = {
        "order_date": date(2026, 1, 1),
        "customer_id": buyer.pk,
        "lines": [
            {
                "line_number": 1,
                "item_code": "I",
                "item_name": "Item",
                "quantity": Decimal("1"),
                "unit_price": Decimal("10"),
                "discount_percent": Decimal("0"),
                "tax_amount": Decimal("0"),
            }
        ],
    }
    order = SalesOrderService.create_order(tenant, actor_id, correlation_id, "flow-create", data)
    order = SalesOrderService.confirm(tenant, order.pk, actor_id, correlation_id, "flow-confirm")
    order = SalesOrderService.start_picking(tenant, order.pk, actor_id, correlation_id, "flow-pick")
    order = SalesOrderService.start_packing(tenant, order.pk, actor_id, correlation_id, "flow-pack")
    order = SalesOrderService.mark_ready(tenant, order.pk, actor_id, correlation_id, "flow-ready")
    order = SalesOrderService.ship(tenant, order.pk, actor_id, correlation_id, "flow-ship")
    with pytest.raises(ResourceConflict, match="delivered first"):
        SalesOrderService.deliver(tenant, order.pk, actor_id, correlation_id, "flow-deliver-early")
    line = order.lines.get()
    line.delivered_quantity = line.quantity
    line.save(update_fields=["delivered_quantity"])
    order = SalesOrderService.deliver(tenant, order.pk, actor_id, correlation_id, "flow-deliver")
    invoice = uuid.uuid4()
    order = SalesOrderService.mark_invoiced(tenant, order.pk, actor_id, correlation_id, "flow-invoice", invoice)
    assert order.status == "invoiced" and order.external_invoice_id == invoice
    with pytest.raises(ValidationError):
        SalesOrderService.cancel(tenant, order.pk, actor_id, correlation_id, "flow-cancel", "")


def test_partial_delivery_completion_is_atomic_and_rejects_over_delivery(actor_id, correlation_id):
    tenant = uuid.uuid4()
    order, line = order_with_line(tenant, status="confirmed")
    note = DeliveryNoteService.create_delivery_note(
        tenant,
        actor_id,
        correlation_id,
        "delivery-create",
        {
            "delivery_date": date(2026, 1, 2),
            "sales_order_id": order.pk,
            "lines": [{"line_number": 1, "sales_order_line_id": line.pk, "quantity_delivered": Decimal("1")}],
        },
    )
    completed = DeliveryNoteService.complete(tenant, note.pk, actor_id, correlation_id, "delivery-complete")
    line.refresh_from_db()
    assert completed.status == "completed" and line.delivered_quantity == Decimal("1")
    assert DeliveryNoteService.complete(tenant, note.pk, actor_id, correlation_id, "delivery-complete").pk == note.pk
    with pytest.raises(ValidationError, match="remaining deliverable"):
        DeliveryNoteService.create_delivery_note(
            tenant,
            actor_id,
            correlation_id,
            "delivery-over",
            {
                "delivery_date": date(2026, 1, 3),
                "sales_order_id": order.pk,
                "lines": [{"line_number": 1, "sales_order_line_id": line.pk, "quantity_delivered": Decimal("2")}],
            },
        )


def test_configuration_import_rejects_unknown_environment_schema_bounds_and_stale_write(actor_id, correlation_id):
    tenant = uuid.uuid4()
    current = SalesConfigurationService.get_current(tenant, "development")
    document = SalesConfigurationService.export_configuration(tenant, "development")
    with pytest.raises(ValidationError, match="unknown or missing"):
        SalesConfigurationService.import_configuration(
            tenant, actor_id, correlation_id, "development", 1, {**document, "extra": True}, True, "bad"
        )
    with pytest.raises(ValidationError, match="Unsupported"):
        SalesConfigurationService.import_configuration(
            tenant, actor_id, correlation_id, "development", 1, {**document, "schema_version": 99}, True, "bad"
        )
    with pytest.raises(ValidationError):
        SalesConfigurationService.preview_change(tenant, actor_id, "development", {"sequence_padding": 99})
    with pytest.raises(ConcurrentModification):
        SalesConfigurationService.apply_change(
            tenant,
            actor_id,
            correlation_id,
            "development",
            current.lock_version + 1,
            {"quotation_prefix": "QX"},
            "stale",
        )
