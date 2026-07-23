"""Transactional procurement application services.

This is the only supported mutation boundary.  Services derive ownership and
actors from their arguments, lock aggregates, enforce optimistic versions and
persist audit/outbox evidence in the same transaction.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from django.db import IntegrityError, models, transaction
from django.db.models import QuerySet, Sum
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import enqueue

from .models import (
    ConfigurationEnvironment,
    ConfigurationStatus,
    ProcurementConfiguration,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
    PurchaseReceipt,
    PurchaseReceiptLine,
    PurchaseReceiptStatus,
    PurchaseRequisition,
    PurchaseRequisitionLine,
    PurchaseRequisitionStatus,
    QuoteStatus,
    RequestForQuotation,
    RFQInvitation,
    RFQInvitationStatus,
    RFQLine,
    RFQStatus,
    Supplier,
    SupplierQuote,
    SupplierQuoteLine,
    SupplierStatus,
)


class ProcurementError(RuntimeError):
    code = "OPERATION_FAILED"
    status_code = 400

    def __init__(self, message: str, *, detail: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.detail = dict(detail or {})


class ProcurementValidationError(ProcurementError):
    code = "VALIDATION_ERROR"


class ProcurementNotFound(ProcurementError):
    code = "NOT_FOUND"
    status_code = 404


class ProcurementConflict(ProcurementError):
    code = "CONFLICT"
    status_code = 409


class ConfigurationUnavailable(ProcurementError):
    code = "CAPABILITY_UNAVAILABLE"
    status_code = 503


def _uuid(value: uuid.UUID | str, name: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ProcurementValidationError(f"{name} must be a UUID") from exc


def _text(value: Any, name: str, *, maximum: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProcurementValidationError(f"{name} must not be blank")
    normalized = value.strip()
    if maximum is not None and len(normalized) > maximum:
        raise ProcurementValidationError(f"{name} must not exceed {maximum} characters")
    return normalized


def _currency(value: Any) -> str:
    normalized = _text(value, "currency", maximum=3).upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ProcurementValidationError("currency must be an uppercase ISO-4217 code")
    return normalized


def _decimal(value: Any, name: str, *, strictly_positive: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ProcurementValidationError(f"{name} must be a decimal") from exc
    if (strictly_positive and result <= 0) or (not strictly_positive and result < 0):
        operator = "greater than zero" if strictly_positive else "non-negative"
        raise ProcurementValidationError(f"{name} must be {operator}")
    return result


def _assert_version(record: Any, expected: int | None) -> None:
    if expected is None or record.lock_version != expected:
        raise ProcurementConflict(
            "The record changed since it was loaded.",
            detail={"expected_lock_version": expected, "actual_lock_version": record.lock_version},
        )


def _event(
    tenant_id: uuid.UUID,
    aggregate: Any,
    event_type: str,
    *,
    actor_id: uuid.UUID,
    correlation_id: str,
    payload: Mapping[str, Any] | None = None,
) -> OutboxEvent:
    return OutboxEvent.objects.create(
        tenant_id=tenant_id,
        aggregate_type=aggregate._meta.label_lower,
        aggregate_id=aggregate.id,
        event_type=event_type,
        payload={
            "event_id": str(uuid.uuid4()),
            "tenant_id": str(tenant_id),
            "aggregate_id": str(aggregate.id),
            "actor_id": str(actor_id),
            "correlation_id": _text(correlation_id, "correlation_id", maximum=64),
            **dict(payload or {}),
        },
    )


def _save_mutation(record: Any, actor_id: uuid.UUID, fields: Iterable[str]) -> None:
    record.updated_by = actor_id
    record.lock_version += 1
    record.save(update_fields=sorted(set(fields) | {"updated_by", "lock_version", "updated_at"}))


def _same_tenant(tenant_id: uuid.UUID, name: str, obj: Any | None) -> None:
    if obj is not None and obj.tenant_id != tenant_id:
        raise ProcurementNotFound(f"{name} was not found")


def _replace_lines(
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    parent: Any,
    line_model: Any,
    parent_field: str,
    lines: Sequence[Mapping[str, Any]],
    builder: Any,
) -> None:
    line_model.objects.for_tenant(tenant_id).filter(**{parent_field: parent}).delete()
    for index, raw in enumerate(lines, start=1):
        values = builder(raw, index)
        line_model.objects.create(
            tenant_id=tenant_id,
            created_by=actor_id,
            updated_by=actor_id,
            **{parent_field: parent},
            **values,
        )


class SupplierService:
    @staticmethod
    def list_suppliers(tenant_id: uuid.UUID | str, filters: Mapping[str, Any] | None = None) -> QuerySet[Supplier]:
        qs = Supplier.objects.for_tenant(_uuid(tenant_id, "tenant_id"))
        values = dict(filters or {})
        if values.get("status"):
            qs = qs.filter(status=values["status"])
        if values.get("currency"):
            qs = qs.filter(currency=_currency(values["currency"]))
        if values.get("search"):
            from django.db.models import Q

            term = str(values["search"]).strip()
            qs = qs.filter(
                Q(supplier_code__icontains=term) | Q(supplier_name__icontains=term) | Q(email__icontains=term)
            )
        return qs

    @staticmethod
    def get_supplier(tenant_id: uuid.UUID | str, supplier_id: uuid.UUID | str) -> Supplier:
        try:
            return Supplier.objects.for_tenant(_uuid(tenant_id, "tenant_id")).get(id=_uuid(supplier_id, "supplier_id"))
        except Supplier.DoesNotExist as exc:
            raise ProcurementNotFound("Supplier was not found") from exc

    @staticmethod
    @transaction.atomic
    def create_supplier(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str | None = None,
        data: Mapping[str, Any] | None = None,
        correlation_id: str = "legacy",
        **legacy: Any,
    ) -> Supplier:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id or tenant, "actor_id")
        values = dict(data or legacy)
        code = _text(values.pop("supplier_code", None), "supplier_code", maximum=50).upper()
        name = _text(values.pop("supplier_name", None), "supplier_name", maximum=255)
        values.pop("tenant_id", None)
        values.pop("status", None)
        try:
            supplier = Supplier.objects.create(
                tenant_id=tenant,
                created_by=actor,
                updated_by=actor,
                supplier_code=code,
                supplier_name=name,
                email=str(values.get("email", "")).strip(),
                phone=str(values.get("phone", "")).strip(),
                address=str(values.get("address", "")).strip(),
                payment_terms=_text(values.get("payment_terms", "Net 30"), "payment_terms", maximum=50),
                currency=_currency(values.get("currency", "USD")),
            )
        except IntegrityError as exc:
            raise ProcurementValidationError("supplier_code already exists") from exc
        _event(tenant, supplier, "purchase.supplier.created.v1", actor_id=actor, correlation_id=correlation_id)
        return supplier

    @staticmethod
    @transaction.atomic
    def update_supplier(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        supplier_id: uuid.UUID | str,
        data: Mapping[str, Any],
        expected_lock_version: int,
        correlation_id: str,
    ) -> Supplier:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        try:
            supplier = Supplier.objects.for_tenant(tenant).select_for_update().get(id=_uuid(supplier_id, "supplier_id"))
        except Supplier.DoesNotExist as exc:
            raise ProcurementNotFound("Supplier was not found") from exc
        _assert_version(supplier, expected_lock_version)
        if supplier.status == SupplierStatus.ARCHIVED:
            raise ProcurementConflict("Archived suppliers are immutable; restore first")
        allowed = {"supplier_code", "supplier_name", "email", "phone", "address", "payment_terms", "currency"}
        unknown = set(data) - allowed
        if unknown:
            raise ProcurementValidationError("Unknown supplier fields", detail={"fields": sorted(unknown)})
        for field, value in data.items():
            if field == "supplier_code":
                value = _text(value, field, maximum=50).upper()
            elif field == "supplier_name":
                value = _text(value, field, maximum=255)
            elif field == "currency":
                value = _currency(value)
            elif field == "payment_terms":
                value = _text(value, field, maximum=50)
            else:
                value = str(value).strip()
            setattr(supplier, field, value)
        try:
            _save_mutation(supplier, actor, data.keys())
        except IntegrityError as exc:
            raise ProcurementValidationError("supplier_code already exists") from exc
        _event(tenant, supplier, "purchase.supplier.updated.v1", actor_id=actor, correlation_id=correlation_id)
        return supplier

    @staticmethod
    @transaction.atomic
    def set_supplier_status(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        supplier_id: uuid.UUID | str,
        status: str,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> Supplier:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        target = SupplierStatus(status) if status in SupplierStatus.values else None
        if target is None:
            raise ProcurementValidationError("Invalid supplier status")
        supplier = SupplierService.get_supplier(tenant, supplier_id)
        with transaction.atomic():
            supplier = Supplier.objects.for_tenant(tenant).select_for_update().get(pk=supplier.pk)
            if supplier.status == target:
                return supplier
            if supplier.status == SupplierStatus.ARCHIVED and target != SupplierStatus.ACTIVE:
                raise ProcurementConflict("Archived suppliers may only be restored to active")
            previous = supplier.status
            supplier.status = target
            supplier.archived_at = timezone.now() if target == SupplierStatus.ARCHIVED else None
            supplier.archived_by = actor if target == SupplierStatus.ARCHIVED else None
            _save_mutation(supplier, actor, ("status", "archived_at", "archived_by"))
            _event(
                tenant,
                supplier,
                "purchase.supplier.status-changed.v1",
                actor_id=actor,
                correlation_id=correlation_id,
                payload={
                    "from": previous,
                    "to": target,
                    "reason": _text(reason, "reason"),
                    "idempotency_key": _text(idempotency_key, "idempotency_key"),
                },
            )
            return supplier

    @staticmethod
    def archive_supplier(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        supplier_id: uuid.UUID | str,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> Supplier:
        return SupplierService.set_supplier_status(
            tenant_id, actor_id, supplier_id, SupplierStatus.ARCHIVED, reason, idempotency_key, correlation_id
        )

    @staticmethod
    def restore_supplier(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        supplier_id: uuid.UUID | str,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> Supplier:
        return SupplierService.set_supplier_status(
            tenant_id, actor_id, supplier_id, SupplierStatus.ACTIVE, reason, idempotency_key, correlation_id
        )


class RequisitionService:
    list_requisitions = staticmethod(
        lambda tenant_id, filters=None: PurchaseRequisition.objects.for_tenant(_uuid(tenant_id, "tenant_id")).filter(
            deleted_at__isnull=True
        )
    )

    @staticmethod
    def get_requisition(tenant_id: uuid.UUID | str, requisition_id: uuid.UUID | str) -> PurchaseRequisition:
        try:
            return (
                PurchaseRequisition.objects.for_tenant(_uuid(tenant_id, "tenant_id"))
                .prefetch_related("lines")
                .get(id=_uuid(requisition_id, "requisition_id"), deleted_at__isnull=True)
            )
        except PurchaseRequisition.DoesNotExist as exc:
            raise ProcurementNotFound("Requisition was not found") from exc

    @staticmethod
    def _line(raw: Mapping[str, Any], number: int) -> dict[str, Any]:
        qty = _decimal(raw.get("quantity"), "quantity", strictly_positive=True)
        price = _decimal(raw.get("estimated_unit_price", 0), "estimated_unit_price")
        return {
            "line_number": int(raw.get("line_number", number)),
            "item_id": raw.get("item_id"),
            "item_code": _text(raw.get("item_code"), "item_code", maximum=100),
            "description": _text(raw.get("description"), "description", maximum=500),
            "quantity": qty,
            "estimated_unit_price": price,
            "estimated_total": qty * price,
            "preferred_supplier_id": raw.get("preferred_supplier_id"),
            "notes": str(raw.get("notes", "")).strip(),
        }

    @staticmethod
    @transaction.atomic
    def create_requisition(
        tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, data: Mapping[str, Any], correlation_id: str
    ) -> PurchaseRequisition:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        lines = list(data.get("lines", []))
        req_date, required = data.get("requisition_date"), data.get("required_date")
        if required < req_date:
            raise ProcurementValidationError("required_date must be on or after requisition_date")
        req = PurchaseRequisition.objects.create(
            tenant_id=tenant,
            created_by=actor,
            updated_by=actor,
            requested_by=actor,
            requisition_number=_text(data.get("requisition_number"), "requisition_number", maximum=50).upper(),
            requisition_date=req_date,
            required_date=required,
            purpose=_text(data.get("purpose"), "purpose"),
            currency=_currency(data.get("currency")),
            total_amount=sum(
                (RequisitionService._line(line, i)["estimated_total"] for i, line in enumerate(lines, 1)), Decimal(0)
            ),
        )
        _replace_lines(
            tenant_id=tenant,
            actor_id=actor,
            parent=req,
            line_model=PurchaseRequisitionLine,
            parent_field="requisition",
            lines=lines,
            builder=RequisitionService._line,
        )
        _event(tenant, req, "purchase.requisition.created.v1", actor_id=actor, correlation_id=correlation_id)
        return req

    @staticmethod
    @transaction.atomic
    def update_requisition(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        requisition_id: uuid.UUID | str,
        data: Mapping[str, Any],
        expected_lock_version: int,
        correlation_id: str,
    ) -> PurchaseRequisition:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        req = (
            PurchaseRequisition.objects.for_tenant(tenant)
            .select_for_update()
            .get(pk=_uuid(requisition_id, "requisition_id"), deleted_at__isnull=True)
        )
        _assert_version(req, expected_lock_version)
        if req.status not in {PurchaseRequisitionStatus.DRAFT, PurchaseRequisitionStatus.REJECTED}:
            raise ProcurementConflict("Only draft or rejected requisitions are editable")
        lines = list(data.get("lines", []))
        for field in ("requisition_date", "required_date", "purpose"):
            if field in data:
                setattr(req, field, data[field])
        if "currency" in data:
            req.currency = _currency(data["currency"])
        if lines:
            req.total_amount = sum(
                (RequisitionService._line(line, i)["estimated_total"] for i, line in enumerate(lines, 1)), Decimal(0)
            )
            _replace_lines(
                tenant_id=tenant,
                actor_id=actor,
                parent=req,
                line_model=PurchaseRequisitionLine,
                parent_field="requisition",
                lines=lines,
                builder=RequisitionService._line,
            )
        _save_mutation(req, actor, ("requisition_date", "required_date", "purpose", "currency", "total_amount"))
        _event(tenant, req, "purchase.requisition.updated.v1", actor_id=actor, correlation_id=correlation_id)
        return req

    @staticmethod
    @transaction.atomic
    def delete_draft_requisition(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        requisition_id: uuid.UUID | str,
        expected_lock_version: int,
        correlation_id: str,
    ) -> PurchaseRequisition:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        req = (
            PurchaseRequisition.objects.for_tenant(tenant)
            .select_for_update()
            .get(pk=_uuid(requisition_id, "requisition_id"), deleted_at__isnull=True)
        )
        _assert_version(req, expected_lock_version)
        if req.status != PurchaseRequisitionStatus.DRAFT:
            raise ProcurementConflict("Only draft requisitions may be deleted")
        req.deleted_at, req.deleted_by = timezone.now(), actor
        _save_mutation(req, actor, ("deleted_at", "deleted_by"))
        _event(tenant, req, "purchase.requisition.deleted.v1", actor_id=actor, correlation_id=correlation_id)
        return req

    @staticmethod
    def _transition(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        requisition_id: uuid.UUID | str,
        expected: set[str],
        target: str,
        correlation_id: str,
        *,
        reason: str = "",
    ) -> PurchaseRequisition:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            req = (
                PurchaseRequisition.objects.for_tenant(tenant)
                .select_for_update()
                .get(pk=_uuid(requisition_id, "requisition_id"), deleted_at__isnull=True)
            )
            if req.status not in expected:
                raise ProcurementConflict(f"Cannot transition requisition from {req.status} to {target}")
            if target == PurchaseRequisitionStatus.PENDING_APPROVAL and not req.lines.exists():
                raise ProcurementValidationError("A requisition must contain at least one line")
            if target == PurchaseRequisitionStatus.APPROVED and req.requested_by == actor:
                raise ProcurementValidationError("Requester cannot approve their own requisition")
            prior = req.status
            req.status = target
            fields = ["status"]
            if target == PurchaseRequisitionStatus.APPROVED:
                req.approved_by, req.approved_at = actor, timezone.now()
                fields += ["approved_by", "approved_at"]
            if target == PurchaseRequisitionStatus.REJECTED:
                req.rejection_reason = _text(reason, "reason")
                fields.append("rejection_reason")
            _save_mutation(req, actor, fields)
            _event(
                tenant,
                req,
                "purchase.requisition.transitioned.v1",
                actor_id=actor,
                correlation_id=correlation_id,
                payload={"from": prior, "to": target, "reason": reason},
            )
            return req

    submit_requisition = staticmethod(
        lambda t, a, i, correlation_id, **k: RequisitionService._transition(
            t, a, i, {PurchaseRequisitionStatus.DRAFT}, PurchaseRequisitionStatus.PENDING_APPROVAL, correlation_id
        )
    )
    approve_requisition = staticmethod(
        lambda t, a, i, correlation_id, **k: RequisitionService._transition(
            t, a, i, {PurchaseRequisitionStatus.PENDING_APPROVAL}, PurchaseRequisitionStatus.APPROVED, correlation_id
        )
    )
    reject_requisition = staticmethod(
        lambda t, a, i, reason, correlation_id, **k: RequisitionService._transition(
            t,
            a,
            i,
            {PurchaseRequisitionStatus.PENDING_APPROVAL},
            PurchaseRequisitionStatus.REJECTED,
            correlation_id,
            reason=reason,
        )
    )
    revise_requisition = staticmethod(
        lambda t, a, i, correlation_id, **k: RequisitionService._transition(
            t, a, i, {PurchaseRequisitionStatus.REJECTED}, PurchaseRequisitionStatus.DRAFT, correlation_id
        )
    )
    cancel_requisition = staticmethod(
        lambda t, a, i, correlation_id, **k: RequisitionService._transition(
            t,
            a,
            i,
            {
                PurchaseRequisitionStatus.DRAFT,
                PurchaseRequisitionStatus.PENDING_APPROVAL,
                PurchaseRequisitionStatus.APPROVED,
            },
            PurchaseRequisitionStatus.CANCELLED,
            correlation_id,
        )
    )

    @staticmethod
    @transaction.atomic
    def convert_to_purchase_order(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        requisition_id: uuid.UUID | str,
        supplier_id: uuid.UUID | str,
        line_selections: Sequence[Mapping[str, Any]],
        correlation_id: str,
        idempotency_key: str,
    ) -> PurchaseOrder:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        req = (
            PurchaseRequisition.objects.for_tenant(tenant)
            .select_for_update()
            .get(pk=_uuid(requisition_id, "requisition_id"))
        )
        if req.status == PurchaseRequisitionStatus.CONVERTED and req.converted_order_id:
            return PurchaseOrder.objects.for_tenant(tenant).get(pk=req.converted_order_id)
        if req.status != PurchaseRequisitionStatus.APPROVED:
            raise ProcurementConflict("Only approved requisitions can be converted")
        supplier = SupplierService.get_supplier(tenant, supplier_id)
        data = {
            "po_number": f"{req.requisition_number}-PO",
            "po_date": timezone.localdate(),
            "supplier_id": supplier.id,
            "requisition_id": req.id,
            "currency": req.currency,
            "payment_terms": supplier.payment_terms,
            "lines": list(line_selections),
        }
        po = PurchaseOrderService.create_purchase_order(tenant, actor, data, correlation_id)
        req.status, req.converted_order_id = PurchaseRequisitionStatus.CONVERTED, po.id
        _save_mutation(req, actor, ("status", "converted_order_id"))
        return po


class RFQService:
    list_rfqs = staticmethod(
        lambda tenant_id, filters=None: RequestForQuotation.objects.for_tenant(_uuid(tenant_id, "tenant_id")).filter(
            deleted_at__isnull=True
        )
    )
    get_rfq = staticmethod(
        lambda tenant_id, rfq_id: RequestForQuotation.objects.for_tenant(_uuid(tenant_id, "tenant_id"))
        .prefetch_related("lines", "invitations", "quotes__lines")
        .get(pk=_uuid(rfq_id, "rfq_id"), deleted_at__isnull=True)
    )

    @staticmethod
    @transaction.atomic
    def create_rfq(
        tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, data: Mapping[str, Any], correlation_id: str
    ) -> RequestForQuotation:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        issue = data.get("issue_date")
        deadline = data.get("submission_deadline")
        if isinstance(deadline, str):
            deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        if deadline is None or issue is None or deadline.date() <= issue:
            raise ProcurementValidationError("submission_deadline must follow issue_date")
        requisition = None
        if data.get("requisition_id"):
            requisition = RequisitionService.get_requisition(tenant, data["requisition_id"])
        rfq = RequestForQuotation.objects.create(
            tenant_id=tenant,
            created_by=actor,
            updated_by=actor,
            rfq_number=_text(data.get("rfq_number"), "rfq_number", maximum=50).upper(),
            title=_text(data.get("title"), "title", maximum=255),
            requisition=requisition,
            issue_date=issue,
            submission_deadline=deadline,
            currency=_currency(data.get("currency")),
            terms=str(data.get("terms", "")).strip(),
            delivery_requirements=str(data.get("delivery_requirements", "")).strip(),
        )
        for index, line in enumerate(data.get("lines", []), 1):
            qty = _decimal(line.get("quantity"), "quantity", strictly_positive=True)
            req_line = None
            if line.get("requisition_line_id"):
                req_line = (
                    PurchaseRequisitionLine.objects.for_tenant(tenant).filter(pk=line["requisition_line_id"]).first()
                )
                if req_line is None:
                    raise ProcurementNotFound("Requisition line was not found")
            RFQLine.objects.create(
                tenant_id=tenant,
                created_by=actor,
                updated_by=actor,
                rfq=rfq,
                line_number=int(line.get("line_number", index)),
                requisition_line=req_line,
                item_id=line.get("item_id"),
                item_code=_text(line.get("item_code"), "item_code"),
                description=_text(line.get("description"), "description"),
                quantity=qty,
                required_date=line.get("required_date"),
                specification=str(line.get("specification", "")).strip(),
            )
        _event(tenant, rfq, "purchase.rfq.created.v1", actor_id=actor, correlation_id=correlation_id)
        return rfq

    @staticmethod
    @transaction.atomic
    def update_rfq(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        rfq_id: uuid.UUID | str,
        data: Mapping[str, Any],
        expected_lock_version: int,
        correlation_id: str,
    ) -> RequestForQuotation:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        rfq = (
            RequestForQuotation.objects.for_tenant(tenant)
            .select_for_update()
            .get(pk=_uuid(rfq_id, "rfq_id"), deleted_at__isnull=True)
        )
        _assert_version(rfq, expected_lock_version)
        if rfq.status != RFQStatus.DRAFT:
            raise ProcurementConflict("Only draft RFQs are editable")
        for field in ("title", "issue_date", "submission_deadline", "terms", "delivery_requirements"):
            if field in data:
                setattr(rfq, field, data[field])
        _save_mutation(rfq, actor, data.keys())
        _event(tenant, rfq, "purchase.rfq.updated.v1", actor_id=actor, correlation_id=correlation_id)
        return rfq

    @staticmethod
    @transaction.atomic
    def delete_draft_rfq(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        rfq_id: uuid.UUID | str,
        expected_lock_version: int,
        correlation_id: str,
    ) -> RequestForQuotation:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        rfq = (
            RequestForQuotation.objects.for_tenant(tenant)
            .select_for_update()
            .get(pk=_uuid(rfq_id, "rfq_id"), deleted_at__isnull=True)
        )
        _assert_version(rfq, expected_lock_version)
        if rfq.status != RFQStatus.DRAFT:
            raise ProcurementConflict("Only draft RFQs may be deleted")
        rfq.deleted_at, rfq.deleted_by = timezone.now(), actor
        _save_mutation(rfq, actor, ("deleted_at", "deleted_by"))
        _event(tenant, rfq, "purchase.rfq.deleted.v1", actor_id=actor, correlation_id=correlation_id)
        return rfq

    @staticmethod
    @transaction.atomic
    def publish_rfq(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        rfq_id: uuid.UUID | str,
        supplier_ids: Sequence[uuid.UUID | str],
        idempotency_key: str,
        correlation_id: str,
    ) -> tuple[RequestForQuotation, AsyncJob]:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        rfq = RequestForQuotation.objects.for_tenant(tenant).select_for_update().get(pk=_uuid(rfq_id, "rfq_id"))
        config = ProcurementConfigurationService.get_active_configuration(tenant, ConfigurationEnvironment.DEVELOPMENT)
        if rfq.status != RFQStatus.DRAFT:
            raise ProcurementConflict("Only draft RFQs may be published")
        if not rfq.lines.exists():
            raise ProcurementValidationError("RFQ must contain a line")
        unique_ids = list(dict.fromkeys(str(value) for value in supplier_ids))
        if len(unique_ids) < config.minimum_rfq_suppliers:
            raise ProcurementValidationError(f"At least {config.minimum_rfq_suppliers} suppliers are required")
        suppliers = list(Supplier.objects.for_tenant(tenant).filter(id__in=unique_ids, status=SupplierStatus.ACTIVE))
        if len(suppliers) != len(unique_ids):
            raise ProcurementNotFound("One or more active suppliers were not found")
        job = enqueue(
            tenant,
            actor,
            "purchase.rfq.publish.v1",
            {"rfq_id": str(rfq.id), "supplier_ids": unique_ids},
            _text(idempotency_key, "idempotency_key"),
        )
        for supplier in suppliers:
            RFQInvitation.objects.get_or_create(
                tenant_id=tenant,
                rfq=rfq,
                supplier=supplier,
                defaults={
                    "created_by": actor,
                    "updated_by": actor,
                    "status": RFQInvitationStatus.QUEUED,
                    "job_id": job.id,
                },
            )
        rfq.status = RFQStatus.OPEN
        _save_mutation(rfq, actor, ("status",))
        _event(
            tenant,
            rfq,
            "purchase.rfq.publish.v1",
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"job_id": str(job.id)},
        )
        return rfq, job

    @staticmethod
    def _simple_transition(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        rfq_id: uuid.UUID | str,
        expected: set[str],
        target: str,
        correlation_id: str,
    ) -> RequestForQuotation:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            rfq = RequestForQuotation.objects.for_tenant(tenant).select_for_update().get(pk=_uuid(rfq_id, "rfq_id"))
            if rfq.status not in expected:
                raise ProcurementConflict(f"Cannot transition RFQ from {rfq.status} to {target}")
            prior = rfq.status
            rfq.status = target
            _save_mutation(rfq, actor, ("status",))
            _event(
                tenant,
                rfq,
                "purchase.rfq.transitioned.v1",
                actor_id=actor,
                correlation_id=correlation_id,
                payload={"from": prior, "to": target},
            )
            return rfq

    close_rfq = staticmethod(
        lambda t, a, i, correlation_id, **k: RFQService._simple_transition(
            t, a, i, {RFQStatus.OPEN}, RFQStatus.CLOSED, correlation_id
        )
    )
    cancel_rfq = staticmethod(
        lambda t, a, i, correlation_id, **k: RFQService._simple_transition(
            t, a, i, {RFQStatus.DRAFT, RFQStatus.OPEN}, RFQStatus.CANCELLED, correlation_id
        )
    )

    @staticmethod
    def compare_quotes(tenant_id: uuid.UUID | str, rfq_id: uuid.UUID | str) -> dict[str, Any]:
        tenant = _uuid(tenant_id, "tenant_id")
        rfq = RFQService.get_rfq(tenant, rfq_id)
        config = ProcurementConfigurationService.get_active_configuration(tenant, ConfigurationEnvironment.DEVELOPMENT)
        quotes = list(rfq.quotes.filter(status=QuoteStatus.SUBMITTED).prefetch_related("lines", "supplier"))
        if not quotes:
            return {"rfq_id": str(rfq.id), "quotes": [], "warnings": ["No submitted quotes"]}
        lowest = min(q.total_amount for q in quotes) or Decimal(1)
        comparisons = []
        for quote in sorted(quotes, key=lambda q: (q.total_amount, q.delivery_date or date.max, str(q.id))):
            price = (lowest / (quote.total_amount or Decimal(1))) * Decimal(100)
            delivery = Decimal(100) if quote.delivery_date else Decimal(0)
            weights = config.quote_scoring_weights
            # Quality/service are deliberately reported as missing rather than fabricated.
            score = price * Decimal(str(weights["price"])) / 100 + delivery * Decimal(str(weights["delivery"])) / 100
            comparisons.append(
                {
                    "quote_id": str(quote.id),
                    "supplier_id": str(quote.supplier_id),
                    "total_amount": str(quote.total_amount),
                    "delivery_date": quote.delivery_date.isoformat() if quote.delivery_date else None,
                    "components": {
                        "price": str(price.quantize(Decimal("0.01"))),
                        "delivery": str(delivery),
                        "quality": None,
                        "service": None,
                    },
                    "configured_score": str(score.quantize(Decimal("0.01"))),
                    "warnings": ["Quality evidence unavailable", "Service evidence unavailable"],
                }
            )
        return {"rfq_id": str(rfq.id), "quotes": comparisons, "weights": config.quote_scoring_weights}

    @staticmethod
    @transaction.atomic
    def award_quote(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        rfq_id: uuid.UUID | str,
        quote_id: uuid.UUID | str,
        create_order: bool,
        idempotency_key: str,
        correlation_id: str,
    ) -> tuple[SupplierQuote, PurchaseOrder | None]:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        rfq = RequestForQuotation.objects.for_tenant(tenant).select_for_update().get(pk=_uuid(rfq_id, "rfq_id"))
        if rfq.status == RFQStatus.AWARDED and rfq.awarded_quote_id:
            quote = SupplierQuote.objects.for_tenant(tenant).get(pk=rfq.awarded_quote_id)
            return quote, quote.purchase_orders.first()
        if rfq.status != RFQStatus.CLOSED:
            raise ProcurementConflict("Only closed RFQs can be awarded")
        quote = (
            SupplierQuote.objects.for_tenant(tenant)
            .select_for_update()
            .filter(pk=_uuid(quote_id, "quote_id"), rfq=rfq, status=QuoteStatus.SUBMITTED)
            .first()
        )
        if quote is None:
            raise ProcurementNotFound("Submitted quote was not found")
        SupplierQuote.objects.for_tenant(tenant).filter(rfq=rfq, status=QuoteStatus.SUBMITTED).exclude(
            pk=quote.pk
        ).update(status=QuoteStatus.REJECTED, updated_by=actor)
        quote.status = QuoteStatus.ACCEPTED
        _save_mutation(quote, actor, ("status",))
        rfq.status, rfq.awarded_quote_id = RFQStatus.AWARDED, quote.id
        _save_mutation(rfq, actor, ("status", "awarded_quote_id"))
        po = None
        if create_order:
            po = PurchaseOrderService.create_purchase_order(
                tenant,
                actor,
                {
                    "po_number": f"{rfq.rfq_number}-PO",
                    "po_date": timezone.localdate(),
                    "supplier_id": quote.supplier_id,
                    "rfq_id": rfq.id,
                    "accepted_quote_id": quote.id,
                    "currency": quote.currency,
                    "payment_terms": quote.payment_terms,
                    "lines": [
                        {
                            "item_id": line.rfq_line.item_id,
                            "item_code": line.rfq_line.item_code,
                            "item_name": line.rfq_line.description,
                            "quantity": line.quantity,
                            "unit_price": line.unit_price,
                            "tax_amount": line.tax_amount,
                            "quote_line_id": line.id,
                        }
                        for line in quote.lines.select_related("rfq_line")
                    ],
                },
                correlation_id,
            )
        _event(
            tenant,
            rfq,
            "purchase.rfq.awarded.v1",
            actor_id=actor,
            correlation_id=correlation_id,
            payload={
                "quote_id": str(quote.id),
                "purchase_order_id": str(po.id) if po else None,
                "idempotency_key": idempotency_key,
            },
        )
        return quote, po


class QuoteService:
    list_quotes = staticmethod(
        lambda tenant_id, filters=None: SupplierQuote.objects.for_tenant(_uuid(tenant_id, "tenant_id"))
    )
    get_quote = staticmethod(
        lambda tenant_id, quote_id: SupplierQuote.objects.for_tenant(_uuid(tenant_id, "tenant_id"))
        .prefetch_related("lines")
        .get(pk=_uuid(quote_id, "quote_id"))
    )

    @staticmethod
    @transaction.atomic
    def create_quote(
        tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, data: Mapping[str, Any], correlation_id: str
    ) -> SupplierQuote:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        rfq = RFQService.get_rfq(tenant, data.get("rfq_id"))
        supplier = SupplierService.get_supplier(tenant, data.get("supplier_id"))
        if rfq.status != RFQStatus.OPEN:
            raise ProcurementConflict("Quotes can only be created for open RFQs")
        if rfq.currency != _currency(data.get("currency")):
            raise ProcurementValidationError("Quote currency must match RFQ currency")
        quote = SupplierQuote.objects.create(
            tenant_id=tenant,
            created_by=actor,
            updated_by=actor,
            quote_number=_text(data.get("quote_number"), "quote_number"),
            rfq=rfq,
            supplier=supplier,
            valid_until=data.get("valid_until"),
            currency=rfq.currency,
            payment_terms=_text(data.get("payment_terms"), "payment_terms"),
            delivery_date=data.get("delivery_date"),
            shipping_amount=_decimal(data.get("shipping_amount", 0), "shipping_amount"),
            supplier_notes=str(data.get("supplier_notes", "")).strip(),
        )
        for raw in data.get("lines", []):
            rfq_line = RFQLine.objects.for_tenant(tenant).filter(pk=raw.get("rfq_line_id"), rfq=rfq).first()
            if rfq_line is None:
                raise ProcurementNotFound("RFQ line was not found")
            qty, price, tax = (
                _decimal(raw.get("quantity"), "quantity", strictly_positive=True),
                _decimal(raw.get("unit_price"), "unit_price"),
                _decimal(raw.get("tax_amount", 0), "tax_amount"),
            )
            if qty > rfq_line.quantity:
                raise ProcurementValidationError("Quote quantity cannot exceed RFQ quantity")
            SupplierQuoteLine.objects.create(
                tenant_id=tenant,
                created_by=actor,
                updated_by=actor,
                quote=quote,
                rfq_line=rfq_line,
                quantity=qty,
                unit_price=price,
                tax_amount=tax,
                line_total=qty * price + tax,
                lead_time_days=raw.get("lead_time_days"),
                notes=str(raw.get("notes", "")).strip(),
            )
        QuoteService.recalculate_totals(quote, actor)
        _event(tenant, quote, "purchase.quote.created.v1", actor_id=actor, correlation_id=correlation_id)
        return quote

    @staticmethod
    def recalculate_totals(quote: SupplierQuote, actor_id: uuid.UUID) -> SupplierQuote:
        aggregate = quote.lines.aggregate(subtotal=Sum("line_total"), tax=Sum("tax_amount"))
        quote.subtotal, quote.tax_amount = aggregate["subtotal"] or Decimal(0), aggregate["tax"] or Decimal(0)
        quote.total_amount = quote.subtotal + quote.shipping_amount
        _save_mutation(quote, actor_id, ("subtotal", "tax_amount", "total_amount"))
        return quote

    @staticmethod
    @transaction.atomic
    def update_quote(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        quote_id: uuid.UUID | str,
        data: Mapping[str, Any],
        expected_lock_version: int,
        correlation_id: str,
    ) -> SupplierQuote:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        quote = SupplierQuote.objects.for_tenant(tenant).select_for_update().get(pk=_uuid(quote_id, "quote_id"))
        _assert_version(quote, expected_lock_version)
        if quote.status != QuoteStatus.DRAFT:
            raise ProcurementConflict("Only draft quotes are editable")
        for field in ("valid_until", "delivery_date", "payment_terms", "supplier_notes", "shipping_amount"):
            if field in data:
                setattr(quote, field, data[field])
        _save_mutation(quote, actor, data.keys())
        QuoteService.recalculate_totals(quote, actor)
        _event(tenant, quote, "purchase.quote.updated.v1", actor_id=actor, correlation_id=correlation_id)
        return quote

    @staticmethod
    @transaction.atomic
    def delete_draft_quote(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        quote_id: uuid.UUID | str,
        expected_lock_version: int,
        correlation_id: str,
    ) -> SupplierQuote:
        quote = QuoteService.get_quote(tenant_id, quote_id)
        if quote.status != QuoteStatus.DRAFT:
            raise ProcurementConflict("Only draft quotes may be deleted")
        quote.delete()
        return quote

    @staticmethod
    def _transition(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        quote_id: uuid.UUID | str,
        expected: str,
        target: str,
        correlation_id: str,
    ) -> SupplierQuote:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            quote = (
                SupplierQuote.objects.for_tenant(tenant)
                .select_for_update()
                .select_related("rfq")
                .get(pk=_uuid(quote_id, "quote_id"))
            )
            if quote.status != expected:
                raise ProcurementConflict(f"Cannot transition quote from {quote.status} to {target}")
            if target == QuoteStatus.SUBMITTED:
                if quote.rfq.status != RFQStatus.OPEN or quote.valid_until < timezone.localdate():
                    raise ProcurementConflict("Quote is expired or RFQ is not open")
                quote.submitted_at = timezone.now()
            quote.status = target
            _save_mutation(quote, actor, ("status", "submitted_at"))
            _event(
                tenant,
                quote,
                "purchase.quote.transitioned.v1",
                actor_id=actor,
                correlation_id=correlation_id,
                payload={"to": target},
            )
            return quote

    submit_quote = staticmethod(
        lambda t, a, i, correlation_id, **k: QuoteService._transition(
            t, a, i, QuoteStatus.DRAFT, QuoteStatus.SUBMITTED, correlation_id
        )
    )
    withdraw_quote = staticmethod(
        lambda t, a, i, correlation_id, **k: QuoteService._transition(
            t, a, i, QuoteStatus.SUBMITTED, QuoteStatus.WITHDRAWN, correlation_id
        )
    )


class PurchaseOrderService:
    list_purchase_orders = staticmethod(
        lambda tenant_id, filters=None: PurchaseOrder.objects.for_tenant(_uuid(tenant_id, "tenant_id")).filter(
            deleted_at__isnull=True
        )
    )
    get_purchase_order = staticmethod(
        lambda tenant_id, order_id: PurchaseOrder.objects.for_tenant(_uuid(tenant_id, "tenant_id"))
        .select_related("supplier")
        .prefetch_related("lines", "receipts")
        .get(pk=_uuid(order_id, "order_id"), deleted_at__isnull=True)
    )

    @staticmethod
    @transaction.atomic
    def create_purchase_order(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str | None = None,
        data: Mapping[str, Any] | None = None,
        correlation_id: str = "legacy",
        **legacy: Any,
    ) -> PurchaseOrder:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id or tenant_id, "actor_id")
        values = dict(data or legacy)
        supplier_id = values.get("supplier_id")
        # Legacy positional signature: create_purchase_order(tenant, supplier_id, po_date=...).
        if data is None and actor_id is not None:
            supplier_id, actor = actor_id, tenant
        supplier = SupplierService.get_supplier(tenant, supplier_id)
        if supplier.status != SupplierStatus.ACTIVE:
            raise ProcurementValidationError("Supplier must be active")
        requisition = (
            RequisitionService.get_requisition(tenant, values["requisition_id"])
            if values.get("requisition_id")
            else None
        )
        rfq = RFQService.get_rfq(tenant, values["rfq_id"]) if values.get("rfq_id") else None
        quote = QuoteService.get_quote(tenant, values["accepted_quote_id"]) if values.get("accepted_quote_id") else None
        for name, obj in (("requisition", requisition), ("rfq", rfq), ("quote", quote)):
            _same_tenant(tenant, name, obj)
        lines = list(values.get("lines", []))
        total = Decimal(0)
        order = PurchaseOrder.objects.create(
            tenant_id=tenant,
            created_by=actor,
            updated_by=actor,
            po_number=_text(values.get("po_number", f"PO-{uuid.uuid4().hex[:8]}"), "po_number").upper(),
            po_date=values.get("po_date"),
            supplier=supplier,
            expected_delivery_date=values.get("expected_delivery_date"),
            currency=_currency(values.get("currency", supplier.currency)),
            requisition=requisition,
            rfq=rfq,
            accepted_quote=quote,
            payment_terms=_text(values.get("payment_terms", supplier.payment_terms), "payment_terms"),
            delivery_terms=str(values.get("delivery_terms", "")).strip(),
            shipping_address=dict(values.get("shipping_address", {})),
            notes=str(values.get("notes", "")).strip(),
        )
        for index, raw in enumerate(lines, 1):
            qty, price, tax = (
                _decimal(raw.get("quantity"), "quantity", strictly_positive=True),
                _decimal(raw.get("unit_price"), "unit_price"),
                _decimal(raw.get("tax_amount", 0), "tax_amount"),
            )
            line_total = qty * price + tax
            total += line_total
            req_line = (
                PurchaseRequisitionLine.objects.for_tenant(tenant).filter(pk=raw.get("requisition_line_id")).first()
                if raw.get("requisition_line_id")
                else None
            )
            quote_line = (
                SupplierQuoteLine.objects.for_tenant(tenant).filter(pk=raw.get("quote_line_id")).first()
                if raw.get("quote_line_id")
                else None
            )
            PurchaseOrderLine.objects.create(
                tenant_id=tenant,
                created_by=actor,
                updated_by=actor,
                purchase_order=order,
                line_number=int(raw.get("line_number", index)),
                requisition_line=req_line,
                quote_line=quote_line,
                item_id=raw.get("item_id"),
                item_code=_text(raw.get("item_code"), "item_code"),
                item_name=_text(raw.get("item_name"), "item_name"),
                quantity=qty,
                unit_price=price,
                tax_amount=tax,
                total_price=line_total,
            )
        order.total_amount = total
        order.save(update_fields=("total_amount", "updated_at"))
        _event(tenant, order, "purchase.order.created.v1", actor_id=actor, correlation_id=correlation_id)
        return order

    @staticmethod
    def recalculate_totals(order: PurchaseOrder, actor_id: uuid.UUID) -> PurchaseOrder:
        order.total_amount = order.lines.aggregate(total=Sum("total_price"))["total"] or Decimal(0)
        _save_mutation(order, actor_id, ("total_amount",))
        return order

    @staticmethod
    @transaction.atomic
    def update_purchase_order(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        order_id: uuid.UUID | str,
        data: Mapping[str, Any],
        expected_lock_version: int,
        correlation_id: str,
    ) -> PurchaseOrder:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        order = (
            PurchaseOrder.objects.for_tenant(tenant)
            .select_for_update()
            .get(pk=_uuid(order_id, "order_id"), deleted_at__isnull=True)
        )
        _assert_version(order, expected_lock_version)
        if order.status != PurchaseOrderStatus.DRAFT:
            raise ProcurementConflict("Only draft orders are editable")
        for field in (
            "po_date",
            "expected_delivery_date",
            "payment_terms",
            "delivery_terms",
            "shipping_address",
            "notes",
        ):
            if field in data:
                setattr(order, field, data[field])
        _save_mutation(order, actor, data.keys())
        _event(tenant, order, "purchase.order.updated.v1", actor_id=actor, correlation_id=correlation_id)
        return order

    @staticmethod
    @transaction.atomic
    def delete_draft_purchase_order(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        order_id: uuid.UUID | str,
        expected_lock_version: int,
        correlation_id: str,
    ) -> PurchaseOrder:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        order = (
            PurchaseOrder.objects.for_tenant(tenant)
            .select_for_update()
            .get(pk=_uuid(order_id, "order_id"), deleted_at__isnull=True)
        )
        _assert_version(order, expected_lock_version)
        if order.status != PurchaseOrderStatus.DRAFT or order.receipts.exists():
            raise ProcurementConflict("Only receipt-free draft orders may be deleted")
        order.deleted_at, order.deleted_by = timezone.now(), actor
        _save_mutation(order, actor, ("deleted_at", "deleted_by"))
        _event(tenant, order, "purchase.order.deleted.v1", actor_id=actor, correlation_id=correlation_id)
        return order

    @staticmethod
    def _transition(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        order_id: uuid.UUID | str,
        expected: set[str],
        target: str,
        correlation_id: str,
    ) -> PurchaseOrder:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            order = (
                PurchaseOrder.objects.for_tenant(tenant)
                .select_for_update()
                .get(pk=_uuid(order_id, "order_id"), deleted_at__isnull=True)
            )
            if order.status not in expected:
                raise ProcurementConflict(f"Cannot transition order from {order.status} to {target}")
            if target == PurchaseOrderStatus.APPROVED and order.created_by == actor:
                raise ProcurementValidationError("Order creator cannot approve their own order")
            if (
                target == PurchaseOrderStatus.CANCELLED
                and order.receipts.filter(status=PurchaseReceiptStatus.COMPLETED).exists()
            ):
                raise ProcurementConflict("Orders with completed receipts cannot be cancelled")
            prior = order.status
            order.status = target
            fields = ["status"]
            if target == PurchaseOrderStatus.APPROVED:
                order.approved_by, order.approved_at = actor, timezone.now()
                fields += ["approved_by", "approved_at"]
            if target == PurchaseOrderStatus.ACKNOWLEDGED:
                order.acknowledged_at = timezone.now()
                fields.append("acknowledged_at")
            _save_mutation(order, actor, fields)
            _event(
                tenant,
                order,
                "purchase.order.transitioned.v1",
                actor_id=actor,
                correlation_id=correlation_id,
                payload={"from": prior, "to": target},
            )
            return order

    submit_purchase_order = staticmethod(
        lambda t, a, i, correlation_id, **k: PurchaseOrderService._transition(
            t, a, i, {PurchaseOrderStatus.DRAFT}, PurchaseOrderStatus.PENDING_APPROVAL, correlation_id
        )
    )
    approve_purchase_order = staticmethod(
        lambda t, a, i, correlation_id, **k: PurchaseOrderService._transition(
            t, a, i, {PurchaseOrderStatus.PENDING_APPROVAL}, PurchaseOrderStatus.APPROVED, correlation_id
        )
    )
    reject_purchase_order = staticmethod(
        lambda t, a, i, correlation_id, **k: PurchaseOrderService._transition(
            t, a, i, {PurchaseOrderStatus.PENDING_APPROVAL}, PurchaseOrderStatus.DRAFT, correlation_id
        )
    )
    acknowledge_purchase_order = staticmethod(
        lambda t, a, i, correlation_id, **k: PurchaseOrderService._transition(
            t, a, i, {PurchaseOrderStatus.SENT}, PurchaseOrderStatus.ACKNOWLEDGED, correlation_id
        )
    )
    cancel_purchase_order = staticmethod(
        lambda t, a, i, correlation_id, **k: PurchaseOrderService._transition(
            t,
            a,
            i,
            {
                PurchaseOrderStatus.DRAFT,
                PurchaseOrderStatus.PENDING_APPROVAL,
                PurchaseOrderStatus.APPROVED,
                PurchaseOrderStatus.SENT,
                PurchaseOrderStatus.ACKNOWLEDGED,
            },
            PurchaseOrderStatus.CANCELLED,
            correlation_id,
        )
    )

    @staticmethod
    @transaction.atomic
    def dispatch_purchase_order(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        order_id: uuid.UUID | str,
        idempotency_key: str,
        correlation_id: str,
    ) -> tuple[PurchaseOrder, AsyncJob]:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        order = PurchaseOrder.objects.for_tenant(tenant).select_for_update().get(pk=_uuid(order_id, "order_id"))
        if order.status == PurchaseOrderStatus.SENT and order.dispatch_job_id:
            return order, AsyncJob.objects.for_tenant(tenant).get(pk=order.dispatch_job_id)
        if order.status != PurchaseOrderStatus.APPROVED:
            raise ProcurementConflict("Only approved orders may be dispatched")
        job = enqueue(
            tenant, actor, "purchase.order.dispatch.v1", {"purchase_order_id": str(order.id)}, idempotency_key
        )
        order.status, order.dispatch_status, order.dispatch_job_id = PurchaseOrderStatus.SENT, "queued", job.id
        _save_mutation(order, actor, ("status", "dispatch_status", "dispatch_job_id"))
        _event(
            tenant,
            order,
            "purchase.order.dispatch.v1",
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"job_id": str(job.id)},
        )
        return order, job


class PurchaseReceiptService:
    list_receipts = staticmethod(
        lambda tenant_id, filters=None: PurchaseReceipt.objects.for_tenant(_uuid(tenant_id, "tenant_id"))
    )
    get_receipt = staticmethod(
        lambda tenant_id, receipt_id: PurchaseReceipt.objects.for_tenant(_uuid(tenant_id, "tenant_id"))
        .select_related("purchase_order")
        .prefetch_related("lines__purchase_order_line")
        .get(pk=_uuid(receipt_id, "receipt_id"))
    )

    @staticmethod
    @transaction.atomic
    def create_receipt(
        tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, data: Mapping[str, Any], correlation_id: str
    ) -> PurchaseReceipt:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        order = PurchaseOrderService.get_purchase_order(tenant, data.get("purchase_order_id"))
        if order.status not in {PurchaseOrderStatus.ACKNOWLEDGED, PurchaseOrderStatus.PARTIALLY_RECEIVED}:
            raise ProcurementConflict("Order is not receivable")
        receipt = PurchaseReceipt.objects.create(
            tenant_id=tenant,
            created_by=actor,
            updated_by=actor,
            received_by=actor,
            receipt_number=_text(data.get("receipt_number"), "receipt_number").upper(),
            receipt_date=data.get("receipt_date"),
            purchase_order=order,
            warehouse_id=_uuid(data.get("warehouse_id"), "warehouse_id"),
        )
        for index, raw in enumerate(data.get("lines", []), 1):
            order_line = (
                PurchaseOrderLine.objects.for_tenant(tenant)
                .filter(pk=raw.get("purchase_order_line_id"), purchase_order=order)
                .first()
            )
            if order_line is None:
                raise ProcurementNotFound("Purchase order line was not found")
            PurchaseReceiptLine.objects.create(
                tenant_id=tenant,
                created_by=actor,
                updated_by=actor,
                purchase_receipt=receipt,
                purchase_order_line=order_line,
                line_number=int(raw.get("line_number", index)),
                item_id=order_line.item_id,
                quantity_received=_decimal(raw.get("quantity_received"), "quantity_received", strictly_positive=True),
                condition=raw.get("condition", "accepted"),
                batch_no=str(raw.get("batch_no", "")).strip(),
                serial_no=str(raw.get("serial_no", "")).strip(),
                notes=str(raw.get("notes", "")).strip(),
            )
        _event(tenant, receipt, "purchase.receipt.created.v1", actor_id=actor, correlation_id=correlation_id)
        return receipt

    @staticmethod
    @transaction.atomic
    def update_receipt(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        receipt_id: uuid.UUID | str,
        data: Mapping[str, Any],
        expected_lock_version: int,
        correlation_id: str,
    ) -> PurchaseReceipt:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        receipt = PurchaseReceipt.objects.for_tenant(tenant).select_for_update().get(pk=_uuid(receipt_id, "receipt_id"))
        _assert_version(receipt, expected_lock_version)
        if receipt.status != PurchaseReceiptStatus.DRAFT:
            raise ProcurementConflict("Only draft receipts are editable")
        if "receipt_date" in data:
            receipt.receipt_date = data["receipt_date"]
        if "warehouse_id" in data:
            receipt.warehouse_id = _uuid(data["warehouse_id"], "warehouse_id")
        _save_mutation(receipt, actor, data.keys())
        _event(tenant, receipt, "purchase.receipt.updated.v1", actor_id=actor, correlation_id=correlation_id)
        return receipt

    @staticmethod
    @transaction.atomic
    def delete_draft_receipt(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        receipt_id: uuid.UUID | str,
        expected_lock_version: int,
        correlation_id: str,
    ) -> PurchaseReceipt:
        receipt = PurchaseReceiptService.get_receipt(tenant_id, receipt_id)
        _assert_version(receipt, expected_lock_version)
        if receipt.status != PurchaseReceiptStatus.DRAFT:
            raise ProcurementConflict("Only draft receipts may be deleted")
        receipt.delete()
        return receipt

    @staticmethod
    @transaction.atomic
    def complete_receipt(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        receipt_id: uuid.UUID | str,
        idempotency_key: str,
        correlation_id: str,
    ) -> PurchaseReceipt:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        receipt = PurchaseReceipt.objects.for_tenant(tenant).select_for_update().get(pk=_uuid(receipt_id, "receipt_id"))
        if receipt.status == PurchaseReceiptStatus.COMPLETED:
            return receipt
        if receipt.status != PurchaseReceiptStatus.DRAFT:
            raise ProcurementConflict("Only draft receipts may be completed")
        order = PurchaseOrder.objects.for_tenant(tenant).select_for_update().get(pk=receipt.purchase_order_id)
        if order.approved_by == actor:
            raise ProcurementValidationError("Order approver cannot complete its receipt")
        config = ProcurementConfigurationService.get_active_configuration(tenant, ConfigurationEnvironment.DEVELOPMENT)
        lines = list(receipt.lines.select_related("purchase_order_line").order_by("purchase_order_line_id"))
        if not lines:
            raise ProcurementValidationError("Receipt must contain at least one line")
        order_lines = {
            line.id: line
            for line in PurchaseOrderLine.objects.for_tenant(tenant)
            .select_for_update()
            .filter(pk__in=[item.purchase_order_line_id for item in lines])
            .order_by("id")
        }
        for receipt_line in lines:
            order_line = order_lines[receipt_line.purchase_order_line_id]
            if order_line.purchase_order_id != order.id or receipt_line.item_id != order_line.item_id:
                raise ProcurementNotFound("Receipt line relationship was not found")
            if receipt_line.condition == "accepted":
                allowable = (order_line.quantity - order_line.cancelled_quantity) * (
                    Decimal(1) + config.receipt_tolerance_percent / Decimal(100)
                )
                if order_line.received_quantity + receipt_line.quantity_received > allowable:
                    raise ProcurementValidationError("Receipt exceeds configured tolerance")
                order_line.received_quantity += receipt_line.quantity_received
                _save_mutation(order_line, actor, ("received_quantity",))
        complete = (
            all(line.received_quantity >= line.quantity - line.cancelled_quantity for line in order_lines.values())
            and order.lines.exclude(pk__in=order_lines)
            .filter(received_quantity__lt=models.F("quantity") - models.F("cancelled_quantity"))
            .count()
            == 0
        )
        order.status = PurchaseOrderStatus.RECEIVED if complete else PurchaseOrderStatus.PARTIALLY_RECEIVED
        _save_mutation(order, actor, ("status",))
        receipt.status, receipt.completed_at = PurchaseReceiptStatus.COMPLETED, timezone.now()
        if config.inventory_integration_enabled:
            job = enqueue(
                tenant, actor, "purchase.inventory.post-receipt.v1", {"receipt_id": str(receipt.id)}, idempotency_key
            )
            receipt.inventory_status, receipt.inventory_job_id = "pending", job.id
        else:
            receipt.inventory_status = "not_required"
        _save_mutation(receipt, actor, ("status", "completed_at", "inventory_status", "inventory_job_id"))
        _event(
            tenant,
            receipt,
            "purchase.receipt.completed.v1",
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"purchase_order_id": str(order.id), "idempotency_key": idempotency_key},
        )
        return receipt

    @staticmethod
    @transaction.atomic
    def cancel_receipt(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        receipt_id: uuid.UUID | str,
        correlation_id: str,
        **_: Any,
    ) -> PurchaseReceipt:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        receipt = PurchaseReceipt.objects.for_tenant(tenant).select_for_update().get(pk=_uuid(receipt_id, "receipt_id"))
        if receipt.status != PurchaseReceiptStatus.DRAFT:
            raise ProcurementConflict("Only draft receipts may be cancelled")
        receipt.status = PurchaseReceiptStatus.CANCELLED
        _save_mutation(receipt, actor, ("status",))
        _event(tenant, receipt, "purchase.receipt.cancelled.v1", actor_id=actor, correlation_id=correlation_id)
        return receipt

    @staticmethod
    def process_receipt(purchase_receipt: PurchaseReceipt) -> PurchaseReceipt:
        """Deprecated compatibility adapter; uses the stored ownership evidence."""
        return PurchaseReceiptService.complete_receipt(
            purchase_receipt.tenant_id,
            purchase_receipt.updated_by,
            purchase_receipt.id,
            f"legacy-{purchase_receipt.id}",
            "legacy",
        )


class ProcurementConfigurationService:
    WEIGHT_KEYS = frozenset({"price", "delivery", "quality", "service"})

    @staticmethod
    def _validate(data: Mapping[str, Any]) -> dict[str, Any]:
        values = dict(data)
        values["default_currency"] = _currency(values.get("default_currency"))
        values["default_payment_terms"] = _text(
            values.get("default_payment_terms"), "default_payment_terms", maximum=50
        )
        for field in ("supplier_code_prefix", "requisition_prefix", "rfq_prefix", "po_prefix", "receipt_prefix"):
            values[field] = _text(values.get(field), field, maximum=20).upper()
        tolerance = _decimal(values.get("receipt_tolerance_percent"), "receipt_tolerance_percent")
        if tolerance > 100:
            raise ProcurementValidationError("receipt_tolerance_percent must not exceed 100")
        values["receipt_tolerance_percent"] = tolerance
        minimum = int(values.get("minimum_rfq_suppliers", 0))
        if minimum < 2 or minimum > 20:
            raise ProcurementValidationError("minimum_rfq_suppliers must be between 2 and 20")
        values["minimum_rfq_suppliers"] = minimum
        weights = values.get("quote_scoring_weights")
        if not isinstance(weights, dict) or set(weights) != ProcurementConfigurationService.WEIGHT_KEYS:
            raise ProcurementValidationError("quote_scoring_weights must contain price, delivery, quality and service")
        if (
            any(
                not isinstance(value, (int, float, str, Decimal))
                or Decimal(str(value)) < 0
                or Decimal(str(value)) > 100
                for value in weights.values()
            )
            or sum(Decimal(str(value)) for value in weights.values()) != 100
        ):
            raise ProcurementValidationError("quote_scoring_weights must be 0..100 and total 100")
        values["quote_scoring_weights"] = {key: int(Decimal(str(weights[key]))) for key in sorted(weights)}
        rules = values.get("approval_rules", [])
        if not isinstance(rules, list) or len(rules) > 50:
            raise ProcurementValidationError("approval_rules must be a list with at most 50 entries")
        for rule in rules:
            if not isinstance(rule, dict) or set(rule) - {
                "minimum_amount",
                "maximum_amount",
                "category",
                "approver_permission",
            }:
                raise ProcurementValidationError("approval rule contains unsupported fields")
        values["approval_rules"] = rules
        rollout = values.get("rollout", {})
        if not isinstance(rollout, dict) or set(rollout) - {"roles", "cohorts", "percentage"}:
            raise ProcurementValidationError("rollout contains unsupported fields")
        percentage = int(rollout.get("percentage", 100))
        if percentage < 0 or percentage > 100:
            raise ProcurementValidationError("rollout percentage must be between 0 and 100")
        values["rollout"] = {
            "roles": list(rollout.get("roles", [])),
            "cohorts": list(rollout.get("cohorts", [])),
            "percentage": percentage,
        }
        for flag in ("inventory_integration_enabled", "accounting_integration_enabled", "supplier_delivery_enabled"):
            values[flag] = bool(values.get(flag, False))
        return values

    @staticmethod
    def get_active_configuration(tenant_id: uuid.UUID | str, environment: str) -> ProcurementConfiguration:
        config = (
            ProcurementConfiguration.objects.for_tenant(_uuid(tenant_id, "tenant_id"))
            .filter(environment=environment, status=ConfigurationStatus.ACTIVE)
            .first()
        )
        if config is None:
            raise ConfigurationUnavailable(f"No active {environment} procurement configuration")
        return config

    @staticmethod
    def list_versions(tenant_id: uuid.UUID | str, environment: str) -> QuerySet[ProcurementConfiguration]:
        return (
            ProcurementConfiguration.objects.for_tenant(_uuid(tenant_id, "tenant_id"))
            .filter(environment=environment)
            .order_by("-version")
        )

    @staticmethod
    def get_version(tenant_id: uuid.UUID | str, configuration_id: uuid.UUID | str) -> ProcurementConfiguration:
        try:
            return ProcurementConfiguration.objects.for_tenant(_uuid(tenant_id, "tenant_id")).get(
                pk=_uuid(configuration_id, "configuration_id")
            )
        except ProcurementConfiguration.DoesNotExist as exc:
            raise ProcurementNotFound("Configuration version was not found") from exc

    @staticmethod
    @transaction.atomic
    def create_draft(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        environment: str,
        data: Mapping[str, Any],
        correlation_id: str,
    ) -> ProcurementConfiguration:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        if environment not in ConfigurationEnvironment.values:
            raise ProcurementValidationError("Invalid environment")
        values = ProcurementConfigurationService._validate(data)
        latest = (
            ProcurementConfiguration.objects.for_tenant(tenant)
            .filter(environment=environment)
            .aggregate(value=models.Max("version"))["value"]
            or 0
        )
        config = ProcurementConfiguration.objects.create(
            tenant_id=tenant, created_by=actor, updated_by=actor, environment=environment, version=latest + 1, **values
        )
        _event(tenant, config, "purchase.configuration.draft-created.v1", actor_id=actor, correlation_id=correlation_id)
        return config

    @staticmethod
    @transaction.atomic
    def update_draft(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        configuration_id: uuid.UUID | str,
        data: Mapping[str, Any],
        expected_lock_version: int,
        correlation_id: str,
    ) -> ProcurementConfiguration:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        config = (
            ProcurementConfiguration.objects.for_tenant(tenant)
            .select_for_update()
            .get(pk=_uuid(configuration_id, "configuration_id"))
        )
        _assert_version(config, expected_lock_version)
        if config.status != ConfigurationStatus.DRAFT:
            raise ProcurementConflict("Only draft configurations are editable")
        merged = {
            field.name: getattr(config, field.name)
            for field in ProcurementConfiguration._meta.fields
            if field.name
            not in {
                "id",
                "tenant_id",
                "created_at",
                "updated_at",
                "created_by",
                "updated_by",
                "lock_version",
                "environment",
                "version",
                "status",
                "activated_at",
                "activated_by",
            }
        }
        merged.update(data)
        validated = ProcurementConfigurationService._validate(merged)
        before = {
            field: (
                str(getattr(config, field)) if isinstance(getattr(config, field), Decimal) else getattr(config, field)
            )
            for field in validated
        }
        for field, value in validated.items():
            setattr(config, field, value)
        _save_mutation(config, actor, validated.keys())
        after = {
            field: (
                str(getattr(config, field)) if isinstance(getattr(config, field), Decimal) else getattr(config, field)
            )
            for field in validated
        }
        _event(
            tenant,
            config,
            "purchase.configuration.draft-updated.v1",
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"before": before, "after": after},
        )
        return config

    @staticmethod
    def preview_configuration(
        tenant_id: uuid.UUID | str,
        environment: str,
        data: Mapping[str, Any],
        simulations: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        tenant = _uuid(tenant_id, "tenant_id")
        validated = ProcurementConfigurationService._validate(data)
        active = (
            ProcurementConfiguration.objects.for_tenant(tenant)
            .filter(environment=environment, status=ConfigurationStatus.ACTIVE)
            .first()
        )
        diff = [
            {"field": key, "before": getattr(active, key, None), "after": value}
            for key, value in validated.items()
            if getattr(active, key, None) != value
        ]
        outcomes = []
        for simulation in simulations or []:
            amount = _decimal(simulation.get("amount", 0), "simulation.amount")
            matching = [
                rule
                for rule in validated["approval_rules"]
                if amount >= Decimal(str(rule.get("minimum_amount", 0)))
                and (rule.get("maximum_amount") is None or amount <= Decimal(str(rule["maximum_amount"])))
            ]
            outcomes.append({"input": dict(simulation), "approval_required": bool(matching), "matched_rules": matching})
        return {
            "valid": True,
            "diff": diff,
            "affected_workflows": sorted(
                {
                    (
                        "approvals"
                        if key == "approval_rules"
                        else (
                            "receipts"
                            if key == "receipt_tolerance_percent"
                            else "rfqs" if key in {"minimum_rfq_suppliers", "quote_scoring_weights"} else "integrations"
                        )
                    )
                    for key in validated
                }
            ),
            "simulations": outcomes,
            "restart_required": False,
        }

    @staticmethod
    @transaction.atomic
    def activate_configuration(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        configuration_id: uuid.UUID | str,
        reason: str,
        correlation_id: str,
    ) -> ProcurementConfiguration:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        config = (
            ProcurementConfiguration.objects.for_tenant(tenant)
            .select_for_update()
            .get(pk=_uuid(configuration_id, "configuration_id"))
        )
        if config.status != ConfigurationStatus.DRAFT:
            raise ProcurementConflict("Only draft configurations may be activated")
        prior = (
            ProcurementConfiguration.objects.for_tenant(tenant)
            .select_for_update()
            .filter(environment=config.environment, status=ConfigurationStatus.ACTIVE)
            .first()
        )
        if prior:
            ProcurementConfiguration.objects.for_tenant(tenant).filter(pk=prior.pk).update(
                status=ConfigurationStatus.ARCHIVED, updated_by=actor, lock_version=prior.lock_version + 1
            )
        ProcurementConfiguration.objects.for_tenant(tenant).filter(pk=config.pk).update(
            status=ConfigurationStatus.ACTIVE,
            activated_at=timezone.now(),
            activated_by=actor,
            updated_by=actor,
            lock_version=config.lock_version + 1,
        )
        config.refresh_from_db()
        _event(
            tenant,
            config,
            "purchase.configuration.activated.v1",
            actor_id=actor,
            correlation_id=correlation_id,
            payload={
                "prior_version": prior.version if prior else None,
                "new_version": config.version,
                "environment": config.environment,
                "reason": _text(reason, "reason"),
            },
        )
        return config

    @staticmethod
    @transaction.atomic
    def rollback_configuration(
        tenant_id: uuid.UUID | str,
        actor_id: uuid.UUID | str,
        configuration_id: uuid.UUID | str,
        reason: str,
        correlation_id: str,
    ) -> ProcurementConfiguration:
        source = ProcurementConfigurationService.get_version(tenant_id, configuration_id)
        fields = {
            field.name: getattr(source, field.name)
            for field in ProcurementConfiguration._meta.fields
            if field.name
            not in {
                "id",
                "tenant_id",
                "created_at",
                "updated_at",
                "created_by",
                "updated_by",
                "lock_version",
                "environment",
                "version",
                "status",
                "activated_at",
                "activated_by",
            }
        }
        draft = ProcurementConfigurationService.create_draft(
            tenant_id, actor_id, source.environment, fields, correlation_id
        )
        return ProcurementConfigurationService.activate_configuration(
            tenant_id, actor_id, draft.id, reason, correlation_id
        )

    @staticmethod
    def export_configuration(
        tenant_id: uuid.UUID | str, environment: str, version: int | None = None
    ) -> dict[str, Any]:
        qs = ProcurementConfiguration.objects.for_tenant(_uuid(tenant_id, "tenant_id")).filter(environment=environment)
        config = qs.get(version=version) if version else qs.get(status=ConfigurationStatus.ACTIVE)
        data = {
            field.name: getattr(config, field.name)
            for field in ProcurementConfiguration._meta.fields
            if field.name
            not in {
                "id",
                "tenant_id",
                "created_at",
                "updated_at",
                "created_by",
                "updated_by",
                "lock_version",
                "activated_by",
            }
        }
        for key, value in list(data.items()):
            if isinstance(value, Decimal):
                data[key] = str(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat()
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
        return {
            "schema": "saraise.purchase.configuration.v1",
            "configuration": data,
            "checksum": f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}",
        }

    @staticmethod
    def import_configuration(
        tenant_id: uuid.UUID | str, actor_id: uuid.UUID | str, document: Mapping[str, Any], correlation_id: str
    ) -> ProcurementConfiguration:
        if document.get("schema") != "saraise.purchase.configuration.v1" or not isinstance(
            document.get("configuration"), dict
        ):
            raise ProcurementValidationError("Unsupported configuration document")
        data = dict(document["configuration"])
        environment = data.pop("environment", None)
        data.pop("version", None)
        data.pop("status", None)
        data.pop("activated_at", None)
        canonical = json.dumps(document["configuration"], sort_keys=True, separators=(",", ":"), default=str)
        if document.get("checksum") != f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}":
            raise ProcurementValidationError("Configuration checksum does not match")
        return ProcurementConfigurationService.create_draft(tenant_id, actor_id, environment, data, correlation_id)


# Protocol aliases make the paid extension surface explicit without importing
# any optional module ORM model.
class ProcurementIntegrationAdapter:
    def deliver(self, tenant_id: uuid.UUID, payload: Mapping[str, Any], correlation_id: str) -> Mapping[str, Any]:
        raise NotImplementedError
