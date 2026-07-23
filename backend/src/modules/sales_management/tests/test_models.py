from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from src.modules.sales_management.models import (
    Customer,
    DeliveryNote,
    DeliveryNoteLine,
    ImmutableRecordError,
    Quotation,
    QuotationLine,
    SalesConfiguration,
    SalesConfigurationVersion,
    SalesDocumentSequence,
    validate_configuration_snapshot,
)
from src.modules.sales_management.tests.conftest import customer, order_with_line

pytestmark = pytest.mark.django_db


def test_customer_defaults_string_scope_and_partial_uniqueness():
    tenant = uuid.uuid4()
    row = customer(tenant, code="C-1", customer_name="Buyer")
    candidate = Customer(tenant_id=tenant, customer_code=" C-2 ", customer_name=" Buyer 2 ")
    candidate.full_clean()
    assert (candidate.customer_code, candidate.customer_name) == ("C-2", "Buyer 2")
    assert (row.customer_code, row.customer_name, row.is_active, row.lock_version) == ("C-1", "Buyer", True, 1)
    assert str(row) == "C-1 - Buyer"
    assert list(Customer.objects.for_tenant(tenant)) == [row]
    with pytest.raises(IntegrityError), transaction.atomic():
        customer(tenant, code="C-1")
    row.deleted_at = timezone.now()
    row.save(update_fields=["deleted_at"])
    assert customer(tenant, code="C-1").pk != row.pk


@pytest.mark.parametrize("credit", [Decimal("-0.01")])
def test_customer_credit_database_bound(credit):
    with pytest.raises(IntegrityError), transaction.atomic():
        customer(uuid.uuid4(), credit_limit=credit)


def test_cross_tenant_relations_fail_model_validation():
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    foreign_customer = customer(tenant_b)
    quote = Quotation(
        tenant_id=tenant_a,
        quotation_number="QT-1",
        quotation_date=date(2026, 1, 1),
        valid_until=date(2026, 1, 2),
        customer=foreign_customer,
    )
    with pytest.raises(ValidationError, match="quotation tenant"):
        quote.full_clean()


def test_line_bounds_and_delivery_item_integrity():
    tenant = uuid.uuid4()
    order, line = order_with_line(tenant)
    line.delivered_quantity = Decimal("2.0001")
    with pytest.raises(ValidationError):
        line.full_clean()
    note = DeliveryNote.objects.create(
        tenant_id=tenant,
        delivery_number="DN-1",
        delivery_date=date(2026, 1, 2),
        sales_order=order,
        created_by=uuid.uuid4(),
        updated_by=uuid.uuid4(),
    )
    delivery_line = DeliveryNoteLine(
        tenant_id=tenant,
        delivery_note=note,
        sales_order_line=line,
        line_number=1,
        item_id=uuid.uuid4(),
        quantity_delivered=Decimal("1"),
    )
    with pytest.raises(ValidationError, match="source order-line item"):
        delivery_line.full_clean()


def test_quotation_line_money_is_not_recalculated_by_model_save():
    tenant = uuid.uuid4()
    buyer = customer(tenant)
    quote = Quotation.objects.create(
        tenant_id=tenant,
        quotation_number="QT-1",
        quotation_date=date(2026, 1, 1),
        valid_until=date(2026, 1, 2),
        customer=buyer,
    )
    line = QuotationLine.objects.create(
        tenant_id=tenant,
        quotation=quote,
        line_number=1,
        item_code="I",
        item_name="Item",
        quantity=Decimal("2"),
        unit_price=Decimal("3"),
        gross_amount=Decimal("6"),
        discount_amount=Decimal("1"),
        tax_amount=Decimal("0.5"),
        line_total=Decimal("5.5"),
    )
    line.quantity = Decimal("4")
    line.save()
    line.refresh_from_db()
    assert line.line_total == Decimal("5.50")


def test_configuration_snapshot_schema_and_append_only_history():
    tenant = uuid.uuid4()
    actor = uuid.uuid4()
    config = SalesConfiguration.objects.create(
        tenant_id=tenant, environment="development", created_by=actor, updated_by=actor
    )
    snapshot = {
        "default_currency": "USD",
        "currency_decimal_places": 2,
        "rounding_mode": "ROUND_HALF_UP",
        "quotation_validity_days": 30,
        "credit_check_enabled": True,
        "inventory_confirmation_required": False,
        "manual_discount_enabled": True,
        "maximum_manual_discount_percent": "20.00",
        "manual_tax_enabled": True,
        "quotation_prefix": "QT",
        "order_prefix": "SO",
        "delivery_prefix": "DN",
        "sequence_padding": 6,
    }
    validate_configuration_snapshot(snapshot)
    with pytest.raises(ValidationError):
        validate_configuration_snapshot({**snapshot, "secret": "x"})
    version = SalesConfigurationVersion.objects.create(
        tenant_id=tenant,
        configuration=config,
        version=1,
        snapshot=snapshot,
        change_reason="initial",
        actor_id=actor,
        correlation_id=uuid.uuid4(),
    )
    version.change_reason = "tampered"
    with pytest.raises(ImmutableRecordError):
        version.save()
    with pytest.raises(ImmutableRecordError):
        SalesConfigurationVersion.objects.filter(pk=version.pk).update(version=2)
    with pytest.raises(ImmutableRecordError):
        version.delete()


def test_sequence_uniqueness_and_next_value_bound():
    tenant = uuid.uuid4()
    SalesDocumentSequence.objects.create(tenant_id=tenant, environment="development", document_kind="quotation")
    with pytest.raises(IntegrityError), transaction.atomic():
        SalesDocumentSequence.objects.create(tenant_id=tenant, environment="development", document_kind="quotation")
    with pytest.raises(IntegrityError), transaction.atomic():
        SalesDocumentSequence.objects.create(
            tenant_id=tenant, environment="development", document_kind="sales_order", next_value=0
        )
