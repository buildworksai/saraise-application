"""Tenant-consistent factories for every purchase-management aggregate.

Factories deliberately expose ``tenant_id`` so isolation tests can build two
complete, related graphs without disabling model validation or tenancy guards.
Lifecycle states are selected with factory-boy traits (for example,
``PurchaseOrderFactory(approved=True)``).
"""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import factory
from django.utils import timezone

from src.modules.purchase_management import models


class TenantModelFactory(factory.django.DjangoModelFactory):
    """Base factory whose related objects can inherit one tenant UUID."""

    class Meta:
        abstract = True

    tenant_id = factory.LazyFunction(uuid4)
    created_by = factory.LazyFunction(uuid4)
    updated_by = factory.SelfAttribute("created_by")


class SupplierFactory(TenantModelFactory):
    class Meta:
        model = models.Supplier

    supplier_code = factory.Sequence(lambda n: f"SUP-{n:06d}")
    supplier_name = factory.Sequence(lambda n: f"Supplier {n}")

    class Params:
        inactive = factory.Trait(status=models.SupplierStatus.INACTIVE)
        archived = factory.Trait(
            status=models.SupplierStatus.ARCHIVED,
            archived_at=factory.LazyFunction(timezone.now),
            archived_by=factory.LazyFunction(uuid4),
        )


class PurchaseRequisitionFactory(TenantModelFactory):
    class Meta:
        model = models.PurchaseRequisition

    requisition_number = factory.Sequence(lambda n: f"PR-{n:06d}")
    requisition_date = factory.LazyFunction(timezone.localdate)
    required_date = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=14))

    class Params:
        pending_approval = factory.Trait(status=models.PurchaseRequisitionStatus.PENDING_APPROVAL)
        approved = factory.Trait(
            status=models.PurchaseRequisitionStatus.APPROVED,
            approved_by=factory.LazyFunction(uuid4),
            approved_at=factory.LazyFunction(timezone.now),
        )
        rejected = factory.Trait(status=models.PurchaseRequisitionStatus.REJECTED, rejection_reason="Budget rejected")
        converted = factory.Trait(
            status=models.PurchaseRequisitionStatus.CONVERTED, converted_order_id=factory.LazyFunction(uuid4)
        )
        cancelled = factory.Trait(status=models.PurchaseRequisitionStatus.CANCELLED)


class PurchaseRequisitionLineFactory(TenantModelFactory):
    class Meta:
        model = models.PurchaseRequisitionLine

    requisition = factory.SubFactory(PurchaseRequisitionFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    line_number = factory.Sequence(lambda n: n + 1)
    item_code = factory.Sequence(lambda n: f"ITEM-{n:06d}")
    description = "Factory test item"
    quantity = Decimal("2.000000")
    estimated_unit_price = Decimal("12.5000")
    estimated_total = Decimal("25.0000")


class RequestForQuotationFactory(TenantModelFactory):
    class Meta:
        model = models.RequestForQuotation

    rfq_number = factory.Sequence(lambda n: f"RFQ-{n:06d}")
    title = factory.Sequence(lambda n: f"Request for quotation {n}")
    issue_date = factory.LazyFunction(timezone.localdate)
    submission_deadline = factory.LazyFunction(lambda: timezone.now() + timedelta(days=7))

    class Params:
        open = factory.Trait(status=models.RFQStatus.OPEN)
        closed = factory.Trait(status=models.RFQStatus.CLOSED)
        awarded = factory.Trait(status=models.RFQStatus.AWARDED, awarded_quote_id=factory.LazyFunction(uuid4))
        cancelled = factory.Trait(status=models.RFQStatus.CANCELLED)


class RFQLineFactory(TenantModelFactory):
    class Meta:
        model = models.RFQLine

    rfq = factory.SubFactory(RequestForQuotationFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    line_number = factory.Sequence(lambda n: n + 1)
    item_code = factory.Sequence(lambda n: f"ITEM-{n:06d}")
    description = "Factory RFQ item"
    quantity = Decimal("2.000000")
    required_date = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=21))


class RFQInvitationFactory(TenantModelFactory):
    class Meta:
        model = models.RFQInvitation

    rfq = factory.SubFactory(RequestForQuotationFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    supplier = factory.SubFactory(SupplierFactory, tenant_id=factory.SelfAttribute("..tenant_id"))

    class Params:
        queued = factory.Trait(status=models.RFQInvitationStatus.QUEUED, job_id=factory.LazyFunction(uuid4))
        sent = factory.Trait(status=models.RFQInvitationStatus.SENT, sent_at=factory.LazyFunction(timezone.now))
        delivered = factory.Trait(
            status=models.RFQInvitationStatus.DELIVERED, delivered_at=factory.LazyFunction(timezone.now)
        )
        failed = factory.Trait(status=models.RFQInvitationStatus.FAILED, failure_code="DELIVERY_FAILED")


class SupplierQuoteFactory(TenantModelFactory):
    class Meta:
        model = models.SupplierQuote

    quote_number = factory.Sequence(lambda n: f"QUOTE-{n:06d}")
    rfq = factory.SubFactory(RequestForQuotationFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    supplier = factory.SubFactory(SupplierFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    valid_until = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=30))
    currency = "USD"

    class Params:
        submitted = factory.Trait(status=models.QuoteStatus.SUBMITTED, submitted_at=factory.LazyFunction(timezone.now))
        accepted = factory.Trait(status=models.QuoteStatus.ACCEPTED)
        rejected = factory.Trait(status=models.QuoteStatus.REJECTED)
        withdrawn = factory.Trait(status=models.QuoteStatus.WITHDRAWN)


class SupplierQuoteLineFactory(TenantModelFactory):
    class Meta:
        model = models.SupplierQuoteLine

    quote = factory.SubFactory(SupplierQuoteFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    rfq_line = factory.SubFactory(RFQLineFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    quantity = Decimal("2.000000")
    unit_price = Decimal("12.5000")
    line_total = Decimal("25.0000")


class PurchaseOrderFactory(TenantModelFactory):
    class Meta:
        model = models.PurchaseOrder

    po_number = factory.Sequence(lambda n: f"PO-{n:06d}")
    po_date = factory.LazyFunction(timezone.localdate)
    supplier = factory.SubFactory(SupplierFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    currency = "USD"

    class Params:
        pending_approval = factory.Trait(status=models.PurchaseOrderStatus.PENDING_APPROVAL)
        approved = factory.Trait(
            status=models.PurchaseOrderStatus.APPROVED,
            approved_by=factory.LazyFunction(uuid4),
            approved_at=factory.LazyFunction(timezone.now),
        )
        sent = factory.Trait(status=models.PurchaseOrderStatus.SENT, dispatch_status="sent")
        acknowledged = factory.Trait(
            status=models.PurchaseOrderStatus.ACKNOWLEDGED, acknowledged_at=factory.LazyFunction(timezone.now)
        )
        partially_received = factory.Trait(status=models.PurchaseOrderStatus.PARTIALLY_RECEIVED)
        received = factory.Trait(status=models.PurchaseOrderStatus.RECEIVED)
        cancelled = factory.Trait(status=models.PurchaseOrderStatus.CANCELLED)


class PurchaseOrderLineFactory(TenantModelFactory):
    class Meta:
        model = models.PurchaseOrderLine

    purchase_order = factory.SubFactory(PurchaseOrderFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    line_number = factory.Sequence(lambda n: n + 1)
    item_code = factory.Sequence(lambda n: f"ITEM-{n:06d}")
    item_name = "Factory purchase item"
    quantity = Decimal("2.000000")
    unit_price = Decimal("12.5000")
    total_price = Decimal("25.0000")


class PurchaseReceiptFactory(TenantModelFactory):
    class Meta:
        model = models.PurchaseReceipt

    receipt_number = factory.Sequence(lambda n: f"GRN-{n:06d}")
    receipt_date = factory.LazyFunction(timezone.localdate)
    purchase_order = factory.SubFactory(PurchaseOrderFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    warehouse_id = factory.LazyFunction(uuid4)

    class Params:
        completed = factory.Trait(
            status=models.PurchaseReceiptStatus.COMPLETED, completed_at=factory.LazyFunction(timezone.now)
        )
        cancelled = factory.Trait(status=models.PurchaseReceiptStatus.CANCELLED)


class PurchaseReceiptLineFactory(TenantModelFactory):
    class Meta:
        model = models.PurchaseReceiptLine

    purchase_receipt = factory.SubFactory(PurchaseReceiptFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    purchase_order_line = factory.SubFactory(PurchaseOrderLineFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    line_number = factory.Sequence(lambda n: n + 1)
    quantity_received = Decimal("1.000000")


class ProcurementConfigurationFactory(TenantModelFactory):
    class Meta:
        model = models.ProcurementConfiguration

    environment = models.ConfigurationEnvironment.DEVELOPMENT
    version = factory.Sequence(lambda n: n + 1)
    default_currency = "USD"
    default_payment_terms = "Net 30"
    supplier_code_prefix = "SUP"
    requisition_prefix = "PR"
    rfq_prefix = "RFQ"
    po_prefix = "PO"
    receipt_prefix = "GRN"
    minimum_rfq_suppliers = 3
    quote_scoring_weights = {"price": 55, "delivery": 20, "quality": 15, "service": 10}

    class Params:
        active = factory.Trait(
            status=models.ConfigurationStatus.ACTIVE,
            activated_at=factory.LazyFunction(timezone.now),
            activated_by=factory.LazyFunction(uuid4),
        )
        archived = factory.Trait(status=models.ConfigurationStatus.ARCHIVED)
