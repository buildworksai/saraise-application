from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.modules.sales_management.models import DeliveryNote, Quotation, QuotationLine
from src.modules.sales_management.services import SalesConfigurationService
from src.modules.sales_management.tests.conftest import API, customer, order_with_line, quote_payload, unwrap

pytestmark = pytest.mark.django_db


def _quote(tenant, buyer, number):
    row = Quotation.objects.create(
        tenant_id=tenant,
        quotation_number=number,
        quotation_date=date(2026, 1, 1),
        valid_until=date(2026, 1, 31),
        customer=buyer,
    )
    QuotationLine.objects.create(
        tenant_id=tenant,
        quotation=row,
        line_number=1,
        item_code="I",
        item_name="Item",
        quantity=Decimal("1"),
        unit_price=Decimal("10"),
        gross_amount=Decimal("10"),
        line_total=Decimal("10"),
    )
    return row


def test_customer_cross_tenant_list_detail_create_update_delete(
    authenticated_tenant_a_client,
    tenant_a,
    tenant_b,
):
    own = customer(tenant_a.id, code="A")
    foreign = customer(tenant_b.id, code="B")
    listed = authenticated_tenant_a_client.get(f"{API}/customers/")
    ids = {item["id"] for item in unwrap(listed)}
    assert str(own.pk) in ids and str(foreign.pk) not in ids
    assert authenticated_tenant_a_client.get(f"{API}/customers/{foreign.pk}/").status_code == 404
    created = authenticated_tenant_a_client.post(
        f"{API}/customers/",
        {"tenant_id": str(tenant_b.id), "customer_code": "SPOOF", "customer_name": "Spoof"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="isolation-customer-create",
    )
    assert created.status_code == 201 and unwrap(created)["tenant_id"] == str(tenant_a.id)
    before = foreign.customer_name
    assert (
        authenticated_tenant_a_client.patch(
            f"{API}/customers/{foreign.pk}/", {"customer_name": "Changed", "expected_version": 1}, format="json"
        ).status_code
        == 404
    )
    foreign.refresh_from_db()
    assert foreign.customer_name == before
    assert authenticated_tenant_a_client.delete(f"{API}/customers/{foreign.pk}/", HTTP_IF_MATCH="1").status_code == 404
    foreign.refresh_from_db()
    assert foreign.deleted_at is None


def test_quotation_isolation_including_nested_lines_and_commands(
    authenticated_tenant_a_client,
    tenant_a,
    tenant_b,
):
    own_customer, foreign_customer = customer(tenant_a.id, code="A"), customer(tenant_b.id, code="B")
    own, foreign = _quote(tenant_a.id, own_customer, "QT-A"), _quote(tenant_b.id, foreign_customer, "QT-B")
    ids = {item["id"] for item in unwrap(authenticated_tenant_a_client.get(f"{API}/quotations/"))}
    assert str(own.pk) in ids and str(foreign.pk) not in ids
    assert authenticated_tenant_a_client.get(f"{API}/quotations/{foreign.pk}/").status_code == 404
    assert (
        authenticated_tenant_a_client.post(
            f"{API}/quotations/",
            quote_payload(foreign_customer.pk),
            format="json",
            HTTP_IDEMPOTENCY_KEY="cross-q-create",
        ).status_code
        == 404
    )
    assert (
        authenticated_tenant_a_client.patch(
            f"{API}/quotations/{foreign.pk}/", {**quote_payload(own_customer.pk), "expected_version": 1}, format="json"
        ).status_code
        == 404
    )
    assert authenticated_tenant_a_client.delete(f"{API}/quotations/{foreign.pk}/", HTTP_IF_MATCH="1").status_code == 404
    assert (
        authenticated_tenant_a_client.post(
            f"{API}/quotations/{foreign.pk}/commands/send/", {}, format="json", HTTP_IDEMPOTENCY_KEY="cross-q-send"
        ).status_code
        == 404
    )
    assert not QuotationLine.objects.for_tenant(tenant_a.id).filter(pk=foreign.lines.get().pk).exists()


def test_order_and_delivery_list_detail_create_update_delete_isolation(
    authenticated_tenant_a_client,
    tenant_a,
    tenant_b,
):
    own_order, own_line = order_with_line(tenant_a.id, code="SO-A")
    foreign_order, foreign_line = order_with_line(tenant_b.id, code="SO-B")
    own_note = DeliveryNote.objects.create(
        tenant_id=tenant_a.id,
        delivery_number="DN-A",
        delivery_date=date(2026, 1, 2),
        sales_order=own_order,
    )
    foreign_note = DeliveryNote.objects.create(
        tenant_id=tenant_b.id,
        delivery_number="DN-B",
        delivery_date=date(2026, 1, 2),
        sales_order=foreign_order,
    )
    order_ids = {item["id"] for item in unwrap(authenticated_tenant_a_client.get(f"{API}/sales-orders/"))}
    note_ids = {item["id"] for item in unwrap(authenticated_tenant_a_client.get(f"{API}/delivery-notes/"))}
    assert str(own_order.pk) in order_ids and str(foreign_order.pk) not in order_ids
    assert str(own_note.pk) in note_ids and str(foreign_note.pk) not in note_ids
    for path, row in (("sales-orders", foreign_order), ("delivery-notes", foreign_note)):
        assert authenticated_tenant_a_client.get(f"{API}/{path}/{row.pk}/").status_code == 404
        assert authenticated_tenant_a_client.delete(f"{API}/{path}/{row.pk}/", HTTP_IF_MATCH="1").status_code == 404
    order_payload = {
        "order_date": "2026-01-01",
        "customer": str(foreign_order.customer_id),
        "lines": [
            {"line_number": 1, "item_code": "I", "item_name": "Item", "quantity": "1.0000", "unit_price": "10.0000"}
        ],
    }
    assert (
        authenticated_tenant_a_client.post(
            f"{API}/sales-orders/", order_payload, format="json", HTTP_IDEMPOTENCY_KEY="cross-o-create"
        ).status_code
        == 404
    )
    assert (
        authenticated_tenant_a_client.patch(
            f"{API}/sales-orders/{foreign_order.pk}/", {**order_payload, "expected_version": 1}, format="json"
        ).status_code
        == 404
    )
    delivery_payload = {
        "delivery_date": "2026-01-02",
        "sales_order": str(foreign_order.pk),
        "lines": [{"line_number": 1, "sales_order_line": str(foreign_line.pk), "quantity_delivered": "1.0000"}],
    }
    assert (
        authenticated_tenant_a_client.post(
            f"{API}/delivery-notes/", delivery_payload, format="json", HTTP_IDEMPOTENCY_KEY="cross-d-create"
        ).status_code
        == 404
    )
    assert (
        authenticated_tenant_a_client.patch(
            f"{API}/delivery-notes/{foreign_note.pk}/", {**delivery_payload, "expected_version": 1}, format="json"
        ).status_code
        == 404
    )
    foreign_order.refresh_from_db()
    foreign_note.refresh_from_db()
    assert foreign_order.deleted_at is None and foreign_note.deleted_at is None


def test_configuration_versions_and_rollback_are_tenant_isolated(tenant_a, tenant_b, actor_id, correlation_id):
    a = SalesConfigurationService.get_current(tenant_a.id, "development")
    b = SalesConfigurationService.get_current(tenant_b.id, "development")
    SalesConfigurationService.apply_change(
        tenant_b.id, actor_id, correlation_id, "development", b.lock_version, {"quotation_prefix": "BQT"}, "tenant B"
    )
    a_versions = list(SalesConfigurationService.list_versions(tenant_a.id, "development"))
    assert {row.configuration_id for row in a_versions} == {a.id}
    with pytest.raises(LookupError):
        SalesConfigurationService.get_version(tenant_a.id, "development", 2)
