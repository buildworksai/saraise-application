"""
Service tests for Purchase Management module.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.modules.purchase_management.models import (
    ConfigurationEnvironment,
    ConfigurationStatus,
    ProcurementConfiguration,
    PurchaseOrder,
    PurchaseOrderStatus,
    PurchaseReceiptLine,
    PurchaseReceiptStatus,
    PurchaseRequisitionStatus,
    QuoteStatus,
    RFQInvitation,
    RFQInvitationStatus,
    RFQLine,
    RFQStatus,
    Supplier,
    SupplierStatus,
)
from src.modules.purchase_management.services import (
    ConfigurationUnavailable,
    ProcurementConfigurationService,
    ProcurementConflict,
    ProcurementNotFound,
    ProcurementValidationError,
    PurchaseOrderService,
    PurchaseReceiptService,
    QuoteService,
    RequisitionService,
    RFQService,
    SupplierService,
    _assert_version,
    _currency,
    _decimal,
    _same_tenant,
    _text,
    _uuid,
)
from src.modules.purchase_management.tests.factories import (
    ProcurementConfigurationFactory,
    PurchaseOrderFactory,
    PurchaseOrderLineFactory,
    PurchaseReceiptFactory,
    PurchaseReceiptLineFactory,
    PurchaseRequisitionFactory,
    PurchaseRequisitionLineFactory,
    RequestForQuotationFactory,
    RFQLineFactory,
    SupplierFactory,
    SupplierQuoteFactory,
    SupplierQuoteLineFactory,
)


def _line(**overrides):
    values = {
        "item_code": "ITEM-001",
        "description": "Procured item",
        "quantity": Decimal("2.000000"),
        "estimated_unit_price": Decimal("10.0000"),
    }
    values.update(overrides)
    return values


def _order_line(**overrides):
    values = {
        "item_code": "ITEM-001",
        "item_name": "Procured item",
        "quantity": Decimal("2.000000"),
        "unit_price": Decimal("10.0000"),
        "tax_amount": Decimal("1.0000"),
    }
    values.update(overrides)
    return values


def _config_data(**overrides):
    values = {
        "default_currency": "USD",
        "default_payment_terms": "Net 30",
        "supplier_code_prefix": "SUP",
        "requisition_prefix": "PR",
        "rfq_prefix": "RFQ",
        "po_prefix": "PO",
        "receipt_prefix": "GRN",
        "approval_rules": [{"minimum_amount": "100.00", "approver_permission": "purchase.approve"}],
        "receipt_tolerance_percent": Decimal("5.00"),
        "minimum_rfq_suppliers": 2,
        "quote_scoring_weights": {"price": 50, "delivery": 20, "quality": 20, "service": 10},
        "inventory_integration_enabled": False,
        "accounting_integration_enabled": False,
        "supplier_delivery_enabled": False,
        "rollout": {"roles": ["buyer"], "cohorts": [], "percentage": 100},
    }
    values.update(overrides)
    return values


def test_procurement_value_helpers_fail_closed_and_preserve_error_details():
    tenant_id = uuid.uuid4()
    assert _uuid(str(tenant_id), "tenant_id") == tenant_id
    assert _text("  Supplier  ", "supplier_name", maximum=20) == "Supplier"
    assert _currency("usd") == "USD"
    assert _decimal("12.34", "amount") == Decimal("12.34")
    assert _decimal("0", "amount") == Decimal("0")

    with pytest.raises(ProcurementValidationError):
        _uuid("bad", "tenant_id")
    with pytest.raises(ProcurementValidationError):
        _text("   ", "supplier_name")
    with pytest.raises(ProcurementValidationError):
        _text("abcd", "code", maximum=3)
    with pytest.raises(ProcurementValidationError):
        _currency("US1")
    with pytest.raises(ProcurementValidationError):
        _decimal("-0.01", "amount")
    with pytest.raises(ProcurementValidationError):
        _decimal("0", "amount", strictly_positive=True)

    versioned = type("Versioned", (), {"lock_version": 3})()
    _assert_version(versioned, 3)
    with pytest.raises(ProcurementConflict) as exc:
        _assert_version(versioned, 2)
    assert exc.value.detail == {"expected_lock_version": 2, "actual_lock_version": 3}


@pytest.mark.django_db
def test_same_tenant_guard_hides_cross_tenant_objects_as_not_found():
    tenant_id = uuid.uuid4()
    foreign = SupplierFactory()

    _same_tenant(foreign.tenant_id, "Supplier", foreign)
    _same_tenant(tenant_id, "Supplier", None)
    with pytest.raises(ProcurementNotFound):
        _same_tenant(tenant_id, "Supplier", foreign)


@pytest.mark.django_db
class TestSupplierService:
    """Test SupplierService."""

    def test_create_supplier(self):
        """Test creating a supplier via service."""
        tenant_id = uuid.uuid4()
        supplier = SupplierService.create_supplier(
            tenant_id=str(tenant_id),
            supplier_code="SUP-001",
            supplier_name="Test Supplier",
        )

        assert supplier.supplier_code == "SUP-001"
        assert supplier.supplier_name == "Test Supplier"
        assert str(supplier.tenant_id) == str(tenant_id)

    def test_update_supplier_stale_version_leaves_row_unchanged(self):
        supplier = SupplierFactory()

        with pytest.raises(ProcurementConflict) as exc:
            SupplierService.update_supplier(
                supplier.tenant_id,
                supplier.created_by,
                supplier.id,
                {"supplier_name": "Changed"},
                expected_lock_version=supplier.lock_version + 1,
                correlation_id="corr",
            )

        assert exc.value.detail == {
            "expected_lock_version": supplier.lock_version + 1,
            "actual_lock_version": supplier.lock_version,
        }
        supplier.refresh_from_db()
        assert supplier.supplier_name != "Changed"

    def test_archived_supplier_is_immutable_until_restored(self):
        supplier = SupplierFactory(archived=True)

        with pytest.raises(ProcurementConflict):
            SupplierService.update_supplier(
                supplier.tenant_id,
                supplier.created_by,
                supplier.id,
                {"supplier_name": "Changed"},
                expected_lock_version=supplier.lock_version,
                correlation_id="corr",
            )

        restored = SupplierService.restore_supplier(
            supplier.tenant_id,
            supplier.created_by,
            supplier.id,
            "Vendor reinstated",
            "restore-supplier",
            "corr",
        )
        assert restored.status == SupplierStatus.ACTIVE

    def test_list_suppliers_filters_and_searches_inside_tenant(self):
        tenant_id = uuid.uuid4()
        SupplierFactory(tenant_id=tenant_id, supplier_code="ACME-1", supplier_name="Acme Tools", email="ops@acme.io")
        SupplierFactory(tenant_id=tenant_id, supplier_code="OTHER", supplier_name="Other", currency="EUR")
        SupplierFactory(supplier_code="ACME-FOREIGN", supplier_name="Acme Foreign")

        suppliers = list(
            SupplierService.list_suppliers(
                tenant_id,
                {"status": SupplierStatus.ACTIVE, "currency": "usd", "search": "acme"},
            )
        )

        assert [supplier.supplier_code for supplier in suppliers] == ["ACME-1"]

    def test_update_supplier_rejects_unknown_fields_before_mutation(self):
        supplier = SupplierFactory()

        with pytest.raises(ProcurementValidationError) as exc:
            SupplierService.update_supplier(
                supplier.tenant_id,
                supplier.created_by,
                supplier.id,
                {"status": SupplierStatus.INACTIVE},
                supplier.lock_version,
                "corr",
            )

        assert exc.value.detail == {"fields": ["status"]}
        supplier.refresh_from_db()
        assert supplier.status == SupplierStatus.ACTIVE


@pytest.mark.django_db
class TestPurchaseOrderService:
    """Test PurchaseOrderService."""

    def test_create_purchase_order(self):
        """Test creating a purchase order via service."""
        tenant_id = uuid.uuid4()
        supplier = Supplier.objects.create(
            tenant_id=tenant_id,
            supplier_code="SUP-001",
            supplier_name="Test Supplier",
        )

        po = PurchaseOrderService.create_purchase_order(
            tenant_id=str(tenant_id),
            supplier_id=str(supplier.id),
            po_date=date(2024, 1, 1),
        )

        assert po.supplier == supplier
        assert str(po.tenant_id) == str(tenant_id)

    def test_create_purchase_order_rejects_inactive_supplier(self):
        supplier = SupplierFactory(inactive=True)

        with pytest.raises(ProcurementValidationError):
            PurchaseOrderService.create_purchase_order(
                supplier.tenant_id,
                supplier.created_by,
                {"supplier_id": supplier.id, "po_date": date(2024, 1, 1), "currency": "USD"},
                "corr",
            )

    def test_order_creator_cannot_approve_own_order(self):
        order = PurchaseOrderFactory(pending_approval=True)

        with pytest.raises(ProcurementValidationError):
            PurchaseOrderService.approve_purchase_order(order.tenant_id, order.created_by, order.id, "corr")

        order.refresh_from_db()
        assert order.status == "pending_approval"

    def test_create_order_rejects_requisition_line_from_different_requisition(self):
        requisition = PurchaseRequisitionFactory(approved=True)
        foreign_line = PurchaseRequisitionLineFactory(tenant_id=requisition.tenant_id)
        supplier = SupplierFactory(tenant_id=requisition.tenant_id)

        with pytest.raises(ProcurementNotFound):
            PurchaseOrderService.create_purchase_order(
                requisition.tenant_id,
                requisition.created_by,
                {
                    "po_number": "PO-BAD-REQ-LINE",
                    "po_date": date(2024, 1, 10),
                    "supplier_id": supplier.id,
                    "requisition_id": requisition.id,
                    "currency": "USD",
                    "payment_terms": "Net 30",
                    "lines": [_order_line(requisition_line_id=foreign_line.id)],
                },
                "corr",
            )

        assert not PurchaseOrder.objects.filter(tenant_id=requisition.tenant_id, po_number="PO-BAD-REQ-LINE").exists()

    def test_create_order_rejects_quote_line_from_different_quote(self):
        quote = SupplierQuoteFactory(submitted=True)
        foreign_quote_line = SupplierQuoteLineFactory(tenant_id=quote.tenant_id)

        with pytest.raises(ProcurementNotFound):
            PurchaseOrderService.create_purchase_order(
                quote.tenant_id,
                quote.created_by,
                {
                    "po_number": "PO-BAD-QUOTE-LINE",
                    "po_date": date(2024, 1, 10),
                    "supplier_id": quote.supplier_id,
                    "accepted_quote_id": quote.id,
                    "currency": quote.currency,
                    "payment_terms": quote.payment_terms,
                    "lines": [_order_line(quote_line_id=foreign_quote_line.id)],
                },
                "corr",
            )

        assert not PurchaseOrder.objects.filter(tenant_id=quote.tenant_id, po_number="PO-BAD-QUOTE-LINE").exists()

    def test_order_lifecycle_dispatch_is_idempotent_and_cancel_guarded(self):
        approver = uuid.uuid4()
        order = PurchaseOrderFactory(approved=True, approved_by=approver)
        line = PurchaseOrderLineFactory(tenant_id=order.tenant_id, purchase_order=order)

        dispatched, job = PurchaseOrderService.dispatch_purchase_order(
            order.tenant_id, order.created_by, order.id, "dispatch-key", "corr"
        )
        repeated, repeated_job = PurchaseOrderService.dispatch_purchase_order(
            order.tenant_id, order.created_by, order.id, "dispatch-key", "corr"
        )

        assert dispatched.status == PurchaseOrderStatus.SENT
        assert dispatched.dispatch_status == "queued"
        assert repeated.id == dispatched.id
        assert repeated_job.id == job.id
        assert AsyncJob.objects.filter(id=job.id, command="purchase.order.dispatch.v1").exists()

        acknowledged = PurchaseOrderService.acknowledge_purchase_order(
            order.tenant_id, order.created_by, order.id, "corr"
        )
        receipt = PurchaseReceiptFactory(tenant_id=order.tenant_id, purchase_order=acknowledged)
        PurchaseReceiptLine.objects.create(
            tenant_id=order.tenant_id,
            created_by=order.created_by,
            updated_by=order.created_by,
            purchase_receipt=receipt,
            purchase_order_line=line,
            line_number=1,
            item_id=line.item_id,
            quantity_received=Decimal("2.000000"),
        )
        ProcurementConfigurationFactory(tenant_id=order.tenant_id, active=True, receipt_tolerance_percent=Decimal("0"))
        completed = PurchaseReceiptService.complete_receipt(
            order.tenant_id, order.created_by, receipt.id, "receipt-key", "corr"
        )

        assert completed.status == PurchaseReceiptStatus.COMPLETED
        order.refresh_from_db()
        assert order.status == PurchaseOrderStatus.RECEIVED
        with pytest.raises(ProcurementConflict):
            PurchaseOrderService.cancel_purchase_order(order.tenant_id, order.created_by, order.id, "corr")

    def test_delete_draft_purchase_order_requires_matching_version_and_no_receipts(self):
        order = PurchaseOrderFactory()
        PurchaseReceiptFactory(tenant_id=order.tenant_id, purchase_order=order)

        with pytest.raises(ProcurementConflict):
            PurchaseOrderService.delete_draft_purchase_order(
                order.tenant_id, order.created_by, order.id, order.lock_version, "corr"
            )

        order.refresh_from_db()
        assert order.deleted_at is None


@pytest.mark.django_db
def test_requisition_submit_requires_at_least_one_line():
    requisition = PurchaseRequisitionFactory()

    with pytest.raises(ProcurementValidationError):
        RequisitionService.submit_requisition(requisition.tenant_id, requisition.created_by, requisition.id, "corr")

    requisition.refresh_from_db()
    assert requisition.status == "draft"


@pytest.mark.django_db
def test_requisition_requester_cannot_approve_own_requisition():
    requisition = PurchaseRequisitionFactory(pending_approval=True)
    PurchaseRequisitionLineFactory(tenant_id=requisition.tenant_id, requisition=requisition)

    with pytest.raises(ProcurementValidationError):
        RequisitionService.approve_requisition(requisition.tenant_id, requisition.requested_by, requisition.id, "corr")

    requisition.refresh_from_db()
    assert requisition.status == "pending_approval"


@pytest.mark.django_db
def test_update_requisition_rejects_partial_date_inversion_without_persisting():
    requisition = PurchaseRequisitionFactory(
        requisition_date=date(2024, 1, 10),
        required_date=date(2024, 1, 20),
        purpose="Original",
    )

    with pytest.raises(ProcurementValidationError):
        RequisitionService.update_requisition(
            requisition.tenant_id,
            requisition.created_by,
            requisition.id,
            {"required_date": date(2024, 1, 1), "purpose": "Changed"},
            requisition.lock_version,
            "corr",
        )

    requisition.refresh_from_db()
    assert requisition.required_date == date(2024, 1, 20)
    assert requisition.purpose == "Original"


@pytest.mark.django_db
def test_requisition_create_update_reject_delete_and_convert_paths():
    actor = uuid.uuid4()
    tenant_id = uuid.uuid4()
    requisition = RequisitionService.create_requisition(
        tenant_id,
        actor,
        {
            "requisition_number": " pr-100 ",
            "requisition_date": date(2024, 1, 1),
            "required_date": date(2024, 1, 15),
            "purpose": "Restock",
            "currency": "usd",
            "lines": [_line(), _line(item_code="ITEM-002", quantity=Decimal("1.000000"))],
        },
        "corr",
    )

    assert requisition.requisition_number == "PR-100"
    assert requisition.total_amount == Decimal("30.0000")
    assert requisition.lines.count() == 2
    assert OutboxEvent.objects.filter(
        aggregate_id=requisition.id,
        event_type="purchase.requisition.created.v1",
    ).exists()

    updated = RequisitionService.update_requisition(
        tenant_id,
        actor,
        requisition.id,
        {"purpose": "Restock updated", "lines": [_line(quantity=Decimal("3.000000"))]},
        requisition.lock_version,
        "corr",
    )
    assert updated.total_amount == Decimal("30.0000")
    assert list(updated.lines.values_list("quantity", flat=True)) == [Decimal("3.000000")]

    submitted = RequisitionService.submit_requisition(tenant_id, actor, requisition.id, "corr")
    rejected = RequisitionService.reject_requisition(tenant_id, uuid.uuid4(), submitted.id, "Budget issue", "corr")
    assert rejected.status == PurchaseRequisitionStatus.REJECTED
    assert rejected.rejection_reason == "Budget issue"
    revised = RequisitionService.revise_requisition(tenant_id, actor, rejected.id, "corr")
    deleted = RequisitionService.delete_draft_requisition(tenant_id, actor, revised.id, revised.lock_version, "corr")
    assert deleted.deleted_at is not None

    approved = PurchaseRequisitionFactory(tenant_id=tenant_id, created_by=actor, updated_by=actor, approved=True)
    req_line = PurchaseRequisitionLineFactory(
        tenant_id=tenant_id,
        requisition=approved,
        item_code="ITEM-CONVERT",
        description="Converted item",
        quantity=Decimal("4.000000"),
        estimated_unit_price=Decimal("7.5000"),
    )
    supplier = SupplierFactory(tenant_id=tenant_id)
    converted_order = RequisitionService.convert_to_purchase_order(
        tenant_id,
        actor,
        approved.id,
        supplier.id,
        [
            _order_line(
                requisition_line_id=req_line.id,
                item_code=req_line.item_code,
                item_name=req_line.description,
                quantity=req_line.quantity,
                unit_price=req_line.estimated_unit_price,
            )
        ],
        "corr",
        "convert-key",
    )
    repeated_order = RequisitionService.convert_to_purchase_order(
        tenant_id, actor, approved.id, supplier.id, [], "corr", "convert-key"
    )

    approved.refresh_from_db()
    assert approved.status == PurchaseRequisitionStatus.CONVERTED
    assert repeated_order.id == converted_order.id
    assert converted_order.total_amount == Decimal("31.0000")


@pytest.mark.django_db
def test_rfq_publish_compare_award_and_quote_guards():
    tenant_id = uuid.uuid4()
    actor = uuid.uuid4()
    ProcurementConfigurationFactory(tenant_id=tenant_id, active=True, minimum_rfq_suppliers=2)
    rfq = RFQService.create_rfq(
        tenant_id,
        actor,
        {
            "rfq_number": "rfq-100",
            "title": "Materials",
            "issue_date": date(2024, 1, 1),
            "submission_deadline": timezone.make_aware(timezone.datetime(2024, 1, 5, 12, 0)),
            "currency": "USD",
            "lines": [
                {
                    "item_code": "ITEM-001",
                    "description": "Quoted item",
                    "quantity": Decimal("5.000000"),
                    "required_date": date(2024, 2, 1),
                }
            ],
        },
        "corr",
    )
    suppliers = [SupplierFactory(tenant_id=tenant_id), SupplierFactory(tenant_id=tenant_id)]

    with pytest.raises(ProcurementValidationError):
        RFQService.publish_rfq(tenant_id, actor, rfq.id, [suppliers[0].id], "publish-short", "corr")

    published, job = RFQService.publish_rfq(
        tenant_id,
        actor,
        rfq.id,
        [item.id for item in suppliers],
        "publish",
        "corr",
    )
    assert published.status == RFQStatus.OPEN
    assert job.command == "purchase.rfq.publish.v1"
    assert RFQInvitation.objects.filter(rfq=rfq, status=RFQInvitationStatus.QUEUED).count() == 2

    inactive = SupplierFactory(tenant_id=tenant_id, inactive=True)
    with pytest.raises(ProcurementValidationError):
        QuoteService.create_quote(
            tenant_id,
            actor,
            {
                "quote_number": "QUOTE-INACTIVE",
                "rfq_id": rfq.id,
                "supplier_id": inactive.id,
                "valid_until": timezone.localdate() + timedelta(days=30),
                "currency": "USD",
                "payment_terms": "Net 30",
                "lines": [],
            },
            "corr",
        )

    rfq_line = RFQLine.objects.get(rfq=rfq)
    quote = QuoteService.create_quote(
        tenant_id,
        actor,
        {
            "quote_number": "QUOTE-1",
            "rfq_id": rfq.id,
            "supplier_id": suppliers[0].id,
            "valid_until": timezone.localdate() + timedelta(days=30),
            "currency": "USD",
            "delivery_date": date(2024, 1, 20),
            "payment_terms": "Net 30",
            "shipping_amount": Decimal("2.0000"),
            "lines": [
                {
                    "rfq_line_id": rfq_line.id,
                    "quantity": Decimal("3.000000"),
                    "unit_price": Decimal("10.0000"),
                    "tax_amount": Decimal("1.0000"),
                }
            ],
        },
        "corr",
    )
    assert quote.total_amount == Decimal("33.0000")

    submitted = QuoteService.submit_quote(tenant_id, actor, quote.id, "corr")
    assert submitted.status == QuoteStatus.SUBMITTED
    assert submitted.submitted_at is not None
    comparison = RFQService.compare_quotes(tenant_id, rfq.id)
    assert comparison["quotes"][0]["quote_id"] == str(quote.id)
    assert comparison["quotes"][0]["warnings"] == ["Quality evidence unavailable", "Service evidence unavailable"]

    closed = RFQService.close_rfq(tenant_id, actor, rfq.id, "corr")
    awarded_quote, order = RFQService.award_quote(
        tenant_id,
        actor,
        closed.id,
        quote.id,
        True,
        "award",
        "corr",
    )
    repeated_quote, repeated_order = RFQService.award_quote(
        tenant_id,
        actor,
        closed.id,
        quote.id,
        True,
        "award",
        "corr",
    )

    assert awarded_quote.status == QuoteStatus.ACCEPTED
    assert order is not None
    assert order.accepted_quote_id == quote.id
    assert repeated_quote.id == awarded_quote.id
    assert repeated_order.id == order.id


@pytest.mark.django_db
def test_rfq_update_and_line_linkage_invariants_are_enforced():
    requisition = PurchaseRequisitionFactory(approved=True)
    foreign_line = PurchaseRequisitionLineFactory(tenant_id=requisition.tenant_id)

    with pytest.raises(ProcurementNotFound):
        RFQService.create_rfq(
            requisition.tenant_id,
            requisition.created_by,
            {
                "rfq_number": "RFQ-BAD-LINE",
                "title": "Bad line",
                "requisition_id": requisition.id,
                "issue_date": date(2024, 1, 1),
                "submission_deadline": timezone.make_aware(timezone.datetime(2024, 1, 5, 12, 0)),
                "currency": "USD",
                "lines": [
                    {
                        "requisition_line_id": foreign_line.id,
                        "item_code": "ITEM-001",
                        "description": "Bad line",
                        "quantity": Decimal("1.000000"),
                        "required_date": date(2024, 2, 1),
                    }
                ],
            },
            "corr",
        )

    rfq = RequestForQuotationFactory(
        tenant_id=requisition.tenant_id,
        issue_date=date(2024, 1, 10),
        submission_deadline=timezone.make_aware(timezone.datetime(2024, 1, 20, 12, 0)),
    )
    with pytest.raises(ProcurementValidationError):
        RFQService.update_rfq(
            rfq.tenant_id,
            rfq.created_by,
            rfq.id,
            {"submission_deadline": timezone.make_aware(timezone.datetime(2024, 1, 9, 12, 0))},
            rfq.lock_version,
            "corr",
        )

    rfq.refresh_from_db()
    assert rfq.submission_deadline.date() == date(2024, 1, 20)


@pytest.mark.django_db
def test_receipt_completion_tolerance_inventory_and_legacy_adapter():
    approver = uuid.uuid4()
    receiver = uuid.uuid4()
    order = PurchaseOrderFactory(acknowledged=True, approved_by=approver)
    line = PurchaseOrderLineFactory(
        tenant_id=order.tenant_id,
        purchase_order=order,
        quantity=Decimal("10.000000"),
        received_quantity=Decimal("0.000000"),
    )
    ProcurementConfigurationFactory(
        tenant_id=order.tenant_id,
        active=True,
        receipt_tolerance_percent=Decimal("10.00"),
        inventory_integration_enabled=True,
    )
    over_receipt = PurchaseReceiptFactory(tenant_id=order.tenant_id, purchase_order=order, updated_by=receiver)
    PurchaseReceiptLineFactory(
        tenant_id=order.tenant_id,
        purchase_receipt=over_receipt,
        purchase_order_line=line,
        quantity_received=Decimal("11.500000"),
    )

    with pytest.raises(ProcurementValidationError):
        PurchaseReceiptService.complete_receipt(order.tenant_id, receiver, over_receipt.id, "over", "corr")

    line.refresh_from_db()
    assert line.received_quantity == Decimal("0.000000")

    receipt = PurchaseReceiptFactory(tenant_id=order.tenant_id, purchase_order=order, updated_by=receiver)
    PurchaseReceiptLineFactory(
        tenant_id=order.tenant_id,
        purchase_receipt=receipt,
        purchase_order_line=line,
        quantity_received=Decimal("10.000000"),
    )
    completed = PurchaseReceiptService.process_receipt(receipt)

    assert completed.status == PurchaseReceiptStatus.COMPLETED
    assert completed.inventory_status == "pending"
    assert completed.inventory_job_id is not None
    assert AsyncJob.objects.filter(id=completed.inventory_job_id, command="purchase.inventory.post-receipt.v1").exists()


@pytest.mark.django_db
def test_quote_update_delete_submit_withdraw_and_validation_paths():
    rfq = RequestForQuotationFactory(open=True, currency="USD")
    rfq_line = RFQLineFactory(tenant_id=rfq.tenant_id, rfq=rfq, quantity=Decimal("5.000000"))
    supplier = SupplierFactory(tenant_id=rfq.tenant_id)
    quote = QuoteService.create_quote(
        rfq.tenant_id,
        rfq.created_by,
        {
            "quote_number": "QUOTE-LIFE",
            "rfq_id": rfq.id,
            "supplier_id": supplier.id,
            "valid_until": timezone.localdate() + timedelta(days=10),
            "currency": "USD",
            "payment_terms": "Net 30",
            "shipping_amount": Decimal("1.0000"),
            "lines": [
                {
                    "rfq_line_id": rfq_line.id,
                    "quantity": Decimal("2.000000"),
                    "unit_price": Decimal("8.0000"),
                    "tax_amount": Decimal("2.0000"),
                }
            ],
        },
        "corr",
    )

    updated = QuoteService.update_quote(
        rfq.tenant_id,
        rfq.created_by,
        quote.id,
        {"shipping_amount": Decimal("3.0000"), "supplier_notes": "Updated"},
        quote.lock_version,
        "corr",
    )
    assert updated.total_amount == Decimal("21.0000")
    assert updated.supplier_notes == "Updated"

    submitted = QuoteService.submit_quote(rfq.tenant_id, rfq.created_by, quote.id, "corr")
    withdrawn = QuoteService.withdraw_quote(rfq.tenant_id, rfq.created_by, submitted.id, "corr")
    assert withdrawn.status == QuoteStatus.WITHDRAWN

    draft = SupplierQuoteFactory(tenant_id=rfq.tenant_id, rfq=rfq, supplier=supplier)
    with pytest.raises(ProcurementConflict):
        QuoteService.delete_draft_quote(rfq.tenant_id, rfq.created_by, withdrawn.id, withdrawn.lock_version, "corr")
    with pytest.raises(ProcurementConflict):
        QuoteService.delete_draft_quote(rfq.tenant_id, rfq.created_by, draft.id, draft.lock_version + 1, "corr")

    deleted_id = draft.id
    deleted = QuoteService.delete_draft_quote(rfq.tenant_id, rfq.created_by, draft.id, draft.lock_version, "corr")
    assert deleted.quote_number == draft.quote_number
    assert not SupplierQuoteFactory._meta.model.objects.filter(id=deleted_id).exists()
    assert OutboxEvent.objects.filter(aggregate_id=deleted_id, event_type="purchase.quote.deleted.v1").exists()

    with pytest.raises(ProcurementValidationError):
        QuoteService.create_quote(
            rfq.tenant_id,
            rfq.created_by,
            {
                "quote_number": "QUOTE-BAD-CURRENCY",
                "rfq_id": rfq.id,
                "supplier_id": supplier.id,
                "valid_until": timezone.localdate() + timedelta(days=10),
                "currency": "EUR",
                "payment_terms": "Net 30",
                "lines": [],
            },
            "corr",
        )
    with pytest.raises(ProcurementValidationError):
        QuoteService.create_quote(
            rfq.tenant_id,
            rfq.created_by,
            {
                "quote_number": "QUOTE-BAD-QTY",
                "rfq_id": rfq.id,
                "supplier_id": supplier.id,
                "valid_until": timezone.localdate() + timedelta(days=10),
                "currency": "USD",
                "payment_terms": "Net 30",
                "lines": [
                    {
                        "rfq_line_id": rfq_line.id,
                        "quantity": Decimal("6.000000"),
                        "unit_price": Decimal("1.0000"),
                    }
                ],
            },
            "corr",
        )


@pytest.mark.django_db
def test_receipt_create_update_delete_cancel_and_relationship_guards():
    order = PurchaseOrderFactory(acknowledged=True)
    order_line = PurchaseOrderLineFactory(tenant_id=order.tenant_id, purchase_order=order)
    foreign_line = PurchaseOrderLineFactory(tenant_id=order.tenant_id)
    warehouse_id = uuid.uuid4()

    with pytest.raises(ProcurementNotFound):
        PurchaseReceiptService.create_receipt(
            order.tenant_id,
            order.created_by,
            {
                "receipt_number": "GRN-BAD-LINE",
                "receipt_date": date(2024, 1, 20),
                "purchase_order_id": order.id,
                "warehouse_id": warehouse_id,
                "lines": [{"purchase_order_line_id": foreign_line.id, "quantity_received": Decimal("1.000000")}],
            },
            "corr",
        )

    receipt = PurchaseReceiptService.create_receipt(
        order.tenant_id,
        order.created_by,
        {
            "receipt_number": "GRN-LIFE",
            "receipt_date": date(2024, 1, 20),
            "purchase_order_id": order.id,
            "warehouse_id": warehouse_id,
            "lines": [
                {
                    "purchase_order_line_id": order_line.id,
                    "quantity_received": Decimal("1.000000"),
                    "condition": "damaged",
                    "batch_no": "B-1",
                    "serial_no": "S-1",
                }
            ],
        },
        "corr",
    )
    assert receipt.lines.get().condition == "damaged"
    assert OutboxEvent.objects.filter(aggregate_id=receipt.id, event_type="purchase.receipt.created.v1").exists()

    new_warehouse = uuid.uuid4()
    updated = PurchaseReceiptService.update_receipt(
        order.tenant_id,
        order.created_by,
        receipt.id,
        {"warehouse_id": new_warehouse, "receipt_date": date(2024, 1, 21)},
        receipt.lock_version,
        "corr",
    )
    assert updated.warehouse_id == new_warehouse
    assert updated.receipt_date == date(2024, 1, 21)

    with pytest.raises(ProcurementConflict):
        PurchaseReceiptService.delete_draft_receipt(
            order.tenant_id, order.created_by, receipt.id, updated.lock_version + 1, "corr"
        )

    deleted_id = receipt.id
    PurchaseReceiptService.delete_draft_receipt(
        order.tenant_id,
        order.created_by,
        receipt.id,
        updated.lock_version,
        "corr",
    )
    assert not PurchaseReceiptFactory._meta.model.objects.filter(id=deleted_id).exists()

    cancellable = PurchaseReceiptFactory(tenant_id=order.tenant_id, purchase_order=order)
    cancelled = PurchaseReceiptService.cancel_receipt(order.tenant_id, order.created_by, cancellable.id, "corr")
    assert cancelled.status == PurchaseReceiptStatus.CANCELLED
    with pytest.raises(ProcurementConflict):
        PurchaseReceiptService.complete_receipt(order.tenant_id, order.created_by, cancellable.id, "complete", "corr")


@pytest.mark.django_db
def test_configuration_lifecycle_preview_export_import_and_rollback():
    tenant_id = uuid.uuid4()
    actor = uuid.uuid4()

    with pytest.raises(ConfigurationUnavailable):
        ProcurementConfigurationService.get_active_configuration(tenant_id, ConfigurationEnvironment.DEVELOPMENT)

    draft = ProcurementConfigurationService.create_draft(
        tenant_id, actor, ConfigurationEnvironment.DEVELOPMENT, _config_data(), "corr"
    )
    assert draft.version == 1
    preview = ProcurementConfigurationService.preview_configuration(
        tenant_id,
        ConfigurationEnvironment.DEVELOPMENT,
        _config_data(receipt_tolerance_percent=Decimal("8.00")),
        [{"amount": "125.00"}],
    )
    assert preview["valid"] is True
    assert preview["simulations"][0]["approval_required"] is True
    assert "receipts" in preview["affected_workflows"]

    active = ProcurementConfigurationService.activate_configuration(tenant_id, actor, draft.id, "initial", "corr")
    assert active.status == ConfigurationStatus.ACTIVE
    exported = ProcurementConfigurationService.export_configuration(tenant_id, ConfigurationEnvironment.DEVELOPMENT)
    imported = ProcurementConfigurationService.import_configuration(tenant_id, actor, exported, "corr")
    assert imported.status == ConfigurationStatus.DRAFT
    assert imported.version == 2

    updated = ProcurementConfigurationService.update_draft(
        tenant_id,
        actor,
        imported.id,
        _config_data(minimum_rfq_suppliers=3),
        imported.lock_version,
        "corr",
    )
    rolled_back = ProcurementConfigurationService.rollback_configuration(
        tenant_id,
        actor,
        active.id,
        "rollback",
        "corr",
    )

    updated.refresh_from_db()
    assert updated.status == ConfigurationStatus.DRAFT
    assert rolled_back.status == ConfigurationStatus.ACTIVE
    assert rolled_back.version == 3
    assert ProcurementConfiguration.objects.filter(tenant_id=tenant_id, status=ConfigurationStatus.ACTIVE).count() == 1
