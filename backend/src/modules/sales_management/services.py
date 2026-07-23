"""Transactional domain authority for the sales quote-to-delivery funnel."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from src.core.api.results import CapabilityUnavailable
from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import enqueue
from src.core.state_machine import StateMachine

from .models import (
    Customer,
    DeliveryNote,
    DeliveryNoteLine,
    Quotation,
    QuotationLine,
    SalesConfiguration,
    SalesConfigurationVersion,
    SalesDocumentSequence,
    SalesOrder,
    SalesOrderLine,
)
from .integrations import (
    Capability,
    IntegrationUnavailable,
    InventoryAvailabilityRequest,
    get_integration_registry,
)

logger = logging.getLogger("saraise.sales_management")
MONEY_ZERO = Decimal("0")
CONFIGURABLE_FIELDS = (
    "default_currency",
    "quotation_validity_days",
    "credit_check_enabled",
    "inventory_confirmation_required",
    "manual_discount_enabled",
    "maximum_manual_discount_percent",
    "manual_tax_enabled",
    "quotation_prefix",
    "order_prefix",
    "delivery_prefix",
    "sequence_padding",
    "currency_decimal_places",
    "rounding_mode",
)


class SalesDomainError(ValueError):
    """A non-leaking business-rule failure."""


class ConcurrentModification(SalesDomainError):
    pass


class IdempotencyConflict(SalesDomainError):
    pass


class ResourceConflict(SalesDomainError):
    pass


def _uuid(value: uuid.UUID | str, field: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({field: "A valid UUID is required."}) from exc


def _active(model: type[Any], tenant_id: uuid.UUID) -> QuerySet[Any]:
    return model.objects.for_tenant(tenant_id).filter(deleted_at__isnull=True)


def _server_environment(environment: str | None = None) -> str:
    current = str(getattr(settings, "SARAISE_ENVIRONMENT", getattr(settings, "SARAISE_MODE", "development")))
    current = {"self_hosted": "self-hosted"}.get(current, current)
    if environment is not None and environment != current:
        raise ValidationError({"environment": "Configuration environment is selected by the server."})
    return current


def _check_version(instance: Any, expected_version: int) -> None:
    if expected_version is None or int(expected_version) != instance.lock_version:
        raise ConcurrentModification("The resource changed since it was read.")


def _clean_save(instance: Any, *, update_fields: list[str] | None = None) -> Any:
    instance.full_clean()
    instance.save(update_fields=update_fields)
    return instance


def _snapshot(config: SalesConfiguration) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in CONFIGURABLE_FIELDS:
        if not hasattr(config, field):
            continue
        value = getattr(config, field)
        result[field] = str(value) if isinstance(value, Decimal) else value
    return result


def _config(tenant_id: uuid.UUID, environment: str | None = None) -> SalesConfiguration:
    env = _server_environment(environment)
    config = _active(SalesConfiguration, tenant_id).filter(environment=env).first()
    if config is not None:
        return config
    # Creation is a deterministic platform bootstrap, not a client-selected policy.
    actor = uuid.UUID(int=0)
    try:
        config = SalesConfiguration.objects.create(
            tenant_id=tenant_id,
            environment=env,
            created_by=actor,
            updated_by=actor,
        )
        SalesConfigurationVersion.objects.create(
            tenant_id=tenant_id,
            configuration=config,
            version=1,
            snapshot=_snapshot(config),
            change_reason="Initial tenant configuration",
            actor_id=actor,
            correlation_id=actor,
        )
        return config
    except Exception:
        existing = _active(SalesConfiguration, tenant_id).filter(environment=env).first()
        if existing is None:
            raise
        return existing


def _round(value: Decimal, config: SalesConfiguration) -> Decimal:
    places = int(getattr(config, "currency_decimal_places", 2))
    mode_name = str(getattr(config, "rounding_mode", "ROUND_HALF_UP"))
    mode = {"ROUND_HALF_UP": ROUND_HALF_UP, "ROUND_HALF_EVEN": ROUND_HALF_EVEN}.get(mode_name)
    if mode is None:
        raise ValidationError({"rounding_mode": "Unsupported rounding mode."})
    return value.quantize(Decimal(1).scaleb(-places), rounding=mode)


def _calculate_lines(
    tenant_id: uuid.UUID, raw_lines: list[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Decimal]]:
    config = _config(tenant_id)
    if not raw_lines:
        raise ValidationError({"lines": "At least one line is required."})
    calculated: list[dict[str, Any]] = []
    totals = {
        "subtotal_amount": MONEY_ZERO,
        "discount_amount": MONEY_ZERO,
        "tax_amount": MONEY_ZERO,
        "total_amount": MONEY_ZERO,
    }
    seen: set[int] = set()
    for raw in raw_lines:
        line = dict(raw)
        number = int(line["line_number"])
        if number in seen:
            raise ValidationError({"lines": "Line numbers must be unique."})
        seen.add(number)
        quantity = Decimal(line["quantity"])
        unit_price = Decimal(line["unit_price"])
        discount_percent = Decimal(line.get("discount_percent", 0))
        tax = Decimal(line.get("tax_amount", 0))
        if quantity <= 0 or quantity > Decimal("999999"):
            raise ValidationError({"quantity": "Quantity must be greater than zero and at most 999999."})
        if unit_price < 0 or unit_price > Decimal("999999999.99"):
            raise ValidationError({"unit_price": "Unit price is outside the safe range."})
        if discount_percent < 0 or discount_percent > 100:
            raise ValidationError({"discount_percent": "Discount must be between 0 and 100."})
        if discount_percent and not config.manual_discount_enabled:
            raise ValidationError({"discount_percent": "Manual discounts are disabled by sales configuration."})
        if discount_percent > config.maximum_manual_discount_percent:
            raise ValidationError({"discount_percent": "Discount exceeds the configured tenant limit."})
        if tax and not config.manual_tax_enabled:
            raise ValidationError({"tax_amount": "Manual tax is disabled by sales configuration."})
        gross = _round(quantity * unit_price, config)
        discount = _round(gross * discount_percent / Decimal("100"), config)
        total = _round(gross - discount + tax, config)
        if tax < 0 or total < 0:
            raise ValidationError({"lines": "Calculated amounts cannot be negative."})
        line.update(gross_amount=gross, discount_amount=discount, tax_amount=_round(tax, config))
        line["line_total"] = total
        calculated.append(line)
        totals["subtotal_amount"] += gross
        totals["discount_amount"] += discount
        totals["tax_amount"] += tax
        totals["total_amount"] += total
    return calculated, {key: _round(value, config) for key, value in totals.items()}


def _idempotent_existing(tenant_id: uuid.UUID, key: str, event_type: str, model: type[Any]) -> Any | None:
    if not key or len(key) > 255:
        raise ValidationError({"idempotency_key": "A key of at most 255 characters is required."})
    job = AsyncJob.objects.for_tenant(tenant_id).filter(idempotency_key=key).first()
    if job is None:
        return None
    if job.command != event_type:
        raise IdempotencyConflict("The idempotency key was already used for a different operation.")
    aggregate_id = job.payload.get("aggregate_id")
    if not aggregate_id:
        raise IdempotencyConflict("The idempotency record is incomplete.")
    result = model.objects.for_tenant(tenant_id).filter(pk=aggregate_id).first()
    if result is None:
        raise IdempotencyConflict("The idempotency record no longer resolves to its aggregate.")
    return result


def _event(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    correlation_id: uuid.UUID,
    key: str,
    event_type: str,
    aggregate: Any,
    *,
    causation_id: str | None = None,
) -> None:
    payload = {
        "tenant_id": str(tenant_id),
        "aggregate_type": aggregate._meta.model_name,
        "aggregate_id": str(aggregate.pk),
        "aggregate_version": int(aggregate.lock_version),
        "actor_id": str(actor_id),
        "correlation_id": str(correlation_id),
        "causation_id": causation_id or key,
        "event_version": 1,
    }
    existing = AsyncJob.objects.for_tenant(tenant_id).filter(idempotency_key=key).first()
    if existing is not None:
        if existing.command != event_type or existing.payload.get("aggregate_id") != str(aggregate.pk):
            raise IdempotencyConflict("The idempotency key conflicts with an existing command.")
        return
    enqueue(tenant_id, actor_id, event_type, payload, key)


def _log(
    event: str,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    correlation_id: uuid.UUID,
    entity: Any,
    start: float,
    **extra: Any,
) -> None:
    logger.info(
        event,
        extra={
            "event": event,
            "tenant_id": str(tenant_id),
            "actor_id": str(actor_id),
            "correlation_id": str(correlation_id),
            "entity_type": entity._meta.model_name,
            "entity_id": str(entity.pk),
            "from_status": extra.get("from_status"),
            "to_status": extra.get("to_status", getattr(entity, "status", None)),
            "lock_version": entity.lock_version,
            "duration_ms": round((time.monotonic() - start) * 1000, 3),
            "outcome": "succeeded",
            "reason_code": extra.get("reason_code", "OK"),
        },
    )


def _allocate_number(tenant_id: uuid.UUID, kind: str) -> str:
    config = _config(tenant_id)
    environment = config.environment
    sequence, _ = SalesDocumentSequence.objects.select_for_update().get_or_create(
        tenant_id=tenant_id,
        environment=environment,
        document_kind=kind,
        defaults={"next_value": 1, "lock_version": 1},
    )
    prefix = {
        "quotation": config.quotation_prefix,
        "sales_order": config.order_prefix,
        "delivery_note": config.delivery_prefix,
    }[kind]
    value = sequence.next_value
    sequence.next_value += 1
    sequence.lock_version += 1
    sequence.save(update_fields=["next_value", "lock_version", "updated_at"])
    return f"{prefix}-{value:0{config.sequence_padding}d}"


QUOTATION_MACHINE = StateMachine(
    name="sales-quotation",
    model=Quotation,
    states=("draft", "sent", "accepted", "rejected", "expired", "converted"),
    transitions=(
        {"command": "send", "source": "draft", "target": "sent"},
        {"command": "accept", "source": "sent", "target": "accepted"},
        {"command": "reject", "source": "sent", "target": "rejected"},
        {"command": "expire", "source": "sent", "target": "expired"},
        {"command": "convert", "source": "accepted", "target": "converted"},
    ),
    terminal_states=("rejected", "expired", "converted"),
)
ORDER_MACHINE = StateMachine(
    name="sales-order",
    model=SalesOrder,
    states=(
        "draft",
        "confirmed",
        "picking",
        "packing",
        "ready_to_ship",
        "shipped",
        "delivered",
        "invoiced",
        "cancelled",
    ),
    transitions=(
        {"command": "confirm", "source": "draft", "target": "confirmed"},
        {"command": "start_picking", "source": "confirmed", "target": "picking"},
        {"command": "start_packing", "source": "picking", "target": "packing"},
        {"command": "mark_ready", "source": "packing", "target": "ready_to_ship"},
        {"command": "ship", "source": "ready_to_ship", "target": "shipped"},
        {"command": "deliver", "source": "shipped", "target": "delivered"},
        {"command": "mark_invoiced", "source": "delivered", "target": "invoiced"},
        *(
            {"command": "cancel", "source": source, "target": "cancelled"}
            for source in ("draft", "confirmed", "picking", "packing", "ready_to_ship")
        ),
    ),
    terminal_states=("invoiced", "cancelled"),
)
DELIVERY_MACHINE = StateMachine(
    name="sales-delivery",
    model=DeliveryNote,
    states=("draft", "completed", "cancelled"),
    transitions=(
        {"command": "complete", "source": "draft", "target": "completed"},
        {"command": "cancel", "source": "draft", "target": "cancelled"},
    ),
    terminal_states=("completed", "cancelled"),
)


class CustomerService:
    @staticmethod
    def list_customers(
        tenant_id: uuid.UUID,
        filters: Mapping[str, Any] | None = None,
        pagination: Any = None,
        ordering: str = "customer_code",
    ):
        del pagination
        qs = _active(Customer, _uuid(tenant_id, "tenant_id"))
        filters = filters or {}
        if filters.get("search"):
            search = str(filters["search"]).strip()
            qs = qs.filter(
                Q(customer_code__icontains=search) | Q(customer_name__icontains=search) | Q(email__icontains=search)
            )
        for key in ("is_active", "currency"):
            if filters.get(key) not in (None, ""):
                qs = qs.filter(**{key: filters[key]})
        allowed = {"customer_code", "customer_name", "created_at"}
        selected = ordering if ordering.removeprefix("-") in allowed else "customer_code"
        return qs.order_by(selected, "id")

    @staticmethod
    def get_customer(tenant_id: uuid.UUID, customer_id: uuid.UUID) -> Customer:
        try:
            return _active(Customer, _uuid(tenant_id, "tenant_id")).get(pk=customer_id)
        except Customer.DoesNotExist as exc:
            raise LookupError("Customer not found.") from exc

    @staticmethod
    @transaction.atomic
    def create_customer(tenant_id, actor_id, correlation_id, idempotency_key, data) -> Customer:
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        existing = _idempotent_existing(tenant, idempotency_key, "sales_management.customer.created.v1", Customer)
        if existing is not None:
            return existing
        start = time.monotonic()
        values = dict(data)
        values.pop("tenant_id", None)
        values.pop("expected_version", None)
        values.setdefault("currency", _config(tenant).default_currency)
        customer = Customer(tenant_id=tenant, created_by=actor, updated_by=actor, **values)
        _clean_save(customer)
        _event(tenant, actor, correlation, idempotency_key, "sales_management.customer.created.v1", customer)
        _log("customer.created", tenant, actor, correlation, customer, start)
        return customer

    @staticmethod
    @transaction.atomic
    def update_customer(tenant_id, customer_id, actor_id, correlation_id, expected_version, data) -> Customer:
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        customer = _active(Customer, tenant).select_for_update().filter(pk=customer_id).first()
        if customer is None:
            raise LookupError("Customer not found.")
        _check_version(customer, expected_version)
        start = time.monotonic()
        for field, value in dict(data).items():
            if field in {
                "customer_code",
                "customer_name",
                "email",
                "phone",
                "address",
                "credit_limit",
                "currency",
                "is_active",
            }:
                setattr(customer, field, value)
        customer.updated_by = actor
        customer.lock_version += 1
        _clean_save(customer)
        _log("customer.updated", tenant, actor, correlation, customer, start)
        return customer

    @staticmethod
    @transaction.atomic
    def archive_customer(tenant_id, customer_id, actor_id, correlation_id, expected_version) -> Customer:
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        customer = _active(Customer, tenant).select_for_update().filter(pk=customer_id).first()
        if customer is None:
            raise LookupError("Customer not found.")
        _check_version(customer, expected_version)
        if (
            _active(Quotation, tenant).filter(customer=customer, status__in=("draft", "sent", "accepted")).exists()
            or _active(SalesOrder, tenant)
            .filter(customer=customer)
            .exclude(status__in=("invoiced", "cancelled"))
            .exists()
        ):
            raise ResourceConflict("Customer has active sales documents and cannot be archived.")
        start = time.monotonic()
        customer.is_active = False
        customer.deleted_at = timezone.now()
        customer.deleted_by = actor
        customer.updated_by = actor
        customer.lock_version += 1
        _clean_save(customer)
        _log("customer.archived", tenant, actor, correlation, customer, start)
        return customer


class QuotationService:
    @staticmethod
    def list_quotations(tenant_id, filters=None, pagination=None, ordering="-quotation_date"):
        del pagination
        qs = _active(Quotation, _uuid(tenant_id, "tenant_id"))
        filters = filters or {}
        if filters.get("search"):
            value = str(filters["search"]).strip()
            qs = qs.filter(Q(quotation_number__icontains=value) | Q(customer__customer_name__icontains=value))
        for key, field in (("customer_id", "customer_id"), ("status", "status"), ("currency", "currency")):
            if filters.get(key):
                qs = qs.filter(**{field: filters[key]})
        for key, lookup in (
            ("date_from", "quotation_date__gte"),
            ("date_to", "quotation_date__lte"),
            ("valid_until_from", "valid_until__gte"),
            ("valid_until_to", "valid_until__lte"),
        ):
            if filters.get(key):
                qs = qs.filter(**{lookup: filters[key]})
        allowed = {"quotation_number", "quotation_date", "valid_until", "total_amount", "created_at"}
        selected = ordering if ordering.removeprefix("-") in allowed else "-quotation_date"
        return qs.select_related("customer").order_by(selected, "id")

    @staticmethod
    def get_quotation(tenant_id, quotation_id):
        obj = (
            _active(Quotation, _uuid(tenant_id, "tenant_id")).select_related("customer").filter(pk=quotation_id).first()
        )
        if obj is None:
            raise LookupError("Quotation not found.")
        return obj

    @staticmethod
    def preview_quotation(tenant_id, actor_id, data):
        del actor_id
        lines, totals = _calculate_lines(_uuid(tenant_id, "tenant_id"), list(data.get("lines", [])))
        return {
            "lines": lines,
            **totals,
            "currency": data.get("currency", _config(_uuid(tenant_id, "tenant_id")).default_currency),
        }

    @staticmethod
    @transaction.atomic
    def create_quotation(tenant_id, actor_id, correlation_id, idempotency_key, data):
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        existing = _idempotent_existing(tenant, idempotency_key, "sales_management.quotation.created.v1", Quotation)
        if existing is not None:
            return existing
        customer = _active(Customer, tenant).filter(pk=data.get("customer_id"), is_active=True).first()
        if customer is None:
            raise LookupError("Customer not found.")
        lines, totals = _calculate_lines(tenant, list(data.get("lines", [])))
        number = _allocate_number(tenant, "quotation")
        existing = _idempotent_existing(tenant, idempotency_key, "sales_management.quotation.created.v1", Quotation)
        if existing is not None:
            return existing
        values = {k: v for k, v in dict(data).items() if k in {"quotation_date", "valid_until", "currency", "notes"}}
        config = _config(tenant)
        values.setdefault("currency", config.default_currency)
        values.setdefault("valid_until", values["quotation_date"] + timedelta(days=config.quotation_validity_days))
        start = time.monotonic()
        quotation = Quotation(
            tenant_id=tenant,
            quotation_number=number,
            customer=customer,
            created_by=actor,
            updated_by=actor,
            **values,
            **totals,
        )
        _clean_save(quotation)
        for line in lines:
            QuotationLine.objects.create(
                tenant_id=tenant, quotation=quotation, created_by=actor, updated_by=actor, **line
            )
        _event(tenant, actor, correlation, idempotency_key, "sales_management.quotation.created.v1", quotation)
        _log("quotation.created", tenant, actor, correlation, quotation, start)
        return quotation

    @staticmethod
    @transaction.atomic
    def update_draft(tenant_id, quotation_id, actor_id, correlation_id, expected_version, data):
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        obj = _active(Quotation, tenant).select_for_update().filter(pk=quotation_id).first()
        if obj is None:
            raise LookupError("Quotation not found.")
        _check_version(obj, expected_version)
        if obj.status != "draft":
            raise ResourceConflict("Only draft quotations can be edited.")
        customer = _active(Customer, tenant).filter(pk=data.get("customer_id", obj.customer_id), is_active=True).first()
        if customer is None:
            raise LookupError("Customer not found.")
        lines = None
        totals: dict[str, Decimal] = {}
        if "lines" in data:
            lines, totals = _calculate_lines(tenant, list(data["lines"]))
        start = time.monotonic()
        for field in ("quotation_date", "valid_until", "currency", "notes"):
            if field in data:
                setattr(obj, field, data[field])
        obj.customer = customer
        for field, value in totals.items():
            setattr(obj, field, value)
        obj.updated_by = actor
        obj.lock_version += 1
        _clean_save(obj)
        if lines is not None:
            obj.lines.filter(deleted_at__isnull=True).update(deleted_at=timezone.now(), deleted_by=actor)
            for line in lines:
                QuotationLine.objects.create(
                    tenant_id=tenant, quotation=obj, created_by=actor, updated_by=actor, **line
                )
        _log("quotation.updated", tenant, actor, correlation, obj, start)
        return obj

    @staticmethod
    @transaction.atomic
    def archive_draft(tenant_id, quotation_id, actor_id, correlation_id, expected_version):
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        obj = _active(Quotation, tenant).select_for_update().filter(pk=quotation_id).first()
        if obj is None:
            raise LookupError("Quotation not found.")
        _check_version(obj, expected_version)
        if obj.status != "draft":
            raise ResourceConflict("Only draft quotations can be archived.")
        start = time.monotonic()
        obj.deleted_at = timezone.now()
        obj.deleted_by = actor
        obj.updated_by = actor
        obj.lock_version += 1
        _clean_save(obj)
        _log("quotation.archived", tenant, actor, correlation, obj, start)
        return obj

    @staticmethod
    @transaction.atomic
    def _transition(tenant_id, quotation_id, actor_id, correlation_id, idempotency_key, command, event_type, reason=""):
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        obj = QuotationService.get_quotation(tenant, quotation_id)
        previous = obj.status
        start = time.monotonic()
        obj = QUOTATION_MACHINE.apply(
            obj,
            command,
            tenant_id=tenant,
            transition_key=idempotency_key,
            metadata={"actor_id": str(actor), "correlation_id": str(correlation), "reason": reason},
        )
        obj.updated_by = actor
        obj.lock_version += 1
        obj.save(update_fields=["updated_by", "lock_version", "updated_at"])
        _event(tenant, actor, correlation, idempotency_key, event_type, obj)
        _log(f"quotation.{command}", tenant, actor, correlation, obj, start, from_status=previous)
        return obj

    @staticmethod
    def send(tenant_id, quotation_id, actor_id, correlation_id, idempotency_key):
        return QuotationService._transition(
            tenant_id,
            quotation_id,
            actor_id,
            correlation_id,
            idempotency_key,
            "send",
            "sales_management.quotation.sent.v1",
        )

    @staticmethod
    def accept(tenant_id, quotation_id, actor_id, correlation_id, idempotency_key):
        return QuotationService._transition(
            tenant_id,
            quotation_id,
            actor_id,
            correlation_id,
            idempotency_key,
            "accept",
            "sales_management.quotation.accepted.v1",
        )

    @staticmethod
    def reject(tenant_id, quotation_id, actor_id, correlation_id, idempotency_key, reason):
        if not str(reason).strip():
            raise ValidationError({"reason": "A rejection reason is required."})
        return QuotationService._transition(
            tenant_id,
            quotation_id,
            actor_id,
            correlation_id,
            idempotency_key,
            "reject",
            "sales_management.quotation.rejected.v1",
            reason,
        )

    @staticmethod
    def expire(tenant_id, quotation_id, actor_id, correlation_id, idempotency_key):
        return QuotationService._transition(
            tenant_id,
            quotation_id,
            actor_id,
            correlation_id,
            idempotency_key,
            "expire",
            "sales_management.quotation.expired.v1",
        )

    @staticmethod
    @transaction.atomic
    def revise(tenant_id, quotation_id, actor_id, correlation_id, idempotency_key):
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        existing = _idempotent_existing(tenant, idempotency_key, "sales_management.quotation.created.v1", Quotation)
        if existing is not None:
            return existing
        original = _active(Quotation, tenant).select_for_update().filter(pk=quotation_id).first()
        if original is None:
            raise LookupError("Quotation not found.")
        if original.status in ("draft", "converted"):
            raise ResourceConflict("This quotation cannot be revised.")
        revision = Quotation.objects.create(
            tenant_id=tenant,
            quotation_number=original.quotation_number,
            quotation_date=timezone.localdate(),
            valid_until=original.valid_until,
            customer=original.customer,
            currency=original.currency,
            subtotal_amount=original.subtotal_amount,
            discount_amount=original.discount_amount,
            tax_amount=original.tax_amount,
            total_amount=original.total_amount,
            status="draft",
            revision_number=original.revision_number + 1,
            revision_of=original,
            notes=original.notes,
            created_by=actor,
            updated_by=actor,
        )
        for line in original.lines.filter(deleted_at__isnull=True):
            QuotationLine.objects.create(
                tenant_id=tenant,
                quotation=revision,
                line_number=line.line_number,
                item_id=line.item_id,
                item_code=line.item_code,
                item_name=line.item_name,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                discount_percent=line.discount_percent,
                gross_amount=line.gross_amount,
                discount_amount=line.discount_amount,
                tax_amount=line.tax_amount,
                line_total=line.line_total,
                created_by=actor,
                updated_by=actor,
            )
        _event(tenant, actor, correlation, idempotency_key, "sales_management.quotation.created.v1", revision)
        return revision

    @staticmethod
    @transaction.atomic
    def convert_to_sales_order(tenant_id, quotation_id, actor_id, correlation_id, idempotency_key):
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        existing = _idempotent_existing(tenant, idempotency_key, "sales_management.quotation.converted.v1", SalesOrder)
        if existing is not None:
            return existing
        quote = _active(Quotation, tenant).select_for_update().filter(pk=quotation_id).first()
        if quote is None:
            raise LookupError("Quotation not found.")
        if quote.status != "accepted":
            raise ResourceConflict("Only an accepted quotation can be converted.")
        if _active(SalesOrder, tenant).filter(quotation=quote).exists():
            raise ResourceConflict("Quotation was already converted.")
        lines = list(quote.lines.filter(deleted_at__isnull=True).order_by("line_number"))
        if not lines:
            raise ResourceConflict("Quotation has no active lines.")
        number = _allocate_number(tenant, "sales_order")
        start = time.monotonic()
        order = SalesOrder.objects.create(
            tenant_id=tenant,
            order_number=number,
            order_date=timezone.localdate(),
            customer=quote.customer,
            quotation=quote,
            currency=quote.currency,
            subtotal_amount=quote.subtotal_amount,
            discount_amount=quote.discount_amount,
            tax_amount=quote.tax_amount,
            total_amount=quote.total_amount,
            status="draft",
            created_by=actor,
            updated_by=actor,
        )
        for line in lines:
            SalesOrderLine.objects.create(
                tenant_id=tenant,
                sales_order=order,
                source_quotation_line_id=line.id,
                line_number=line.line_number,
                item_id=line.item_id,
                item_code=line.item_code,
                item_name=line.item_name,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                discount_percent=line.discount_percent,
                gross_amount=line.gross_amount,
                discount_amount=line.discount_amount,
                tax_amount=line.tax_amount,
                total_price=line.line_total,
                created_by=actor,
                updated_by=actor,
            )
        quote = QUOTATION_MACHINE.apply(
            quote,
            "convert",
            tenant_id=tenant,
            transition_key=idempotency_key,
            metadata={"actor_id": str(actor), "correlation_id": str(correlation), "sales_order_id": str(order.id)},
        )
        quote.updated_by = actor
        quote.lock_version += 1
        quote.save(update_fields=["updated_by", "lock_version", "updated_at"])
        _event(tenant, actor, correlation, idempotency_key, "sales_management.quotation.converted.v1", order)
        _log("quotation.converted", tenant, actor, correlation, quote, start, from_status="accepted")
        return order


class SalesOrderService:
    # Tests and embedded deployments may inject a protocol implementation.
    # Normal runtime resolution uses the versioned extension registry.
    inventory_gateway: Any = None

    @staticmethod
    def list_orders(tenant_id, filters=None, pagination=None, ordering="-order_date"):
        del pagination
        qs = _active(SalesOrder, _uuid(tenant_id, "tenant_id"))
        filters = filters or {}
        if filters.get("search"):
            value = str(filters["search"]).strip()
            qs = qs.filter(Q(order_number__icontains=value) | Q(customer__customer_name__icontains=value))
        for key in ("customer_id", "quotation_id", "status", "warehouse_id", "currency"):
            if filters.get(key):
                qs = qs.filter(**{key: filters[key]})
        for key, lookup in (
            ("date_from", "order_date__gte"),
            ("date_to", "order_date__lte"),
            ("delivery_from", "delivery_date__gte"),
            ("delivery_to", "delivery_date__lte"),
        ):
            if filters.get(key):
                qs = qs.filter(**{lookup: filters[key]})
        allowed = {"order_number", "order_date", "delivery_date", "total_amount", "created_at"}
        selected = ordering if ordering.removeprefix("-") in allowed else "-order_date"
        return qs.select_related("customer", "quotation").order_by(selected, "id")

    @staticmethod
    def get_order(tenant_id, order_id):
        obj = (
            _active(SalesOrder, _uuid(tenant_id, "tenant_id"))
            .select_related("customer", "quotation")
            .filter(pk=order_id)
            .first()
        )
        if obj is None:
            raise LookupError("Sales order not found.")
        return obj

    @staticmethod
    @transaction.atomic
    def create_order(tenant_id, actor_id, correlation_id, idempotency_key, data):
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        existing = _idempotent_existing(tenant, idempotency_key, "sales_management.order.created.v1", SalesOrder)
        if existing is not None:
            return existing
        customer = _active(Customer, tenant).filter(pk=data.get("customer_id"), is_active=True).first()
        if customer is None:
            raise LookupError("Customer not found.")
        quotation = None
        if data.get("quotation_id"):
            quotation = (
                _active(Quotation, tenant).filter(pk=data["quotation_id"], status__in=("accepted", "converted")).first()
            )
            if quotation is None:
                raise LookupError("Quotation not found.")
            if _active(SalesOrder, tenant).filter(quotation=quotation).exists():
                raise ResourceConflict("Quotation already has an order.")
        lines, totals = _calculate_lines(tenant, list(data.get("lines", [])))
        number = _allocate_number(tenant, "sales_order")
        values = {
            k: v
            for k, v in dict(data).items()
            if k in {"order_date", "delivery_date", "currency", "warehouse_id", "notes"}
        }
        values.setdefault("currency", _config(tenant).default_currency)
        start = time.monotonic()
        order = SalesOrder(
            tenant_id=tenant,
            order_number=number,
            customer=customer,
            quotation=quotation,
            created_by=actor,
            updated_by=actor,
            **values,
            **totals,
        )
        _clean_save(order)
        for line in lines:
            line["total_price"] = line.pop("line_total")
            SalesOrderLine.objects.create(
                tenant_id=tenant, sales_order=order, created_by=actor, updated_by=actor, **line
            )
        _event(tenant, actor, correlation, idempotency_key, "sales_management.order.created.v1", order)
        _log("order.created", tenant, actor, correlation, order, start)
        return order

    @staticmethod
    @transaction.atomic
    def update_draft(tenant_id, order_id, actor_id, correlation_id, expected_version, data):
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        obj = _active(SalesOrder, tenant).select_for_update().filter(pk=order_id).first()
        if obj is None:
            raise LookupError("Sales order not found.")
        _check_version(obj, expected_version)
        if obj.status != "draft":
            raise ResourceConflict("Only draft orders can be edited.")
        customer = _active(Customer, tenant).filter(pk=data.get("customer_id", obj.customer_id), is_active=True).first()
        if customer is None:
            raise LookupError("Customer not found.")
        lines = None
        totals: dict[str, Decimal] = {}
        if "lines" in data:
            lines, totals = _calculate_lines(tenant, list(data["lines"]))
        start = time.monotonic()
        obj.customer = customer
        for field in ("order_date", "delivery_date", "currency", "warehouse_id", "notes"):
            if field in data:
                setattr(obj, field, data[field])
        for field, value in totals.items():
            setattr(obj, field, value)
        obj.updated_by = actor
        obj.lock_version += 1
        _clean_save(obj)
        if lines is not None:
            obj.lines.filter(deleted_at__isnull=True).update(deleted_at=timezone.now(), deleted_by=actor)
            for line in lines:
                line["total_price"] = line.pop("line_total")
                SalesOrderLine.objects.create(
                    tenant_id=tenant, sales_order=obj, created_by=actor, updated_by=actor, **line
                )
        _log("order.updated", tenant, actor, correlation, obj, start)
        return obj

    @staticmethod
    @transaction.atomic
    def archive_draft(tenant_id, order_id, actor_id, correlation_id, expected_version):
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        obj = _active(SalesOrder, tenant).select_for_update().filter(pk=order_id).first()
        if obj is None:
            raise LookupError("Sales order not found.")
        _check_version(obj, expected_version)
        if obj.status != "draft":
            raise ResourceConflict("Only draft orders can be archived.")
        start = time.monotonic()
        obj.deleted_at = timezone.now()
        obj.deleted_by = actor
        obj.updated_by = actor
        obj.lock_version += 1
        _clean_save(obj)
        _log("order.archived", tenant, actor, correlation, obj, start)
        return obj

    @staticmethod
    @transaction.atomic
    def _transition(
        tenant_id, order_id, actor_id, correlation_id, idempotency_key, command, *, reason="", invoice_id=None
    ):
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        obj = SalesOrderService.get_order(tenant, order_id)
        previous = obj.status
        if command == "confirm":
            lines = list(obj.lines.filter(deleted_at__isnull=True))
            if not lines:
                raise ResourceConflict("Order requires at least one active line.")
            if not obj.customer.is_active:
                raise ResourceConflict("Customer is inactive.")
            config = _config(tenant)
            if (
                config.credit_check_enabled
                and obj.customer.credit_limit is not None
                and obj.total_amount > obj.customer.credit_limit
            ):
                raise ResourceConflict("Order exceeds the configured customer credit limit.")
            if config.inventory_confirmation_required:
                if any(line.item_id is None for line in lines):
                    raise ResourceConflict("Inventory confirmation requires an item reference on every line.")
                gateway = SalesOrderService.inventory_gateway
                if gateway is None:
                    try:
                        gateway = get_integration_registry().resolve(tenant, Capability.INVENTORY_AVAILABILITY)
                    except IntegrationUnavailable as exc:
                        raise CapabilityUnavailable(
                            capability="inventory_availability",
                            message="Inventory confirmation is required but no available provider is configured.",
                            detail={"capability": "inventory_availability", "reason_code": exc.state.reason_code},
                        ) from exc
                request = InventoryAvailabilityRequest(
                    tenant_id=tenant,
                    order_id=obj.id,
                    warehouse_id=obj.warehouse_id,
                    lines=tuple((line.item_id, line.quantity) for line in lines if line.item_id is not None),
                    correlation_id=correlation,
                )
                result = gateway.check_availability(request)
                if not result.succeeded or result.value is None:
                    reason = result.failure.code.value if result.failure else "DEPENDENCY_UNAVAILABLE"
                    raise CapabilityUnavailable(
                        capability="inventory_availability",
                        message="Inventory availability could not be confirmed.",
                        detail={"capability": "inventory_availability", "reason_code": reason},
                    )
                if not result.value.accepted:
                    raise ResourceConflict("Inventory is insufficient for order confirmation.")
        if command == "deliver":
            if any(line.delivered_quantity < line.quantity for line in obj.lines.filter(deleted_at__isnull=True)):
                raise ResourceConflict("All order quantities must be delivered first.")
        start = time.monotonic()
        obj = ORDER_MACHINE.apply(
            obj,
            command,
            tenant_id=tenant,
            transition_key=idempotency_key,
            metadata={"actor_id": str(actor), "correlation_id": str(correlation), "reason": reason},
        )
        if invoice_id is not None:
            obj.external_invoice_id = _uuid(invoice_id, "invoice_id")
        obj.updated_by = actor
        obj.lock_version += 1
        obj.save()
        event = (
            "sales_management.order.confirmed.v1"
            if command == "confirm"
            else (
                "sales_management.order.cancelled.v1"
                if command == "cancel"
                else "sales_management.order.status_changed.v1"
            )
        )
        _event(tenant, actor, correlation, idempotency_key, event, obj)
        _log(f"order.{command}", tenant, actor, correlation, obj, start, from_status=previous)
        return obj

    @staticmethod
    def confirm(tenant_id, order_id, actor_id, correlation_id, idempotency_key):
        return SalesOrderService._transition(tenant_id, order_id, actor_id, correlation_id, idempotency_key, "confirm")

    @staticmethod
    def start_picking(tenant_id, order_id, actor_id, correlation_id, idempotency_key):
        return SalesOrderService._transition(
            tenant_id, order_id, actor_id, correlation_id, idempotency_key, "start_picking"
        )

    @staticmethod
    def start_packing(tenant_id, order_id, actor_id, correlation_id, idempotency_key):
        return SalesOrderService._transition(
            tenant_id, order_id, actor_id, correlation_id, idempotency_key, "start_packing"
        )

    @staticmethod
    def mark_ready(tenant_id, order_id, actor_id, correlation_id, idempotency_key):
        return SalesOrderService._transition(
            tenant_id, order_id, actor_id, correlation_id, idempotency_key, "mark_ready"
        )

    @staticmethod
    def ship(tenant_id, order_id, actor_id, correlation_id, idempotency_key):
        return SalesOrderService._transition(tenant_id, order_id, actor_id, correlation_id, idempotency_key, "ship")

    @staticmethod
    def deliver(tenant_id, order_id, actor_id, correlation_id, idempotency_key):
        return SalesOrderService._transition(tenant_id, order_id, actor_id, correlation_id, idempotency_key, "deliver")

    @staticmethod
    def mark_invoiced(tenant_id, order_id, actor_id, correlation_id, idempotency_key, invoice_id):
        return SalesOrderService._transition(
            tenant_id, order_id, actor_id, correlation_id, idempotency_key, "mark_invoiced", invoice_id=invoice_id
        )

    @staticmethod
    def cancel(tenant_id, order_id, actor_id, correlation_id, idempotency_key, reason):
        if not str(reason).strip():
            raise ValidationError({"reason": "A cancellation reason is required."})
        return SalesOrderService._transition(
            tenant_id, order_id, actor_id, correlation_id, idempotency_key, "cancel", reason=reason
        )


class DeliveryNoteService:
    @staticmethod
    def list_delivery_notes(tenant_id, filters=None, pagination=None, ordering="-delivery_date"):
        del pagination
        qs = _active(DeliveryNote, _uuid(tenant_id, "tenant_id"))
        filters = filters or {}
        if filters.get("search"):
            value = str(filters["search"]).strip()
            qs = qs.filter(Q(delivery_number__icontains=value) | Q(tracking_number__icontains=value))
        for key in ("sales_order_id", "status", "warehouse_id", "tracking_number"):
            if filters.get(key):
                qs = qs.filter(**{key: filters[key]})
        for key, lookup in (("date_from", "delivery_date__gte"), ("date_to", "delivery_date__lte")):
            if filters.get(key):
                qs = qs.filter(**{lookup: filters[key]})
        allowed = {"delivery_number", "delivery_date", "created_at"}
        selected = ordering if ordering.removeprefix("-") in allowed else "-delivery_date"
        return qs.select_related("sales_order").order_by(selected, "id")

    @staticmethod
    def get_delivery_note(tenant_id, delivery_note_id):
        obj = (
            _active(DeliveryNote, _uuid(tenant_id, "tenant_id"))
            .select_related("sales_order")
            .filter(pk=delivery_note_id)
            .first()
        )
        if obj is None:
            raise LookupError("Delivery note not found.")
        return obj

    @staticmethod
    @transaction.atomic
    def create_delivery_note(tenant_id, actor_id, correlation_id, idempotency_key, data):
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        existing = _idempotent_existing(tenant, idempotency_key, "sales_management.delivery.created.v1", DeliveryNote)
        if existing is not None:
            return existing
        order = (
            _active(SalesOrder, tenant)
            .filter(
                pk=data.get("sales_order_id"),
                status__in=("confirmed", "picking", "packing", "ready_to_ship", "shipped"),
            )
            .first()
        )
        if order is None:
            raise LookupError("Eligible sales order not found.")
        raw_lines = list(data.get("lines", []))
        if not raw_lines:
            raise ValidationError({"lines": "At least one delivery line is required."})
        source_ids = [line.get("sales_order_line_id") for line in raw_lines]
        sources = {
            str(line.id): line
            for line in _active(SalesOrderLine, tenant).filter(sales_order=order, id__in=source_ids).select_for_update()
        }
        if len(sources) != len(set(map(str, source_ids))):
            raise LookupError("Sales order line not found.")
        for line in raw_lines:
            source = sources[str(line["sales_order_line_id"])]
            quantity = Decimal(line["quantity_delivered"])
            if quantity <= 0 or quantity > source.quantity - source.delivered_quantity:
                raise ValidationError({"quantity_delivered": "Quantity exceeds the remaining deliverable quantity."})
            supplied = line.get("item_id")
            if supplied is not None and supplied != source.item_id:
                raise ValidationError({"item_id": "Item must match the source order line."})
        number = _allocate_number(tenant, "delivery_note")
        values = {
            k: v
            for k, v in dict(data).items()
            if k in {"delivery_date", "warehouse_id", "carrier_name", "tracking_number", "proof_document_id", "notes"}
        }
        start = time.monotonic()
        note = DeliveryNote(
            tenant_id=tenant, delivery_number=number, sales_order=order, created_by=actor, updated_by=actor, **values
        )
        _clean_save(note)
        for raw in raw_lines:
            line = dict(raw)
            source = sources[str(line.pop("sales_order_line_id"))]
            line["item_id"] = source.item_id
            DeliveryNoteLine.objects.create(
                tenant_id=tenant,
                delivery_note=note,
                sales_order_line=source,
                created_by=actor,
                updated_by=actor,
                **line,
            )
        _event(tenant, actor, correlation, idempotency_key, "sales_management.delivery.created.v1", note)
        _log("delivery.created", tenant, actor, correlation, note, start)
        return note

    @staticmethod
    @transaction.atomic
    def update_draft(tenant_id, delivery_note_id, actor_id, correlation_id, expected_version, data):
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        obj = _active(DeliveryNote, tenant).select_for_update().filter(pk=delivery_note_id).first()
        if obj is None:
            raise LookupError("Delivery note not found.")
        _check_version(obj, expected_version)
        if obj.status != "draft":
            raise ResourceConflict("Only draft delivery notes can be edited.")
        # Reuse create validation against the same order without allocating another document.
        raw_lines = None
        sources: dict[str, SalesOrderLine] = {}
        if "lines" in data:
            raw_lines = list(data["lines"])
            source_ids = [line.get("sales_order_line_id") for line in raw_lines]
            sources = {
                str(line.id): line
                for line in _active(SalesOrderLine, tenant)
                .filter(sales_order=obj.sales_order, id__in=source_ids)
                .select_for_update()
            }
            if not raw_lines or len(sources) != len(set(map(str, source_ids))):
                raise LookupError("Sales order line not found.")
            for raw in raw_lines:
                source = sources[str(raw["sales_order_line_id"])]
                quantity = Decimal(raw["quantity_delivered"])
                if quantity <= 0 or quantity > source.quantity - source.delivered_quantity:
                    raise ValidationError(
                        {"quantity_delivered": "Quantity exceeds the remaining deliverable quantity."}
                    )
        start = time.monotonic()
        for field in ("delivery_date", "warehouse_id", "carrier_name", "tracking_number", "proof_document_id", "notes"):
            if field in data:
                setattr(obj, field, data[field])
        obj.updated_by = actor
        obj.lock_version += 1
        _clean_save(obj)
        if raw_lines is not None:
            obj.lines.filter(deleted_at__isnull=True).update(deleted_at=timezone.now(), deleted_by=actor)
            for raw in raw_lines:
                line = dict(raw)
                source = sources[str(line.pop("sales_order_line_id"))]
                line["item_id"] = source.item_id
                DeliveryNoteLine.objects.create(
                    tenant_id=tenant,
                    delivery_note=obj,
                    sales_order_line=source,
                    created_by=actor,
                    updated_by=actor,
                    **line,
                )
        _log("delivery.updated", tenant, actor, correlation, obj, start)
        return obj

    @staticmethod
    @transaction.atomic
    def archive_draft(tenant_id, delivery_note_id, actor_id, correlation_id, expected_version):
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        obj = _active(DeliveryNote, tenant).select_for_update().filter(pk=delivery_note_id).first()
        if obj is None:
            raise LookupError("Delivery note not found.")
        _check_version(obj, expected_version)
        if obj.status != "draft":
            raise ResourceConflict("Only draft delivery notes can be archived.")
        start = time.monotonic()
        obj.deleted_at = timezone.now()
        obj.deleted_by = actor
        obj.updated_by = actor
        obj.lock_version += 1
        _clean_save(obj)
        _log("delivery.archived", tenant, actor, correlation, obj, start)
        return obj

    @staticmethod
    @transaction.atomic
    def complete(tenant_id, delivery_note_id, actor_id, correlation_id, idempotency_key):
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        note = _active(DeliveryNote, tenant).select_for_update().filter(pk=delivery_note_id).first()
        if note is None:
            raise LookupError("Delivery note not found.")
        if note.status == "completed" and any(
            record.get("transition_key") == idempotency_key for record in note.transition_history
        ):
            return note
        order = _active(SalesOrder, tenant).select_for_update().filter(pk=note.sales_order_id).first()
        if order is None:
            raise LookupError("Sales order not found.")
        if order.status not in ("confirmed", "picking", "packing", "ready_to_ship", "shipped"):
            raise ResourceConflict("Order is not eligible for delivery completion.")
        lines = list(note.lines.filter(deleted_at__isnull=True).select_related("sales_order_line"))
        if not lines:
            raise ResourceConflict("Delivery note has no active lines.")
        locked = {
            line.id: line
            for line in _active(SalesOrderLine, tenant)
            .select_for_update()
            .filter(id__in=[row.sales_order_line_id for row in lines])
        }
        start = time.monotonic()
        for row in lines:
            source = locked[row.sales_order_line_id]
            if source.delivered_quantity + row.quantity_delivered > source.quantity:
                raise ResourceConflict("Delivery would exceed the ordered quantity.")
        for row in lines:
            source = locked[row.sales_order_line_id]
            source.delivered_quantity += row.quantity_delivered
            source.updated_by = actor
            source.lock_version += 1
            source.save(update_fields=["delivered_quantity", "updated_by", "lock_version", "updated_at"])
        note = DELIVERY_MACHINE.apply(
            note,
            "complete",
            tenant_id=tenant,
            transition_key=idempotency_key,
            metadata={"actor_id": str(actor), "correlation_id": str(correlation)},
        )
        note.updated_by = actor
        note.lock_version += 1
        note.save(update_fields=["updated_by", "lock_version", "updated_at"])
        _event(tenant, actor, correlation, idempotency_key, "sales_management.delivery.completed.v1", note)
        _log("delivery.completed", tenant, actor, correlation, note, start, from_status="draft")
        return note

    @staticmethod
    @transaction.atomic
    def cancel(tenant_id, delivery_note_id, actor_id, correlation_id, idempotency_key):
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        note = DeliveryNoteService.get_delivery_note(tenant, delivery_note_id)
        start = time.monotonic()
        note = DELIVERY_MACHINE.apply(
            note,
            "cancel",
            tenant_id=tenant,
            transition_key=idempotency_key,
            metadata={"actor_id": str(actor), "correlation_id": str(correlation)},
        )
        note.updated_by = actor
        note.lock_version += 1
        note.save()
        _event(tenant, actor, correlation, idempotency_key, "sales_management.delivery.cancelled.v1", note)
        _log("delivery.cancelled", tenant, actor, correlation, note, start, from_status="draft")
        return note


class SalesConfigurationService:
    @staticmethod
    def get_current(tenant_id, environment):
        return _config(_uuid(tenant_id, "tenant_id"), environment)

    @staticmethod
    def preview_change(tenant_id, actor_id, environment, proposed_values):
        del actor_id
        current = _config(_uuid(tenant_id, "tenant_id"), environment)
        values = SalesConfigurationService._validate(current, proposed_values)
        before = _snapshot(current)
        after = {**before, **values}
        diff = [
            {"field": key, "before": before.get(key), "after": after.get(key)}
            for key in after
            if before.get(key) != after.get(key)
        ]
        return {
            "valid": True,
            "diff": diff,
            "affected_workflows": sorted(
                {
                    (
                        "quotation"
                        if "quotation" in item["field"]
                        else (
                            "pricing" if "discount" in item["field"] or "tax" in item["field"] else "document_numbering"
                        )
                    )
                    for item in diff
                }
            ),
            "restart_required": False,
            "proposed": after,
        }

    @staticmethod
    def _validate(current, proposed_values):
        from .serializers import SalesConfigurationWriteSerializer

        serializer = SalesConfigurationWriteSerializer(data=dict(proposed_values), partial=True)
        if not serializer.is_valid():
            # Serializers are an input-schema implementation detail.  The
            # service contract consistently exposes Django/domain validation
            # errors to every caller (HTTP, jobs and module integrations).
            errors = {field: [str(message) for message in messages] for field, messages in serializer.errors.items()}
            raise ValidationError(errors)
        return {k: v for k, v in serializer.validated_data.items() if k in CONFIGURABLE_FIELDS and hasattr(current, k)}

    @staticmethod
    @transaction.atomic
    def apply_change(tenant_id, actor_id, correlation_id, environment, expected_version, proposed_values, reason):
        tenant, actor, correlation = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(correlation_id, "correlation_id"),
        )
        current = _active(SalesConfiguration, tenant).select_for_update().filter(
            environment=_server_environment(environment)
        ).first() or _config(tenant, environment)
        _check_version(current, expected_version)
        if not str(reason).strip():
            raise ValidationError({"reason": "A change reason is required."})
        values = SalesConfigurationService._validate(current, proposed_values)
        if not values:
            raise ValidationError({"configuration": "At least one setting must be supplied."})
        for field, value in values.items():
            setattr(current, field, value)
        current.version += 1
        current.lock_version += 1
        current.updated_by = actor
        _clean_save(current)
        SalesConfigurationVersion.objects.create(
            tenant_id=tenant,
            configuration=current,
            version=current.version,
            snapshot=_snapshot(current),
            change_reason=reason,
            actor_id=actor,
            correlation_id=correlation,
        )
        _event(
            tenant,
            actor,
            correlation,
            f"configuration:{current.id}:{current.version}",
            "sales_management.configuration.changed.v1",
            current,
        )
        return current

    @staticmethod
    def list_versions(tenant_id, environment, pagination=None):
        del pagination
        config = _config(_uuid(tenant_id, "tenant_id"), environment)
        return (
            SalesConfigurationVersion.objects.for_tenant(config.tenant_id)
            .filter(configuration=config)
            .order_by("-version")
        )

    @staticmethod
    def get_version(tenant_id, environment, version):
        config = _config(_uuid(tenant_id, "tenant_id"), environment)
        obj = (
            SalesConfigurationVersion.objects.for_tenant(config.tenant_id)
            .filter(configuration=config, version=version)
            .first()
        )
        if obj is None:
            raise LookupError("Configuration version not found.")
        return obj

    @staticmethod
    def rollback(tenant_id, actor_id, correlation_id, environment, target_version, expected_version, reason):
        version = SalesConfigurationService.get_version(tenant_id, environment, target_version)
        return SalesConfigurationService.apply_change(
            tenant_id, actor_id, correlation_id, environment, expected_version, version.snapshot, reason
        )

    @staticmethod
    def export_configuration(tenant_id, environment):
        config = _config(_uuid(tenant_id, "tenant_id"), environment)
        return {
            "schema_version": 1,
            "environment": config.environment,
            "exported_at": timezone.now().isoformat(),
            "values": _snapshot(config),
        }

    @staticmethod
    def import_configuration(
        tenant_id, actor_id, correlation_id, environment, expected_version, document, dry_run, reason
    ):
        if not isinstance(document, Mapping) or set(document) != {
            "schema_version",
            "environment",
            "exported_at",
            "values",
        }:
            raise ValidationError({"document": "Configuration document has unknown or missing keys."})
        if document["schema_version"] != 1:
            raise ValidationError({"document": "Unsupported configuration schema."})
        if document["environment"] != _server_environment(environment):
            raise ValidationError({"document": "Configuration environment does not match this server."})
        preview = SalesConfigurationService.preview_change(tenant_id, actor_id, environment, document["values"])
        if dry_run:
            return preview
        return SalesConfigurationService.apply_change(
            tenant_id, actor_id, correlation_id, environment, expected_version, document["values"], reason
        )


class SalesDashboardService:
    """Efficient, non-fabricated overview and extension discovery."""

    @staticmethod
    def summary(tenant_id: uuid.UUID) -> dict[str, Any]:
        tenant = _uuid(tenant_id, "tenant_id")
        quotation_counts = dict(_active(Quotation, tenant).values_list("status").annotate(total=Count("id")))
        order_counts = dict(_active(SalesOrder, tenant).values_list("status").annotate(total=Count("id")))
        recent = list(
            _active(DeliveryNote, tenant)
            .order_by("-delivery_date", "-created_at")
            .values("id", "delivery_number", "delivery_date", "status")[:5]
        )
        return {
            "open_quotations": sum(quotation_counts.get(state, 0) for state in ("draft", "sent", "accepted")),
            "confirmed_orders": order_counts.get("confirmed", 0),
            "fulfillment_stages": {
                state: order_counts.get(state, 0)
                for state in ("confirmed", "picking", "packing", "ready_to_ship", "shipped")
            },
            "recent_deliveries": recent,
            "generated_at": timezone.now().isoformat(),
        }

    @staticmethod
    def capabilities(tenant_id: uuid.UUID) -> list[dict[str, object]]:
        tenant = _uuid(tenant_id, "tenant_id")
        return [item.as_dict() for item in get_integration_registry().capabilities(tenant)]
