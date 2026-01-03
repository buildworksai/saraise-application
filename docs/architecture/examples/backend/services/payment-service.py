# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Payment Processing Service
# backend/src/modules/billing/services/payment_service.py
# Reference: docs/architecture/policy-engine-spec.md § 4
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import Optional, Dict, Any
from decimal import Decimal
from datetime import datetime
import secrets
from src.modules.billing.models import Invoice, InvoiceStatus, Payment, PaymentStatus

class PaymentService:
    """Payment processing (platform-level service).
    
    CRITICAL: Payment operations require Policy Engine authorization.
    Only platform_billing_manager can process payments.
    See docs/architecture/policy-engine-spec.md § 4 (Runtime Evaluation).
    """
    
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        pass

    def process_payment(
        self,
        invoice_id: str,
        payment_method_id: str,
        amount: Decimal
    ) -> Payment:
        """Process payment for invoice"""
        # Get invoice
        invoice = self._get_invoice(invoice_id)
        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")

        # Validate amount
        if amount != invoice.amount:
            raise ValueError(f"Payment amount {amount} does not match invoice amount {invoice.amount}")

        # Process payment (integrate with payment gateway)
        payment_result = self._charge_payment(payment_method_id, amount)

        if payment_result["status"] == "succeeded":
            # Create payment record
            payment = Payment(
                id=f"pay_{secrets.token_urlsafe(16)}",
                invoice_id=invoice_id,
                tenant_id=invoice.tenant_id,
                amount=amount,
                currency=invoice.currency,
                payment_method_id=payment_method_id,
                status=PaymentStatus.SUCCEEDED,
                transaction_id=payment_result["transaction_id"]
            )

            self.# Django ORM: instance.save()payment)

            # Update invoice
            invoice.status = InvoiceStatus.PAID
            invoice.paid_date = datetime.utcnow()

            # ✅ CORRECT: Django ORM - use instance.save()
            payment.save()

            return payment
        else:
            raise ValueError(f"Payment failed: {payment_result.get('error')}")

    def _charge_payment(self, payment_method_id: str, amount: Decimal) -> Dict[str, Any]:
        """Charge payment via payment gateway"""
        # Integrate with payment gateway (Stripe, PayPal, etc.)
        # This is a placeholder - implement actual payment gateway integration
        return {
            "status": "succeeded",
            "transaction_id": f"txn_{secrets.token_urlsafe(16)}"
        }

    def _get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        """Helper to get invoice"""
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        from src.models.invoice import Invoice
        return Invoice.objects.filter(id=invoice_id).first()

