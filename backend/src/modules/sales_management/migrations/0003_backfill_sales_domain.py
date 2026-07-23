"""Populate legacy aggregates without inventing business transitions."""

from __future__ import annotations

import re
import uuid
from collections import defaultdict

from django.conf import settings
from django.db import migrations

ZERO_UUID = uuid.UUID(int=0)
NUMBER_SUFFIX = re.compile(r"(\d+)$")


def _history(record):
    """Record imported state as migration provenance, not as a transition."""

    return [
        {
            "status": record.status,
            "recorded_at": record.created_at.isoformat(),
            "source": "legacy_import",
        }
    ]


def _snapshot(configuration):
    return {
        "default_currency": configuration.default_currency,
        "currency_decimal_places": configuration.currency_decimal_places,
        "rounding_mode": configuration.rounding_mode,
        "quotation_validity_days": configuration.quotation_validity_days,
        "credit_check_enabled": configuration.credit_check_enabled,
        "inventory_confirmation_required": configuration.inventory_confirmation_required,
        "manual_discount_enabled": configuration.manual_discount_enabled,
        "maximum_manual_discount_percent": str(configuration.maximum_manual_discount_percent),
        "manual_tax_enabled": configuration.manual_tax_enabled,
        "quotation_prefix": configuration.quotation_prefix,
        "order_prefix": configuration.order_prefix,
        "delivery_prefix": configuration.delivery_prefix,
        "sequence_padding": configuration.sequence_padding,
    }


def backfill_sales_domain(apps, schema_editor):
    Customer = apps.get_model("sales_management", "Customer")
    Quotation = apps.get_model("sales_management", "Quotation")
    SalesOrder = apps.get_model("sales_management", "SalesOrder")
    SalesOrderLine = apps.get_model("sales_management", "SalesOrderLine")
    DeliveryNote = apps.get_model("sales_management", "DeliveryNote")
    DeliveryNoteLine = apps.get_model("sales_management", "DeliveryNoteLine")
    SalesConfiguration = apps.get_model("sales_management", "SalesConfiguration")
    SalesConfigurationVersion = apps.get_model("sales_management", "SalesConfigurationVersion")
    SalesDocumentSequence = apps.get_model("sales_management", "SalesDocumentSequence")

    tenant_ids = set()
    for model in (Customer, Quotation, SalesOrder, SalesOrderLine, DeliveryNote, DeliveryNoteLine):
        tenant_ids.update(model.objects.values_list("tenant_id", flat=True).distinct())

    for quotation in Quotation.objects.all().iterator():
        quotation.valid_until = quotation.valid_until or quotation.quotation_date
        quotation.subtotal_amount = quotation.total_amount
        quotation.discount_amount = 0
        quotation.tax_amount = 0
        quotation.transition_history = _history(quotation)
        quotation.created_by = ZERO_UUID
        quotation.updated_by = ZERO_UUID
        quotation.save(
            update_fields=(
                "valid_until",
                "subtotal_amount",
                "discount_amount",
                "tax_amount",
                "transition_history",
                "created_by",
                "updated_by",
            )
        )

    for order in SalesOrder.objects.all().iterator():
        order.subtotal_amount = order.total_amount
        order.discount_amount = 0
        order.tax_amount = 0
        order.transition_history = _history(order)
        order.created_by = ZERO_UUID
        order.updated_by = ZERO_UUID
        order.save(
            update_fields=(
                "subtotal_amount",
                "discount_amount",
                "tax_amount",
                "transition_history",
                "created_by",
                "updated_by",
            )
        )

    for note in DeliveryNote.objects.all().iterator():
        note.transition_history = _history(note)
        note.created_by = ZERO_UUID
        note.updated_by = ZERO_UUID
        note.save(update_fields=("transition_history", "created_by", "updated_by"))

    for model in (Customer, SalesOrderLine, DeliveryNoteLine):
        model.objects.all().update(created_by=ZERO_UUID, updated_by=ZERO_UUID)

    for order_id in SalesOrderLine.objects.values_list("sales_order_id", flat=True).distinct():
        rows = SalesOrderLine.objects.filter(sales_order_id=order_id).order_by("created_at", "id")
        for line_number, line in enumerate(rows.iterator(), start=1):
            line.line_number = line_number
            line.gross_amount = line.total_price
            line.discount_amount = 0
            line.tax_amount = 0
            line.save(update_fields=("line_number", "gross_amount", "discount_amount", "tax_amount"))

    for note_id in DeliveryNoteLine.objects.values_list("delivery_note_id", flat=True).distinct():
        rows = DeliveryNoteLine.objects.filter(delivery_note_id=note_id).order_by("created_at", "id")
        for line_number, line in enumerate(rows.iterator(), start=1):
            line.line_number = line_number
            line.save(update_fields=("line_number",))

    environment = getattr(settings, "SARAISE_MODE", "development")
    sequence_maxima: dict[tuple[uuid.UUID, str], int] = defaultdict(int)
    document_sources = (
        (Quotation, "quotation_number", "quotation"),
        (SalesOrder, "order_number", "sales_order"),
        (DeliveryNote, "delivery_number", "delivery_note"),
    )
    for model, field, kind in document_sources:
        for tenant_id, number in model.objects.values_list("tenant_id", field).iterator():
            match = NUMBER_SUFFIX.search(number or "")
            if match:
                sequence_maxima[(tenant_id, kind)] = max(sequence_maxima[(tenant_id, kind)], int(match.group(1)))

    for tenant_id in tenant_ids:
        currencies = list(
            Customer.objects.filter(tenant_id=tenant_id)
            .exclude(currency="")
            .values_list("currency", flat=True)[:1]
        )
        configuration = SalesConfiguration.objects.create(
            tenant_id=tenant_id,
            environment=environment,
            default_currency=currencies[0] if currencies else "USD",
            created_by=ZERO_UUID,
            updated_by=ZERO_UUID,
        )
        SalesConfigurationVersion.objects.create(
            tenant_id=tenant_id,
            configuration=configuration,
            version=1,
            snapshot=_snapshot(configuration),
            change_reason="Initial configuration created from legacy sales data.",
            actor_id=ZERO_UUID,
            correlation_id=ZERO_UUID,
        )
        for kind in ("quotation", "sales_order", "delivery_note"):
            SalesDocumentSequence.objects.create(
                tenant_id=tenant_id,
                environment=environment,
                document_kind=kind,
                next_value=sequence_maxima[(tenant_id, kind)] + 1,
                lock_version=1,
            )


def reverse_sales_domain_backfill(apps, schema_editor):
    SalesConfigurationVersion = apps.get_model("sales_management", "SalesConfigurationVersion")
    SalesConfiguration = apps.get_model("sales_management", "SalesConfiguration")
    SalesDocumentSequence = apps.get_model("sales_management", "SalesDocumentSequence")
    Quotation = apps.get_model("sales_management", "Quotation")
    SalesOrder = apps.get_model("sales_management", "SalesOrder")
    DeliveryNote = apps.get_model("sales_management", "DeliveryNote")

    SalesConfigurationVersion.objects.all().delete()
    SalesConfiguration.objects.all().delete()
    SalesDocumentSequence.objects.all().delete()
    Quotation.objects.all().update(transition_history=[])
    SalesOrder.objects.all().update(transition_history=[])
    DeliveryNote.objects.all().update(transition_history=[])


class Migration(migrations.Migration):
    dependencies = [("sales_management", "0002_complete_sales_domain")]
    operations = [migrations.RunPython(backfill_sales_domain, reverse_sales_domain_backfill)]
